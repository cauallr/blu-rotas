import json
import os
from pathlib import Path

import pytest

from backend.engine import Simulator
from backend.experiment_analysis import compare, confidence_interval, interpret, summarize
from backend.experiment_report import csv_export, pdf_export
from backend.experiments import ExperimentManager, deterministic_demand, focus_new_road_demand
from backend.map_manager import MapManager
from backend.storage import Storage


def test_metrics_keep_unfinished_and_pairing():
    vehicles = [
        {"completed": True, "travel_time_s": 20, "waiting_time_s": 3, "distance_m": 100,
         "reroutes": 1, "origin_neighborhood": "Centro", "final_route": ["a", "b"]},
        {"completed": False, "travel_time_s": 30, "waiting_time_s": 10, "distance_m": 25,
         "reroutes": 0, "origin_neighborhood": "Centro", "final_route": ["a", "b"]},
    ]
    summary = summarize(vehicles, [], 30)
    assert summary["completed"] == 1
    assert summary["unfinished"] == 1
    assert summary["completion_rate"] == .5
    assert summary["mean_travel_s"] == 20
    assert summary["by_neighborhood"]["Centro"]["unfinished"] == 1
    assert summary["route_distribution"][0]["vehicles"] == 2
    assert confidence_interval([10, 20, 30])["n"] == 3
    a = {"summary": summary, "seed": 1, "demand_hash": "same", "network_version": "net",
         "parameters": {"gps_strategy": "static"}}
    b = {**a, "parameters": {"gps_strategy": "dynamic"}}
    assert compare(a, b)["directly_comparable"]
    assert not compare(a, {**b, "demand_hash": "different"})["directly_comparable"]
    a["summary"]["roads"] = {"via": {"name": "Rua teste", "mean_queue": 1, "mean_vehicles": 2}}
    changed = {**b, "summary": {**summary, "roads": {"via": {"name": "Rua teste", "mean_queue": 3, "mean_vehicles": 5}}}}
    assert compare(a, changed)["road_impacts"][0]["queue_difference"] == 2


def test_exports_contain_recorded_values():
    report = {"config": {"name": "Teste", "question": "Questão?", "hypothesis": "Hipótese",
              "independent_variable": "GPS", "vehicles": 1, "repetitions": 1, "seed": 7,
              "duration_s": 60, "departure_window_s": 0, "code_version": "code1",
              "source_network_version": "net1", "gps_interval": 30, "mode": "fast", "kind": "gps",
              "variants": [{"label": "Estático", "parameters": {"gps_strategy": "static"}}],
              "controlled_conditions": ["demanda"], "limitations": ["sintético"]},
              "results": {"runs": [{"id": "static-r1", "variant_label": "Estático", "seed": 7,
              "network_version": "net1", "demand_hash": "hash", "summary": {"mean_travel_s": 20,
              "completion_rate": 1, "mean_waiting_s": 2, "completed": 1, "unfinished": 0,
              "p95_travel_s": 20}, "vehicles": [{"id": "v1"}],
              "road_samples": []}], "aggregates": {"static": {"label": "Estático", "mean_travel_s": 20,
              "mean_completion_rate": 1, "mean_waiting_s": 2, "confidence_interval_95": None}},
              "interpretation": "Resultado observado", "limitations": ["sintético"]}}
    assert "static-r1" in csv_export(report, "summary")
    assert csv_export(report, "vehicles")
    assert pdf_export(report).startswith(b"%PDF-")


def test_saturation_scales_to_selected_region(tmp_path):
    manager = ExperimentManager(tmp_path, tmp_path)
    variants = manager._variants({"kind": "saturation", "vehicles": 25}, None)
    assert [item["parameters"]["vehicle_limit"] for item in variants] == [5, 12, 25]
    assert len(manager._variants({"kind": "saturation", "vehicles": 500}, None)) == 5
    variants = manager._variants({"kind": "saturation", "vehicles": 25}, None)
    config = {"kind": "saturation", "variants": variants}
    aggregates = {item["key"]: {"mean_travel_s": value}
                  for item, value in zip(variants, [40, 50, 90])}
    assert "12 e 25" in interpret(config, [], aggregates)


def test_custom_variant_ids_cannot_escape_experiment_folder(tmp_path):
    manager = ExperimentManager(tmp_path, tmp_path)
    spec = {"kind": "custom", "vehicles": 5, "variants": [
        {"key": "../../outside", "label": "Inválida", "parameters": {"weather": "sun"}},
        {"key": "rain", "label": "Chuva", "parameters": {"weather": "light_rain"}}]}
    with pytest.raises(ValueError, match="chave única"):
        manager._variants(spec, None)


def test_new_road_demand_is_paired_and_uses_real_connection(tmp_path):
    scenario_dir = Path("data/scenarios/8e6a547f53d8")
    source = Simulator("data", Storage(str(tmp_path / "source.sqlite3")))
    source.load_network()
    modified = Simulator(str(scenario_dir), Storage(str(tmp_path / "modified.sqlite3")))
    modified.net_path = scenario_dir / "network.net.xml"
    modified.load_network()
    roads = json.loads((scenario_dir / "manifest.json").read_text(encoding="utf-8"))["roads"]
    trips = deterministic_demand(source, 42, 8, 20, 112)
    original_departures = [(trip["id"], trip["departed"]) for trip in trips]
    assert focus_new_road_demand(source, modified, roads, trips, 42, 112) == 2
    assert [(trip["id"], trip["departed"]) for trip in trips] == original_departures
    for trip in trips[:2]:
        first = modified.nearest_road(*trip["origin_coordinates"])["edge_id"]
        last = modified.nearest_road(*trip["destination_coordinates"])["edge_id"]
        assert any("8000033445870992" in edge for edge in modified.route(first, last))


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY"), reason="SUMO indisponível")
def test_imported_map_and_deterministic_demand(tmp_path):
    manager = MapManager(tmp_path)
    source = Path("data/blumenau-centro.osm.xml").read_bytes()
    city = manager.import_xml(source, "Blumenau teste", "Centro")
    assert city["drivable_edges"] > 5
    city_dir = tmp_path / "cities" / city["id"]
    assert (city_dir / "network.net.xml").exists()
    assert manager.get(city["id"])["network_version"] == city["network_version"]
    sim = Simulator(str(city_dir), Storage(str(tmp_path / "runs.sqlite3")))
    sim.net_path = city_dir / "network.net.xml"
    sim.load_network()
    first = deterministic_demand(sim, 13, 5, 10)
    assert first == deterministic_demand(sim, 13, 5, 10)
    assert first != deterministic_demand(sim, 14, 5, 10)
    assert json.loads((city_dir / "roads.geojson").read_text(encoding="utf-8"))["features"]
    sim.start(13, 8)
    try:
        assert sim.connected
        assert sim.snapshot()["clock_hour"] == 8
    finally:
        sim.stop()
