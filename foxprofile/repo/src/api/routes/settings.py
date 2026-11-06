from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from ...core import muse_team, post_map, settings, upload_dirs
from ...interfaces import IProfileManager
from ..dependencies import get_profile_manager
from ..schemas.settings import (
    MuseTeamResponse,
    MuseTeamUpdate,
    PostMapResponse,
    PostMapUpdate,
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


def _team(pm: IProfileManager) -> MuseTeamResponse:
    return MuseTeamResponse(
        **asdict(muse_team.current()),
        profiles=[p.name for p in pm.list_profiles()],
        langs=muse_team.LANGS,
        templates=muse_team.TEMPLATES,
    )


@router.get("/muse-team", response_model=MuseTeamResponse)
def get_muse_team(pm: IProfileManager = Depends(get_profile_manager)) -> MuseTeamResponse:
    return _team(pm)


@router.put("/muse-team", response_model=MuseTeamResponse)
def update_muse_team(
    body: MuseTeamUpdate, pm: IProfileManager = Depends(get_profile_manager)
) -> MuseTeamResponse:
    """Muse2Tele team mode: each Muse alone, or one chief Muse (General topic) leading the
    others (minus the excluded ones), with tasks sent automatically or after the owner approves
    them, plus the review settings (pass score, redo rounds...) and each Muse's answer language
    and long-term context (setup). reset_data wipes the Muse data
    of the chief and the team once. Applies at once."""
    names = [p.name for p in pm.list_profiles()]
    if body.mode == "chief" and body.chief not in names:
        raise HTTPException(status_code=400, detail=f"Profile not found: {body.chief}")
    try:
        params = body.model_dump(
            include=set(muse_team.DEFAULTS), exclude_none=True
        )
        muse_team.save(
            body.mode,
            body.chief,
            body.approval,
            body.roles,
            body.excluded,
            params,
            body.reset_data,
            body.setup,
            body.task_lang,
            body.post_mode,
            body.post_profile,
        )
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _team(pm)


def _post_map(pm: IProfileManager) -> PostMapResponse:
    cfg = post_map.current()
    rows = [
        {
            "name": p.name,
            "auto_post_fanpage": p.auto_post_fanpage,
            "auto_post_tiktok": p.auto_post_tiktok,
            "known_pages": post_map.known_pages(p.name),
            "check": post_map.check_result(p.name),
        }
        for p in pm.list_profiles()
    ]
    return PostMapResponse(
        file=cfg.file, installed=cfg.installed, profiles=cfg.profiles, rows=rows, langs=muse_team.LANGS
    )


@router.get("/post-map", response_model=PostMapResponse)
def get_post_map(pm: IProfileManager = Depends(get_profile_manager)) -> PostMapResponse:
    return _post_map(pm)


@router.put("/post-map", response_model=PostMapResponse)
def update_post_map(
    body: PostMapUpdate, pm: IProfileManager = Depends(get_profile_manager)
) -> PostMapResponse:
    """Which Facebook Pages (by Page ID) and TikTok account each profile auto-posts to. Auto-post
    only posts to mapped Pages and stops when the logged-in account does not match. A Page ID or
    TikTok account can belong to one profile only."""
    names = {p.name for p in pm.list_profiles()}
    unknown = [n for n in body.profiles if n not in names]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Profile not found: {unknown[0]}")
    try:
        post_map.save(body.profiles)
    except post_map.PostMapError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _post_map(pm)


@router.post("/post-map/check/{name}", response_model=PostMapResponse)
def check_post_map(name: str, pm: IProfileManager = Depends(get_profile_manager)) -> PostMapResponse:
    """Open the profile in the background and compare the logged-in Facebook Pages and TikTok
    account with the posting map, posting nothing. Poll GET /post-map: rows[].check.running."""
    if name not in {p.name for p in pm.list_profiles()}:
        raise HTTPException(status_code=404, detail=f"Profile not found: {name}")
    try:
        post_map.start_check(name)
    except post_map.PostMapError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _post_map(pm)
