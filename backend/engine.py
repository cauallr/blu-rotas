"""Controlador único do SUMO. O estado do navegador vem exclusivamente do TraCI."""
from __future__ import annotations

import copy
import json
import math
import os
import random
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import sumolib
import traci

from .graphs import Graph
from .route_choices import alternatives
from .storage import Storage
from .telemetry import city_hour, remaining_route_metrics
from .traffic_signals import load_simulated_signals


WEATHER = {
    "sun": {"speed_factor": 1.0, "tau": 1.0, "accel": 2.6, "decel": 4.5},
    "light_rain": {"speed_factor": 0.85, "tau": 1.4, "accel": 2.1, "decel": 3.7},
    "heavy_rain": {"speed_factor": 0.65, "tau": 1.9, "accel": 1.6, "decel": 3.0},
}
STEP_SECONDS = 0.25
BLUMENAU_NETWORK_VERSION = "blumenau-centro-expandido-v4"


def lane_tail(shape: list[tuple[float, float]], metres: float) -> list[tuple[float, float]]:
    """Return the last metres of an incoming lane, in driving direction."""
    result = [shape[-1]]
    remaining = metres
    for index in range(len(shape) - 2, -1, -1):
        a, b = shape[index], result[-1]
        distance = math.dist(a, b)
        if distance >= remaining and distance:
            ratio = remaining / distance
            result.append((b[0] + (a[0] - b[0]) * ratio,
                           b[1] + (a[1] - b[1]) * ratio))
            break
        result.append(a)
        remaining -= distance
    return list(reversed(result))


class Simulator:
    def __init__(self, data_dir: str, storage: Storage):
        self.data_dir = Path(data_dir)
        self.net_path = self.data_dir / "blumenau.net.xml"
        self.storage = storage
        self.connected = False
        self.running = False
        self.speed = 1
        self.weather = "sun"
        self.seed = 42
        self.rng = random.Random(self.seed)
        self.run_id: int | None = None
        self.gps_interval = 30.0
        self.gps_benefit = 0.12
        self.dynamic_percent = 0.5
        self.next_gps = 30.0
        self.vehicles: dict[str, dict] = {}
        self.next_vehicle_id = 0
        self.completed = 0
        self.route_changes = 0
        self.algorithm_ms = 0.0
        self.blocked: set[str] = set()
        self.reduced: dict[str, float] = {}
        self.partial: set[str] = set()
        self.tls_original: dict = {}
        self.tls_phases: dict[str, list[dict]] = {}
        self.tls_coordinates: dict[str, list[float]] = {}
        self.edge_speed: dict[str, float] = {}
        self.edge_lengths: dict[str, float] = {}
        self.continuous_rate = 0.0
        self.spawn_credit = 0.0
        self.last_sample_at = 0.0
        self.signal_links: dict[str, list[dict]] = {}
        self.simulated_signals: dict[str, str] = {}
        self.loop_enabled = False
        self.city_start_hour = 6.0
        self.network_version = BLUMENAU_NETWORK_VERSION
        self.network_scenario_id = None
        self.city_id = None
        self.city_name = "Blumenau central"
        self.loop_start_hour = 6.0
        self.loop_base_per_minute = 6.0
        self.loop_peak_multiplier = 3.0
        self.pending_trips: list[dict] = []
        self.lane_permissions: dict[str, list[str]] = {}
        self.latest_sample: dict = {}
        self.net = None
        self.places: list[dict] = []
        self.osm_names: dict[str, str] = {}
        self.graph = Graph()
        self.access_points: dict[str, dict] = {}
        self.access_point_store = None
        self.turn_lanes: dict[tuple[str, str], set[str]] = {}
        if self.net_path.exists():
            self.load_network()

    def load_network(self):
        self.net = sumolib.net.readNet(str(self.net_path), withInternal=True)
        self.simulated_signals = load_simulated_signals(self.data_dir)
        places_path = self.data_dir / "places.geojson"
        roads_path = self.data_dir / "roads.geojson"
        self.places = json.loads(places_path.read_text(encoding="utf-8"))["features"] if places_path.exists() else []
        self.osm_names = {str(feature["properties"]["id"]): feature["properties"]["name"]
                          for feature in json.loads(roads_path.read_text(encoding="utf-8"))["features"]} if roads_path.exists() else {}
        self.graph = Graph()
        # O grafo anterior foi descartado; seus vértices de acesso também.
        # set_access_points só deve remover vértices que pertençam a este grafo.
        self.access_points = {}
        self.turn_lanes = {}
        self.edge_speed = {}
        self.edge_lengths = {}
        self.edges = {edge.getID(): edge for edge in self.net.getEdges()
                      if not edge.getID().startswith(":") and edge.allows("passenger")}
        for edge_id, edge in self.edges.items():
            self.graph.add_vertex(edge_id)
            self.edge_speed[edge_id] = edge.getSpeed()
            self.edge_lengths[edge_id] = edge.getLength()
        for edge_id, edge in self.edges.items():
            for connection in edge.getOutgoing().values():
                # sumolib returns a list of connections per outgoing edge.
                for item in connection:
                    target = item.getTo().getID()
                    via = item.getViaLaneID()
                    via_allowed = not via or self.net.getLane(via).allows("passenger")
                    if target in self.edges and via_allowed and item.getFromLane().allows("passenger") and item.getToLane().allows("passenger"):
                        other = self.edges[target]
                        self.graph.add_edge(edge_id, target, other.getLength() / max(other.getSpeed(), 1))
                        self.turn_lanes.setdefault((edge_id, target), set()).add(item.getFromLane().getID())
        if self.access_point_store:
            self.set_access_points(self.access_point_store.for_sim(self))

    def set_access_points(self, points: list[dict]):
        for vertex in self.access_points:
            self.graph.remove_vertex(vertex)
        self.access_points = {}
        by_edge: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for point in points:
            edge_id = point["edge_id"]
            if edge_id not in self.edges:
                continue
            vertex = f"access:{point['id']}"
            edge = self.edges[edge_id]
            position = min(max(0.0, float(point["position"])), edge.getLength())
            speed = max(edge.getSpeed(), 1)
            self.graph.add_edge(edge_id, vertex, position / speed)
            self.graph.add_edge(vertex, edge_id, (edge.getLength() - position) / speed)
            self.access_points[vertex] = {**point, "vertex_id": vertex, "position": position}
            by_edge[edge_id].append((position, vertex))
        for edge_id, entries in by_edge.items():
            speed = max(self.edges[edge_id].getSpeed(), 1)
            for (position_a, vertex_a), (position_b, vertex_b) in zip(sorted(entries), sorted(entries)[1:]):
                self.graph.add_edge(vertex_a, vertex_b, (position_b - position_a) / speed)

    def start(self, seed: int = 42, start_hour: float = 6.0,
              tripinfo_output: str | None = None):
        if not self.net_path.exists():
            raise RuntimeError("Rede SUMO ausente. Execute scripts/build-network.ps1")
        self.stop()
        self.blocked.clear()
        self.load_network()
        binary = os.environ.get("SUMO_BINARY", "sumo")
        command = [binary, "-n", str(self.net_path), "--step-length", str(STEP_SECONDS),
                   "--no-step-log", "true", "--duration-log.disable", "true",
                   "--time-to-teleport", "-1", "--seed", str(seed)]
        if tripinfo_output:
            command.extend(["--tripinfo-output", str(tripinfo_output)])
        traci.start(command)
        self.connected = True
        self.running = False
        self.seed = seed
        self.rng = random.Random(seed)
        self.run_id = self.storage.new_run(seed)
        self.vehicles.clear()
        self.next_vehicle_id = 0
        self.completed = 0
        self.route_changes = 0
        self.blocked.clear()
        self.reduced.clear()
        self.partial.clear()
        self.weather = "sun"
        self.pending_trips.clear()
        self.spawn_credit = 0.0
        self.last_sample_at = 0.0
        self.loop_enabled = False
        self.city_start_hour = start_hour
        self.loop_start_hour = start_hour
        self.lane_permissions = {lane.getID(): list(traci.lane.getAllowed(lane.getID()))
                                 for edge in self.edges.values() for lane in edge.getLanes()}
        self.next_gps = self.gps_interval
        self.tls_original = {tls: copy.deepcopy(traci.trafficlight.getAllProgramLogics(tls))
                             for tls in traci.trafficlight.getIDList()}
        self.tls_phases = {tls: [{"index": i, "duration": phase.duration, "state": phase.state}
                                 for i, phase in enumerate(logics[0].phases)] if logics else []
                           for tls, logics in self.tls_original.items()}
        self.tls_coordinates = {tls: list(self.net.convertXY2LonLat(*self.net.getNode(tls).getCoord()))
                                for tls in self.tls_original if self.net.hasNode(tls)}
        self.signal_links = {}
        for tls_id in self.tls_original:
            movements = []
            seen_lanes: dict[str, int] = defaultdict(int)
            controlled_nodes = {}
            for index, connections in enumerate(traci.trafficlight.getControlledLinks(tls_id)):
                for link_index, (incoming_id, outgoing_id, _) in enumerate(connections):
                    if not incoming_id or not outgoing_id:
                        continue
                    incoming = self.net.getLane(incoming_id)
                    outgoing = self.net.getLane(outgoing_id)
                    if not incoming.allows("passenger") or not outgoing.allows("passenger"):
                        continue
                    shape = incoming.getShape()
                    if len(shape) < 2:
                        continue
                    slot = seen_lanes[incoming_id]
                    seen_lanes[incoming_id] += 1
                    marker = lane_tail(shape, min(5 + slot * 5, incoming.getLength() * 0.8))[0]
                    approach = lane_tail(shape, min(15, incoming.getLength() * 0.9))
                    in_edge = incoming.getEdge()
                    out_edge = outgoing.getEdge()
                    junction = in_edge.getToNode()
                    controlled_nodes[junction.getID()] = junction.getCoord()
                    movements.append({"id": f"{tls_id}:{index}:{link_index}", "index": index,
                                      "incoming_lane": incoming_id, "outgoing_lane": outgoing_id,
                                      "incoming_road": in_edge.getName() or self.osm_names.get(in_edge.getID().lstrip('-').split('#')[0], "Via sem nome"),
                                      "outgoing_road": out_edge.getName() or self.osm_names.get(out_edge.getID().lstrip('-').split('#')[0], "Via sem nome"),
                                      "coordinates": list(self.net.convertXY2LonLat(*marker)),
                                      "approach": [list(self.net.convertXY2LonLat(*xy)) for xy in approach]})
            if tls_id not in self.tls_coordinates and controlled_nodes:
                x = sum(point[0] for point in controlled_nodes.values()) / len(controlled_nodes)
                y = sum(point[1] for point in controlled_nodes.values()) / len(controlled_nodes)
                self.tls_coordinates[tls_id] = list(self.net.convertXY2LonLat(x, y))
            self.signal_links[tls_id] = movements
        return self.snapshot()

    def stop(self):
        self.running = False
        if self.connected:
            try:
                traci.close()
            finally:
                self.connected = False

    def route(self, origin: str, destination: str, costs: dict | None = None) -> list[str]:
        if origin in self.blocked or destination in self.blocked:
            return []
        costs = dict(costs or {})
        for edge in self.blocked:
            costs[edge] = float("inf")
        for vertex in self.access_points:
            costs[vertex] = float("inf")
        distance, previous = self.graph.dijkstra(origin, destination, costs)
        if distance.get(destination, float("inf")) == float("inf"):
            return []
        return self.graph.path(previous, origin, destination)

    def route_through(self, points: list[str], costs: dict | None = None) -> list[str]:
        if len(points) < 2:
            return []
        combined = []
        for origin, destination in zip(points, points[1:]):
            segment = self.route(origin, destination, costs)
            if not segment:
                return []
            combined.extend(segment if not combined else segment[1:])
        return combined

    def route_choices(self, checkpoints: list[str]) -> list[dict]:
        costs = self._edge_costs() if self.connected else {
            edge_id: edge.getLength() / max(edge.getSpeed(), 1) for edge_id, edge in self.edges.items()}
        return alternatives(self.route_through, checkpoints, costs, self.edge_lengths)

    def nearest_road(self, lon: float, lat: float, radius: float = 100,
                     allowed_way_ids: set[str] | None = None) -> dict:
        if not self.net:
            raise RuntimeError("Rede SUMO indisponível")
        x, y = self.net.convertLonLat2XY(lon, lat)
        candidates = [(edge, distance) for edge, distance in self.net.getNeighboringEdges(x, y, radius)
                      if edge.getID() in self.edges and edge.getID() not in self.blocked
                      and (allowed_way_ids is None or edge.getID().lstrip('-').split('#')[0] in allowed_way_ids)]
        if not candidates:
            raise ValueError("Nenhuma via para automóveis encontrada neste ponto. Clique mais perto de uma rua.")
        edge, _ = min(candidates, key=lambda item: item[1])
        shape = edge.getShape()
        best = (float("inf"), 0.0, shape[0])
        traveled = 0.0
        total = sum(math.dist(a, b) for a, b in zip(shape, shape[1:]))
        for a, b in zip(shape, shape[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length2 = dx * dx + dy * dy
            ratio = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / length2)) if length2 else 0.0
            snapped = (a[0] + dx * ratio, a[1] + dy * ratio)
            distance = math.dist((x, y), snapped)
            if distance < best[0]:
                best = (distance, (traveled + math.sqrt(length2) * ratio) / max(total, 1) * edge.getLength(), snapped)
            traveled += math.sqrt(length2)
        snap_lon, snap_lat = self.net.convertXY2LonLat(*best[2])
        osm_id = edge.getID().lstrip("-").split("#")[0]
        return {"edge_id": edge.getID(), "name": self.osm_names.get(osm_id) or edge.getName() or "Via sem nome",
                "coordinates": [snap_lon, snap_lat], "position": max(0.1, min(best[1], edge.getLength() - 0.1)),
                "distance_m": round(best[0], 1)}

    def set_loop(self, enabled: bool, start_hour: float = 6.0, base_per_minute: float = 6.0,
                 peak_multiplier: float = 3.0) -> dict:
        self.loop_enabled = enabled
        self.set_city_clock(start_hour)
        self.loop_start_hour = start_hour
        self.loop_base_per_minute = base_per_minute
        self.loop_peak_multiplier = peak_multiplier
        self.spawn_credit = 0.0
        return self.loop_state()

    def loop_state(self) -> dict:
        seconds = traci.simulation.getTime() if self.connected else 0
        hour = city_hour(self.city_start_hour, seconds)
        peak = 7 <= hour < 9 or 17 <= hour < 19
        rate = self.loop_base_per_minute * (self.loop_peak_multiplier if peak else 1)
        return {"enabled": self.loop_enabled, "hour": hour, "peak": peak,
                "vehicles_per_minute": rate if self.loop_enabled else 0,
                "base_per_minute": self.loop_base_per_minute,
                "peak_multiplier": self.loop_peak_multiplier,
                "start_hour": self.loop_start_hour}

    def set_city_clock(self, hour: float) -> float:
        if not 0 <= hour < 24:
            raise ValueError("O horário deve estar entre 00:00 e 23:59")
        seconds = traci.simulation.getTime() if self.connected else 0
        self.city_start_hour = (hour - seconds / 3600) % 24
        return hour

    def spawn(self, count: int = 10):
        if not self.connected:
            raise RuntimeError("Inicie o motor SUMO antes de adicionar carros")
        available = [edge for edge in self.edges if edge not in self.blocked and
                     self.edges[edge].getLength() >= 25]
        added = 0
        attempts = 0
        while added < count and attempts < count * 40:
            attempts += 1
            origin, destination = self.rng.sample(available, 2)
            path = self.route(origin, destination)
            if len(path) < 4:
                continue
            strategy = "dynamic" if self.rng.random() < self.dynamic_percent else "static"
            if self.spawn_trip(origin, destination, strategy, path):
                added += 1
        return {"requested": count, "added": added}

    def spawn_trip(self, origin: str, destination: str, strategy: str = "dynamic",
                   path: list[str] | None = None, *, origin_pos: float | None = None,
                   destination_pos: float | None = None, color: str = "#4de1cc",
                   gps_interval: float | None = None, gps_benefit: float | None = None,
                   speed_factor: float = 1.0, waypoints: list[str] | None = None,
                   group_label: str | None = None, route_choice: str = "best") -> bool:
        path = self.route(origin, destination) if path is None else path
        if not path or (len(path) == 1 and (origin_pos is None or destination_pos is None or destination_pos <= origin_pos + 5)):
            return False
        self.next_vehicle_id += 1
        vehicle_id = f"car-{self.run_id}-{self.next_vehicle_id}"
        route_id = f"route-{vehicle_id}"
        try:
            traci.route.add(route_id, path)
            traci.vehicle.add(vehicle_id, route_id, typeID="DEFAULT_VEHTYPE",
                              depart="now", departLane="best", departSpeed="max",
                              departPos=str(origin_pos) if origin_pos is not None else "base",
                              arrivalPos=str(destination_pos) if destination_pos is not None else "max")
            rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
            traci.vehicle.setColor(vehicle_id, (*rgb, 255))
        except traci.TraCIException:
            return False
        departed = traci.simulation.getTime()
        lengths = {edge_id: self.edges[edge_id].getLength() for edge_id in path if edge_id in self.edges}
        free_costs = {edge_id: lengths[edge_id] / max(self.edges[edge_id].getSpeed(), 1)
                      for edge_id in lengths}
        remaining_metres, remaining_seconds = remaining_route_metrics(
            path, 0, origin, origin_pos or 0, lengths, free_costs)
        origin_xy = self.edges[origin].getShape()[0]
        destination_xy = self.edges[destination].getShape()[-1]
        self.vehicles[vehicle_id] = {
            "id": vehicle_id, "origin": origin, "destination": destination,
            "origin_neighborhood": self._nearest_place(origin),
            "destination_neighborhood": self._nearest_place(destination),
            "departed": departed, "route": path, "initial_route": list(path),
            "origin_coordinates": list(self.net.convertXY2LonLat(*origin_xy)),
            "destination_coordinates": list(self.net.convertXY2LonLat(*destination_xy)),
            "previous_route": [], "route_history": [], "last_route_change": None,
            "strategy": strategy, "reroutes": 0, "waiting_time": 0.0,
            "group_label": group_label, "route_choice": route_choice,
            "distance": 0.0, "state": "departing", "color": color,
            "origin_pos": origin_pos, "destination_pos": destination_pos,
            "waypoints": waypoints or [], "remaining_waypoints": list(waypoints or []), "speed_factor": speed_factor,
            "gps_interval": gps_interval if gps_interval is not None else self.gps_interval,
            "gps_benefit": gps_benefit if gps_benefit is not None else self.gps_benefit,
            "gps_customized": gps_interval is not None or gps_benefit is not None,
            "gps_last_checked": None,
            "gps_next_check": departed + (gps_interval if gps_interval is not None else self.gps_interval),
            "gps_estimated_remaining": remaining_seconds, "gps_alternative_saving": 0.0,
            "remaining_distance_m": remaining_metres,
            "predicted_arrival_sim_time": departed + remaining_seconds,
            "initial_predicted_arrival_sim_time": departed + remaining_seconds,
            "forecast_updated_at": departed, "forecast_error_s": None,
            "algorithm": "Dijkstra (heap)",
            "gps_status": "Previsão inicial calculada"}
        self._apply_weather(vehicle_id)
        return True

    def spawn_custom(self, origin: dict, destination: dict, waypoints: list[dict],
                     color: str, strategy: str, gps_interval: float,
                     gps_benefit: float, speed_factor: float,
                     route_choice: str = "best") -> dict:
        if not self.connected:
            raise RuntimeError("Inicie a simulação antes de criar o carro")
        snapped = [self.nearest_road(*point["coordinates"]) for point in [origin, *waypoints, destination]]
        edge_ids = [point["edge_id"] for point in snapped]
        options = self.route_choices(edge_ids)
        choice = next((item for item in options if item["key"] == route_choice), None)
        path = choice["route"] if choice else []
        if not path:
            raise ValueError("Não existe rota viária válida passando por todos os pontos. Ajuste os pontos no mapa.")
        if edge_ids[0] == edge_ids[-1] and len(edge_ids) == 2 and snapped[-1]["position"] <= snapped[0]["position"] + 5:
            raise ValueError("Na mesma via, o destino precisa estar adiante da origem no sentido de circulação.")
        created = self.spawn_trip(edge_ids[0], edge_ids[-1], strategy, path,
                                  origin_pos=snapped[0]["position"], destination_pos=snapped[-1]["position"],
                                  color=color, gps_interval=gps_interval, gps_benefit=gps_benefit,
                                  speed_factor=speed_factor, waypoints=edge_ids[1:-1],
                                  route_choice=route_choice)
        if not created:
            raise ValueError("SUMO não aceitou a viagem. Escolha outros pontos da via.")
        vehicle_id = f"car-{self.run_id}-{self.next_vehicle_id}"
        info = self.vehicles[vehicle_id]
        info["origin_coordinates"] = snapped[0]["coordinates"]
        info["destination_coordinates"] = snapped[-1]["coordinates"]
        info["waypoint_coordinates"] = [point["coordinates"] for point in snapped[1:-1]]
        return {"vehicle_id": vehicle_id, "route": path, "points": snapped}

    def spawn_custom_groups(self, origin: dict, destination: dict, waypoints: list[dict],
                            groups: list[dict], strategy: str, gps_interval: float,
                            gps_benefit: float, speed_factor: float) -> dict:
        if not self.connected:
            raise RuntimeError("Inicie a simulação antes de criar os grupos")
        snapped = [self.nearest_road(*point["coordinates"]) for point in [origin, *waypoints, destination]]
        edge_ids = [point["edge_id"] for point in snapped]
        choices = {item["key"]: item for item in self.route_choices(edge_ids)}
        if not choices:
            raise ValueError("Não existe rota válida passando pelos pontos escolhidos")
        if sum(group["count"] for group in groups) > 100:
            raise ValueError("O limite é 100 carros por lançamento")
        for group in groups:
            if group["choice"] not in choices:
                raise ValueError(f"Rota {group['choice']} indisponível nesta rede")
        started_at = traci.simulation.getTime()
        created = []
        for group in groups:
            for _ in range(group["count"]):
                if not self.spawn_trip(edge_ids[0], edge_ids[-1], strategy, choices[group["choice"]]["route"],
                                       origin_pos=snapped[0]["position"], destination_pos=snapped[-1]["position"],
                                       color=group["color"], gps_interval=gps_interval,
                                       gps_benefit=gps_benefit, speed_factor=speed_factor,
                                       waypoints=edge_ids[1:-1], group_label=group["choice"],
                                       route_choice=group["choice"]):
                    continue
                vehicle_id = f"car-{self.run_id}-{self.next_vehicle_id}"
                info = self.vehicles[vehicle_id]
                info["origin_coordinates"] = snapped[0]["coordinates"]
                info["destination_coordinates"] = snapped[-1]["coordinates"]
                info["waypoint_coordinates"] = [point["coordinates"] for point in snapped[1:-1]]
                created.append(vehicle_id)
        return {"vehicle_ids": created, "requested": sum(group["count"] for group in groups),
                "created": len(created), "departed_sim_time": started_at,
                "groups": [{"choice": group["choice"], "count": sum(
                    self.vehicles[vehicle_id]["group_label"] == group["choice"] for vehicle_id in created)}
                    for group in groups]}

    def vehicle_route_choices(self, vehicle_id: str) -> list[dict]:
        info = self.vehicles.get(vehicle_id)
        if not info or not self.connected or vehicle_id not in traci.vehicle.getIDList():
            raise ValueError("Veículo ativo não encontrado")
        current = traci.vehicle.getRoadID(vehicle_id)
        if current not in self.edges:
            raise ValueError("Aguarde o veículo sair da interseção para escolher uma rota")
        return self.route_choices([current, *info.get("remaining_waypoints", []), info["destination"]])

    def choose_vehicle_route(self, vehicle_id: str, choice: str) -> dict:
        options = self.vehicle_route_choices(vehicle_id)
        selected = next((item for item in options if item["key"] == choice), None)
        if not selected:
            raise ValueError("Esta alternativa não está disponível para o veículo")
        info = self.vehicles[vehicle_id]
        old = list(traci.vehicle.getRoute(vehicle_id))
        index = traci.vehicle.getRouteIndex(vehicle_id)
        remaining = old[max(index, 0):]
        candidate = selected["route"]
        if candidate == remaining:
            info["strategy"] = "static"
            info["route_choice"] = choice
            info["gps_status"] = "Rota escolhida manualmente; GPS estático até nova configuração"
            return {"vehicle_id": vehicle_id, "choice": choice, "route": candidate,
                    "previous_route": info["previous_route"], "seconds": selected["seconds"]}
        try:
            traci.vehicle.setRoute(vehicle_id, candidate)
        except traci.TraCIException as exc:
            raise ValueError(f"SUMO não aceitou a rota: {exc}") from exc
        costs = self._edge_costs()
        old_seconds = sum(costs.get(edge, float("inf")) for edge in remaining[1:])
        new_seconds = sum(costs.get(edge, float("inf")) for edge in candidate[1:])
        before_metres = sum(self.edge_lengths.get(edge, 0) for edge in remaining[1:])
        after_metres = sum(self.edge_lengths.get(edge, 0) for edge in candidate[1:])
        change = {"at_sim_time": traci.simulation.getTime(), "reason": "escolha manual",
                  "before_seconds": round(old_seconds, 1) if math.isfinite(old_seconds) else None,
                  "after_seconds": round(new_seconds, 1),
                  "saved_seconds": round(old_seconds - new_seconds, 1) if math.isfinite(old_seconds) else None,
                  "before_metres": round(before_metres, 1), "after_metres": round(after_metres, 1),
                  "distance_delta_m": round(after_metres - before_metres, 1),
                  "previous_route": remaining, "new_route": candidate}
        info["route"] = list(candidate)
        info["previous_route"] = remaining
        info["last_route_change"] = change
        info["route_history"].append(change)
        info["route_choice"] = choice
        info["strategy"] = "static"
        info["gps_status"] = "Rota escolhida manualmente; GPS estático até nova configuração"
        info["reroutes"] += 1
        self.route_changes += 1
        return {"vehicle_id": vehicle_id, "choice": choice, "route": candidate,
                "previous_route": remaining, "seconds": selected["seconds"]}

    def update_vehicle_gps(self, vehicle_id: str, strategy: str, interval: float,
                           benefit: float) -> dict:
        info = self.vehicles.get(vehicle_id)
        if not info or info["state"] == "arrived":
            raise ValueError("Veículo ativo não encontrado")
        info.update(strategy=strategy, gps_interval=interval, gps_benefit=benefit,
                    gps_customized=True, gps_next_check=traci.simulation.getTime() + interval)
        return info

    def update_vehicle_style(self, vehicle_id: str, color: str, speed_factor: float) -> dict:
        info = self.vehicles.get(vehicle_id)
        if not info or info["state"] == "arrived":
            raise ValueError("Veículo ativo não encontrado")
        rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
        traci.vehicle.setColor(vehicle_id, (*rgb, 255))
        info.update(color=color, speed_factor=speed_factor)
        self._apply_weather(vehicle_id)
        return info

    def _nearest_place(self, edge_id: str) -> str:
        if not self.places or edge_id not in self.edges:
            return "Não informado"
        x, y = self.edges[edge_id].getFromNode().getCoord()
        lon, lat = self.net.convertXY2LonLat(x, y)
        place = min(self.places, key=lambda feature:
                    (feature["geometry"]["coordinates"][0] - lon) ** 2 +
                    (feature["geometry"]["coordinates"][1] - lat) ** 2)
        return place["properties"]["name"]

    def _apply_weather(self, vehicle_id: str):
        settings = WEATHER[self.weather]
        traci.vehicle.setSpeedFactor(vehicle_id, settings["speed_factor"] * self.vehicles[vehicle_id].get("speed_factor", 1.0))
        traci.vehicle.setAccel(vehicle_id, settings["accel"])
        traci.vehicle.setDecel(vehicle_id, settings["decel"])
        traci.vehicle.setTau(vehicle_id, settings["tau"])

    def set_weather(self, weather: str):
        if weather not in WEATHER:
            raise ValueError("Clima inválido")
        self.weather = weather
        if self.connected:
            for vehicle_id in traci.vehicle.getIDList():
                self._apply_weather(vehicle_id)
            self.storage.add_intervention(self.run_id, traci.simulation.getTime(),
                                          "weather", weather, WEATHER[weather],
                                          traci.vehicle.getIDCount())

    def road_action(self, edge_id: str, action: str, speed_kmh: float | None = None):
        if not self.connected or edge_id not in self.edges:
            raise ValueError("Via não encontrada na rede SUMO ativa")
        lanes = [lane.getID() for lane in self.edges[edge_id].getLanes()]
        if action == "close":
            self.blocked.add(edge_id)
            for lane in lanes:
                traci.lane.setDisallowed(lane, ["passenger"])
        elif action == "partial":
            if len(lanes) < 2:
                raise ValueError("Interdição parcial exige uma via com ao menos duas faixas")
            traci.lane.setDisallowed(lanes[-1], ["passenger"])
            self.partial.add(edge_id)
        elif action == "slow":
            if not speed_kmh or not 5 <= speed_kmh <= 80:
                raise ValueError("Velocidade deve estar entre 5 e 80 km/h")
            self.reduced[edge_id] = speed_kmh / 3.6
            traci.edge.setMaxSpeed(edge_id, speed_kmh / 3.6)
        elif action == "restore":
            self.blocked.discard(edge_id)
            self.reduced.pop(edge_id, None)
            self.partial.discard(edge_id)
            for lane in lanes:
                traci.lane.setAllowed(lane, self.lane_permissions[lane])
            traci.edge.setMaxSpeed(edge_id, self.edge_speed[edge_id])
        else:
            raise ValueError("Ação desconhecida")
        affected = sum(edge_id in traci.vehicle.getRoute(vehicle_id) for vehicle_id in traci.vehicle.getIDList())
        self.storage.add_intervention(self.run_id, traci.simulation.getTime(),
                                      action, edge_id, {"speed_kmh": speed_kmh}, affected)
        self._reroute(force=True)
        return {"affected": affected}

    def traffic_light(self, tls_id: str, phase: int, duration: float | None = None,
                      restore: bool = False):
        if not self.connected or tls_id not in self.tls_original:
            raise ValueError("Semáforo não encontrado")
        if restore:
            for logic in self.tls_original[tls_id]:
                traci.trafficlight.setProgramLogic(tls_id, logic)
            self.tls_phases[tls_id] = [{"index": i, "duration": phase.duration, "state": phase.state}
                                       for i, phase in enumerate(self.tls_original[tls_id][0].phases)]
            return
        if duration is None or not 3 <= duration <= 180:
            raise ValueError("Duração deve estar entre 3 e 180 s")
        current_program = traci.trafficlight.getProgram(tls_id)
        logic = next((copy.deepcopy(item) for item in traci.trafficlight.getAllProgramLogics(tls_id)
                      if item.programID == current_program), None)
        if logic is None or not 0 <= phase < len(logic.phases):
            raise ValueError("Fase inválida")
        # Só ajusta a duração; nunca modifica os estados de sinais conflitantes.
        logic.phases[phase].duration = duration
        traci.trafficlight.setProgramLogic(tls_id, logic)
        self.tls_phases[tls_id] = [{"index": i, "duration": item.duration, "state": item.state}
                                   for i, item in enumerate(logic.phases)]
        self.storage.add_intervention(self.run_id, traci.simulation.getTime(),
                                      "traffic_light", tls_id,
                                      {"phase": phase, "duration": duration}, 0)

    def _edge_costs(self):
        observed: dict[str, list[float]] = defaultdict(list)
        for vehicle_id in traci.vehicle.getIDList():
            road = traci.vehicle.getRoadID(vehicle_id)
            if road in self.edges:
                observed[road].append(traci.vehicle.getSpeed(vehicle_id))
        costs = {}
        for edge_id, edge in self.edges.items():
            if edge_id in self.blocked:
                costs[edge_id] = float("inf")
                continue
            base = edge.getLength() / max(self.reduced.get(edge_id, edge.getSpeed()) * WEATHER[self.weather]["speed_factor"], 1)
            speeds = observed.get(edge_id)
            mean_speed = sum(speeds) / len(speeds) if speeds else None
            costs[edge_id] = max(base, edge.getLength() / max(mean_speed, 1)) if mean_speed is not None else base
        return costs

    def _reroute(self, force=False):
        begin = perf_counter()
        costs = self._edge_costs()
        now = traci.simulation.getTime()
        for vehicle_id in traci.vehicle.getIDList():
            info = self.vehicles.get(vehicle_id)
            if not info:
                continue
            old = list(traci.vehicle.getRoute(vehicle_id))
            current = traci.vehicle.getRoadID(vehicle_id)
            if current.startswith(":") or current not in self.edges:
                continue
            index = traci.vehicle.getRouteIndex(vehicle_id)
            remaining = old[max(index, 0):]
            obstructed = any(edge in self.blocked for edge in remaining[1:])
            due = info["strategy"] == "dynamic" and now >= info["gps_next_check"]
            if not obstructed and not due and not force:
                continue
            if not obstructed and info["strategy"] == "static":
                continue
            checkpoints = [current, *info.get("remaining_waypoints", []), info["destination"]]
            candidate = self.route_through(checkpoints, costs)
            old_cost = sum(costs.get(edge, float("inf")) for edge in remaining[1:])
            new_cost = sum(costs.get(edge, float("inf")) for edge in candidate[1:]) if candidate else float("inf")
            info["gps_last_checked"] = now
            info["gps_next_check"] = now + info["gps_interval"]
            info["gps_estimated_remaining"] = new_cost if math.isfinite(new_cost) else None
            info["gps_alternative_saving"] = max(0.0, old_cost - new_cost) if math.isfinite(old_cost) and math.isfinite(new_cost) else 0.0
            if len(candidate) < 2:
                info["gps_status"] = "Sem desvio disponível" if obstructed else "Sem rota alternativa"
                continue
            if candidate != remaining and (obstructed or new_cost < old_cost * (1 - info["gps_benefit"])):
                current_lane = traci.vehicle.getLaneID(vehicle_id)
                distance_to_junction = self.edges[current].getLength() - traci.vehicle.getLanePosition(vehicle_id)
                if current_lane not in self.turn_lanes.get((current, candidate[1]), set()) and distance_to_junction < 50:
                    info["gps_status"] = "Desvio aguardando acesso à faixa correta"
                    continue
                try:
                    traci.vehicle.setRoute(vehicle_id, candidate)
                except traci.TraCIException:
                    info["gps_status"] = "Desvio inviável na posição atual"
                    continue
                before_metres = sum(self.edges[edge].getLength() for edge in remaining[1:] if edge in self.edges)
                after_metres = sum(self.edges[edge].getLength() for edge in candidate[1:] if edge in self.edges)
                change = {"at_sim_time": now, "reason": "interdição" if obstructed else "trânsito",
                          "before_seconds": round(old_cost, 1) if math.isfinite(old_cost) else None,
                          "after_seconds": round(new_cost, 1),
                          "saved_seconds": round(old_cost - new_cost, 1) if math.isfinite(old_cost) else None,
                          "before_metres": round(before_metres, 1), "after_metres": round(after_metres, 1),
                          "distance_delta_m": round(after_metres - before_metres, 1),
                          "previous_route": remaining, "new_route": candidate}
                info["previous_route"] = remaining
                info["last_route_change"] = change
                info["route_history"].append(change)
                info["route"] = candidate
                info["reroutes"] += 1
                self.route_changes += 1
                info["gps_status"] = "Rota atualizada por trânsito" if not obstructed else "Desvio por interdição"
            else:
                info["gps_status"] = "Rota atual mantida"
        self.algorithm_ms = (perf_counter() - begin) * 1000

    def _update_forecasts(self, now: float):
        costs = self._edge_costs()
        for vehicle_id in traci.vehicle.getIDList():
            info = self.vehicles.get(vehicle_id)
            if not info:
                continue
            route = list(traci.vehicle.getRoute(vehicle_id))
            road = traci.vehicle.getRoadID(vehicle_id)
            position = traci.vehicle.getLanePosition(vehicle_id)
            index = traci.vehicle.getRouteIndex(vehicle_id)
            metres, seconds = remaining_route_metrics(
                route, index, road, position, self.edge_lengths, costs)
            info["remaining_distance_m"] = metres
            info["gps_estimated_remaining"] = seconds
            info["predicted_arrival_sim_time"] = now + seconds
            info["forecast_updated_at"] = now

    def step(self):
        if not self.connected:
            raise RuntimeError("SUMO não iniciado")
        traci.simulationStep()
        now = traci.simulation.getTime()
        while self.pending_trips and self.pending_trips[0]["departed"] <= now:
            trip = self.pending_trips.pop(0)
            points = [trip["origin"], *trip.get("waypoints", []), trip["destination"]]
            self.spawn_trip(trip["origin"], trip["destination"], trip["strategy"],
                            self.route_through(points), origin_pos=trip.get("origin_pos"),
                            destination_pos=trip.get("destination_pos"), color=trip.get("color", "#4de1cc"),
                            gps_interval=trip.get("gps_interval"), gps_benefit=trip.get("gps_benefit"),
                            speed_factor=trip.get("speed_factor", 1.0), waypoints=trip.get("waypoints", []))
        self.spawn_credit += (self.loop_state()["vehicles_per_minute"] / 60 if self.loop_enabled else self.continuous_rate) * STEP_SECONDS
        extra = int(self.spawn_credit)
        self.spawn_credit -= extra
        if extra:
            self.spawn(min(extra, 20))
        for vehicle_id in traci.simulation.getArrivedIDList():
            info = self.vehicles.get(vehicle_id)
            if not info:
                continue
            info["state"] = "arrived"
            info["arrived"] = now
            info["travel_time"] = now - info["departed"]
            predicted = info.get("predicted_arrival_sim_time")
            info["forecast_error_s"] = round(now - predicted, 1) if predicted is not None else None
            self.storage.add_trip(self.run_id, info)
            self.completed += 1
        for vehicle_id in traci.vehicle.getIDList():
            info = self.vehicles.get(vehicle_id)
            if info:
                road = traci.vehicle.getRoadID(vehicle_id)
                if info.get("remaining_waypoints") and road == info["remaining_waypoints"][0]:
                    info["remaining_waypoints"].pop(0)
                speed = traci.vehicle.getSpeed(vehicle_id)
                allowed = traci.vehicle.getAllowedSpeed(vehicle_id)
                next_lights = traci.vehicle.getNextTLS(vehicle_id)
                at_red = any(distance <= 35 and state.lower() in ("r", "y")
                             for _, _, distance, state in next_lights)
                if at_red and speed < 3:
                    info["state"] = "at_signal"
                elif speed < 1 or (allowed > 4 and speed < allowed * 0.25):
                    info["state"] = "congested"
                else:
                    info["state"] = "moving"
                info["distance"] = traci.vehicle.getDistance(vehicle_id)
                info["waiting_time"] = traci.vehicle.getAccumulatedWaitingTime(vehicle_id)
        if any(info["strategy"] == "dynamic" and info["state"] != "arrived" and now >= info["gps_next_check"]
               for info in self.vehicles.values()):
            self._reroute()
        if now - self.last_sample_at >= 5 - 1e-6:
            self._update_forecasts(now)
            self.latest_sample = self._sample()
            self.storage.add_sample(self.run_id, self.latest_sample)
            self.last_sample_at = now

    def _sample(self):
        ids = traci.vehicle.getIDList()
        speeds = [traci.vehicle.getSpeed(vehicle_id) for vehicle_id in ids]
        waits = [traci.vehicle.getAccumulatedWaitingTime(vehicle_id) for vehicle_id in ids]
        finished = [info["travel_time"] for info in self.vehicles.values() if info["state"] == "arrived"]
        return {"sim_time": traci.simulation.getTime(), "active": len(ids),
                "completed": self.completed, "mean_speed": sum(speeds) / len(speeds) if speeds else 0,
                "mean_wait": sum(waits) / len(waits) if waits else 0,
                "mean_travel": sum(finished) / len(finished) if finished else 0,
                "reroutes": self.route_changes, "algorithm_ms": self.algorithm_ms}

    def network_geojson(self):
        features = []
        if not self.net:
            return {"type": "FeatureCollection", "features": []}
        for edge_id, edge in self.edges.items():
            shape = [self.net.convertXY2LonLat(x, y) for x, y in edge.getShape()]
            osm_id = edge_id.lstrip("-").split("#")[0]
            name = self.osm_names.get(osm_id, edge.getName())
            if name == edge_id or name == osm_id or name == "Via sem nome":
                name = ""
            features.append({"type": "Feature", "id": edge_id,
                             "geometry": {"type": "LineString", "coordinates": shape},
                             "properties": {"id": edge_id, "name": name,
                                            "length": round(edge.getLength(), 1),
                                            "speed_kmh": round(edge.getSpeed() * 3.6, 1),
                                            "lanes": len(edge.getLanes())}})
        lanes = []
        for edge in self.net.getEdges():
            if edge.getID() not in self.edges and edge.getFunction() != "internal":
                continue
            for lane in edge.getLanes():
                if not lane.allows("passenger"):
                    continue
                shape = lane.getShape()
                if len(shape) < 2:
                    continue
                lanes.append({"type": "Feature", "id": lane.getID(),
                              "geometry": {"type": "LineString", "coordinates": [
                                  self.net.convertXY2LonLat(x, y) for x, y in shape]},
                              "properties": {"width_m": lane.getWidth() if lane.getWidth() > 0 else 3.2}})
        simulated_lights = [
            {"id": tls.getID(), "coordinates": self.net.convertXY2LonLat(*self.net.getNode(tls.getID()).getCoord())}
            for tls in self.net.getTrafficLights()
            if tls.getID() in self.simulated_signals and self.net.hasNode(tls.getID())
        ]
        return {"type": "FeatureCollection", "features": features,
                "lanes": {"type": "FeatureCollection", "features": lanes},
                "simulated_lights": simulated_lights}

    def snapshot(self):
        if not self.connected:
            return {"ready": bool(self.net), "connected": False, "running": False,
                    "speed": self.speed,
                    "error": None if self.net else "Rede SUMO ainda não construída"}
        ids = traci.vehicle.getIDList()
        vehicles = []
        road_speeds: dict[str, list[float]] = defaultdict(list)
        now = traci.simulation.getTime()
        for vehicle_id in ids:
            info = self.vehicles.get(vehicle_id)
            if not info:
                continue
            xy = traci.vehicle.getPosition(vehicle_id)
            lon, lat = traci.simulation.convertGeo(*xy)
            speed = traci.vehicle.getSpeed(vehicle_id)
            road = traci.vehicle.getRoadID(vehicle_id)
            if road in self.edges:
                road_speeds[road].append(speed)
            vehicles.append({**info, "coordinates": [lon, lat],
                             "speed": speed,
                             "angle": traci.vehicle.getAngle(vehicle_id),
                             "lane_id": traci.vehicle.getLaneID(vehicle_id),
                             "road": road,
                             "eta_city_hour": city_hour(self.city_start_hour, info["predicted_arrival_sim_time"])
                             if info.get("predicted_arrival_sim_time") is not None else None,
                             "travel_time": now - info["departed"]})
        lights = []
        for tls_id, coordinates in self.tls_coordinates.items():
            signal_state = traci.trafficlight.getRedYellowGreenState(tls_id)
            counts = {"red": sum(char in "rR" for char in signal_state),
                      "yellow": sum(char in "yY" for char in signal_state),
                      "green": sum(char in "gG" for char in signal_state)}
            aspect = ("attention" if counts["yellow"] else
                      "mixed" if counts["red"] and counts["green"] else
                      "open" if counts["green"] else "closed")
            lane_aspects: dict[str, set[str]] = defaultdict(set)
            movements = []
            for movement in self.signal_links.get(tls_id, []):
                state = signal_state[movement["index"]] if movement["index"] < len(signal_state) else "r"
                link_aspect = "closed" if state in "rR" else "open" if state in "gG" else "attention"
                lane_aspects[movement["incoming_lane"]].add(link_aspect)
                movements.append({**movement, "aspect": link_aspect})
            for movement in movements:
                movement["show_approach"] = len(lane_aspects[movement["incoming_lane"]]) == 1
            lights.append({"id": tls_id, "coordinates": coordinates,
                           "simulated_neighborhood": self.simulated_signals.get(tls_id),
                           "state": signal_state, "aspect": aspect, "counts": counts,
                           "movements": movements,
                           "phase": traci.trafficlight.getPhase(tls_id),
                           "next_switch": traci.trafficlight.getNextSwitch(tls_id),
                           "phases": self.tls_phases.get(tls_id, [])})
        congestion = [{"id": edge_id, "count": len(speeds), "speed": sum(speeds) / len(speeds)}
                      for edge_id, speeds in road_speeds.items()]
        return {"ready": True, "connected": True, "running": self.running,
                "network_version": self.network_version, "network_scenario_id": self.network_scenario_id,
                "city_id": self.city_id, "city_name": self.city_name,
                "sim_time": now, "speed": self.speed,
                "clock_hour": city_hour(self.city_start_hour, now),
                "city_start_hour": self.city_start_hour,
                "weather": self.weather, "weather_modifiers": WEATHER[self.weather],
                "vehicles": vehicles, "active": len(ids), "completed": self.completed,
                "spawned": len(self.vehicles), "reroutes": self.route_changes,
                "lights": lights, "congestion": congestion,
                "blocked": list(self.blocked), "reduced": self.reduced,
                "partial": list(self.partial),
                "sample": self.latest_sample, "run_id": self.run_id,
                "loop": self.loop_state(),
                "gps": {"interval": self.gps_interval, "benefit": self.gps_benefit,
                         "dynamic_percent": self.dynamic_percent}}
