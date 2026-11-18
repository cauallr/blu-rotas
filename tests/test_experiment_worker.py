import json
from pathlib import Path

import pytest

from scripts import experiment_worker


def test_status_write_recovers_from_windows_file_sharing(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    target.write_text('{"state":"queued"}', encoding="utf-8")
    original_replace = Path.replace
    attempts = 0

    def temporarily_locked(path, destination):
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            assert json.loads(target.read_text(encoding="utf-8"))["state"] == "queued"
            raise PermissionError(13, "file in use", str(destination), 5)
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", temporarily_locked)
    monkeypatch.setattr(experiment_worker.time, "sleep", lambda _: None)
    experiment_worker.write_json(target, {"state": "complete", "progress": 1})

    assert attempts == 4
    assert json.loads(target.read_text(encoding="utf-8")) == {"state": "complete", "progress": 1}
    assert not target.with_suffix(".tmp").exists()


def test_status_write_surfaces_persistent_permission_error(tmp_path, monkeypatch):
    target = tmp_path / "status.json"

    def always_locked(path, destination):
        raise PermissionError(13, "file in use", str(destination), 5)

    monkeypatch.setattr(Path, "replace", always_locked)
    monkeypatch.setattr(experiment_worker.time, "sleep", lambda _: None)
    with pytest.raises(PermissionError):
        experiment_worker.write_json(target, {"state": "running"})
