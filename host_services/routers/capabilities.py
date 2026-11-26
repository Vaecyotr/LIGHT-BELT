from fastapi import APIRouter, Request
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Capabilities"])


@router.get("/capabilities")
async def get_capabilities(request: Request):
    return ok(request, engine_adapter.get_capabilities())
