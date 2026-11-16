"""Pontos de acesso persistentes associados à rede física ativa."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


class AccessPoints:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def for_sim(self, sim) -> list[dict]:
        """Reassocia os pontos à versão ativa da rede, sem mover o cadastro salvo."""
        active = []
        for point in self.list():
            if point.get("city_id") != sim.city_id:
                continue
            way_id = point.get("edge_id", "").lstrip("-").split("#")[0]
            try:
                try:
                    snapped = sim.nearest_road(*point["coordinates"], allowed_way_ids={way_id})
                except ValueError:
                    snapped = sim.nearest_road(*point["coordinates"])
            except ValueError:
                continue
            active.append({**point, "edge_id": snapped["edge_id"],
                           "position": snapped["position"], "coordinates": snapped["coordinates"]})
        return active

    def add(self, sim, coordinates: tuple[float, float], name: str) -> dict:
        snapped = sim.nearest_road(*coordinates)
        point = {"id": uuid4().hex[:12], "name": name.strip() or snapped["name"],
                 "kind": "acesso", "network": sim.net_path.name, "city_id": sim.city_id,
                 "coordinates": snapped["coordinates"], "edge_id": snapped["edge_id"],
                 "position": snapped["position"], "distance_m": snapped["distance_m"]}
        points = self.list()
        points.append(point)
        self._save(points)
        return point

    def remove(self, point_id: str) -> bool:
        points = self.list()
        kept = [point for point in points if point["id"] != point_id]
        if len(kept) == len(points):
            return False
        self._save(kept)
        return True

    def _save(self, points: list[dict]):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(points, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
