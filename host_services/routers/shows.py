from fastapi import APIRouter, Request
from ..response import ok
from .. import engine_adapter

router = APIRouter(prefix="/api/v1", tags=["Shows"])


@router.get("/shows")
async def list_shows(request: Request):
    return ok(request, {"shows": engine_adapter.get_shows()})
