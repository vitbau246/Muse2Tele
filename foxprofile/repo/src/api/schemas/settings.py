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


class VideoSaveResponse(BaseModel):
    env_file: str = Field(description=".env the setting is saved to")
    enabled: bool = Field(description="MUSE_SAVE_VIDEOS: the bot keeps a copy of every video Muse sends")
    save_dir: str = Field(description="MUSE_SAVE_VIDEO_DIR: base folder; videos go to <folder>/<Muse profile>/")
    default_dir: str = Field(description="Folder used when MUSE_SAVE_VIDEO_DIR is not set")
    custom: bool = Field(description="False = not set, default_dir applies")


class VideoSaveUpdate(BaseModel):
    enabled: bool = Field(description="Save every video Muse sends")
    save_dir: str | None = Field(default=None, description="Full folder path; empty = default_dir")


class MuseTeamResponse(BaseModel):
    file: str = Field(description="muse_team.json the settings are saved to")
    id: str = Field(default="default", description="Team id (each team works in its own Telegram group)")
    name: str = Field(default="", description="Team name")
    is_default: bool = Field(default=True, description="Default team: gets every profile no other team lists")
    team_profiles: list[str] | None = Field(
        default=None, description="Profiles in this team's group; null on the default team (= the rest)"
    )
    group_profiles: list[str] = Field(
        default_factory=list, description="Profiles in this team's group right now (resolved team_profiles)"
    )
    group: int | None = Field(default=None, description="Telegram group the bot linked to this team")
    group_title: str = Field(default="", description="Title of that group")
    teams: list[dict] = Field(default_factory=list, description="Every team, short (id, name, default, group...)")
    assigned: dict[str, str] = Field(default_factory=dict, description="Profile -> team id that lists it")
    skill: str = Field(default="", description="Skill pack the team was set up from")
    features: list[str] = Field(default_factory=list, description='Bot workflows the team uses ("video")')
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
    reset_full: bool = Field(
        default=False, description="The last wipe is a full team reset (tasks, samples, character sets too)"
    )
    reset_targets: list[str] = Field(default_factory=list, description="Muses a full reset wipes")
    reset_pending: bool = Field(default=False, description="The bot has not started the last wipe yet")
    detached: dict[str, dict] = Field(
        default_factory=dict,
        description='Members taken out of the team: profile -> {"id", "wipe"} (the bot acts once per id)',
    )
    muse_profiles: list[str] = Field(
        default_factory=list, description="Profiles the bot runs as a Muse (they have a Telegram topic)"
    )
    bot_installed: bool
    profiles: list[str] = Field(default_factory=list, description="Profiles that can join the team")
    langs: dict[str, str] = Field(default_factory=dict, description="Language code -> name")
    templates: list[dict] = Field(
        default_factory=list,
        description="Skill packs: id, label, description, features, settings (video settings), chief "
        "(context for the chief), member (context for every member), member_role, license, source",
    )


class MuseTeamUpdate(BaseModel):
    name: str | None = Field(default=None, description="Team name; null = keep")
    team_profiles: list[str] | None = Field(
        default=None, description="Profiles in the team's group (not the default team); null = keep"
    )
    skill: str | None = Field(default=None, description='Skill pack id ("" = none); null = keep')
    features: list[str] | None = Field(
        default=None, description='Bot workflows ("video"); null = keep, or those of the new skill pack'
    )
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
    reset_targets: list[str] | None = Field(
        default=None,
        description="With reset_data: wipe only these Muses (e.g. those whose context changed); "
        "empty = the chief and the whole team",
    )
    reset_team_data: bool = Field(
        default=False,
        description="With reset_data: also drop the team's tasks, sample videos and scripts and archive "
        "the locked character sets (use when switching to another template)",
    )


class MuseTeamReset(BaseModel):
    profiles: list[str] = Field(
        default_factory=list,
        description="Muses whose data the bot wipes (chief + team members). Every team setting "
        "goes back to its default and the bot clears the team's tasks, sample videos, scripts "
        "and locked character sets. Cannot be undone.",
    )


class MuseTeamCreate(BaseModel):
    name: str = Field(description="Team name")
    team_profiles: list[str] = Field(default_factory=list, description="Profiles in the team's group")


class MuseTeamDetach(BaseModel):
    profile: str = Field(description="Team member (not the chief) to take out of the team")
    wipe: bool = Field(
        default=False,
        description="Also wipe its Muse data (chats, files, artifacts, topic messages) so nothing of "
        "the team stays in its memory. Cannot be undone. False: the bot tells the Muse it left the team.",
    )


class PostMapPage(BaseModel):
    id: str = Field(description="Facebook Page ID (the asset_id in Meta Business Suite links)")
    name: str = ""


class PostMapEntry(BaseModel):
    fanpages: list[PostMapPage] = Field(default_factory=list, description="Pages this profile posts to")
    tiktok: str = Field(default="", description="TikTok username this profile posts with (no @)")
    youtube: str = Field(default="", description="YouTube channel handle this profile posts to (no @)")
    max_per_day: int = Field(
        default=0, description="Posts per Page / TikTok account / YouTube channel a day; 0 = no limit"
    )
    hours: str = Field(default="", description='Posting hours like "11-13, 19-23"; empty = any time')
    caption_lang: str = Field(default="", description="Language code of the caption the team bot asks for")


class PostMapRow(BaseModel):
    name: str
    auto_post_fanpage: bool
    auto_post_tiktok: bool
    auto_post_youtube: bool = False
    known_pages: list[PostMapPage] = Field(
        default_factory=list, description="Pages fanpage_post.py last found for this profile"
    )
    known_tiktok: str = Field(default="", description="TikTok account last seen logged in (account check)")
    known_youtube: list[dict] = Field(
        default_factory=list, description="YouTube channels ({name, handle}) the logged-in Google account manages"
    )
    check: dict | None = Field(
        default=None, description="Last account check (check_accounts.py): running, at, fanpage, tiktok"
    )


class PostMapResponse(BaseModel):
    file: str = Field(description="post_map.json the map is saved to")
    installed: bool = Field(description="social_post folder found next to FoxProfile")
    profiles: dict[str, PostMapEntry] = Field(
        description="Profile -> its Pages, TikTok account and YouTube channel"
    )
    rows: list[PostMapRow] = Field(default_factory=list, description="Every profile, for the table")
    langs: dict[str, str] = Field(default_factory=dict, description="Language code -> name")


class PostMapUpdate(BaseModel):
    profiles: dict[str, dict] = Field(
        description='Profile -> {"fanpages": [IDs] or "id1, id2", "tiktok": "handle or profile link", '
        '"youtube": "channel handle or link", "max_per_day": 0-100, "hours": "11-13, 19-23", '
        '"caption_lang": code}; profiles left out are removed'
    )
