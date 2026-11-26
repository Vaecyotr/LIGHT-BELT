from fastapi import APIRouter, Request
from ..schemas import BrightnessSetRequest
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1/brightness", tags=["Brightness"])


@router.get("")
def get_brightness(request: Request):
    data = engine_adapter.get_brightness_scale()
    return ok(request, data)


@router.post("/set")
def set_brightness(body: BrightnessSetRequest, request: Request):
    data, _ = engine_adapter.brightness_scale_set(body.brightness_scale, body.transition_ms or 0)
    return ok(request, data)
