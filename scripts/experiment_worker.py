"""Executado em outro processo para não perturbar o TraCI do jogo visual."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import traci  # noqa: E402

from backend.engine import Simulator, STEP_SECONDS  # noqa: E402
from backend.experiment_analysis import confidence_interval, interpret, mean, summarize  # noqa: E402
from backend.storage import Storage  # noqa: E402


def write_json(path: Path, value: dict):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    # On Windows, a brief concurrent read of status.json can prevent the
    # atomic replacement. Keep the old complete file visible and retry.
    for attempt in range(20):
        try:
            temp.replace(path)
            return
        except PermissionError as exc:
            if os.name != "nt" or exc.winerror not in (5, 32) or attempt == 19:
                raise
            time.sleep(0.01 * (attempt + 1))


def run_variant(job_dir: Path, config: dict, variant: dict, repetition: int,
                progress_callback) -> dict:
    parameters = variant["parameters"]
    scenario_id = parameters.get("network_scenario_id", config["source_network_scenario_id"])
    city_id = config.get("source_city_id")
    city_dir = ROOT / "data" / "cities" / city_id if city_id else ROOT / "data"
    data_dir = city_dir / "scenarios" / scenario_id if scenario_id else city_dir
    net_path = data_dir / ("network.net.xml" if scenario_id or city_id else "blumenau.net.xml")
    network_version = hashlib.sha256(net_path.read_bytes()).hexdigest()[:16]
    run_key = f"{variant['key']}-r{repetition + 1}"
    store = Storage(str(job_dir / f"{run_key}.sqlite3"))
    sim = Simulator(str(data_dir), store)
    sim.net_path = net_path
    demand = config["demand"][repetition][:parameters.get("vehicle_limit", config["vehicles"])]
    requested = []
    spawned: dict[int, dict] = {}
    unserved: set[int] = set()
    road_samples = []
    frame_path = job_dir / f"{run_key}.ndjson"
    try:
        sim.start(config["seed"] + repetition, config["start_hour"])
        sim.network_version = network_version
        sim.gps_interval = config["gps_interval"]
        # Mapear as mesmas coordenadas antes de aplicar a intervenção.
        for trip in demand:
            try:
                origin = sim.nearest_road(*trip["origin_coordinates"])
                destination = sim.nearest_road(*trip["destination_coordinates"])
                requested.append({**trip, "origin": origin, "destination": destination})
            except ValueError:
                unserved.add(trip["id"])
        requested.sort(key=lambda item: (item["departed"], item["id"]))
        weather = parameters.get("weather", "sun")
        if weather != "sun":
            sim.set_weather(weather)
        light_duration = parameters.get("light_duration_s")
        if light_duration is not None and config.get("tls_id"):
            original = sim.tls_original[config["tls_id"]][0].phases[config["phase"]].duration
            if abs(light_duration - original) > 1e-6:
                sim.traffic_light(config["tls_id"], config["phase"], light_duration)
        action = parameters.get("road_action", "none")
        if action != "none" and config.get("road_id"):
            sim.road_action(config["road_id"], action, 20 if action == "slow" else None)
        next_trip = 0
        next_capture = 0.0
        wall_start = time.perf_counter()
        with frame_path.open("w", encoding="utf-8") as frames:
            while traci.simulation.getTime() < config["duration_s"]:
                now = traci.simulation.getTime()
                while next_trip < len(requested) and requested[next_trip]["departed"] <= now + STEP_SECONDS:
                    trip = requested[next_trip]
                    next_trip += 1
                    if trip["id"] in unserved:
                        continue
                    origin = trip["origin"]["edge_id"]
                    destination = trip["destination"]["edge_id"]
                    path = sim.route(origin, destination)
                    strategy = parameters.get("gps_strategy", "dynamic")
                    created = sim.spawn_trip(origin, destination, strategy, path,
                        origin_pos=trip["origin"]["position"], destination_pos=trip["destination"]["position"])
                    if created:
                        info = sim.vehicles[f"car-{sim.run_id}-{sim.next_vehicle_id}"]
                        info["demand_id"] = trip["id"]
                        info["planned_departed"] = trip["departed"]
                        spawned[trip["id"]] = info
                    else:
                        unserved.add(trip["id"])
                sim.step()
                now = traci.simulation.getTime()
                if now + 1e-6 >= next_capture:
                    state = sim.snapshot()
                    cars = [{"id": car["id"], "coordinates": car["coordinates"], "angle": car["angle"],
                             "color": car["color"], "state": car["state"], "speed": round(car["speed"], 2)}
                            for car in state["vehicles"]]
                    lights = [{"id": light["id"], "coordinates": light["coordinates"], "aspect": light["aspect"]}
                              for light in state["lights"]]
                    frame = {"time": now, "vehicles": cars, "lights": lights, "active": state["active"],
                             "completed": state["completed"], "mean_speed": state["sample"].get("mean_speed", 0)}
                    frames.write(json.dumps(frame, ensure_ascii=False) + "\n")
                    frames.flush()
                    roads = []
                    for edge_id in sim.edges:
                        count = traci.edge.getLastStepVehicleNumber(edge_id)
                        if count:
                            roads.append({"id": edge_id, "count": count,
                                          "name": sim.edges[edge_id].getName() or sim.osm_names.get(edge_id.lstrip("-").split("#")[0], "Via sem nome"),
                                          "speed_mps": round(traci.edge.getLastStepMeanSpeed(edge_id), 2),
                                          "queue": traci.edge.getLastStepHaltingNumber(edge_id),
                                          "waiting_s": round(traci.edge.getWaitingTime(edge_id), 2),
                                          "travel_time_s": round(traci.edge.getTraveltime(edge_id), 2)})
                    road_samples.append({"time": now, "roads": roads})
                    next_capture += config["snapshot_interval_s"]
                    progress_callback(run_key, now / config["duration_s"], frame)
                if next_trip == len(requested) and not traci.vehicle.getIDList() and now > config["departure_window_s"]:
                    break
                if config["mode"] == "visual":
                    target = now / config["visual_speed"]
                    delay = target - (time.perf_counter() - wall_start)
                    if delay > 0:
                        time.sleep(min(delay, .25))
        end_time = traci.simulation.getTime()
        records = []
        for trip in demand:
            info = spawned.get(trip["id"])
            completed = bool(info and info["state"] == "arrived")
            records.append({"demand_id": trip["id"], "vehicle_id": info["id"] if info else None,
                            "origin": trip["origin_edge"], "destination": trip["destination_edge"],
                            "origin_coordinates": trip["origin_coordinates"],
                            "destination_coordinates": trip["destination_coordinates"],
                            "planned_departed_s": trip["departed"],
                            "departed_s": info["departed"] if info else None,
                            "arrived_s": info.get("arrived") if info else None,
                            "completed": completed, "status": "concluída" if completed else "não iniciada" if not info else "em curso no limite",
                            "travel_time_s": round(info["travel_time"] if completed else end_time - info["departed"], 2) if info else 0,
                            "distance_m": round(info["distance"], 2) if info else 0,
                            "waiting_time_s": round(info["waiting_time"], 2) if info else 0,
                            "mean_speed_mps": round(info["distance"] / max(info.get("travel_time", end_time - info["departed"]), 1), 2) if info else 0,
                            "reroutes": info["reroutes"] if info else 0,
                            "initial_route": info.get("initial_route", []) if info else [],
                            "final_route": info.get("route", []) if info else [],
                            "route_history": info.get("route_history", []) if info else [],
                            "forecast_error_s": info.get("forecast_error_s") if info else None,
                            "origin_neighborhood": info.get("origin_neighborhood") if info else None,
                            "destination_neighborhood": info.get("destination_neighborhood") if info else None})
        summary = summarize(records, road_samples, end_time)
        if scenario_id:
            manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
            new_way_ids = {str(road["id"]) for road in manifest.get("roads", [])}
            summary["fictional_road_vehicles"] = sum(any(edge.lstrip("-").split("#")[0] in new_way_ids
                for edge in record["final_route"]) for record in records)
        demand_hash = hashlib.sha256(json.dumps(demand, sort_keys=True).encode()).hexdigest()[:16]
        return {"id": run_key, "variant": variant["key"], "variant_label": variant["label"],
                "repetition": repetition + 1, "seed": config["seed"] + repetition,
                "network_version": network_version, "demand_hash": demand_hash,
                "parameters": parameters, "summary": summary, "vehicles": records,
                "road_samples": road_samples, "frames_file": frame_path.name,
                "limitations": config["limitations"]}
    finally:
        sim.stop()


def main(job_dir: Path):
    config = json.loads((job_dir / "config.json").read_text(encoding="utf-8"))
    status_path = job_dir / "status.json"
    runs = []
    total = len(config["variants"]) * config["repetitions"]
    try:
        for variant in config["variants"]:
            for repetition in range(config["repetitions"]):
                done = len(runs)
                def progress(run_key, fraction, frame):
                    write_json(status_path, {"state": "running", "run": run_key,
                        "progress": round((done + fraction) / total, 4), "sim_time": frame["time"],
                        "active": frame["active"], "completed": frame["completed"]})
                progress(f"{variant['key']}-r{repetition + 1}", 0, {"time": 0, "active": 0, "completed": 0})
                runs.append(run_variant(job_dir, config, variant, repetition, progress))
        aggregates = {}
        for variant in config["variants"]:
            group = [item for item in runs if item["variant"] == variant["key"]]
            values = [item["summary"]["mean_travel_s"] for item in group if item["summary"]["mean_travel_s"] is not None]
            aggregates[variant["key"]] = {"label": variant["label"], "mean_travel_s": mean(values),
                "confidence_interval_95": confidence_interval(values),
                "mean_completion_rate": mean([item["summary"]["completion_rate"] for item in group]),
                "mean_waiting_s": mean([item["summary"]["mean_waiting_s"] for item in group if item["summary"]["mean_waiting_s"] is not None])}
        write_json(job_dir / "results.json", {"runs": runs, "aggregates": aggregates,
            "interpretation": interpret(config, runs, aggregates),
            "limitations": config["limitations"]})
        write_json(status_path, {"state": "complete", "progress": 1, "runs": total})
    except Exception as exc:
        traceback.print_exc()
        write_json(status_path, {"state": "error", "progress": len(runs) / total,
                                "error": str(exc)})


if __name__ == "__main__":
    main(Path(sys.argv[1]))
