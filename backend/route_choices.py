"""Alternativas dirigíveis calculadas sobre o mesmo grafo e custos do GPS."""
from __future__ import annotations

from collections.abc import Callable


def alternatives(route_through: Callable[[list[str], dict[str, float]], list[str]],
                 checkpoints: list[str], costs: dict[str, float], lengths: dict[str, float],
                 limit: int = 3) -> list[dict]:
    best = route_through(checkpoints, costs)
    if not best:
        return []
    candidates: dict[tuple[str, ...], list[str]] = {tuple(best): best}
    # Penalizar blocos diferentes revela desvios legais sem fabricar viagens ou ciclos.
    portions = ((.15, .85), (0, .5), (.5, 1), (.3, .7), (0, 1))
    for factor in (1.5, 2.5, 4):
        for start, end in portions:
            target = best[max(1, int(len(best) * start)):max(2, int(len(best) * end))]
            if not target:
                continue
            adjusted = dict(costs)
            for edge_id in target:
                if edge_id in costs:
                    adjusted[edge_id] = costs[edge_id] * factor
            path = route_through(checkpoints, adjusted)
            if path and len(path) <= 250:
                candidates[tuple(path)] = path
            if len(candidates) >= 12:
                break
        if len(candidates) >= 12:
            break

    def metrics(path: list[str]) -> tuple[float, float]:
        return (sum(costs[edge_id] for edge_id in path if edge_id in costs),
                sum(lengths[edge_id] for edge_id in path if edge_id in lengths))

    ranked = sorted(((metrics(path), path) for path in candidates.values()), key=lambda item: item[0][0])
    best_seconds = ranked[0][0][0]
    reasonable = [item for item in ranked if item[0][0] <= max(best_seconds * 3, best_seconds + 90)]
    chosen = reasonable[:1]
    if len(reasonable) > 1:
        chosen.append(reasonable[1])
    if limit >= 3 and len(reasonable) > 2:
        chosen.append(reasonable[-1])
    labels = (("best", "Melhor rota"), ("secondary", "Rota secundária"),
              ("longer", "Mais demorada entre as encontradas"))
    return [{"key": key, "label": label, "route": path,
             "seconds": round(measure[0], 1), "distance_m": round(measure[1], 1),
             "segments": len(path)}
            for (key, label), (measure, path) in zip(labels, chosen)]
