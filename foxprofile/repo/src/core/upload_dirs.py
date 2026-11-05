"""Upload folders shared by FoxProfile and the Muse2Tele bot, kept in Muse2Tele's .env.

FOXPROFILE_UPLOAD_DIRS  folders the browsers may attach files from (the REST "upload"
                        action refuses anything else). Several folders are separated by ";"
                        on Windows (":" elsewhere). Read by each browser process when it
                        starts, so a change applies to profiles launched afterwards.
MUSE_UPLOAD_DIR         folder the Telegram bot saves files from Telegram into before it
                        sends them to Muse. It must sit inside one of the upload folders,
                        otherwise FoxProfile refuses to attach them. The bot reads it at start.

Both are saved as absolute paths with forward slashes: .env is read by python-dotenv, which
treats backslashes in quoted values as escapes, and Windows accepts "/" everywhere.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
from dataclasses import dataclass, field

from .logging import get_logger

logger = get_logger("upload_dirs")

UPLOAD_DIRS_KEY = "FOXPROFILE_UPLOAD_DIRS"
MUSE_DIR_KEY = "MUSE_UPLOAD_DIR"
MAX_PATH_LENGTH = 400


class UploadDirsError(ValueError):
    """The requested folders cannot be used."""


@dataclass
class UploadDirs:
    env_file: str
    upload_dirs: list[str] = field(default_factory=list)
    muse_upload_dir: str = ""
    muse_default_dir: str = ""
    muse_custom: bool = False  # False = MUSE_UPLOAD_DIR not set, the bot's default applies
    muse_inside: bool = False  # MUSE_UPLOAD_DIR lies inside one of upload_dirs
    bot_installed: bool = False


def env_file() -> pathlib.Path:
    """Muse2Tele's .env: FOXPROFILE_ENV_FILE, else the nearest .env (or .env.example)
    above the working directory, else ./.env."""
    explicit = os.environ.get("FOXPROFILE_ENV_FILE", "").strip()
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    cwd = pathlib.Path.cwd().resolve()
    for name in (".env", ".env.example"):
        for folder in (cwd, *cwd.parents):
            if (folder / name).is_file():
                return folder / ".env"
    return cwd / ".env"


def _root() -> pathlib.Path:
    return env_file().parent


def _bot_dir() -> pathlib.Path:
    return _root() / "muse_telebot"


def _resolve(value: str, base: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(value.strip()).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def muse_default() -> pathlib.Path:
    """Same default as muse_telebot.py."""
    return (_root() / "Videos" / "downloads" / "muse_telebot").resolve()


def _inside(path: pathlib.Path, roots: list[pathlib.Path]) -> bool:
    return any(path == r or path.is_relative_to(r) for r in roots)


def current() -> UploadDirs:
    """The folders in effect right now (FoxProfile's environment, then the bot's .env)."""
    raw = os.environ.get(UPLOAD_DIRS_KEY, "")
    cwd = pathlib.Path.cwd()
    roots = [_resolve(d, cwd) for d in raw.split(os.pathsep) if d.strip()]
    muse_raw = os.environ.get(MUSE_DIR_KEY, "").strip() or _read_env().get(MUSE_DIR_KEY, "")
    muse = _resolve(muse_raw, _bot_dir()) if muse_raw else muse_default()
    return UploadDirs(
        env_file=str(env_file()),
        upload_dirs=[str(r) for r in roots],
        muse_upload_dir=str(muse),
        muse_default_dir=str(muse_default()),
        muse_custom=bool(muse_raw),
        muse_inside=_inside(muse, roots),
        bot_installed=_bot_dir().is_dir(),
    )


def _check_folder(value: str) -> pathlib.Path:
    value = value.strip()
    if len(value) > MAX_PATH_LENGTH or "\x00" in value or os.pathsep in value:
        raise UploadDirsError(f"Invalid folder path: {value}")
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        raise UploadDirsError(f"Enter a full folder path, e.g. D:/Muse2Tele/Videos/downloads: {value}")
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
    except OSError as e:
        raise UploadDirsError(f"Cannot write to {value}: {e.strerror or e}") from e
    return path.resolve()


def save(upload_dirs: list[str], muse_upload_dir: str | None) -> UploadDirs:
    """Check, create and save both settings; an empty muse_upload_dir restores the bot's default.

    Refuses a Muse folder outside the upload folders: the bot would save files there that
    FoxProfile then refuses to attach.
    """
    roots: list[pathlib.Path] = []
    for value in upload_dirs:
        if value.strip():
            path = _check_folder(value)
            if path not in roots:
                roots.append(path)
    if not roots:
        raise UploadDirsError("Add at least one upload folder")

    muse_value = (muse_upload_dir or "").strip()
    muse = _check_folder(muse_value) if muse_value else muse_default()
    if _bot_dir().is_dir() and not _inside(muse, roots):
        raise UploadDirsError(f"{MUSE_DIR_KEY} must be inside one of the upload folders: {muse}")

    joined = os.pathsep.join(r.as_posix() for r in roots)
    _write_env({UPLOAD_DIRS_KEY: joined, MUSE_DIR_KEY: muse.as_posix() if muse_value else None})
    # Browsers launched from now on inherit this process's environment.
    os.environ[UPLOAD_DIRS_KEY] = joined
    if muse_value:
        os.environ[MUSE_DIR_KEY] = muse.as_posix()
    else:
        os.environ.pop(MUSE_DIR_KEY, None)
    logger.info("Upload folders saved to %s", env_file())
    return current()


def _quote(value: str) -> str:
    return f"'{value}'" if any(c in value for c in " #'\"") else value


def _read_env() -> dict[str, str]:
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    path = env_file()
    if not path.is_file():
        return {}
    return {k: v or "" for k, v in dotenv_values(path).items()}


def _write_env(values: dict[str, str | None]) -> None:
    """Set (or, for None, remove) KEY=value lines in .env, keeping every other line."""
    path = env_file()
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    out: list[str] = []
    done: set[str] = set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in values:
            if key in done or values[key] is None:
                continue
            out.append(f"{key}={_quote(values[key])}")
            done.add(key)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in done and value is not None:
            out.append(f"{key}={_quote(value)}")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)
