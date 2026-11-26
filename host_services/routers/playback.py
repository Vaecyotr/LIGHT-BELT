from fastapi import APIRouter, Request
from ..schemas import PlayRequest, SeekRequest
from ..response import ok, error
from .. import engine_adapter

router = APIRouter(prefix="/api/v1/playback", tags=["Playback"])


@router.post("/play")
def play(body: PlayRequest, request: Request):
    data, err = engine_adapter.playback_play(body.show_id, body.start_position_ms)
    if err:
        if err == "NOT_FOUND":
            code = 404
        elif err == "INVALID_ARGUMENT":
            code = 400
        elif err == "ENGINE_UNAVAILABLE":
            return error(request, err, "The managed lighting engine is unavailable", 503)
        elif err == "MPV_UNAVAILABLE":
            return error(request, err,
                         "mpv is not available; check that mpv is installed and "
                         "/run/light-belt exists (or RuntimeDirectory=light-belt in the systemd unit)",
                         503)
        else:
            code = 409
        return error(request, err, f"Playback play failed: {err}", code)
    return ok(request, data)


@router.post("/pause")
def pause(request: Request):
    data, err = engine_adapter.playback_pause()
    if err:
        return error(request, err, f"Cannot pause: {err}", 409)
    return ok(request, data)


@router.post("/resume")
def resume(request: Request):
    data, err = engine_adapter.playback_resume()
    if err:
        return error(request, err, f"Cannot resume: {err}", 409)
    return ok(request, data)


@router.post("/stop")
def stop(request: Request):
    data, err = engine_adapter.playback_stop()
    if err:
        return error(request, err, f"Cannot stop: {err}", 503)
    return ok(request, data)


@router.post("/seek")
def seek(body: SeekRequest, request: Request):
    data, err = engine_adapter.playback_seek(body.position_ms)
    if err:
        return error(request, err, f"Cannot seek: {err}", 409)
    return ok(request, data)


@router.get("/state")
def playback_state(request: Request):
    data = engine_adapter.get_playback_state()
    return ok(request, data)


@router.post("/reset")
def reset(request: Request):
    data, err = engine_adapter.playback_reset()
    if err:
        if err == "PLAYBACK_NOT_READY":
            return error(request, err, "No show is currently playing or paused", 409)
        if err == "NO_ACTIVE_SHOW":
            return error(request, err, "No active show to reset to", 409)
        return error(request, err, f"Playback reset failed: {err}", 500)
    return ok(request, data)
