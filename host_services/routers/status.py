from fastapi import APIRouter, Request
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Status"])


@router.get("/status")
async def status(request: Request):
    data = engine_adapter.get_status()
    data.update(request.app.state.runtime_identity)
    data["ready"] = request.app.state.ready
    data["adapter"] = engine_adapter.ENGINE_ADAPTER
    return ok(request, data)
