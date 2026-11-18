"""Compare paired SUMO runs for five route-allocation fractions in Castelo Branco."""
from __future__ import annotations

import csv
import json
import math
import statistics
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research" / "estudo-castelo-branco"
SWEEP = ROOT / "research" / "estudo-proporcoes-castelo"
SEEDS = (20261114, 20261115, 20261116)
STRATEGIES = {0: "principal", 25: "um_quarto", 50: "dividido",
              75: "tres_quartos", 100: "todos_desvio"}
METRICS = ("mean_travel_s", "mean_door_to_door_s", "mean_depart_delay_s",
           "p95_travel_s", "mean_time_loss_s", "mean_waiting_s",
           "peak_queue_primary", "peak_queue_alternative", "peak_pending_insertion")
T_CRITICAL_DF2 = 4.302652729911275


def paired_interval(values: list[float]) -> tuple[float, float, float]:
    assert len(values) == 3
    center = statistics.mean(values)
    margin = T_CRITICAL_DF2 * statistics.stdev(values) / math.sqrt(3)
    return round(center, 2), round(center - margin, 2), round(center + margin, 2)


def load_runs() -> dict[int, list[dict]]:
    original = json.loads((BASE / "routes.json").read_text(encoding="utf-8"))
    additional = json.loads((SWEEP / "routes.json").read_text(encoding="utf-8"))
    for key in ("network_sha256_16", "primary", "alternative"):
        assert original[key] == additional[key], f"Rede ou rota diferente: {key}"
    groups = {}
    for percent, strategy in STRATEGIES.items():
        folder = SWEEP if percent in (25, 75) else BASE
        runs = [json.loads((folder / "runs" / f"alto__{strategy}__{seed}.json").read_text(encoding="utf-8"))
                for seed in SEEDS]
        for seed, run in zip(SEEDS, runs):
            assert run["seed"] == seed and run["requested"] == 180
            assert run["network_sha256_16"] == original["network_sha256_16"]
            assert run["summary"]["completed"] == 180 and not run["summary"]["unfinished"]
            assert sum(vehicle["assigned_route"] == "alternative" for vehicle in run["vehicles"]) == 180 * percent // 100
        groups[percent] = runs
    for index, seed in enumerate(SEEDS):
        reference = {vehicle["demand_index"]: vehicle["planned_depart_s"]
                     for vehicle in groups[0][index]["vehicles"]}
        for runs in groups.values():
            assert {vehicle["demand_index"]: vehicle["planned_depart_s"]
                    for vehicle in runs[index]["vehicles"]} == reference, f"Partidas diferentes: {seed}"
    return groups


def make_chart(rows: list[dict]) -> str:
    width, height = 1050, 570
    left, right, top, bottom = 90, 985, 100, 455
    min_y, max_y = 180, 420
    x = lambda percent: left + (right - left) * percent / 100
    y = lambda seconds: bottom - (seconds - min_y) * (bottom - top) / (max_y - min_y)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<style>text{font-family:Arial,sans-serif;fill:#203239}.title{font-size:23px;font-weight:bold}.small{font-size:13px;fill:#52636b}.tick{font-size:12px;fill:#52636b}.value{font-size:13px;font-weight:bold}</style>',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="55" y="42" class="title">Quanto tráfego enviar pela rota alternativa?</text>',
             '<text x="55" y="68" class="small">Avenida Presidente Castelo Branco · 180 veículos em 240 s · 3 sementes pareadas · SUMO 1.28</text>']
    for seconds in range(200, 421, 40):
        yy = y(seconds)
        parts += [f'<line x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#e8edef"/>',
                  f'<text x="{left-12}" y="{yy+4:.1f}" text-anchor="end" class="tick">{seconds}</text>']
    for row in rows:
        xx = x(row["alternative_percent"])
        parts += [f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{top}" y2="{bottom}" stroke="#eef2f3"/>',
                  f'<text x="{xx:.1f}" y="{bottom+26}" text-anchor="middle" class="tick">{row["alternative_percent"]}%</text>']
    parts += [f'<text x="{(left+right)/2:.1f}" y="{bottom+58}" text-anchor="middle" class="small">Veículos enviados pela alternativa</text>',
              f'<text transform="translate(27 {(top+bottom)/2}) rotate(-90)" text-anchor="middle" class="small">Tempo médio (segundos)</text>']
    for metric, color, label, offset in (("mean_travel_s", "#2563a8", "Dentro da rede", 23),
                                          ("mean_door_to_door_s", "#d3712c", "Desde a partida planejada", -17)):
        points = " ".join(f'{x(row["alternative_percent"]):.1f},{y(row[metric]):.1f}' for row in rows)
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round"/>')
        for row in rows:
            xx, yy = x(row["alternative_percent"]), y(row[metric])
            parts += [f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="6" fill="{color}" stroke="white" stroke-width="2"/>',
                      f'<text x="{xx:.1f}" y="{yy+offset:.1f}" text-anchor="middle" class="value" fill="{color}">{row[metric]:.1f}</text>']
        legend_x = 625 if metric == "mean_travel_s" else 790
        parts += [f'<line x1="{legend_x}" x2="{legend_x+28}" y1="90" y2="90" stroke="{color}" stroke-width="4"/>',
                  f'<text x="{legend_x+35}" y="94" class="small">{escape(label)}</text>']
    parts += ['<text x="55" y="543" class="small">Médias de execuções; dados sintéticos do recorte OSM. Compare intervalos pareados no CSV e no relatório.</text>', '</svg>']
    return "\n".join(parts)


def main() -> None:
    groups = load_runs()
    rows = []
    for percent, runs in groups.items():
        row = {"alternative_percent": percent, "repetitions": len(runs),
               "requested_total": sum(run["requested"] for run in runs),
               "completed_total": sum(run["summary"]["completed"] for run in runs)}
        row.update({metric: round(statistics.mean(run["summary"][metric] for run in runs), 2)
                    for metric in METRICS})
        for reference, prefix in ((0, "vs_0"), (50, "vs_50")):
            for metric, short in (("mean_travel_s", "travel"), ("mean_door_to_door_s", "door")):
                differences = [run["summary"][metric] - base["summary"][metric]
                               for run, base in zip(runs, groups[reference])]
                mean, low, high = paired_interval(differences)
                row.update({f"{prefix}_{short}_difference_s": mean,
                            f"{prefix}_{short}_ci95_low_s": low,
                            f"{prefix}_{short}_ci95_high_s": high})
        rows.append(row)
    with (SWEEP / "proporcoes.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (SWEEP / "proporcoes.svg").write_text(make_chart(rows), encoding="utf-8")
    print("Percentual | Tempo na rede | Porta a porta | Atraso para entrar | P95")
    for row in rows:
        print(f'{row["alternative_percent"]:>3}% | {row["mean_travel_s"]:>6.2f} | '
              f'{row["mean_door_to_door_s"]:>6.2f} | {row["mean_depart_delay_s"]:>6.2f} | '
              f'{row["p95_travel_s"]:>6.2f}')


if __name__ == "__main__":
    main()
