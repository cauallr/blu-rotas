"""Estruturas e algoritmos acadêmicos próprios, sem NetworkX."""
from __future__ import annotations

from collections import deque
from heapq import heappop, heappush
from math import inf
from time import perf_counter_ns
from typing import Hashable


class Graph:
    def __init__(self, directed: bool = True):
        self.directed = directed
        self.adj: dict[Hashable, dict[Hashable, float]] = {}

    def add_vertex(self, vertex: Hashable) -> None:
        self.adj.setdefault(vertex, {})

    def remove_vertex(self, vertex: Hashable) -> None:
        self.adj.pop(vertex)
        for neighbors in self.adj.values():
            neighbors.pop(vertex, None)

    def add_edge(self, source: Hashable, target: Hashable, weight: float = 1) -> None:
        if weight < 0:
            raise ValueError("Pesos negativos não são aceitos")
        self.add_vertex(source)
        self.add_vertex(target)
        self.adj[source][target] = float(weight)
        if not self.directed:
            self.adj[target][source] = float(weight)

    def remove_edge(self, source: Hashable, target: Hashable) -> None:
        self.adj[source].pop(target)
        if not self.directed:
            self.adj[target].pop(source)

    def matrix(self) -> tuple[list[Hashable], list[list[float]]]:
        vertices = list(self.adj)
        index = {vertex: i for i, vertex in enumerate(vertices)}
        matrix = [[inf] * len(vertices) for _ in vertices]
        for i in range(len(vertices)):
            matrix[i][i] = 0
        for source, neighbors in self.adj.items():
            for target, weight in neighbors.items():
                matrix[index[source]][index[target]] = weight
        return vertices, matrix

    def bfs(self, start: Hashable) -> list[Hashable]:
        if start not in self.adj:
            raise KeyError(start)
        visited = {start}
        queue = deque([start])
        order = []
        while queue:
            vertex = queue.popleft()
            order.append(vertex)
            for neighbor in self.adj[vertex]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return order

    def dfs(self, start: Hashable) -> list[Hashable]:
        if start not in self.adj:
            raise KeyError(start)
        visited = set()
        stack = [start]
        order = []
        while stack:
            vertex = stack.pop()
            if vertex in visited:
                continue
            visited.add(vertex)
            order.append(vertex)
            stack.extend(reversed(list(self.adj[vertex])))
        return order

    def dijkstra(self, start: Hashable, end: Hashable | None = None,
                 costs: dict[Hashable, float] | None = None,
                 method: str = "heap") -> tuple[dict, dict]:
        if start not in self.adj:
            raise KeyError(start)
        distance = {vertex: inf for vertex in self.adj}
        previous: dict[Hashable, Hashable] = {}
        distance[start] = 0
        if method == "heap":
            heap = [(0, 0, start)]
            serial = 1
            while heap:
                value, _, vertex = heappop(heap)
                if value != distance[vertex]:
                    continue
                if vertex == end:
                    break
                for neighbor, weight in self.adj[vertex].items():
                    candidate = value + (costs.get(neighbor, weight) if costs else weight)
                    if candidate < distance[neighbor]:
                        distance[neighbor] = candidate
                        previous[neighbor] = vertex
                        heappush(heap, (candidate, serial, neighbor))
                        serial += 1
        elif method == "simple":
            unvisited = set(self.adj)
            while unvisited:
                vertex = min(unvisited, key=lambda item: distance[item])
                if distance[vertex] == inf or vertex == end:
                    break
                unvisited.remove(vertex)
                for neighbor, weight in self.adj[vertex].items():
                    candidate = distance[vertex] + (costs.get(neighbor, weight) if costs else weight)
                    if neighbor in unvisited and candidate < distance[neighbor]:
                        distance[neighbor] = candidate
                        previous[neighbor] = vertex
        else:
            raise ValueError("method deve ser heap ou simple")
        return distance, previous

    def dijkstra_matrix(self, start: Hashable, end: Hashable | None = None) -> tuple[dict, dict]:
        vertices, matrix = self.matrix()
        index = {vertex: i for i, vertex in enumerate(vertices)}
        if start not in index:
            raise KeyError(start)
        distances = [inf] * len(vertices)
        distances[index[start]] = 0
        previous: dict[Hashable, Hashable] = {}
        visited = [False] * len(vertices)
        for _ in vertices:
            candidates = [i for i in range(len(vertices)) if not visited[i]]
            if not candidates:
                break
            u = min(candidates, key=lambda i: distances[i])
            if distances[u] == inf or vertices[u] == end:
                break
            visited[u] = True
            for v, weight in enumerate(matrix[u]):
                if not visited[v] and weight != inf and distances[u] + weight < distances[v]:
                    distances[v] = distances[u] + weight
                    previous[vertices[v]] = vertices[u]
        return dict(zip(vertices, distances)), previous

    @staticmethod
    def path(previous: dict, start: Hashable, end: Hashable) -> list[Hashable]:
        if start == end:
            return [start]
        if end not in previous:
            return []
        result = [end]
        while result[-1] != start:
            result.append(previous[result[-1]])
        return list(reversed(result))

    def components(self) -> list[list[Hashable]]:
        # Componentes fracos para grafos direcionados.
        undirected = {vertex: set(neighbors) for vertex, neighbors in self.adj.items()}
        for source, neighbors in self.adj.items():
            for target in neighbors:
                undirected[target].add(source)
        unseen = set(self.adj)
        components = []
        while unseen:
            start = next(iter(unseen))
            queue = [start]
            unseen.remove(start)
            component = []
            while queue:
                vertex = queue.pop()
                component.append(vertex)
                for neighbor in undirected[vertex] & unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
            components.append(component)
        return components

    def prim(self, start: Hashable | None = None) -> tuple[list[tuple], float]:
        if self.directed:
            raise ValueError("Prim exige grafo não direcionado")
        if not self.adj:
            return [], 0
        start = start if start is not None else next(iter(self.adj))
        visited = {start}
        heap = [(weight, str(start), str(target), start, target)
                for target, weight in self.adj[start].items()]
        from heapq import heapify
        heapify(heap)
        edges = []
        total = 0.0
        while heap:
            weight, _, _, source, target = heappop(heap)
            if target in visited:
                continue
            visited.add(target)
            edges.append((source, target, weight))
            total += weight
            for neighbor, next_weight in self.adj[target].items():
                if neighbor not in visited:
                    heappush(heap, (next_weight, str(target), str(neighbor), target, neighbor))
        return edges, total

    def stats(self) -> dict:
        edge_count = sum(len(neighbors) for neighbors in self.adj.values())
        if not self.directed:
            edge_count //= 2
        n = len(self.adj)
        return {"vertices": n, "edges": edge_count,
                "density": edge_count / (n * (n - 1)) * (1 if self.directed else 2) if n > 1 else 0,
                "components": len(self.components())}


def benchmark(graph: Graph, start, end) -> dict:
    result = {}
    for method in ("simple", "heap"):
        begin = perf_counter_ns()
        distances, previous = graph.dijkstra(start, end, method=method)
        result[method] = {"nanoseconds": perf_counter_ns() - begin,
                          "distance": distances[end], "path": graph.path(previous, start, end)}
    return result
