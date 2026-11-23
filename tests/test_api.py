import asyncio
from contextlib import suppress
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend import main
from backend.main import SIM, app


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


def test_speed_selected_before_start_is_reported(monkeypatch):
    monkeypatch.setattr(SIM, "speed", 1)
    with TestClient(app) as client:
        response = client.post("/api/speed", json={"speed": 10})
        assert response.status_code == 200
        assert response.json()["speed"] == 10
        assert client.get("/api/status").json()["speed"] == 10
        with client.websocket_connect("/ws") as socket:
            assert socket.receive_json()["speed"] == 10


def test_ticker_can_resume_after_step_error(monkeypatch):
    async def exercise_ticker():
        failed = asyncio.Event()
        advanced = asyncio.Event()

        def step():
            if not failed.is_set():
                failed.set()
                raise RuntimeError("Falha transitória")
            advanced.set()

        simulator = SimpleNamespace(connected=True, running=True, speed=1, step=step,
                                    snapshot=lambda: {"running": True})
        monkeypatch.setattr(main, "SIM", simulator)
        monkeypatch.setattr(main, "STEP_SECONDS", 0.01)
        monkeypatch.setattr(app.state, "latest_snapshot", None, raising=False)
        worker = asyncio.create_task(main.ticker())
        try:
            await asyncio.wait_for(failed.wait(), timeout=2)
            assert not simulator.running
            simulator.running = True
            await asyncio.wait_for(advanced.wait(), timeout=2)
            assert app.state.latest_snapshot == {"running": True}
        finally:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

    asyncio.run(exercise_ticker())


def test_situations_tutorial_is_served():
    with TestClient(app) as client:
        response = client.get('/tutorial_de_situações.html')
        assert response.status_code == 200
        assert 'Como simular situações e coletar dados' in response.text
