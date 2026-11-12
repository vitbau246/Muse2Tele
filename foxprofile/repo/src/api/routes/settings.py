from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ...core import muse_team, post_map, settings, upload_dirs, video_save
from ...interfaces import IProfileManager
from ..dependencies import get_profile_manager
from ..schemas.settings import (
    MuseTeamCreate,
    MuseTeamDetach,
    MuseTeamReset,
    MuseTeamResponse,
    MuseTeamUpdate,
    PostMapResponse,
    PostMapUpdate,
    SettingsResponse,
    SettingsUpdate,
    UploadDirsResponse,
    UploadDirsUpdate,
    VideoSaveResponse,
    VideoSaveUpdate,
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


@router.get("/video-save", response_model=VideoSaveResponse)
def get_video_save() -> VideoSaveResponse:
    return VideoSaveResponse(**asdict(video_save.current()))


@router.put("/video-save", response_model=VideoSaveResponse)
def update_video_save(body: VideoSaveUpdate) -> VideoSaveResponse:
    """Turn on / off the auto-save of the videos Muse sends and choose the base folder (saved to
    .env). Each video goes to <folder>/<Muse profile>/. The Telegram bot applies it at once."""
    try:
        result = video_save.save(body.enabled, body.save_dir)
    except video_save.VideoSaveError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return VideoSaveResponse(**asdict(result))


def _team(pm: IProfileManager, team: str | None = None) -> MuseTeamResponse:
    try:
        cfg = muse_team.current(team)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    names = [p.name for p in pm.list_profiles()]
    data = asdict(cfg)
    data["team_profiles"] = data.pop("profiles")
    data.pop("muse_profiles")
    return MuseTeamResponse(
        **data,
        muse_profiles=cfg.muse_profiles,
        group_profiles=muse_team.team_profiles(cfg, names),
        profiles=names,
        langs=muse_team.LANGS,
        templates=muse_team.skills(),
    )


TeamQuery = Annotated[str | None, Query(description="Team id; empty = the default team")]


@router.get("/muse-team", response_model=MuseTeamResponse)
def get_muse_team(
    pm: IProfileManager = Depends(get_profile_manager), team: TeamQuery = None
) -> MuseTeamResponse:
    return _team(pm, team)


@router.put("/muse-team", response_model=MuseTeamResponse)
def update_muse_team(
    body: MuseTeamUpdate, pm: IProfileManager = Depends(get_profile_manager), team: TeamQuery = None
) -> MuseTeamResponse:
    """Settings of one Muse team (each team works in its own Telegram group): name, the profiles
    in its group, each Muse alone or one chief Muse (General topic) leading the others (minus the
    excluded ones), tasks sent automatically or after the owner approves them, the review
    settings, the skill pack (contexts + video settings) and each Muse's answer language and
    long-term context (setup). reset_data wipes the Muse data of the chief and the team once.
    Applies at once."""
    names = [p.name for p in pm.list_profiles()]
    if body.mode == "chief" and body.chief not in names:
        raise HTTPException(status_code=400, detail=f"Profile not found: {body.chief}")
    try:
        params = body.model_dump(
            include=set(muse_team.DEFAULTS), exclude_none=True
        )
        extra = {} if body.team_profiles is None else {"profiles": body.team_profiles}
        cfg = muse_team.save(
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
            body.reset_targets,
            body.reset_team_data,
            team_id=team,
            name=body.name,
            skill_id=body.skill,
            features=body.features,
            **extra,
        )
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _team(pm, cfg.id)


@router.post("/muse-team/teams", response_model=MuseTeamResponse)
def create_muse_team(
    body: MuseTeamCreate, pm: IProfileManager = Depends(get_profile_manager)
) -> MuseTeamResponse:
    """Add a Muse team. Link it to a Telegram group: add the bot to a new group with Topics on and
    send /setup there, then pick this team."""
    try:
        cfg = muse_team.create_team(body.name, body.team_profiles)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _team(pm, cfg.id)


@router.delete("/muse-team/teams/{team_id}", response_model=MuseTeamResponse)
def delete_muse_team(team_id: str, pm: IProfileManager = Depends(get_profile_manager)) -> MuseTeamResponse:
    """Remove a Muse team (not the default one). Its profiles go back to the default team and
    the bot stops using its group. Returns the default team."""
    try:
        cfg = muse_team.delete_team(team_id)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _team(pm, cfg.id)


@router.post("/muse-team/reset", response_model=MuseTeamResponse)
def reset_muse_team(
    body: MuseTeamReset, pm: IProfileManager = Depends(get_profile_manager), team: TeamQuery = None
) -> MuseTeamResponse:
    """Reset one Muse team: every setting back to its default (solo mode, no skill pack), and the
    bot wipes the Muse data of the listed profiles once and clears the team's tasks, sample
    videos, scripts and locked character sets. Cannot be undone."""
    try:
        cfg = muse_team.reset(body.profiles, team)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _team(pm, cfg.id)


@router.post("/muse-team/detach", response_model=MuseTeamResponse)
def detach_muse_team_member(
    body: MuseTeamDetach, pm: IProfileManager = Depends(get_profile_manager), team: TeamQuery = None
) -> MuseTeamResponse:
    """Take one member out of a Muse team: it is left out of the team, its role and team setup
    are dropped, and the bot drops every open task of that Muse (the running one too), then wipes
    its Muse data (wipe) or tells it it left the team. It joins again when ticked back in."""
    try:
        cfg = muse_team.current(team)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    names = [p.name for p in pm.list_profiles()]
    profile = body.profile.strip()
    if profile not in names and profile not in cfg.muse_profiles:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile}")
    try:
        cfg = muse_team.detach(profile, body.wipe, muse_team.team_profiles(cfg, names), cfg.id)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _team(pm, cfg.id)


@router.get("/muse-team/skills", response_model=list[dict])
def list_skills() -> list[dict]:
    """Skill packs: built-in ones and the ones installed in muse_telebot/skills/."""
    return muse_team.skills()


@router.post("/muse-team/skills", response_model=dict)
def install_skill(body: dict = Body(...)) -> dict:
    """Install (or update) a skill pack from its JSON (format 1, see src/core/muse_team.py)."""
    try:
        return muse_team.install_skill(body)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/muse-team/skills/{skill_id}", response_model=list[dict])
def remove_skill(skill_id: str) -> list[dict]:
    """Remove an installed skill pack (built-in packs stay)."""
    try:
        muse_team.remove_skill(skill_id)
    except muse_team.MuseTeamError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return muse_team.skills()


def _post_map(pm: IProfileManager) -> PostMapResponse:
    cfg = post_map.current()
    rows = [
        {
            "name": p.name,
            "auto_post_fanpage": p.auto_post_fanpage,
            "auto_post_tiktok": p.auto_post_tiktok,
            "auto_post_youtube": p.auto_post_youtube,
            "known_pages": post_map.known_pages(p.name),
            "known_tiktok": post_map.known_tiktok(p.name),
            "known_youtube": post_map.known_youtube(p.name),
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
    """Which Facebook Pages (by Page ID), TikTok account and YouTube channel each profile
    auto-posts to. Auto-post only posts to mapped Pages and stops when the logged-in account does
    not match. A Page ID, TikTok account or YouTube channel can belong to one profile only."""
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
