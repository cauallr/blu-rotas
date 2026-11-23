import os
from collections import Counter
from pathlib import Path

import pytest
import traci

from backend.engine import Simulator
from backend.storage import Storage


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY") or not Path("data/blumenau.net.xml").exists(),
                    reason="Defina SUMO_BINARY para o teste de integração real")
def test_expanded_map_exposes_grouped_traffic_lights(tmp_path):
    sim = Simulator("data", Storage(str(tmp_path / "traffic-lights.sqlite3")))
    try:
        snapshot = sim.start(42)
        lights = {light["id"]: light for light in snapshot["lights"]}
        assert set(lights) == set(traci.trafficlight.getIDList())
        simulated = [light for light in lights.values() if light["simulated_neighborhood"]]
        assert Counter(light["simulated_neighborhood"] for light in simulated) == {
            "Água Verde": 1, "Boa Vista": 1, "Bom Retiro": 6, "Do Salto": 1, "Garcia": 3,
            "Ribeirão Fresco": 4, "Velha": 4, "Vila Formosa": 1,
        }
        for light in simulated:
            assert len(light["phases"]) >= 2
            assert len({movement["incoming_road"] for movement in light["movements"]}) >= 2
        grouped = lights["GS_13081239399"]
        assert not sim.net.hasNode(grouped["id"])
        assert grouped["coordinates"] == pytest.approx([-49.059319, -26.8940652], abs=0.0002)
        assert len(grouped["phases"]) >= 2
        assert len({movement["incoming_lane"] for movement in grouped["movements"]}) >= 2
        for light in lights.values():
            links = traci.trafficlight.getControlledLinks(light["id"])
            movements = light["movements"]
            assert len({movement["id"] for movement in movements}) == len(movements)
            for movement in movements:
                assert any(incoming == movement["incoming_lane"] and outgoing == movement["outgoing_lane"]
                           for incoming, outgoing, _ in links[movement["index"]])
    finally:
        sim.stop()


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY") or not Path("data/blumenau.net.xml").exists(),
                    reason="Defina SUMO_BINARY para o teste de integração real")
def test_sumo_vehicle_weather_light_and_reroute(tmp_path):
    sim = Simulator("data", Storage(str(tmp_path / "test.sqlite3")))
    try:
        sim.start(222)
        assert sim.spawn(100)["added"] == 100
        for _ in range(80):
            sim.step()
        assert sim.snapshot()["active"] > 0
        sim.set_weather("heavy_rain")
        assert sim.snapshot()["weather"] == "heavy_rain"
        light = sim.snapshot()["lights"][0]
        sim.traffic_light(light["id"], 0, 35)
        assert sim.snapshot()["lights"][0]["phases"][0]["duration"] == 35
        candidate = None
        for vehicle_id in traci.vehicle.getIDList():
            info = sim.vehicles[vehicle_id]
            current = traci.vehicle.getRoadID(vehicle_id)
            if current not in sim.edges:
                continue
            route = list(traci.vehicle.getRoute(vehicle_id))
            index = traci.vehicle.getRouteIndex(vehicle_id)
            for target in route[index + 2:index + 8]:
                sim.blocked.add(target)
                alternate = sim.route(current, info["destination"])
                sim.blocked.remove(target)
                if alternate and target not in alternate:
                    candidate = vehicle_id, target
                    break
            if candidate:
                break
        assert candidate is not None
        sim.road_action(candidate[1], "close")
        assert sim.route_changes > 0
        assert candidate[1] not in traci.vehicle.getRoute(candidate[0])
        partial_edge = next(edge_id for edge_id, edge in sim.edges.items()
                            if edge_id != candidate[1] and len(edge.getLanes()) > 1)
        last_lane = sim.edges[partial_edge].getLanes()[-1].getID()
        sim.road_action(partial_edge, "partial")
        assert partial_edge in sim.snapshot()["partial"]
        assert "passenger" not in traci.lane.getAllowed(last_lane)
        sim.road_action(partial_edge, "restore")
        assert partial_edge not in sim.snapshot()["partial"]
        assert sim.storage.metrics(sim.run_id)["samples"]
    finally:
        sim.stop()


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY") or not Path("data/blumenau.net.xml").exists(),
                    reason="Defina SUMO_BINARY para o teste de integração real")
def test_custom_car_waypoint_gps_and_peak_loop(tmp_path):
    sim = Simulator("data", Storage(str(tmp_path / "custom.sqlite3")))
    try:
        sim.start(77)
        points = None
        for origin in sim.edges:
            if sim.edges[origin].getLength() < 60:
                continue
            for destination in list(sim.edges)[::31]:
                path = sim.route(origin, destination)
                if len(path) < 10:
                    continue
                candidate = []
                for edge_id in (path[0], path[4], path[8]):
                    edge = sim.edges[edge_id]
                    x, y = edge.getShape()[len(edge.getShape()) // 2]
                    candidate.append({"coordinates": sim.net.convertXY2LonLat(x, y)})
                snapped = [sim.nearest_road(*point["coordinates"]) for point in candidate]
                if sim.route_through([point["edge_id"] for point in snapped]):
                    points = candidate
                    break
            if points:
                break
        assert points is not None
        result = sim.spawn_custom(points[0], points[2], [points[1]], "#e544aa", "dynamic", 5, 0.05, 1.2)
        assert len(result["points"]) == 3
        vehicle_id = result["vehicle_id"]
        for _ in range(24):
            sim.step()
        car = next(item for item in sim.snapshot()["vehicles"] if item["id"] == vehicle_id)
        assert car["color"] == "#e544aa"
        assert car["gps_last_checked"] >= 5
        assert car["state"] in {"moving", "congested", "at_signal"}
        assert car["waypoints"]
        sim.update_vehicle_gps(vehicle_id, "dynamic", 10, 0.1)
        sim.update_vehicle_style(vehicle_id, "#44aaff", 0.9)
        assert sim.vehicles[vehicle_id]["gps_interval"] == 10
        assert sim.vehicles[vehicle_id]["color"] == "#44aaff"
        loop = sim.set_loop(True, 7.5, 60, 3)
        assert loop["peak"] and loop["vehicles_per_minute"] == 180
        for _ in range(16):
            sim.step()
        assert len(sim.vehicles) >= 13
        assert sim.snapshot()["lights"][0]["aspect"] in {"open", "closed", "attention", "mixed"}
        assert sim.snapshot()["sim_time"] == 10
        for light in sim.snapshot()["lights"]:
            for movement in light["movements"]:
                assert movement["aspect"] in {"open", "closed", "attention"}
                assert len(movement["approach"]) >= 2
                state = light["state"][movement["index"]]
                if state in "rR":
                    assert movement["aspect"] == "closed"
                elif state in "gG":
                    assert movement["aspect"] == "open"
        assert any(light["aspect"] == "mixed" and
                   {movement["aspect"] for movement in light["movements"]} >= {"open", "closed"}
                   for light in sim.snapshot()["lights"])
    finally:
        sim.stop()


@pytest.mark.skipif(not os.environ.get("SUMO_BINARY") or not Path("data/blumenau.net.xml").exists(),
                    reason="Defina SUMO_BINARY para o teste de integração real")
def test_route_alternatives_and_simultaneous_groups(tmp_path):
    sim = Simulator("data", Storage(str(tmp_path / "groups.sqlite3")))
    try:
        sim.start(123)
        ids = list(sim.edges)
        candidate = None
        for origin in ids[::17][:30]:
            for destination in ids[::19][:40]:
                options = sim.route_choices([origin, destination])
                if len(options) >= 2 and len(options[0]["route"]) >= 6:
                    candidate = origin, destination, options
                    break
            if candidate:
                break
        assert candidate is not None
        origin, destination, options = candidate
        assert len({tuple(option["route"]) for option in options}) == len(options)
        assert options[0]["seconds"] <= options[1]["seconds"]
        def point(edge_id):
            x, y = sim.edges[edge_id].getShape()[0]
            return {"coordinates": sim.net.convertXY2LonLat(x, y)}
        result = sim.spawn_custom_groups(point(origin), point(destination), [], [
            {"choice": "best", "count": 1, "color": "#22aa88"},
            {"choice": "secondary", "count": 1, "color": "#aa8822"}],
            "static", 30, .05, 1.0)
        assert result["created"] == 2
        assert result["departed_sim_time"] == 0
        assert {sim.vehicles[id]["route_choice"] for id in result["vehicle_ids"]} == {"best", "secondary"}
        for _ in range(5):
            sim.step()
        assert any(id in traci.vehicle.getIDList() for id in result["vehicle_ids"])
    finally:
        sim.stop()
