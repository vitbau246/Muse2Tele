"""Muse2Tele self-update, wrapping <Muse2Tele>/updater.py.

check: cached (30 min; 5 min after an error), compares the installed commit with GitHub.
apply: copies updater.py to a temp folder and starts it detached. It stops the profiles
through this API, stops FoxProfile/bot/AutoPost, updates the code while keeping every data
folder, then runs start_all.bat again, so this process does not outlive the update.
Outside Muse2Tele (no updater.py above the working directory) the feature is off.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType

from .config import API_PORT
from .logging import get_logger

logger = get_logger("app_update")

CHECK_TTL = 1800
ERROR_TTL = 300
BUSY_STATES = ("starting", "checking", "preparing", "stopping", "applying", "installing", "restarting")

_lock = threading.Lock()
_cache: dict | None = None
_cache_at = 0.0


def root() -> pathlib.Path | None:
    cwd = pathlib.Path.cwd().resolve()
    for d in (cwd, *cwd.parents):
        if (d / "updater.py").is_file() and (d / "start_all.bat").is_file():
            return d
    return None


def _module(r: pathlib.Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("muse2tele_updater", r / "updater.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_update(r: pathlib.Path | None = None) -> dict | None:
    """The latest apply run, from .update/status.json."""
    r = r or root()
    if not r:
        return None
    try:
        data = json.loads((r / ".update" / "status.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def busy(r: pathlib.Path | None = None) -> bool:
    st = last_update(r)
    if not st or st.get("state") not in BUSY_STATES:
        return False
    try:
        age = time.time() - time.mktime(time.strptime(st["at"][:19], "%Y-%m-%dT%H:%M:%S"))
    except (KeyError, ValueError):
        return False
    return age < 900  # a run that died stops counting as busy after 15 minutes


def status(force: bool = False) -> dict:
    """{supported, available, mode, local_sha, remote, changes, error, note, last_update, busy}."""
    global _cache, _cache_at
    r = root()
    if not r:
        return {"supported": False, "available": False}
    with _lock:
        ttl = ERROR_TTL if (_cache or {}).get("error") else CHECK_TTL
        if force or _cache is None or time.time() - _cache_at > ttl:
            try:
                _cache = _module(r).check(r)
            except Exception as e:  # a broken updater.py must not break the dashboard
                logger.warning("Update check failed: %s", e)
                _cache = {"available": False, "error": str(e)}
            _cache_at = time.time()
        result = dict(_cache)
    result.update(supported=True, last_update=last_update(r), busy=busy(r))
    return result


def apply() -> dict:
    """Start the detached updater; returns the status it starts with."""
    r = root()
    if not r:
        raise RuntimeError("Self-update is only available in Muse2Tele")
    if busy(r):
        raise RuntimeError("An update is already running")
    work = pathlib.Path(tempfile.mkdtemp(prefix="muse2tele-update-"))
    # Run a copy: the update replaces updater.py itself.
    shutil.copy2(r / "updater.py", work / "updater.py")
    (r / ".update").mkdir(exist_ok=True)
    first = {"state": "starting", "message": "Đang bắt đầu cập nhật...",
             "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (r / ".update" / "status.json").write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    cmd = [sys.executable, str(work / "updater.py"), "apply", "--root", str(r),
           "--fox-url", f"http://127.0.0.1:{API_PORT}", "--fox-pid", str(os.getpid())]
    subprocess.Popen(cmd, cwd=work, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info("Started updater: %s", " ".join(cmd))
    return first
