"""Auto-save of the videos Muse sends, shared by FoxProfile and the Muse2Tele bot via Muse2Tele's .env.

MUSE_SAVE_VIDEOS     "1" (default) / "0": the bot keeps a copy of every video it fetches from
                     a Muse chat, also the ones it holds back from Telegram or that are too big
                     for Telegram.
MUSE_SAVE_VIDEO_DIR  base folder; each video goes to <folder>/<Muse profile>/<file name>.
                     Default E:/Videos/Downloaded (so Muse2 -> E:/Videos/Downloaded/Muse2/).

The bot re-reads .env whenever it changes, so a change applies at once without a restart.
Paths are saved with forward slashes (see upload_dirs: python-dotenv reads backslashes as escapes).
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from dataclasses import dataclass

from .logging import get_logger
from .upload_dirs import MAX_PATH_LENGTH, _read_env, _write_env, env_file

logger = get_logger("video_save")

ENABLED_KEY = "MUSE_SAVE_VIDEOS"
DIR_KEY = "MUSE_SAVE_VIDEO_DIR"
DEFAULT_DIR = "E:/Videos/Downloaded"
OFF_VALUES = {"0", "false", "no", "off"}


class VideoSaveError(ValueError):
    """The requested folder cannot be used."""


@dataclass
class VideoSave:
    env_file: str
    enabled: bool
    save_dir: str
    default_dir: str
    custom: bool  # False = MUSE_SAVE_VIDEO_DIR not set, DEFAULT_DIR applies


def current() -> VideoSave:
    env = _read_env()
    raw_dir = (env.get(DIR_KEY) or "").strip()
    return VideoSave(
        env_file=str(env_file()),
        enabled=(env.get(ENABLED_KEY) or "1").strip().lower() not in OFF_VALUES,
        save_dir=raw_dir or DEFAULT_DIR,
        default_dir=DEFAULT_DIR,
        custom=bool(raw_dir),
    )


def _check_folder(value: str) -> pathlib.Path:
    if len(value) > MAX_PATH_LENGTH or "\x00" in value or os.pathsep in value:
        raise VideoSaveError(f"Invalid folder path: {value}")
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        raise VideoSaveError(f"Enter a full folder path, e.g. {DEFAULT_DIR}: {value}")
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as e:
        raise VideoSaveError(f"Cannot write to {value}: {e.strerror or e}") from e
    return path.resolve()


def save(enabled: bool, save_dir: str | None) -> VideoSave:
    """Turn auto-save on / off and choose the base folder (empty = DEFAULT_DIR).

    When it is on, the folder is created and checked for writing now rather than
    surfacing later as videos that silently fail to save.
    """
    value = (save_dir or "").strip()
    if enabled:
        _check_folder(value or DEFAULT_DIR)
    elif value:
        path = pathlib.Path(value).expanduser()
        if not path.is_absolute() or len(value) > MAX_PATH_LENGTH or "\x00" in value:
            raise VideoSaveError(f"Enter a full folder path, e.g. {DEFAULT_DIR}: {value}")
    _write_env(
        {
            ENABLED_KEY: "1" if enabled else "0",
            DIR_KEY: pathlib.Path(value).expanduser().as_posix() if value else None,
        }
    )
    logger.info(
        "Video auto-save %s (%s) saved to %s",
        "on" if enabled else "off",
        value or DEFAULT_DIR,
        env_file(),
    )
    return current()
