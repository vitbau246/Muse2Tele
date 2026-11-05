from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from ...core import settings, upload_dirs
from ..schemas.settings import (
    SettingsResponse,
    SettingsUpdate,
    UploadDirsResponse,
    UploadDirsUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _current() -> SettingsResponse:
    return SettingsResponse(
        download_dir=str(settings.download_dir()),
        default_download_dir=str(settings.default_download_dir()),
        custom=settings.custom_download_dir() is not None,
    )


@router.get("", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _current()


@router.put("", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate) -> SettingsResponse:
    """Choose where browsers save downloaded files (empty = default). Applies at once, also to running profiles."""
    try:
        settings.set_download_dir(body.download_dir)
    except settings.SettingsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _current()


@router.get("/upload-dirs", response_model=UploadDirsResponse)
def get_upload_dirs() -> UploadDirsResponse:
    return UploadDirsResponse(**asdict(upload_dirs.current()))


@router.put("/upload-dirs", response_model=UploadDirsResponse)
def update_upload_dirs(body: UploadDirsUpdate) -> UploadDirsResponse:
    """Choose FOXPROFILE_UPLOAD_DIRS and MUSE_UPLOAD_DIR (saved to .env). Applies to profiles
    launched afterwards; the Telegram bot picks up MUSE_UPLOAD_DIR when restarted."""
    try:
        result = upload_dirs.save(body.upload_dirs, body.muse_upload_dir)
    except upload_dirs.UploadDirsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return UploadDirsResponse(**asdict(result))
