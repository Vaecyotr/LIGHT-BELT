"""Unit tests for host_services/shows_loader.py.

Uses tmp_path for filesystem; ffprobe is monkeypatched to avoid subprocess.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from host_services.shows_loader import load_shows


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_show_dir(assets: Path, name: str, media: str | None = None, yaml_name: str | None = None):
    d = assets / name
    d.mkdir()
    if media:
        (d / media).write_text("fake")
    if yaml_name:
        (d / yaml_name).write_text("schema_version: 2\n")
    return d


def _no_ffprobe(*_args, **_kwargs):
    return 0


# Patch ffprobe away in all tests unless explicitly testing duration.
@pytest.fixture(autouse=True)
def patch_ffprobe():
    with patch("host_services.shows_loader._probe_duration_ms", return_value=0):
        yield


# ── basic discovery ───────────────────────────────────────────────────────────

def test_discovers_show_with_media_and_yaml(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "demo", media="demo.mp4", yaml_name="demo.yaml")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    s = shows[0]
    assert s["show_id"] == "demo"
    assert s["name"] == "demo"
    assert s["media_path"] is not None and "demo.mp4" in s["media_path"]
    assert s["show_yaml"] is not None and "demo.yaml" in s["show_yaml"]


def test_show_without_media_still_discovered_if_yaml_present(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "yaml-only", yaml_name="show.yaml")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    assert shows[0]["show_id"] == "yaml-only"
    assert shows[0]["media_path"] is None


def test_show_without_yaml_still_discovered_if_media_present(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "media-only", media="track.mp3")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    assert shows[0]["show_id"] == "media-only"
    assert shows[0]["show_yaml"] is None


def test_dir_with_neither_media_nor_yaml_is_skipped(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "empty"
    d.mkdir()
    (d / "notes.txt").write_text("irrelevant")

    shows = load_shows(assets_dir=assets)
    assert shows == []


def test_multiple_shows_all_discovered(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "show-a", media="a.mp4")
    _make_show_dir(assets, "show-b", yaml_name="b.yaml")

    shows = load_shows(assets_dir=assets)
    ids = {s["show_id"] for s in shows}
    assert ids == {"show-a", "show-b"}


def test_multiple_media_uses_first_alphabetically(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "multi"
    d.mkdir()
    (d / "b.mp4").write_text("b")
    (d / "a.mp4").write_text("a")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    assert "a.mp4" in shows[0]["media_path"]


def test_multiple_yaml_uses_first_alphabetically(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "multi"
    d.mkdir()
    (d / "z.yaml").write_text("")
    (d / "a.yaml").write_text("")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    assert "a.yaml" in shows[0]["show_yaml"]


# ── manifest overlay ──────────────────────────────────────────────────────────

def test_manifest_overlay_overrides_name(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "demo", media="demo.mp4")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"demo": {"show_id": "demo", "name": "Custom Name"}}))

    shows = load_shows(assets_dir=assets, manifest_path=manifest)
    assert shows[0]["name"] == "Custom Name"


def test_manifest_overlay_adds_aux_triggers(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "demo", media="demo.mp4")

    triggers = [{"target": "starry_sky", "at_ms": 230000, "action": "on"}]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "demo": {"show_id": "demo", "aux_triggers": triggers}
    }))

    shows = load_shows(assets_dir=assets, manifest_path=manifest)
    assert shows[0]["aux_triggers"] == triggers


def test_manifest_only_entry_without_assets(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "legacy-show": {
            "show_id": "legacy-show",
            "name": "Legacy",
            "media_path": "/some/path.mp4",
            "duration_ms": 60000,
        }
    }))

    shows = load_shows(assets_dir=assets, manifest_path=manifest)
    assert len(shows) == 1
    assert shows[0]["show_id"] == "legacy-show"


def test_missing_manifest_is_silent(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "demo", media="demo.mp4")

    shows = load_shows(assets_dir=assets, manifest_path=tmp_path / "nonexistent.json")
    assert len(shows) == 1


def test_legacy_array_manifest_is_accepted(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"show_id": "legacy-show", "name": "Legacy", "media_path": "/p.mp4", "duration_ms": 0}
    ]))

    shows = load_shows(assets_dir=assets, manifest_path=manifest)
    assert any(s["show_id"] == "legacy-show" for s in shows)


# ── duration via ffprobe ──────────────────────────────────────────────────────

def test_duration_from_ffprobe(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "demo", media="demo.mp4")

    with patch("host_services.shows_loader._probe_duration_ms", return_value=305000):
        shows = load_shows(assets_dir=assets)
    assert shows[0]["duration_ms"] == 305000


def test_duration_zero_when_ffprobe_fails(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    _make_show_dir(assets, "demo", media="demo.mp4")

    # _probe_duration_ms already patched to 0 by autouse fixture
    shows = load_shows(assets_dir=assets)
    assert shows[0]["duration_ms"] == 0


def test_missing_assets_dir_returns_empty(tmp_path):
    shows = load_shows(assets_dir=tmp_path / "nonexistent")
    assert shows == []


# ── dual-media (Feature 2) ────────────────────────────────────────────────────

def test_dual_media_video_and_audio(tmp_path):
    """Folder with mp4 + mp3: media_path is video, audio_path is audio."""
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "dual"
    d.mkdir()
    (d / "video.mp4").write_text("fake")
    (d / "audio.mp3").write_text("fake")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    s = shows[0]
    assert s["media_path"] is not None and "video.mp4" in s["media_path"]
    assert s["audio_path"] is not None and "audio.mp3" in s["audio_path"]


def test_video_only_no_audio_path(tmp_path):
    """Folder with only mp4: media_path is video, audio_path is None."""
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "video-only"
    d.mkdir()
    (d / "video.mp4").write_text("fake")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    assert "video.mp4" in shows[0]["media_path"]
    assert shows[0]["audio_path"] is None


def test_audio_only_no_audio_path(tmp_path):
    """Folder with only mp3: media_path is the audio file, audio_path is None."""
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "audio-only"
    d.mkdir()
    (d / "track.mp3").write_text("fake")

    shows = load_shows(assets_dir=assets)
    assert len(shows) == 1
    assert "track.mp3" in shows[0]["media_path"]
    assert shows[0]["audio_path"] is None


def test_dual_media_duration_uses_video(tmp_path):
    """When both video and audio are present, duration_ms comes from the video file."""
    assets = tmp_path / "assets"
    assets.mkdir()
    d = assets / "dual"
    d.mkdir()
    (d / "video.mp4").write_text("fake")
    (d / "audio.mp3").write_text("fake")

    with patch("host_services.shows_loader._probe_duration_ms") as mock_probe:
        mock_probe.side_effect = lambda path: 120000 if path.endswith(".mp4") else 90000
        shows = load_shows(assets_dir=assets)

    assert shows[0]["duration_ms"] == 120000


def test_product_catalog_excludes_retired_demo_and_rejects_it_before_playback(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from host_services import engine_adapter
    from host_services.main import app

    assets = Path(__file__).resolve().parents[1] / "assets"
    shows = load_shows(assets_dir=assets, manifest_path=tmp_path / "no-overlay.json")
    by_id = {show["show_id"]: show for show in shows}
    retired = "phase-17-full-show-wled-five-board"
    assert "energy-wakeup" in by_id
    assert retired not in by_id
    assert Path(by_id["energy-wakeup"]["show_yaml"]).is_file()
    monkeypatch.setattr(engine_adapter, "_shows", shows)
    monkeypatch.setattr(engine_adapter, "_state", {
        **engine_adapter._state, "show_id": "energy-wakeup", "playback_state": "playing",
    })

    def unexpected_player_start():
        pytest.fail("A missing show must be rejected before the player is touched")

    monkeypatch.setattr(engine_adapter, "_ensure_mpv", unexpected_player_start)
    before = dict(engine_adapter._state)
    client = TestClient(app)
    response = client.get("/api/v1/shows")
    assert response.status_code == 200
    listed = response.json()["data"]["shows"]
    assert {show["show_id"] for show in listed} == set(by_id)
    assert all("media_path" not in show and "show_yaml" not in show for show in listed)
    response = client.post("/api/v1/playback/play", json={"show_id": retired})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert engine_adapter._state == before
