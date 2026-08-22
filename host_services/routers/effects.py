from fastapi import APIRouter, Request, Depends
from ..schemas import EffectsSetRequest
from ..deps import require_auth
from ..response import ok, invalid_argument, not_found
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Effects"],
                   dependencies=[Depends(require_auth)])


@router.post("/effects/set")
async def effects_set(body: EffectsSetRequest, request: Request):
    data, err = engine_adapter.effects_set(
        body.target_id, body.effect_type,
        body.transition_ms or 0,
        params=body.params,
        effect_params=body.effect_params,
    )
    if err == "NOT_FOUND":
        return not_found(request, f"Unknown target_id: {body.target_id}")
    if err == "INVALID_ARGUMENT":
        details = data.get("error_detail") if data else None
        return invalid_argument(request, "Effect validation failed", details)
    return ok(request, data)
