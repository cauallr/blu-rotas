"""Paired SUMO experiment: keep a route or divert at a shared approach edge.

The focal vehicle and all background vehicles are identical up to the decision.
Only the focal vehicle's route is changed in the diversion variant. The script
records both the GPS graph estimate and the road edges physically traversed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import traci  # noqa: E402

from backend.engine import STEP_SECONDS, Simulator  # noqa: E402
from backend.storage import Storage  # noqa: E402
from scripts.collective_route_study import CORRIDORS, DEPARTURE_WINDOW, FOCAL_INDEX, departures  # noqa: E402

MAX_TIME = 1800.0
LEVELS = ("medio", "alto")
SEEDS = (20261114, 20261115, 20261116)


def run_one(output: Path, corridor: str, level: str, seed: int, choice: str) -> dict:
    origin, destination, name = CORRIDORS[corridor]
    route_data = json.loads((ROOT / "research" / ("estudo-castelo-branco" if corridor == "castelo"
                             else "estudo-rotas-coletivas") / "routes.json").read_text(encoding="utf-8"))
    actual_network = hashlib.sha256((ROOT / "data" / "blumenau.net.xml").read_bytes()).hexdigest()[:16]
    if actual_network != route_data["network_sha256_16"]:
        raise RuntimeError(f"As rotas publicadas usam a malha {route_data['network_sha256_16']}, "
                           f"mas a malha atual é {actual_network}. Use a tag "
                           "study-rotas-malha-633d9a08 em outra pasta para reproduzir este estudo.")
    primary = route_data["primary"]["route"]
    alternative = route_data["alternative"]["route"]
    common = []
    for left, right in zip(primary, alternative):
        if left != right:
            break
        common.append(left)
    if len(common) < 3:
        raise RuntimeError("No shared approach with room to decide")
    decision_edge = common[-2]
    schedule = departures(seed, level)
    key = f"{corridor}__{level}__{seed}__{choice}"
    tripinfo_path = output / f"{key}.tripinfo.xml"
    result_path = output / f"{key}.json"
    if result_path.exists() and tripinfo_path.exists() and tripinfo_path.stat().st_size:
        cached = json.loads(result_path.read_text(encoding="utf-8"))
        if cached.get("network_sha256_16") == route_data["network_sha256_16"] and cached.get("vehicles") == len(schedule):
            return cached
    store = Storage(":memory:")
    sim = Simulator(str(ROOT / "data"), store)
    planned_by_id = {}
    focal_id = None
    decision = None
    traversed = []
    next_trip = 0
    try:
        sim.start(seed, 8.0, str(tripinfo_path))
        while traci.simulation.getTime() < MAX_TIME:
            now = traci.simulation.getTime()
            while next_trip < len(schedule) and schedule[next_trip]["planned_depart_s"] <= now + STEP_SECONDS:
                trip = schedule[next_trip]
                next_trip += 1
                if not sim.spawn_trip(origin, destination, "static", primary):
                    raise RuntimeError(f"SUMO rejected scheduled vehicle {trip['demand_index']}")
                car_id = f"car-{sim.run_id}-{sim.next_vehicle_id}"
                planned_by_id[car_id] = trip["planned_depart_s"]
                if trip["demand_index"] == FOCAL_INDEX:
                    focal_id = car_id
            sim.step()
            now = traci.simulation.getTime()
            active = traci.vehicle.getIDList()
            if focal_id in active:
                road = traci.vehicle.getRoadID(focal_id)
                if road and not road.startswith(":") and (not traversed or traversed[-1] != road):
                    traversed.append(road)
                if decision is None and road == decision_edge:
                    primary_index = primary.index(road)
                    alternative_index = alternative.index(road)
                    costs = sim._edge_costs()
                    primary_remaining = primary[primary_index:]
                    alternative_remaining = alternative[alternative_index:]
                    estimate_primary = sum(costs[edge] for edge in primary_remaining[1:])
                    estimate_alternative = sum(costs[edge] for edge in alternative_remaining[1:])
                    gps_route = sim.route(road, destination, costs)
                    state = [(vid, traci.vehicle.getRoadID(vid), round(traci.vehicle.getLanePosition(vid), 2))
                             for vid in sorted(active)]
                    decision = {
                        "time_s": now,
                        "road": road,
                        "road_name": sim.osm_names.get(road.lstrip("-").split("#")[0], name),
                        "focal_lane_position_m": round(traci.vehicle.getLanePosition(focal_id), 2),
                        "focal_speed_mps": round(traci.vehicle.getSpeed(focal_id), 2),
                        "active_vehicles": len(active),
                        "queued_on_primary_only": sum(traci.edge.getLastStepHaltingNumber(edge)
                                                       for edge in route_data["exclusive_primary"]),
                        "estimated_primary_remaining_s": round(estimate_primary, 2),
                        "estimated_alternative_remaining_s": round(estimate_alternative, 2),
                        "gps_prefers_alternative_by_5_percent": estimate_alternative < .95 * estimate_primary,
                        "gps_path_is_recorded_alternative": gps_route == alternative_remaining,
                        "state_sha256_16": hashlib.sha256(json.dumps(state).encode()).hexdigest()[:16],
                    }
                    if choice == "divert":
                        traci.vehicle.setRoute(focal_id, alternative_remaining)
                        sim.vehicles[focal_id]["route"] = list(alternative_remaining)
            if next_trip == len(schedule) and not active and not traci.simulation.getPendingVehicles():
                break
    finally:
        sim.stop()
        store.db.close()
    if decision is None:
        raise RuntimeError(f"Focal vehicle never reached decision edge in {key}")
    tripinfo = {entry.attrib["id"]: entry.attrib for entry in ET.parse(tripinfo_path).getroot().findall("tripinfo")}
    if len(tripinfo) != len(schedule) or focal_id not in tripinfo:
        raise RuntimeError(f"Incomplete SUMO output in {key}: {len(tripinfo)}/{len(schedule)}")
    focal = tripinfo[focal_id]
    exclusive = route_data["exclusive_alternative" if choice == "divert" else "exclusive_primary"]
    if not any(edge in traversed for edge in exclusive):
        raise RuntimeError(f"Focal did not physically traverse selected branch in {key}: {traversed}")
    door_times = [float(info["arrival"]) - planned_by_id[car_id] for car_id, info in tripinfo.items()]
    result = {
        "key": key, "corridor": corridor, "corridor_name": name, "level": level,
        "vehicles": len(schedule), "seed": seed, "choice": choice,
        "network_sha256_16": route_data["network_sha256_16"],
        "decision": decision,
        "focal": {
            "planned_depart_s": planned_by_id[focal_id],
            "actual_depart_s": float(focal["depart"]),
            "arrival_s": float(focal["arrival"]),
            "from_decision_to_arrival_s": round(float(focal["arrival"]) - decision["time_s"], 2),
            "door_to_door_s": round(float(focal["arrival"]) - planned_by_id[focal_id], 2),
            "travel_s": float(focal["duration"]),
            "waiting_s": float(focal["waitingTime"]),
            "distance_m": float(focal["routeLength"]),
            "physically_traversed_edges": traversed,
        },
        "collective_mean_door_to_door_s": round(statistics.mean(door_times), 2),
        "completed": len(tripinfo),
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "research" / "estudo-escolha-no-transito")
    parser.add_argument("--corridors", nargs="+", choices=CORRIDORS, default=list(CORRIDORS))
    parser.add_argument("--levels", nargs="+", choices=LEVELS, default=list(LEVELS))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(SEEDS))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for corridor in args.corridors:
        for level in args.levels:
            for seed in args.seeds:
                pair = [run_one(output, corridor, level, seed, choice) for choice in ("stay", "divert")]
                stay, divert = pair
                if stay["decision"]["state_sha256_16"] != divert["decision"]["state_sha256_16"]:
                    raise RuntimeError(f"Paired states differed before decision: {corridor}/{level}/{seed}")
                row = {
                    "corridor": corridor, "level": level, "vehicles": stay["vehicles"], "seed": seed,
                    "decision_time_s": stay["decision"]["time_s"],
                    "queue_ahead": stay["decision"]["queued_on_primary_only"],
                    "gps_estimate_stay_s": stay["decision"]["estimated_primary_remaining_s"],
                    "gps_estimate_divert_s": stay["decision"]["estimated_alternative_remaining_s"],
                    "gps_prefers_divert": stay["decision"]["gps_prefers_alternative_by_5_percent"],
                    "gps_path_matches_alternative": stay["decision"]["gps_path_is_recorded_alternative"],
                    "stay_remaining_s": stay["focal"]["from_decision_to_arrival_s"],
                    "divert_remaining_s": divert["focal"]["from_decision_to_arrival_s"],
                    "divert_minus_stay_s": round(divert["focal"]["from_decision_to_arrival_s"] -
                                                 stay["focal"]["from_decision_to_arrival_s"], 2),
                    "stay_collective_mean_s": stay["collective_mean_door_to_door_s"],
                    "divert_collective_mean_s": divert["collective_mean_door_to_door_s"],
                    "pair_state_sha256_16": stay["decision"]["state_sha256_16"],
                }
                rows.append(row)
                print(f"{corridor}/{level}/{seed}: GPS {row['gps_estimate_stay_s']} vs "
                      f"{row['gps_estimate_divert_s']} s; actual stay {row['stay_remaining_s']} "
                      f"vs divert {row['divert_remaining_s']} s", flush=True)
    with (output / "paired.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for corridor in args.corridors:
        for level in args.levels:
            group = [row for row in rows if row["corridor"] == corridor and row["level"] == level]
            summary.append({
                "corridor": corridor, "level": level, "vehicles": group[0]["vehicles"],
                "seeds": len(group), "mean_queue_ahead": round(statistics.mean(row["queue_ahead"] for row in group), 2),
                "gps_recommended_divert_count": sum(row["gps_prefers_divert"] for row in group),
                "mean_stay_remaining_s": round(statistics.mean(row["stay_remaining_s"] for row in group), 2),
                "mean_divert_remaining_s": round(statistics.mean(row["divert_remaining_s"] for row in group), 2),
                "mean_divert_minus_stay_s": round(statistics.mean(row["divert_minus_stay_s"] for row in group), 2),
            })
    first_run = json.loads((output / f"{args.corridors[0]}__{args.levels[0]}__{args.seeds[0]}__stay.json").read_text(encoding="utf-8"))
    (output / "summary.json").write_text(json.dumps({"design": {
        "network_sha256_16": first_run["network_sha256_16"],
        "step_seconds": STEP_SECONDS, "departure_window_seconds": DEPARTURE_WINDOW,
        "background_policy": "all vehicles initially follow main route; focal changes only at shared approach edge",
        "focal_demand_index": FOCAL_INDEX,
        "weather": "sun", "teleport": "disabled", "max_sim_time_s": MAX_TIME,
        "limitations": "synthetic single-OD demand; route choice tested at one approach edge; three seeds"},
        "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
