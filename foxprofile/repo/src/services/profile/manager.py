import contextlib
import json
import os
import pathlib
import shutil
import threading
import time

from ...core.config import DATA_DIR, PROFILES_FILE
from ...core.logging import get_logger
from ...models.profile import ENGINES, Profile
from ..browser import fingerprint
from ...utils.validation import (
    valid_or_none,
    validate_locale,
    validate_profile_name,
    validate_timezone,
)
from .transfer import export_to_zip, import_from_zip, read_profile_meta

logger = get_logger("profile.manager")


def _engine_or_default(value: object) -> str:
    return value if value in ENGINES else "camoufox"


def _replace(src: pathlib.Path, dst: pathlib.Path, attempts: int = 10) -> None:
    """os.replace, retried briefly: on Windows it fails with a sharing violation
    while another process (antivirus, indexer, a reader) has the target open."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


# Left out of a clone: browser locks (they would block the clone's first launch) and
# caches (rebuilt on launch). Camoufox/Firefox names first, then the Chrome engine's.
_CLONE_SKIP = shutil.ignore_patterns(
    "parent.lock",
    "lock",
    ".parentlock",
    "cache2",
    "startupCache",
    "shader-cache",
    "crashes",
    "minidumps",
    "SingletonLock",
    "SingletonSocket",
    "SingletonCookie",
    "lockfile",
    "Cache",
    "Code Cache",
    "GPUCache",
    "*.tmp",
)


def _copy_profile_data(src: pathlib.Path, dst: pathlib.Path) -> int:
    """Copy a profile's data dir into the existing *dst*; return how many files could
    not be read (held open by the running browser)."""
    try:
        shutil.copytree(src, dst, ignore=_CLONE_SKIP, dirs_exist_ok=True)
    except shutil.Error as e:
        for failed in e.args[0]:
            logger.warning("Clone skipped %s: %s", failed[0], failed[2])
        return len(e.args[0])
    return 0


class ProfileManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.profiles: dict[str, Profile] = {}
        self._load_profiles()
        pathlib.Path(DATA_DIR).mkdir(exist_ok=True, parents=True)

    def _find_by_casefold(self, name: str) -> str | None:
        """Return the existing profile key that case-folds to *name*, or None.

        Used to enforce case-insensitive uniqueness across all platforms so that
        a profiles.json exported on Linux (case-sensitive FS) can be imported on
        Windows/macOS (case-insensitive FS) without data-dir collisions.
        """
        lower = name.casefold()
        return next((k for k in self.profiles if k.casefold() == lower), None)

    def _data_path(self, name: str) -> str:
        return os.path.join(DATA_DIR, name)

    def _load_profiles(self) -> None:
        if pathlib.Path(PROFILES_FILE).exists():
            try:
                with pathlib.Path(PROFILES_FILE).open(encoding="utf-8") as f:
                    data = json.load(f)
                    for name, p_data in data.items():
                        if not validate_profile_name(name)[0] or p_data.get("name") != name:
                            logger.warning("Skipping profile with unsafe name: %r", name)
                            continue
                        clean_data = {
                            "name": p_data.get("name"),
                            "proxy": p_data.get("proxy"),
                            "os_type": p_data.get(
                                "os_type",
                                p_data.get("config", {}).get("os", "windows"),
                            ),
                            "timezone": valid_or_none(p_data.get("timezone"), validate_timezone),
                            "locale": valid_or_none(p_data.get("locale"), validate_locale),
                            "engine": _engine_or_default(p_data.get("engine")),
                            "auto_post_fanpage": p_data.get("auto_post_fanpage") is True,
                            "auto_post_tiktok": p_data.get("auto_post_tiktok") is True,
                        }
                        self.profiles[name] = Profile(**clean_data)
                logger.info("Loaded %d profiles", len(self.profiles))
            except Exception as e:
                logger.exception("Error loading profiles: %s", e)

    def save_profiles(self) -> None:
        """Atomic write: write to a temp file then os.replace."""
        path = pathlib.Path(PROFILES_FILE)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {name: p.to_dict() for name, p in self.profiles.items()},
                    indent=4,
                ),
                encoding="utf-8",
            )
            _replace(tmp, path)
            logger.debug("Profiles saved")
        except Exception as e:
            logger.exception("Error saving profiles: %s", e)
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def add_profile(
        self,
        name: str,
        proxy: str,
        os_type: str,
        timezone: str | None = None,
        locale: str | None = None,
        engine: str = "camoufox",
    ) -> bool:
        with self._lock:
            if self._find_by_casefold(name) is not None:
                return False
            # Create directory before touching profiles.json so a mkdir failure
            # does not leave an entry with no data dir on disk.
            try:
                pathlib.Path(self._data_path(name)).mkdir(exist_ok=True, parents=True)
            except OSError as e:
                logger.warning("Could not create data dir for %s: %s", name, e)
                return False
            self.profiles[name] = Profile(
                name=name,
                proxy=proxy or None,
                os_type=os_type,
                timezone=timezone or None,
                locale=locale or None,
                engine=engine,
            )
            self.save_profiles()
            logger.info("Created profile: %s", name)
            return True

    def update_profile(
        self,
        original_name: str,
        new_name: str,
        new_proxy: str,
        new_os: str,
        new_timezone: str | None = None,
        new_locale: str | None = None,
    ) -> bool:
        """Replace every field; a None/empty timezone or locale means automatic."""
        with self._lock:
            if original_name not in self.profiles:
                return False

            if new_name != original_name:
                # Case-insensitive uniqueness: a case-only rename of the profile
                # itself is allowed; renaming to another profile's casefold is not.
                conflicting = self._find_by_casefold(new_name)
                if conflicting is not None and conflicting != original_name:
                    return False

            # Rename the data directory BEFORE mutating in-memory state so that
            # an OSError leaves memory and JSON untouched.
            if new_name != original_name:
                old_dir = pathlib.Path(self._data_path(original_name))
                new_dir = pathlib.Path(self._data_path(new_name))
                if old_dir.exists():
                    if new_dir.exists():
                        # On case-insensitive filesystems (Windows/macOS) a
                        # case-only rename sees the target as existing because
                        # both paths point to the same directory entry.  Allow
                        # the rename only in that situation.
                        try:
                            same = old_dir.samefile(new_dir)
                        except OSError:
                            same = False
                        if not same:
                            # Refuse: do NOT delete potential user data.
                            logger.warning(
                                "Cannot rename %s -> %s: target data dir already exists",
                                original_name,
                                new_name,
                            )
                            return False
                    try:
                        old_dir.rename(new_dir)
                    except OSError as e:
                        logger.warning("Could not rename data dir for %s: %s", original_name, e)
                        return False

            profile = self.profiles[original_name]
            profile.name = new_name
            profile.proxy = new_proxy or None
            profile.os_type = new_os
            profile.timezone = new_timezone or None
            profile.locale = new_locale or None

            if new_name != original_name:
                del self.profiles[original_name]
                self.profiles[new_name] = profile

            self.save_profiles()
            logger.info("Updated profile: %s -> %s", original_name, new_name)
            return True

    def set_auto_post(
        self, name: str, fanpage: bool | None = None, tiktok: bool | None = None
    ) -> bool:
        """Turn automatic posting to a Facebook page / TikTok on or off; None keeps the value."""
        with self._lock:
            profile = self.profiles.get(name)
            if profile is None:
                return False
            if fanpage is not None:
                profile.auto_post_fanpage = bool(fanpage)
            if tiktok is not None:
                profile.auto_post_tiktok = bool(tiktok)
            self.save_profiles()
            return True

    def delete_profile(self, name: str) -> bool:
        with self._lock:
            if name not in self.profiles:
                return False
            del self.profiles[name]
            self.save_profiles()
            # Inside the lock: a profile re-created under the same (or, on a
            # case-insensitive file system, a case-variant) name must not have
            # its fresh data dir removed by this delete.
            shutil.rmtree(self._data_path(name), ignore_errors=True)
        logger.info("Deleted profile: %s", name)
        return True

    def clone_profile(
        self,
        source: str,
        new_name: str,
        include_data: bool = True,
        new_fingerprint: bool = True,
    ) -> tuple[bool, str]:
        """Create *new_name* with the settings of *source* and, optionally, a copy of its
        browser data (cookies, logins, tabs). The copy can run while the source is open:
        lock and cache files are skipped, files the browser holds locked are left out.
        new_fingerprint drops the copied fingerprint so the clone becomes another device."""
        valid, msg = validate_profile_name(new_name)
        if not valid:
            return False, msg
        with self._lock:
            if source not in self.profiles:
                return False, "Profile not found"
            if self._find_by_casefold(new_name) is not None:
                return False, f"Profile '{new_name}' already exists"
            src = self.profiles[source]
            src_dir = pathlib.Path(self._data_path(source))
            dst_dir = pathlib.Path(self._data_path(new_name))
            if dst_dir.exists():
                return False, f"Data directory for '{new_name}' already exists"
            # Copy outside the lock (a data dir can be GBs) into a hidden temp dir.
            tmp_dir = dst_dir.with_name(f".{new_name}.clone-tmp")
            try:
                tmp_dir.mkdir(parents=True)
            except OSError as e:
                return False, f"Could not create data dir: {e}"

        skipped = 0
        try:
            if include_data and src_dir.is_dir():
                skipped = _copy_profile_data(src_dir, tmp_dir)
            if new_fingerprint:
                fingerprint.reset(str(tmp_dir))
            with self._lock:
                if self._find_by_casefold(new_name) is not None or dst_dir.exists():
                    raise FileExistsError(f"Profile '{new_name}' already exists")
                _replace(tmp_dir, dst_dir)
                self.profiles[new_name] = Profile(
                    name=new_name,
                    proxy=src.proxy,
                    os_type=src.os_type,
                    timezone=src.timezone,
                    locale=src.locale,
                    engine=src.engine,
                    auto_post_fanpage=src.auto_post_fanpage,
                    auto_post_tiktok=src.auto_post_tiktok,
                )
                self.save_profiles()
        except OSError as e:  # FileExistsError included
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.warning("Clone %s -> %s failed: %s", source, new_name, e)
            return False, str(e)
        logger.info(
            "Cloned profile: %s -> %s (data=%s, skipped=%d)", source, new_name, include_data, skipped
        )
        return True, new_name

    def list_profiles(self) -> list[Profile]:
        with self._lock:
            return list(self.profiles.values())

    def export_profile(
        self,
        name: str,
        export_path: str,
        include_data: bool = True,
    ) -> tuple[bool, str]:
        with self._lock:
            if name not in self.profiles:
                return False, "Profile not found"
            profile = self.profiles[name]
            data_path = self._data_path(name)
        return export_to_zip(profile, data_path, export_path, include_data)

    def import_profile(
        self,
        zip_path: str,
        overwrite: bool = False,
    ) -> tuple[bool, str]:
        # Decide before extracting: an archive must not write into an existing
        # profile's data unless overwriting, and an overwrite that changes the
        # engine starts from an empty directory (the engines' data do not mix).
        meta = read_profile_meta(zip_path) or {}
        name = meta.get("name")
        with self._lock:
            # Case-insensitive collision check: find any existing profile whose
            # name casefolds to the imported name so the check is consistent on
            # all platforms (Windows/macOS case-insensitive FS, Linux sensitive).
            existing_key = self._find_by_casefold(name) if name else None
            if existing_key is not None:
                if not overwrite:
                    return False, f"Profile '{name}' already exists"
                if (meta.get("engine") or "camoufox") != self.profiles[existing_key].engine:
                    shutil.rmtree(self._data_path(existing_key), ignore_errors=True)

            success, result = import_from_zip(zip_path, DATA_DIR)
            if not success:
                return False, result

            profile = result

            # An overwrite under a different case replaces the old entry rather
            # than leaving two names for one data directory.
            if existing_key is not None and existing_key != profile.name:
                old_dir = pathlib.Path(self._data_path(existing_key))
                new_dir = pathlib.Path(self._data_path(profile.name))
                if old_dir.exists() and not (new_dir.exists() and old_dir.samefile(new_dir)):
                    shutil.rmtree(old_dir, ignore_errors=True)
                del self.profiles[existing_key]
            self.profiles[profile.name] = profile
            self.save_profiles()
            logger.info("Registered imported profile: %s", profile.name)
            return True, profile.name
