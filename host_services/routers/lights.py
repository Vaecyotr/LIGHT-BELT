from fastapi import APIRouter, Request
from ..schemas import LightsSetRequest
from ..response import ok, error, invalid_argument, not_found
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Lights"])


@router.post("/lights/set")
def lights_set(body: LightsSetRequest, request: Request):
    data, err = engine_adapter.lights_set(
        body.target_id, body.brightness,
        body.color_temperature, body.transition_ms or 0,
        color=body.color,
    )
    if err == "NOT_FOUND":
        return not_found(request, f"Unknown target_id: {body.target_id}")
    if err == "INVALID_ARGUMENT":
        return invalid_argument(request, "brightness or color_temperature required")
    return ok(request, data)
