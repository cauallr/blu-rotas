"""Previsões derivadas da rota física do SUMO, sem avançar a simulação."""
from __future__ import annotations

import math


def remaining_route_metrics(route: list[str], route_index: int, road: str,
                            lane_position: float, lengths: dict[str, float],
                            costs: dict[str, float]) -> tuple[float, float]:
    """Return remaining metres and seconds from the current road position."""
    if not route:
        return 0.0, 0.0
    start = max(route_index, 0)
    if road.startswith(":"):
        start += 1
    remaining = route[start:]
    metres = 0.0
    seconds = 0.0
    for offset, edge_id in enumerate(remaining):
        length = lengths.get(edge_id, 0.0)
        fraction = 1.0
        if offset == 0 and edge_id == road and length > 0:
            fraction = max(0.0, min(1.0, (length - lane_position) / length))
        metres += length * fraction
        edge_seconds = costs.get(edge_id, math.inf)
        if math.isfinite(edge_seconds):
            seconds += edge_seconds * fraction
    return round(metres, 1), round(seconds, 1)


def city_hour(start_hour: float, sim_seconds: float) -> float:
    return (start_hour + sim_seconds / 3600) % 24
