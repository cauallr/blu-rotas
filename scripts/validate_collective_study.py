"""Confere dados brutos, pareamento e artefatos do estudo de rotas."""
from __future__ import annotations

import json
import csv
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT.parent / "estudo-rotas-coletivas"
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
files = sorted((OUT / "runs").glob("*.json"))
runs = [json.loads(path.read_text(encoding="utf-8")) for path in files]
assert runs, "Nenhuma execução encontrada"
groups = defaultdict(dict)

for run in runs:
    key = (run["level"], run["seed"])
    assert run["strategy"] not in groups[key], f"Execução duplicada: {run['key']}"
    groups[key][run["strategy"]] = run
    cars = run["vehicles"]
    assert len(cars) == run["requested"], run["key"]
    assert len({car["demand_index"] for car in cars}) == len(cars), run["key"]
    assert sum(car["completed"] for car in cars) == run["summary"]["completed"], run["key"]
    assert run["summary"]["completed"] + run["summary"]["unfinished"] == len(cars), run["key"]
    tripinfo = OUT / "runs" / run["tripinfo_file"]
    trips = ET.parse(tripinfo).getroot().findall("tripinfo")
    assert len(trips) == run["summary"]["completed"], run["key"]
    for car in cars:
        if car["completed"]:
            assert car["travel_s"] > 0 and car["door_to_door_s"] >= car["travel_s"] - .3, run["key"]
            assert car["actual_depart_s"] >= car["planned_depart_s"] - .5, run["key"]
    alt = sum(car["assigned_route"] == "alternative" for car in cars)
    expected = {"principal": 0, "um_desvio": 1, "todos_desvio": len(cars),
                "dividido": len(cars)//2, "gps_dinamico": 0}[run["strategy"]]
    assert alt == expected, (run["key"], alt, expected)

for key, variants in groups.items():
    schedules = [[(car["demand_index"], car["planned_depart_s"])
                  for car in run["vehicles"]] for run in variants.values()]
    assert all(schedule == schedules[0] for schedule in schedules), f"Demanda não pareada: {key}"

for seed in summary["design"]["seeds"]:
    by_level = {level: {car["demand_index"]: car["planned_depart_s"]
                        for car in next(iter(groups[(level, seed)].values()))["vehicles"]}
                for level in summary["design"]["levels"]}
    assert all(set(by_level["baixo"]).issubset(by_level[level]) for level in ("medio", "alto"))
    assert set(by_level["medio"]).issubset(by_level["alto"])
    assert all(by_level["alto"][index] == departure for level in ("baixo", "medio")
               for index, departure in by_level[level].items())

rows = summary["aggregates"]
assert sum(row["repetitions"] for row in rows) == len(runs)
assert sum(row["requested_total"] for row in rows) == sum(run["requested"] for run in runs)
for name, expected in (("summary.csv", len(rows)),
                       ("run_summary.csv", len(runs)),
                       ("vehicles.csv", sum(run["requested"] for run in runs)),
                       ("occupancy.csv", sum(len(run["route_occupancy"]) for run in runs)),
                       ("roads.csv", sum(len(run["roads"]) for run in runs))):
    with (OUT / name).open(newline="", encoding="utf-8-sig") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == expected, name
for name in ("tempo-medio-demanda.svg", "tempo-total-demanda.svg",
             "tempo-perdido-demanda.svg", "mapas-calor-fluxo-alto.svg",
             "ocupacao-rotas-fluxo-alto.svg"):
    ET.parse(OUT / name)

print(f"VÁLIDO: {len(runs)} execuções, {sum(run['requested'] for run in runs)} viagens, "
      f"{sum(run['summary']['completed'] for run in runs)} concluídas, "
      f"{len(rows)} agregados, 5 gráficos SVG.")
