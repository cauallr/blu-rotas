"""Indicadores e comparações descritivas de execuções físicas do SUMO."""
from __future__ import annotations

import math
import statistics as stats
from collections import Counter


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * percent / 100
    low, high = math.floor(position), math.ceil(position)
    return round(values[low] + (values[high] - values[low]) * (position - low), 2)


def mean(values: list[float]) -> float | None:
    return round(stats.mean(values), 2) if values else None


def summarize(vehicles: list[dict], road_samples: list[dict], duration_s: float) -> dict:
    finished = [item for item in vehicles if item["completed"]]
    travel = [item["travel_time_s"] for item in finished]
    waits = [item["waiting_time_s"] for item in vehicles]
    distances = [item["distance_m"] for item in vehicles]
    speeds = [item["distance_m"] / item["travel_time_s"] for item in finished if item["travel_time_s"] > 0]
    by_neighborhood: dict[str, dict] = {}
    route_counts = Counter(tuple(item.get("final_route") or []) for item in vehicles if item.get("final_route"))
    for item in vehicles:
        group = by_neighborhood.setdefault(item.get("origin_neighborhood") or "Não informado",
                                           {"requested": 0, "completed": 0, "times": []})
        group["requested"] += 1
        if item["completed"]:
            group["completed"] += 1
            group["times"].append(item["travel_time_s"])
    road_count: dict[str, dict] = {}
    for sample in road_samples:
        for road in sample["roads"]:
            aggregate = road_count.setdefault(road["id"], {"name": road.get("name") or road["id"], "observations": 0, "vehicles_sum": 0,
                "speed_sum": 0.0, "queue_sum": 0, "wait_sum": 0.0, "travel_time_sum": 0.0})
            aggregate["observations"] += 1
            aggregate["vehicles_sum"] += road["count"]
            aggregate["speed_sum"] += road["speed_mps"]
            aggregate["queue_sum"] += road["queue"]
            aggregate["wait_sum"] += road["waiting_s"]
            aggregate["travel_time_sum"] += road["travel_time_s"]
    roads = {road_id: {"name": value["name"], "mean_vehicles": round(value["vehicles_sum"] / value["observations"], 2),
                       "mean_speed_mps": round(value["speed_sum"] / value["observations"], 2),
                       "mean_queue": round(value["queue_sum"] / value["observations"], 2),
                       "mean_waiting_s": round(value["wait_sum"] / value["observations"], 2),
                       "mean_traversal_s": round(value["travel_time_sum"] / value["observations"], 2)}
             for road_id, value in road_count.items()}
    total = len(vehicles)
    return {"vehicles": total, "completed": len(finished), "unfinished": total - len(finished),
            "completion_rate": round(len(finished) / total, 4) if total else 0,
            "mean_travel_s": mean(travel), "median_travel_s": percentile(travel, 50),
            "p95_travel_s": percentile(travel, 95),
            "std_travel_s": round(stats.stdev(travel), 2) if len(travel) > 1 else None,
            "total_travel_s": round(sum(travel), 2),
            "mean_waiting_s": mean(waits), "total_waiting_s": round(sum(waits), 2),
            "mean_distance_m": mean(distances), "mean_speed_mps": mean(speeds),
            "reroutes": sum(item["reroutes"] for item in vehicles),
            "fictional_road_vehicles": 0,
            "route_distribution": [{"route": list(route), "vehicles": count}
                                   for route, count in route_counts.most_common(10)],
            "mean_queue": mean([road["queue"] for sample in road_samples for road in sample["roads"]]),
            "congested_road_observations": sum(road["count"] > 0 and road["speed_mps"] < 2
                                              for sample in road_samples for road in sample["roads"]),
            "duration_s": duration_s, "roads": roads,
            "by_neighborhood": {name: {"requested": value["requested"],
                                       "completed": value["completed"],
                                       "unfinished": value["requested"] - value["completed"],
                                       "mean_travel_s": mean(value["times"])}
                                for name, value in by_neighborhood.items()}}


def interpret(config: dict, runs: list[dict], aggregates: dict[str, dict]) -> str:
    """Descreve métricas observadas sem pressupor que uma hipótese foi confirmada."""
    kind = config["kind"]
    parts = ["Resultados do cenário simulado; a interpretação causal cabe aos estudantes."]
    if kind == "saturation":
        points = [(int(variant["parameters"]["vehicle_limit"]), aggregates[variant["key"]]["mean_travel_s"])
                  for variant in config["variants"]]
        observed = [(count, value) for count, value in points if value is not None]
        if len(observed) >= 2:
            slopes = [(round((right[1] - left[1]) / (right[0] - left[0]), 2), left[0], right[0])
                      for left, right in zip(observed, observed[1:])]
            steepest = max(slopes, key=lambda item: item[0])
            parts.append(f"Maior crescimento observado do tempo médio por veículo adicional entre "
                         f"{steepest[1]} e {steepest[2]} veículos: {steepest[0]} s/veículo.")
        else:
            parts.append("Não houve conclusões suficientes para estimar a inclinação do atraso.")
        parts.append("Os grupos têm composição de viagens diferente; compare também a taxa de conclusão.")
    elif kind == "new_road":
        base = [item["summary"] for item in runs if item["variant"] == "base"]
        changed = [item["summary"] for item in runs if item["variant"] == "new"]
        if base and changed:
            parts.append(f"Rede original: {sum(item['completed'] for item in base)}/{sum(item['vehicles'] for item in base)} viagens concluídas; "
                         f"rede nova: {sum(item['completed'] for item in changed)}/{sum(item['vehicles'] for item in changed)}.")
            parts.append(f"{sum(item.get('fictional_road_vehicles', 0) for item in changed)} veículos receberam rota "
                         "que usa a conexão fictícia.")
            left, right = aggregates["base"]["mean_travel_s"], aggregates["new"]["mean_travel_s"]
            if left is not None and right is not None:
                delta = round(right - left, 2)
                parts.append(f"Diferença observada da média das viagens concluídas: {delta:+.2f} s.")
            parts.append("O paradoxo de Braess não é presumido; examine rotas e conclusões antes de discutir sua ocorrência.")
    else:
        labels = [(variant["label"], aggregates[variant["key"]]["mean_travel_s"])
                  for variant in config["variants"]]
        observed = [(label, value) for label, value in labels if value is not None]
        if len(observed) >= 2:
            fastest = min(observed, key=lambda item: item[1])
            slowest = max(observed, key=lambda item: item[1])
            parts.append(f"Entre as viagens concluídas, menor média: {fastest[0]} ({fastest[1]} s); "
                         f"maior média: {slowest[0]} ({slowest[1]} s).")
        else:
            parts.append("Não houve conclusões suficientes para comparar médias de viagem.")
    return " ".join(parts)


def confidence_interval(values: list[float]) -> dict | None:
    if len(values) < 2:
        return None
    estimate = stats.mean(values)
    # Critérios t de Student bilaterais, 95%; aproximação normal para amostras grandes.
    critical = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
                6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
                11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
                16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
                21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
                26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045}.get(len(values) - 1, 1.96)
    margin = critical * stats.stdev(values) / math.sqrt(len(values))
    return {"mean": round(estimate, 2), "lower": round(estimate - margin, 2),
            "upper": round(estimate + margin, 2), "n": len(values), "confidence": 0.95}


def compare(a: dict, b: dict) -> dict:
    metrics = ["completion_rate", "mean_travel_s", "median_travel_s", "p95_travel_s",
               "mean_waiting_s", "mean_distance_m", "mean_speed_mps", "reroutes", "mean_queue"]
    values = {}
    for key in metrics:
        left, right = a["summary"].get(key), b["summary"].get(key)
        values[key] = {"a": left, "b": right,
                       "difference": round(right - left, 2) if left is not None and right is not None else None,
                       "percent": round((right - left) / left * 100, 2) if left not in (None, 0) and right is not None else None}
    controlled = a.get("demand_hash") == b.get("demand_hash") and a.get("seed") == b.get("seed")
    changed = [key for key in set(a.get("parameters", {})) | set(b.get("parameters", {}))
               if a.get("parameters", {}).get(key) != b.get("parameters", {}).get(key)]
    if a.get("network_version") != b.get("network_version") and "network_scenario_id" not in changed:
        changed.append("network_version")
    comparable = controlled and len(changed) == 1
    difference = values["mean_travel_s"]["difference"]
    if difference is None:
        interpretation = "Uma execução não concluiu viagens suficientes para comparar tempos médios."
    else:
        interpretation = f"A média de B foi {abs(difference):.1f} s {'maior' if difference > 0 else 'menor' if difference < 0 else 'igual'} à de A."
    if not comparable:
        interpretation += " As condições diferem em mais de uma variável ou a demanda/rede não é pareada; não se atribui causalidade."
    roads_a, roads_b = a["summary"].get("roads", {}), b["summary"].get("roads", {})
    road_impacts = []
    if a.get("network_version") == b.get("network_version"):
        for road_id in roads_a.keys() | roads_b.keys():
            left, right = roads_a.get(road_id, {}), roads_b.get(road_id, {})
            queue_a, queue_b = left.get("mean_queue", 0), right.get("mean_queue", 0)
            road_impacts.append({"id": road_id, "name": right.get("name") or left.get("name") or road_id,
                                 "queue_a": queue_a, "queue_b": queue_b,
                                 "queue_difference": round(queue_b - queue_a, 2),
                                 "vehicles_a": left.get("mean_vehicles", 0),
                                 "vehicles_b": right.get("mean_vehicles", 0)})
        road_impacts.sort(key=lambda item: abs(item["queue_difference"]), reverse=True)
    return {"metrics": values, "changed_parameters": changed,
            "same_demand": a.get("demand_hash") == b.get("demand_hash"),
            "same_network": a.get("network_version") == b.get("network_version"),
            "paired": controlled, "directly_comparable": comparable,
            "road_impacts": road_impacts[:8], "interpretation": interpretation}
