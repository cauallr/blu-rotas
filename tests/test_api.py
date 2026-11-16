from fastapi.testclient import TestClient

from backend.main import app


def test_map_and_status_without_sumo():
    with TestClient(app) as client:
        status = client.get('/api/status')
        assert status.status_code == 200
        assert 'ready' in status.json()
        roads = client.get('/api/network')
        assert roads.status_code == 200
        assert roads.json()['type'] == 'FeatureCollection'
        assert len(roads.json()['features']) > 100


def test_cannot_spawn_without_engine():
    with TestClient(app) as client:
        if not client.get('/api/status').json()['connected']:
            response = client.post('/api/spawn', json={'count': 10})
            assert response.status_code == 400
