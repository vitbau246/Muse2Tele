from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...core import app_update

router = APIRouter(prefix="/update", tags=["update"])


@router.get("")
def get_update(force: bool = Query(False, description="Check GitHub now instead of the cached result")) -> dict:
    """Muse2Tele: is a newer version on GitHub? (supported=false outside Muse2Tele)"""
    return app_update.status(force)


@router.post("/apply", status_code=202)
def apply_update() -> dict:
    """Update the whole project from GitHub, keeping data. FoxProfile, the bot and AutoPost
    restart; running profiles are stopped and reopened. Progress: GET /update -> last_update."""
    try:
        return app_update.apply()
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
