import json
import os
import shutil
from pathlib import Path

import pytest

from backend.scenario_network import ScenarioNetwork, way_id_from_edge
from backend.engine import Simulator
from backend.storage import Storage
from backend.urban import AccessPoints
import sumolib


def test_osm_edge_id_extraction():
    assert way_id_from_edge("-35894592#2") == "35894592"
    with pytest.raises(ValueError):
        way_id_from_edge(":junction_0")


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY"), reason="SUMO indisponível")
def test_fictional_road_is_in_real_sumo_network(tmp_path):
    source = Path("data")
    for name in ("blumenau-centro.osm.xml", "roads.geojson", "places.geojson"):
        shutil.copy2(source / name, tmp_path / name)
    roads = json.loads((tmp_path / "roads.geojson").read_text(encoding="utf-8"))["features"]
    a, b = roads[:2]
    a_point = a["geometry"]["coordinates"][len(a["geometry"]["coordinates"]) // 2]
    b_point = b["geometry"]["coordinates"][0]
    builder = ScenarioNetwork(tmp_path)
    manifest = builder.build([{"origin_way": a["properties"]["id"],
                              "destination_way": b["properties"]["id"],
                              "origin_coordinates": a_point, "destination_coordinates": b_point,
                              "name": "Conexão experimental", "oneway": False,
                              "speed_kmh": 35, "lanes": 1,
                              "capacity_estimate": 900, "hypothetical_cost": 100000}], "Teste")
    assert manifest["network_version"]
    assert manifest["network_path"] == "network.net.xml"
    assert manifest["map_path"] == "roads.geojson"
    assert (tmp_path / "scenarios" / manifest["id"] / "network.net.xml").exists()
    assert manifest["roads"][0]["id"] in {feature["properties"]["id"] for feature in
                                           json.loads((tmp_path / "scenarios" / manifest["id"] / "roads.geojson").read_text(encoding="utf-8"))["features"]}
    scenario_dir = tmp_path / "scenarios" / manifest["id"]
    sim = Simulator(str(scenario_dir), Storage(str(tmp_path / "simulation.sqlite3")))
    sim.net_path = scenario_dir / "network.net.xml"
    sim.load_network()
    created = [edge for edge in sim.edges if edge.lstrip("-").split("#")[0] == manifest["roads"][0]["id"]]
    assert created
    assert any(sim.graph.adj[edge] for edge in created)
    assert any(edge in neighbors for neighbors in sim.graph.adj.values() for edge in created)


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY"), reason="SUMO indisponível")
def test_saved_access_point_is_a_routing_vertex(tmp_path):
    sim = Simulator("data", Storage(str(tmp_path / "access.sqlite3")))
    store = AccessPoints(tmp_path / "points.json")
    edge = next(edge for edge in sim.edges.values() if edge.allows("passenger") and edge.getLength() > 50)
    x, y = edge.getShape()[len(edge.getShape()) // 2]
    point = store.add(sim, sim.net.convertXY2LonLat(x, y), "Ponto de pesquisa")
    sim.set_access_points(store.for_sim(sim))
    vertex = f"access:{point['id']}"
    assert vertex in sim.graph.adj
    assert sim.graph.adj[vertex]
    distances, previous = sim.graph.dijkstra(vertex, point["edge_id"])
    assert distances[point["edge_id"]] < float("inf")
    assert sim.graph.path(previous, vertex, point["edge_id"])
    assert store.for_sim(sim)[0]["name"] == "Ponto de pesquisa"
    sim.access_point_store = store
    try:
        sim.start(42)
        assert vertex in sim.graph.adj
        assert vertex in sim.access_points
        assert sim.connected
    finally:
        sim.stop()


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY"), reason="SUMO indisponível")
def test_edited_lanes_direction_and_signal_reach_sumo(tmp_path):
    for name in ("blumenau-centro.osm.xml", "roads.geojson", "places.geojson"):
        shutil.copy2(Path("data") / name, tmp_path / name)
    builder = ScenarioNetwork(tmp_path)
    way_id = "1010048512"
    signal_point = [-49.0597191, -26.9136574]
    manifest = builder.build([], "Rede editada", [{"way_id": way_id, "direction": "both",
        "lanes_forward": 2, "lanes_backward": 1, "speed_kmh": 35, "name": "Rua do Estudo"}],
        [{"coordinates": signal_point}])
    net = sumolib.net.readNet(str(tmp_path / "scenarios" / manifest["id"] / "network.net.xml"))
    directions = {direction: [edge for edge in net.getEdges()
        if edge.getID().lstrip("-").split("#")[0] == way_id and edge.getID().startswith("-") == reverse]
        for direction, reverse in (("forward", False), ("backward", True))}
    assert directions["forward"] and directions["backward"]
    assert max(len(edge.getLanes()) for edge in directions["forward"]) >= 2
    assert all(edge.getName() == "Rua do Estudo" for edge in directions["forward"])
    mapped = json.loads((tmp_path / "scenarios" / manifest["id"] / "roads.geojson").read_text(encoding="utf-8"))
    assert all(feature["properties"]["name"] == "Rua do Estudo" for feature in mapped["features"]
               if str(feature["properties"]["id"]) == way_id)
    assert any(node.getType() == "traffic_light" for node in net.getNodes())
    assert manifest["signals"][0]["node_id"]
