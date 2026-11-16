"""SQLite para viagens, amostras, intervenções e cenários reproduzíveis."""
import json
import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS scenarios (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, scenario_id INTEGER, seed INTEGER NOT NULL,
          started_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS trips (
          id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, vehicle_id TEXT NOT NULL,
          origin TEXT, destination TEXT, departed REAL, arrived REAL,
          travel_time REAL, waiting_time REAL, distance REAL, reroutes INTEGER,
          strategy TEXT, forecast_error_s REAL, predicted_arrival_sim_time REAL,
          initial_predicted_arrival_sim_time REAL, route_history TEXT);
        CREATE TABLE IF NOT EXISTS samples (
          id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, sim_time REAL NOT NULL,
          active INTEGER, completed INTEGER, mean_speed REAL, mean_wait REAL,
          mean_travel REAL, reroutes INTEGER, algorithm_ms REAL);
        CREATE TABLE IF NOT EXISTS interventions (
          id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, sim_time REAL,
          kind TEXT, target TEXT, parameters TEXT, affected INTEGER);
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(trips)")}
        for column in ("origin_neighborhood", "destination_neighborhood", "route_history"):
            if column not in columns:
                self.db.execute(f"ALTER TABLE trips ADD COLUMN {column} TEXT")
        for column in ("forecast_error_s", "predicted_arrival_sim_time", "initial_predicted_arrival_sim_time"):
            if column not in columns:
                self.db.execute(f"ALTER TABLE trips ADD COLUMN {column} REAL")
        self.db.commit()

    def new_run(self, seed: int, scenario_id: int | None = None) -> int:
        cursor = self.db.execute("INSERT INTO runs(scenario_id,seed) VALUES (?,?)", (scenario_id, seed))
        self.db.commit()
        return cursor.lastrowid

    def save_scenario(self, name: str, config: dict) -> int:
        cursor = self.db.execute("INSERT INTO scenarios(name,config) VALUES (?,?)", (name, json.dumps(config)))
        self.db.commit()
        return cursor.lastrowid

    def scenarios(self) -> list[dict]:
        return [dict(row) | {"config": json.loads(row["config"])} for row in
                self.db.execute("SELECT * FROM scenarios ORDER BY id DESC")]

    def add_trip(self, run_id: int, trip: dict) -> None:
        self.db.execute("""INSERT INTO trips
          (run_id,vehicle_id,origin,destination,departed,arrived,travel_time,
           waiting_time,distance,reroutes,strategy,origin_neighborhood,destination_neighborhood,
           forecast_error_s,predicted_arrival_sim_time,initial_predicted_arrival_sim_time,route_history)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (run_id, trip["id"], trip["origin"], trip["destination"], trip["departed"],
           trip["arrived"], trip["travel_time"], trip["waiting_time"],
           trip["distance"], trip["reroutes"], trip["strategy"],
           trip.get("origin_neighborhood"), trip.get("destination_neighborhood"),
           trip.get("forecast_error_s"), trip.get("predicted_arrival_sim_time"),
           trip.get("initial_predicted_arrival_sim_time"), json.dumps(trip.get("route_history", []))))
        self.db.commit()

    def add_sample(self, run_id: int, sample: dict) -> None:
        self.db.execute("""INSERT INTO samples
          (run_id,sim_time,active,completed,mean_speed,mean_wait,mean_travel,reroutes,algorithm_ms)
          VALUES (?,?,?,?,?,?,?,?,?)""",
          (run_id, *[sample[key] for key in ("sim_time", "active", "completed",
          "mean_speed", "mean_wait", "mean_travel", "reroutes", "algorithm_ms")]))
        self.db.commit()

    def add_intervention(self, run_id: int, time: float, kind: str, target: str,
                         parameters: dict, affected: int) -> None:
        self.db.execute("INSERT INTO interventions(run_id,sim_time,kind,target,parameters,affected) VALUES (?,?,?,?,?,?)",
                        (run_id, time, kind, target, json.dumps(parameters), affected))
        self.db.commit()

    def metrics(self, run_id: int) -> dict:
        samples = [dict(row) for row in self.db.execute(
            "SELECT * FROM samples WHERE run_id=? ORDER BY sim_time", (run_id,))]
        trips = [dict(row) for row in self.db.execute(
            "SELECT * FROM trips WHERE run_id=? ORDER BY arrived", (run_id,))]
        interventions = [dict(row) for row in self.db.execute(
            "SELECT * FROM interventions WHERE run_id=? ORDER BY sim_time", (run_id,))]
        return {"samples": samples, "trips": trips, "interventions": interventions}
