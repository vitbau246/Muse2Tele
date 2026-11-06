from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    download_dir: str = Field(description="Folder downloads are saved to right now")
    default_download_dir: str
    custom: bool = Field(description="True when the folder was chosen in the panel")


class SettingsUpdate(BaseModel):
    download_dir: str | None = Field(
        default=None, description="Full folder path; empty restores the default"
    )


class UploadDirsResponse(BaseModel):
    env_file: str = Field(description=".env the folders are saved to")
    upload_dirs: list[str] = Field(description="FOXPROFILE_UPLOAD_DIRS: folders browsers may attach files from")
    muse_upload_dir: str = Field(description="MUSE_UPLOAD_DIR: where the Telegram bot saves incoming files")
    muse_default_dir: str = Field(description="The bot's default MUSE_UPLOAD_DIR")
    muse_custom: bool = Field(description="False = not set, the bot's default folder applies")
    muse_inside: bool = Field(description="MUSE_UPLOAD_DIR lies inside one of upload_dirs")
    bot_installed: bool


class UploadDirsUpdate(BaseModel):
    upload_dirs: list[str] = Field(description="Full folder paths; at least one")
    muse_upload_dir: str | None = Field(default=None, description="Full folder path; empty = bot default")


class MuseTeamResponse(BaseModel):
    file: str = Field(description="muse_team.json the settings are saved to")
    mode: str = Field(
        description='"solo": each Muse works alone; "chief": one Muse leads the others'
    )
    chief: str = Field(description="Profile of the chief Muse (answers in the General topic)")
    approval: str = Field(
        description='"manual": owner approves each task in Telegram; "auto": sent at once'
    )
    roles: dict[str, str] = Field(description="Profile -> its role, told to the chief")
    task_lang: str = Field(default="", description="Language code the chief writes tasks in; empty = no rule")
    post_mode: str = Field(default="ask", description='Passed videos: "off", "ask" (Post buttons) or "auto"')
    post_profile: str = Field(default="", description="Default channel (profile) passed videos are queued for")
    excluded: list[str] = Field(description="Profiles left out of the team")
    setup: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description='Profile -> {"lang": code, "context": text}: answer language and long-term context '
        "the bot sends that Muse (chief included)",
    )
    pass_score: int = Field(description="Lowest passing score out of 10; below it the bot asks for a redo")
    max_rounds: int = Field(description="Redo rounds per task (per video for video tasks)")
    max_new_per_hour: int = Field(description="New tasks the chief may hand out per hour")
    quiet_minutes: int = Field(description="Silent minutes before a working Muse is reminded / reported")
    overdue_minutes: int = Field(description="Minutes after which a running task is flagged")
    one_video: bool = Field(description="Video tasks: one video at a time, next only after it passes")
    show_failed_media: bool = Field(description="Also post images / videos that have not passed to Telegram")
    reset_id: str = Field(description="Id of the last Muse data wipe asked for (the bot runs each once)")
    bot_installed: bool
    profiles: list[str] = Field(default_factory=list, description="Profiles that can join the team")
    langs: dict[str, str] = Field(default_factory=dict, description="Language code -> name")
    templates: list[dict[str, str]] = Field(
        default_factory=list, description="Ready-made contexts: id, label, text"
    )


class MuseTeamUpdate(BaseModel):
    mode: str = Field(description='"solo" or "chief"')
    chief: str | None = Field(default=None, description="Profile name; required in chief mode")
    approval: str = Field(default="manual", description='"manual" or "auto"')
    roles: dict[str, str] = Field(default_factory=dict)
    task_lang: str | None = Field(default=None, description="Language code from langs; empty string = no rule; null = keep")
    post_mode: str | None = Field(default=None, description='"off", "ask" or "auto"; null = keep')
    post_profile: str | None = Field(default=None, description="Default channel profile; empty = none; null = keep")
    excluded: list[str] = Field(
        default_factory=list, description="Profiles left out of the team; others are in it"
    )
    pass_score: int | None = Field(default=None, ge=1, le=10, description="1-10; empty = keep")
    max_rounds: int | None = Field(default=None, ge=1, le=10, description="1-10; empty = keep")
    max_new_per_hour: int | None = Field(default=None, ge=1, le=200, description="1-200; empty = keep")
    quiet_minutes: int | None = Field(default=None, ge=1, le=60, description="1-60; empty = keep")
    overdue_minutes: int | None = Field(default=None, ge=5, le=600, description="5-600; empty = keep")
    one_video: bool | None = Field(default=None, description="empty = keep")
    show_failed_media: bool | None = Field(default=None, description="empty = keep")
    setup: dict[str, dict[str, str]] | None = Field(
        default=None,
        description='Profile -> {"lang": code from langs, "context": text up to 6000 chars}; empty = keep',
    )
    reset_data: bool = Field(
        default=False,
        description="Chief mode: wipe the Muse data (chats, files, artifacts) of the chief and every "
        "team member once, with their Telegram topics. Cannot be undone.",
    )


class PostMapPage(BaseModel):
    id: str = Field(description="Facebook Page ID (the asset_id in Meta Business Suite links)")
    name: str = ""


class PostMapEntry(BaseModel):
    fanpages: list[PostMapPage] = Field(default_factory=list, description="Pages this profile posts to")
    tiktok: str = Field(default="", description="TikTok username this profile posts with (no @)")
    max_per_day: int = Field(default=0, description="Posts per Page / TikTok account a day; 0 = no limit")
    hours: str = Field(default="", description='Posting hours like "11-13, 19-23"; empty = any time')
    caption_lang: str = Field(default="", description="Language code of the caption the team bot asks for")


class PostMapRow(BaseModel):
    name: str
    auto_post_fanpage: bool
    auto_post_tiktok: bool
    known_pages: list[PostMapPage] = Field(
        default_factory=list, description="Pages fanpage_post.py last found for this profile"
    )
    check: dict | None = Field(
        default=None, description="Last account check (check_accounts.py): running, at, fanpage, tiktok"
    )


class PostMapResponse(BaseModel):
    file: str = Field(description="post_map.json the map is saved to")
    installed: bool = Field(description="social_post folder found next to FoxProfile")
    profiles: dict[str, PostMapEntry] = Field(description="Profile -> its Pages and TikTok account")
    rows: list[PostMapRow] = Field(default_factory=list, description="Every profile, for the table")
    langs: dict[str, str] = Field(default_factory=dict, description="Language code -> name")


class PostMapUpdate(BaseModel):
    profiles: dict[str, dict] = Field(
        description='Profile -> {"fanpages": [IDs] or "id1, id2", "tiktok": "handle or profile link", '
        '"max_per_day": 0-100, "hours": "11-13, 19-23", "caption_lang": code}; profiles left out are removed'
    )
