"""Scene API success commits both the file and the in-memory snapshot."""

import builtins
import json

import pytest
from fastapi.testclient import TestClient

from host_services import auth_manager, engine_adapter
from host_services.main import app


@pytest.fixture
def scene_store(tmp_path, monkeypatch):
    original = {
        "existing": {
            "name": "Original", "audio": {"volume": 0.2}, "entries": None,
            "created_ms": 1, "updated_ms": 1,
        }
    }
    path = tmp_path / "scenes.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(engine_adapter, "SCENE_FILE_PATH", str(path))
    monkeypatch.setattr(engine_adapter, "_scenes", original)
    monkeypatch.setitem(engine_adapter._state, "scene_id", "existing")
    token, _ = auth_manager.create_access_token("scene-test", ["scenes:write"])
    with TestClient(app) as client:
        yield client, {"Authorization": "Bearer " + token}, path


def change_scene(client, headers, operation):
    if operation == "delete":
        return client.post("/api/v1/scenes/delete", headers=headers,
                           json={"scene_id": "existing"})
    return client.post("/api/v1/scenes/save", headers=headers, json={
        "scene_id": "existing" if operation == "overwrite" else "new",
        "name": "Changed", "audio": {"volume": 0.7},
    })


@pytest.mark.parametrize("operation", ["create", "overwrite", "delete"])
@pytest.mark.parametrize("failure", ["open", "replace"])
def test_scene_write_failure_preserves_memory_and_disk(scene_store, monkeypatch,
                                                       operation, failure):
    client, headers, path = scene_store
    before_disk = path.read_bytes()
    before_memory = json.loads(json.dumps(engine_adapter._scenes))
    if failure == "open":
        real_open = builtins.open

        def reject_write(file, mode="r", *args, **kwargs):
            if "w" in mode:
                raise PermissionError("scene storage is read-only")
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", reject_write)
    else:
        def reject_replace(*_args):
            raise OSError("scene replacement failed")

        monkeypatch.setattr(engine_adapter.os, "replace", reject_replace)

    response = change_scene(client, headers, operation)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert engine_adapter._scenes == before_memory
    assert engine_adapter._state["scene_id"] == "existing"
    assert path.read_bytes() == before_disk
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("operation", ["create", "overwrite", "delete"])
def test_scene_success_survives_reload(scene_store, operation):
    client, headers, path = scene_store

    response = change_scene(client, headers, operation)

    assert response.status_code == 200
    assert engine_adapter._load_scenes() == engine_adapter._scenes
    assert json.loads(path.read_text(encoding="utf-8")) == engine_adapter._scenes
    if operation == "delete":
        assert "existing" not in engine_adapter._scenes
        assert engine_adapter._state["scene_id"] is None
    else:
        scene_id = "existing" if operation == "overwrite" else "new"
        assert engine_adapter._scenes[scene_id]["name"] == "Changed"
