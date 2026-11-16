"""Módulo acadêmico de municípios, independente da malha urbana."""
import random
import sqlite3
from pathlib import Path
from time import perf_counter_ns

from .graphs import Graph


class MunicipalityLab:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS cities(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
          CREATE TABLE IF NOT EXISTS links(a INTEGER NOT NULL, b INTEGER NOT NULL, distance REAL NOT NULL,
            PRIMARY KEY(a,b), FOREIGN KEY(a) REFERENCES cities(id), FOREIGN KEY(b) REFERENCES cities(id));
        """)
        self.db.commit()

    def list(self):
        return {"cities": [dict(row) for row in self.db.execute("SELECT * FROM cities ORDER BY name")],
                "links": [dict(row) for row in self.db.execute("SELECT * FROM links ORDER BY a,b")]}

    def create(self, name: str):
        cursor = self.db.execute("INSERT INTO cities(name) VALUES (?)", (name,))
        self.db.commit()
        return {"id": cursor.lastrowid, "name": name}

    def rename(self, city_id: int, name: str):
        cursor = self.db.execute("UPDATE cities SET name=? WHERE id=?", (name, city_id))
        self.db.commit()
        if not cursor.rowcount:
            raise KeyError(city_id)

    def delete(self, city_id: int):
        self.db.execute("DELETE FROM links WHERE a=? OR b=?", (city_id, city_id))
        self.db.execute("DELETE FROM cities WHERE id=?", (city_id,))
        self.db.commit()

    def link(self, a: int, b: int, distance: float):
        if a == b or distance <= 0:
            raise ValueError("Ligação exige cidades distintas e distância positiva")
        a, b = sorted((a, b))
        self.db.execute("INSERT OR REPLACE INTO links(a,b,distance) VALUES (?,?,?)", (a, b, distance))
        self.db.commit()

    def graph(self):
        graph = Graph(directed=False)
        for row in self.db.execute("SELECT id FROM cities"):
            graph.add_vertex(row["id"])
        for row in self.db.execute("SELECT a,b,distance FROM links"):
            graph.add_edge(row["a"], row["b"], row["distance"])
        return graph


def scale_experiments(seed: int = 42):
    results = []
    for size in (10, 20, 50, 100):
        rng = random.Random(seed + size)
        graph = Graph(directed=False)
        for vertex in range(size):
            graph.add_vertex(vertex)
        for vertex in range(size - 1):
            graph.add_edge(vertex, vertex + 1, rng.randint(5, 100))
        for _ in range(size * 2):
            a, b = rng.sample(range(size), 2)
            graph.add_edge(a, b, rng.randint(5, 100))
        row = {"cities": size, "edges": graph.stats()["edges"]}
        for method in ("heap", "simple"):
            begin = perf_counter_ns()
            distance, _ = graph.dijkstra(0, size - 1, method=method)
            row[f"dijkstra_{method}_ns"] = perf_counter_ns() - begin
            row[f"dijkstra_{method}_distance"] = distance[size - 1]
        begin = perf_counter_ns()
        matrix_distance, _ = graph.dijkstra_matrix(0, size - 1)
        row["dijkstra_matrix_ns"] = perf_counter_ns() - begin
        row["dijkstra_matrix_distance"] = matrix_distance[size - 1]
        results.append(row)
    return results
