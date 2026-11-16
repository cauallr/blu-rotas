from backend.graphs import Graph
from backend.municipalities import scale_experiments


def test_algorithms_and_matrix():
    graph = Graph(directed=False)
    for source, target, weight in [('A', 'B', 4), ('A', 'C', 1), ('C', 'B', 2), ('B', 'D', 1)]:
        graph.add_edge(source, target, weight)
    distances, previous = graph.dijkstra('A', 'D')
    assert distances['D'] == 4
    assert graph.path(previous, 'A', 'D') == ['A', 'C', 'B', 'D']
    assert graph.dijkstra('A', 'D', method='simple')[0]['D'] == 4
    assert graph.dijkstra_matrix('A', 'D')[0]['D'] == 4
    assert set(graph.bfs('A')) == {'A', 'B', 'C', 'D'}
    assert set(graph.dfs('A')) == {'A', 'B', 'C', 'D'}
    vertices, matrix = graph.matrix()
    assert matrix[vertices.index('A')][vertices.index('C')] == 1
    assert graph.prim('A')[1] == 4
    assert graph.stats()['components'] == 1


def test_disconnected_and_crud():
    graph = Graph()
    graph.add_edge('A', 'B', 3)
    graph.add_vertex('C')
    assert graph.path(graph.dijkstra('A', 'C')[1], 'A', 'C') == []
    assert graph.stats()['components'] == 2
    graph.remove_edge('A', 'B')
    graph.remove_vertex('B')
    assert graph.stats()['vertices'] == 2


def test_scale_experiments_reproducible_distances():
    first = scale_experiments(7)
    second = scale_experiments(7)
    assert [row['cities'] for row in first] == [10, 20, 50, 100]
    assert [row['dijkstra_heap_distance'] for row in first] == [row['dijkstra_simple_distance'] for row in second]
    assert [row['dijkstra_matrix_distance'] for row in first] == [row['dijkstra_heap_distance'] for row in second]
