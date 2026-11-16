"""Estudo pareado de distribuição de rotas no corredor da Avenida Brasil.

Executa o motor Simulator/TraCI existente sem renderizar frames. Os dados
brutos, partidas e resultados ficam em uma pasta separada do banco do jogo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import traci  # noqa: E402

from backend.engine import STEP_SECONDS, Simulator  # noqa: E402
from backend.experiment_analysis import confidence_interval, percentile  # noqa: E402
from backend.storage import Storage  # noqa: E402

ORIGIN = "1560016695"
DESTINATION = "93392451#3"
PRIMARY_NAME = "Avenida Brasil"
CORRIDORS = {"brasil": (ORIGIN, DESTINATION, PRIMARY_NAME),
             "castelo": ("1151559472#0", "284625097#1", "Avenida Presidente Castelo Branco")}
STRATEGIES = ("principal", "um_desvio", "todos_desvio", "dividido", "gps_dinamico")
LABELS = {
    "principal": "Todos na Avenida Brasil",
    "um_desvio": "Um motorista na alternativa",
    "todos_desvio": "Todos na alternativa",
    "dividido": "Metade em cada rota",
    "gps_dinamico": "GPS dinâmico, partida principal",
}
LEVELS = {"baixo": 30, "medio": 90, "alto": 180}
SEEDS = (20261114, 20261115, 20261116)
DEPARTURE_WINDOW = 240.0
MAX_TIME = 1800.0
CAPTURE_SECONDS = 5.0
FOCAL_INDEX = 90


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def route_definition() -> dict:
    store = Storage(":memory:")
    sim = Simulator(str(ROOT / "data"), store)
    try:
        choices = sim.route_choices([ORIGIN, DESTINATION])
        if len(choices) < 2:
            raise RuntimeError("Este par origem/destino não apresenta rota alternativa")
        primary, alternative = choices[:2]
        if not all(sim.osm_names.get(edge.lstrip("-").split("#")[0]) == PRIMARY_NAME
                   for edge in primary["route"]):
            raise RuntimeError("A rota principal deixou de seguir a Avenida Brasil")
        network_hash = hashlib.sha256(sim.net_path.read_bytes()).hexdigest()[:16]
        names = lambda path: list(dict.fromkeys(sim.osm_names.get(edge.lstrip("-").split("#")[0], "Via sem nome")
                                                for edge in path))
        return {"origin": ORIGIN, "destination": DESTINATION,
                "origin_coordinates": list(sim.net.convertXY2LonLat(*sim.edges[ORIGIN].getShape()[0])),
                "destination_coordinates": list(sim.net.convertXY2LonLat(*sim.edges[DESTINATION].getShape()[-1])),
                "primary": primary, "alternative": alternative,
                "primary_streets": names(primary["route"]),
                "alternative_streets": names(alternative["route"]),
                "network_sha256_16": network_hash,
                "shared_edges": len(set(primary["route"]) & set(alternative["route"])),
                "exclusive_primary": sorted(set(primary["route"]) - set(alternative["route"])),
                "exclusive_alternative": sorted(set(alternative["route"]) - set(primary["route"]))}
    finally:
        store.db.close()


def departures(seed: int, level: str) -> list[dict]:
    """A demanda menor é subconjunto da maior; sementes iguais pareiam variantes."""
    maximum = max(LEVELS.values())
    stride = maximum // LEVELS[level]
    rng = random.Random(seed)
    jitter = [rng.uniform(-.35, .35) for _ in range(maximum)]
    result = []
    for index in range(0, maximum, stride):
        at = max(0.0, 2 + index * DEPARTURE_WINDOW / maximum + jitter[index])
        result.append({"demand_index": index, "planned_depart_s": round(at, 2),
                       "focal": index == FOCAL_INDEX})
    return result


def balanced_ids(schedule: list[dict]) -> set[int]:
    selected = {trip["demand_index"] for trip in schedule[::2]}
    if FOCAL_INDEX not in selected:
        selected.remove(next(index for index in sorted(selected, reverse=True) if index != FOCAL_INDEX))
        selected.add(FOCAL_INDEX)
    return selected


def assigned_route(strategy: str, index: int, balanced: set[int]) -> str:
    if strategy == "todos_desvio" or strategy == "um_desvio" and index == FOCAL_INDEX:
        return "alternative"
    if strategy == "dividido" and index in balanced:
        return "alternative"
    return "primary"


def run_one(output: Path, route: dict, level: str, strategy: str, seed: int) -> dict:
    key = f"{level}__{strategy}__{seed}"
    path = output / "runs" / f"{key}.json"
    signature = hashlib.sha256(json.dumps({"network": route["network_sha256_16"],
        "level": level, "strategy": strategy, "seed": seed, "window": DEPARTURE_WINDOW,
        "limit": MAX_TIME, "capture": CAPTURE_SECONDS,
        "balanced_policy": 2 if strategy == "dividido" else 1,
        **({"corridor": [ORIGIN, DESTINATION]} if PRIMARY_NAME != "Avenida Brasil" else {})},
        sort_keys=True).encode()).hexdigest()[:16]
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("signature") == signature:
            if previous.get("strategy_label") != LABELS[strategy]:
                previous["strategy_label"] = LABELS[strategy]
                write_json(path, previous)
            print(f"reutilizado {key}", flush=True)
            return previous
    schedule = departures(seed, level)
    half_alt = balanced_ids(schedule)
    tripinfo_file = output / "runs" / f"{key}.tripinfo.xml"
    store = Storage(str(output / "runs" / f"{key}.sqlite3"))
    sim = Simulator(str(ROOT / "data"), store)
    main_only = set(route["exclusive_primary"])
    alt_only = set(route["exclusive_alternative"])
    route_edges = set(route["primary"]["route"]) | set(route["alternative"]["route"])
    schedule_by_car: dict[str, dict] = {}
    unserved = []
    time_series = []
    edge_totals = defaultdict(lambda: {"vehicle_seconds": 0.0, "distance_vehicle_m": 0.0,
                                       "speed_vehicle_sum": 0.0, "queue_seconds": 0.0,
                                       "max_queue": 0, "observed_s": 0.0})
    next_trip = 0
    next_capture = 0.0
    try:
        sim.start(seed, 8.0, str(tripinfo_file))
        sim.gps_interval = 15.0
        sim.gps_benefit = .05
        while traci.simulation.getTime() < MAX_TIME:
            now = traci.simulation.getTime()
            while next_trip < len(schedule) and schedule[next_trip]["planned_depart_s"] <= now + STEP_SECONDS:
                trip = schedule[next_trip]
                next_trip += 1
                choice = assigned_route(strategy, trip["demand_index"], half_alt)
                path_edges = route[choice]["route"]
                created = sim.spawn_trip(ORIGIN, DESTINATION,
                    "dynamic" if strategy == "gps_dinamico" else "static", path_edges,
                    group_label=choice, route_choice="best" if choice == "primary" else "secondary",
                    gps_interval=15.0 if strategy == "gps_dinamico" else None,
                    gps_benefit=.05 if strategy == "gps_dinamico" else None)
                if created:
                    car_id = f"car-{sim.run_id}-{sim.next_vehicle_id}"
                    sim.vehicles[car_id]["demand_index"] = trip["demand_index"]
                    schedule_by_car[car_id] = {**trip, "assigned_route": choice}
                else:
                    unserved.append(trip)
            sim.step()
            now = traci.simulation.getTime()
            if now + 1e-6 >= next_capture:
                ids = traci.vehicle.getIDList()
                positions = Counter(traci.vehicle.getRoadID(car_id) for car_id in ids)
                occupied_main = sum(positions[edge] for edge in main_only)
                occupied_alt = sum(positions[edge] for edge in alt_only)
                occupied_shared = sum(positions[edge] for edge in route_edges - main_only - alt_only)
                queue_main = queue_alt = 0
                for edge in route_edges:
                    count = traci.edge.getLastStepVehicleNumber(edge)
                    queue = traci.edge.getLastStepHaltingNumber(edge)
                    if edge in main_only:
                        queue_main += queue
                    elif edge in alt_only:
                        queue_alt += queue
                    speed = traci.edge.getLastStepMeanSpeed(edge) if count else 0.0
                    item = edge_totals[edge]
                    item["vehicle_seconds"] += count * CAPTURE_SECONDS
                    item["speed_vehicle_sum"] += speed * count
                    item["queue_seconds"] += queue * CAPTURE_SECONDS
                    item["max_queue"] = max(item["max_queue"], queue)
                    item["observed_s"] += CAPTURE_SECONDS
                time_series.append({"time_s": round(now, 2), "active": len(ids),
                    "inserted": sum(1 for item in schedule_by_car if item in ids or sim.vehicles[item]["state"] == "arrived"),
                    "completed": sim.completed, "on_primary_only": occupied_main,
                    "on_alternative_only": occupied_alt, "on_shared": occupied_shared,
                    "queue_primary": queue_main, "queue_alternative": queue_alt,
                    "pending_insertion": len(traci.simulation.getPendingVehicles()),
                    "reroutes": sim.route_changes})
                next_capture += CAPTURE_SECONDS
            if next_trip == len(schedule) and not traci.vehicle.getIDList() and not traci.simulation.getPendingVehicles():
                break
        end_time = traci.simulation.getTime()
    finally:
        sim.stop()
        store.db.close()
    tripinfos = {item.attrib["id"]: item.attrib for item in ET.parse(tripinfo_file).getroot().findall("tripinfo")}
    records = []
    for car_id, trip in schedule_by_car.items():
        info = sim.vehicles[car_id]
        actual = tripinfos.get(car_id)
        records.append({"demand_index": trip["demand_index"], "focal": trip["focal"],
            "vehicle_id": car_id, "assigned_route": trip["assigned_route"],
            "planned_depart_s": trip["planned_depart_s"],
            "actual_depart_s": float(actual["depart"]) if actual else None,
            "arrived_s": float(actual["arrival"]) if actual else None,
            "depart_delay_s": float(actual["departDelay"]) if actual else None,
            "travel_s": float(actual["duration"]) if actual else None,
            "door_to_door_s": round(float(actual["arrival"]) - trip["planned_depart_s"], 2) if actual else None,
            "time_loss_s": float(actual["timeLoss"]) if actual else None,
            "waiting_s": float(actual["waitingTime"]) if actual else None,
            "distance_m": float(actual["routeLength"]) if actual else None,
            "reroutes": info["reroutes"], "completed": bool(actual),
            "status": "concluída" if actual else "não concluída no limite",
            "final_route": info.get("route", []),
            "route_changes": info.get("route_history", [])})
    for trip in unserved:
        records.append({"demand_index": trip["demand_index"], "focal": trip["focal"],
            "vehicle_id": None, "assigned_route": assigned_route(strategy, trip["demand_index"], half_alt),
            "planned_depart_s": trip["planned_depart_s"], "completed": False,
            "status": "SUMO rejeitou a viagem"})
    records.sort(key=lambda item: item["demand_index"])
    completed = [item for item in records if item["completed"]]
    measure = lambda key: [item[key] for item in completed if item.get(key) is not None]
    road_stats = {}
    for edge, item in edge_totals.items():
        road_stats[edge] = {"name": sim.osm_names.get(edge.lstrip("-").split("#")[0], "Via sem nome"),
            "mean_speed_kmh": round(item["speed_vehicle_sum"] / item["vehicle_seconds"] * CAPTURE_SECONDS * 3.6, 2)
                if item["vehicle_seconds"] else None,
            "vehicle_observations": round(item["vehicle_seconds"] / CAPTURE_SECONDS),
            "mean_queue": round(item["queue_seconds"] / item["observed_s"], 3) if item["observed_s"] else 0,
            "max_queue": item["max_queue"], "free_speed_kmh": round(sim.edges[edge].getSpeed() * 3.6, 1)}
    focal = next((item for item in records if item["focal"]), None)
    result = {"key": key, "signature": signature, "level": level, "requested": LEVELS[level], "strategy": strategy,
        "strategy_label": LABELS[strategy], "seed": seed,
        "network_sha256_16": route["network_sha256_16"], "duration_s": round(end_time, 2),
        "tripinfo_file": tripinfo_file.name,
        "summary": {"completed": len(completed), "unfinished": len(records) - len(completed),
            "completion_rate": round(len(completed) / len(records), 4),
            "mean_travel_s": round(statistics.mean(measure("travel_s")), 2) if completed else None,
            "median_travel_s": percentile(measure("travel_s"), 50),
            "p95_travel_s": percentile(measure("travel_s"), 95),
            "max_travel_s": max(measure("travel_s"), default=None),
            "mean_door_to_door_s": round(statistics.mean(measure("door_to_door_s")), 2) if completed else None,
            "mean_time_loss_s": round(statistics.mean(measure("time_loss_s")), 2) if completed else None,
            "mean_waiting_s": round(statistics.mean(measure("waiting_s")), 2) if completed else None,
            "mean_depart_delay_s": round(statistics.mean(measure("depart_delay_s")), 2) if completed else None,
            "mean_distance_m": round(statistics.mean(measure("distance_m")), 2) if completed else None,
            "reroutes": sum(item.get("reroutes", 0) for item in records),
            "assigned_primary": sum(item["assigned_route"] == "primary" for item in records),
            "assigned_alternative": sum(item["assigned_route"] == "alternative" for item in records),
            "peak_queue_primary": max((item["queue_primary"] for item in time_series), default=0),
            "peak_queue_alternative": max((item["queue_alternative"] for item in time_series), default=0),
            "mean_queue_primary": round(statistics.mean(item["queue_primary"] for item in time_series), 2),
            "mean_queue_alternative": round(statistics.mean(item["queue_alternative"] for item in time_series), 2),
            "peak_pending_insertion": max((item["pending_insertion"] for item in time_series), default=0),
            "focal_travel_s": focal.get("travel_s") if focal else None,
            "focal_door_to_door_s": focal.get("door_to_door_s") if focal else None},
        "vehicles": records, "route_occupancy": time_series, "roads": road_stats}
    write_json(path, result)
    print(f"feito {key}: {len(completed)}/{len(records)}; viagem média {result['summary']['mean_travel_s']} s; "
          f"fila pico {result['summary']['peak_queue_primary']}+{result['summary']['peak_queue_alternative']}", flush=True)
    return result


def aggregate(output: Path, route: dict, runs: list[dict]) -> None:
    code_digest = hashlib.sha256()
    for name in ("backend/engine.py", "backend/graphs.py", "backend/route_choices.py",
                 "scripts/collective_route_study.py"):
        code_digest.update(name.encode())
        code_digest.update((ROOT / name).read_bytes())
    try:
        sumo_version = subprocess.check_output([os.environ.get("SUMO_BINARY", "sumo"), "--version"],
                                               text=True, timeout=5).splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        sumo_version = "não identificado"
    groups = defaultdict(list)
    for item in runs:
        groups[(item["level"], item["strategy"])].append(item)
    rows = []
    metrics = ("mean_travel_s", "mean_door_to_door_s", "mean_time_loss_s", "mean_waiting_s",
               "mean_depart_delay_s", "median_travel_s", "p95_travel_s", "max_travel_s",
               "mean_distance_m", "completion_rate", "mean_queue_primary", "mean_queue_alternative",
               "peak_queue_primary", "peak_queue_alternative", "peak_pending_insertion",
               "reroutes", "focal_travel_s", "focal_door_to_door_s")
    for (level, strategy), items in groups.items():
        row = {"level": level, "vehicles": LEVELS[level], "strategy": strategy,
               "strategy_label": LABELS[strategy], "repetitions": len(items),
               "completed_total": sum(item["summary"]["completed"] for item in items),
               "requested_total": sum(item["requested"] for item in items)}
        for metric in metrics:
            values = [item["summary"][metric] for item in items if item["summary"][metric] is not None]
            row[metric] = round(statistics.mean(values), 2) if values else None
        ci = confidence_interval([item["summary"]["mean_travel_s"] for item in items
                                  if item["summary"]["mean_travel_s"] is not None])
        row["mean_travel_ci95_low"] = ci["lower"] if ci else None
        row["mean_travel_ci95_high"] = ci["upper"] if ci else None
        rows.append(row)
    rows.sort(key=lambda row: (LEVELS[row["level"]], STRATEGIES.index(row["strategy"])))
    paired = []
    for level in LEVELS:
        reference = {item["seed"]: item for item in groups.get((level, "principal"), [])}
        for strategy in STRATEGIES[1:]:
            differences = []
            focal_differences = []
            for item in groups.get((level, strategy), []):
                base = reference.get(item["seed"])
                if not base:
                    continue
                a, b = base["summary"], item["summary"]
                if a["mean_travel_s"] is not None and b["mean_travel_s"] is not None:
                    differences.append(round(b["mean_travel_s"] - a["mean_travel_s"], 2))
                if a["focal_travel_s"] is not None and b["focal_travel_s"] is not None:
                    focal_differences.append(round(b["focal_travel_s"] - a["focal_travel_s"], 2))
            if differences:
                paired.append({"level": level, "strategy": strategy, "seeds": len(differences),
                    "mean_difference_s": round(statistics.mean(differences), 2),
                    "individual_differences_s": differences,
                    "confidence_interval_95": confidence_interval(differences),
                    "focal_mean_difference_s": round(statistics.mean(focal_differences), 2)
                        if focal_differences else None,
                    "focal_individual_differences_s": focal_differences})
    write_json(output / "summary.json", {"route": route, "design": {
        "levels": LEVELS, "strategies": LABELS, "seeds": SEEDS,
        "code_sha256_16": code_digest.hexdigest()[:16], "sumo_version": sumo_version,
        "departure_window_s": DEPARTURE_WINDOW, "max_time_s": MAX_TIME,
        "physical_step_s": STEP_SECONDS, "capture_step_s": CAPTURE_SECONDS,
        "focal_demand_index": FOCAL_INDEX,
        "demand_rule": "30/90/180 partidas no mesmo intervalo; as menores são subconjuntos determinísticos das 180",
        "gps": "15 s, ganho mínimo 5%, todos começam na rota principal",
        "teleport": "desativado", "weather": "sol", "start_city_hour": "08:00",
        "limitations": ["Recorte central OSM, demanda sintética de um único par origem-destino",
                        "Saída de uma única via pode limitar inserção de veículos",
                        "Tempo médio e p95 usam apenas viagens concluídas; taxa de conclusão é apresentada separadamente",
                        "Três sementes fornecem intervalos de confiança exploratórios, não validação de tráfego real"]},
        "aggregates": rows, "paired_vs_primary": paired})
    with (output / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    with (output / "run_summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["level", "strategy", "seed", "requested", *runs[0]["summary"].keys()]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            writer.writerow({**{key: run[key] for key in ("level", "strategy", "seed", "requested")},
                             **run["summary"]})
    with (output / "paired_vs_primary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["level", "strategy", "seeds", "mean_difference_s", "ci95_low_s", "ci95_high_s",
                  "focal_mean_difference_s", "individual_differences_s", "focal_individual_differences_s"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in paired:
            ci = item["confidence_interval_95"]
            writer.writerow({"level": item["level"], "strategy": item["strategy"],
                             "seeds": item["seeds"], "mean_difference_s": item["mean_difference_s"],
                             "ci95_low_s": ci["lower"] if ci else None,
                             "ci95_high_s": ci["upper"] if ci else None,
                             "focal_mean_difference_s": item["focal_mean_difference_s"],
                             "individual_differences_s": json.dumps(item["individual_differences_s"]),
                             "focal_individual_differences_s": json.dumps(item["focal_individual_differences_s"])})
    with (output / "vehicles.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["level", "strategy", "seed", "demand_index", "focal", "vehicle_id", "assigned_route",
                  "planned_depart_s", "actual_depart_s", "arrived_s", "depart_delay_s", "travel_s",
                  "door_to_door_s", "time_loss_s", "waiting_s", "distance_m", "reroutes", "completed", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            for vehicle in run["vehicles"]:
                writer.writerow({key: run[key] if key in ("level", "strategy", "seed")
                                 else vehicle.get(key) for key in fields})
    with (output / "occupancy.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["level", "strategy", "seed", "time_s", "active", "inserted", "completed",
                  "on_primary_only", "on_alternative_only", "on_shared", "queue_primary",
                  "queue_alternative", "pending_insertion", "reroutes"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            for sample in run["route_occupancy"]:
                writer.writerow({**{key: run[key] for key in ("level", "strategy", "seed")}, **sample})
    with (output / "roads.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        fields = ["level", "strategy", "seed", "edge_id", "name", "mean_speed_kmh",
                  "vehicle_observations", "mean_queue", "max_queue", "free_speed_kmh"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            for edge_id, road in run["roads"].items():
                writer.writerow({**{key: run[key] for key in ("level", "strategy", "seed")},
                                 "edge_id": edge_id, **road})


def main() -> None:
    global ORIGIN, DESTINATION, PRIMARY_NAME
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--corridor", choices=CORRIDORS, default="brasil")
    parser.add_argument("--levels", nargs="+", choices=LEVELS, default=list(LEVELS))
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(SEEDS))
    args = parser.parse_args()
    ORIGIN, DESTINATION, PRIMARY_NAME = CORRIDORS[args.corridor]
    LABELS["principal"] = f"Todos na {PRIMARY_NAME}"
    output = (args.output or ROOT.parent / ("estudo-rotas-coletivas" if args.corridor == "brasil"
                                           else "estudo-castelo-branco")).resolve()
    (output / "runs").mkdir(parents=True, exist_ok=True)
    route = route_definition()
    write_json(output / "routes.json", route)
    runs = [run_one(output, route, level, strategy, seed)
            for level in args.levels for seed in args.seeds for strategy in args.strategies]
    aggregate(output, route, runs)


if __name__ == "__main__":
    main()
