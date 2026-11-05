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
