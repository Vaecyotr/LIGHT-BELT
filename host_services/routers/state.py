from fastapi import APIRouter, Request
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["State"])


@router.get("/state")
async def get_state(request: Request):
    return ok(request, engine_adapter.get_state())
