"""Visão cartográfica fiel ao grafo de roteamento (vértices = arestas SUMO)."""
from __future__ import annotations


def graph_overlay(sim) -> dict:
    if not sim.net:
        return {"vertices": {"type": "FeatureCollection", "features": []},
                "arcs": {"type": "FeatureCollection", "features": []}, "components": 0}
    component_ids = {edge_id: index for index, group in enumerate(sim.graph.components()) for edge_id in group}
    incoming = {edge_id: [] for edge_id in sim.graph.adj}
    for source, neighbors in sim.graph.adj.items():
        for target in neighbors:
            incoming[target].append(source)
    centers = {}
    vertices = []
    for edge_id, neighbors in sim.graph.adj.items():
        access = sim.access_points.get(edge_id)
        edge = sim.edges.get(edge_id)
        if access:
            coordinates = list(access["coordinates"])
            length_m = 0
            speed_kmh = round(sim.edges[access["edge_id"]].getSpeed() * 3.6, 1)
            neighborhood = sim._nearest_place(access["edge_id"])
            kind = "ponto de acesso"
        else:
            shape = edge.getShape()
            point = shape[len(shape) // 2]
            coordinates = list(sim.net.convertXY2LonLat(*point))
            length_m = round(edge.getLength(), 1)
            speed_kmh = round(edge.getSpeed() * 3.6, 1)
            neighborhood = sim._nearest_place(edge_id)
            kind = "cruzamento" if len(incoming[edge_id]) + len(neighbors) > 3 else "trecho"
        centers[edge_id] = coordinates
        vertices.append({"type": "Feature", "id": edge_id,
                         "geometry": {"type": "Point", "coordinates": coordinates},
                         "properties": {"id": edge_id, "degree_in": len(incoming[edge_id]),
                                        "degree_out": len(neighbors), "incoming": incoming[edge_id],
                                        "outgoing": list(neighbors), "component": component_ids[edge_id],
                                        "neighborhood": neighborhood,
                                        "intersection_type": kind, "name": access["name"] if access else "",
                                        "access_edge": access["edge_id"] if access else None,
                                        "length_m": length_m, "speed_kmh": speed_kmh}})
    arcs = [{"type": "Feature", "geometry": {"type": "LineString",
             "coordinates": [centers[source], centers[target]]},
             "properties": {"source": source, "target": target, "weight_s": round(weight, 1),
                            "component": component_ids[source]}}
            for source, neighbors in sim.graph.adj.items() for target, weight in neighbors.items()]
    return {"vertices": {"type": "FeatureCollection", "features": vertices},
            "arcs": {"type": "FeatureCollection", "features": arcs},
            "components": len(set(component_ids.values())),
            "note": "Vértices viários representam arestas SUMO; pontos de acesso registrados são vértices virtuais ponderados pela posição na via. Eles não criam cruzamentos físicos."}
