"""Posting map for Muse2Tele auto-post: which Facebook Pages (by Page ID) and which TikTok account
each FoxProfile profile may post to, plus how much and when. Kept in social_post/data/post_map.json:

    {"profiles": {"<profile>": {"fanpages": [{"id": "1234567890", "name": "Phim 365"}],
                                "tiktok": "handle", "max_per_day": 3, "hours": "11-13, 19-23",
                                "caption_lang": "en"}}}

social_post/auto_post.py posts only to the Pages listed here (never to every Page the account
manages), at most max_per_day posts per Page / TikTok account a day (0 = no limit), only inside
the hours (empty = any time), and never the same video twice to the same Page / account.
fanpage_post.py picks each Page by its ID and stops if the logged-in account does not manage it;
tiktok_post.py stops when the logged-in TikTok account is not the one listed. caption_lang: the
Muse team bot asks for a caption in that language for videos posted through this profile.
A Page ID or TikTok account can belong to one profile only.

"Check accounts" runs social_post/check_accounts.py for one profile in the background: it opens
the profile, lists the Pages the Facebook account manages and reads the TikTok account, without
posting, and writes social_post/data/account_check_<profile>.json.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

from .logging import get_logger
from .muse_team import LANGS
from .upload_dirs import env_file

logger = get_logger("post_map")

FILE_NAME = "post_map.json"
MAX_PAGES = 30
MAX_PER_DAY = 100
CHECK_STALE_SECONDS = 15 * 60
PAGE_ID_RE = re.compile(r"^\d{5,25}$")
TIKTOK_RE = re.compile(r"^[a-z0-9._]{2,24}$")
HOURS_RE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})$")


class PostMapError(ValueError):
    """The posting map cannot be saved."""


@dataclass
class PostMap:
    file: str
    profiles: dict[str, dict] = field(default_factory=dict)
    installed: bool = False


def data_dir():
    return env_file().parent / "social_post" / "data"


def config_file():
    return data_dir() / FILE_NAME


def _safe(profile: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in profile)


def known_pages(profile: str) -> list[dict[str, str]]:
    """Pages fanpage_post.py last found for this profile (social_post/data/fb_pages_<profile>.json)."""
    try:
        raw = json.loads((data_dir() / f"fb_pages_{_safe(profile)}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [
        {"id": str(p.get("asset_id")), "name": str(p.get("name") or "")}
        for p in raw if isinstance(p, dict) and p.get("asset_id")
    ]


def tiktok_handle(raw: object) -> str:
    """'@Abc.Def', 'https://www.tiktok.com/@abc.def?lang=vi' -> 'abc.def'."""
    text = str(raw or "").strip()
    m = re.search(r"tiktok\.com/@([^/?#\s]+)", text)
    return (m.group(1) if m else text).lstrip("@").strip().lower()


def page_ids(raw: object) -> list[str]:
    """Page IDs from a list or from text separated by commas, spaces or new lines; Facebook
    links like facebook.com/profile.php?id=123 are read too."""
    items = raw if isinstance(raw, list) else re.split(r"[\s,;]+", str(raw or ""))
    out: list[str] = []
    for item in items:
        text = str(item.get("id") if isinstance(item, dict) else item).strip()
        m = re.search(r"[?&](?:id|asset_id)=(\d+)", text)
        text = m.group(1) if m else text
        if text and text not in out:
            out.append(text)
    return out


def hours(raw: object) -> str:
    """'8-11,19 - 23' -> '8-11, 19-23'; '' = any time. Raises PostMapError on a bad range.
    A range runs from the start hour up to (not including) the end hour; 22-2 crosses midnight."""
    out = []
    for part in [p for p in re.split(r"[,;]+", str(raw or "")) if p.strip()]:
        m = HOURS_RE.match(part.strip())
        if not m or not (0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 24) or m.group(1) == m.group(2):
            raise PostMapError(f"Posting hours must look like 11-13, 19-23 (got {part.strip()[:20]})")
        out.append(f"{int(m.group(1))}-{int(m.group(2))}")
    return ", ".join(out)


def _clean(raw: object) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, item in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(item, dict):
            continue
        pages = [
            {"id": str(p.get("id")), "name": str(p.get("name") or "")}
            for p in item.get("fanpages") or [] if isinstance(p, dict) and PAGE_ID_RE.match(str(p.get("id")))
        ]
        tiktok = tiktok_handle(item.get("tiktok"))
        tiktok = tiktok if TIKTOK_RE.match(tiktok) else ""
        try:
            per_day = min(MAX_PER_DAY, max(0, int(item.get("max_per_day") or 0)))
        except (TypeError, ValueError):
            per_day = 0
        try:
            span = hours(item.get("hours"))
        except PostMapError:
            span = ""
        lang = str(item.get("caption_lang") or "")
        if str(name).strip() and (pages or tiktok or per_day or span or lang in LANGS and lang):
            out[str(name).strip()] = {"fanpages": pages, "tiktok": tiktok, "max_per_day": per_day,
                                      "hours": span, "caption_lang": lang if lang in LANGS else ""}
    return out


def current() -> PostMap:
    path = config_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    profiles = raw.get("profiles") if isinstance(raw, dict) else {}
    return PostMap(file=str(path), profiles=_clean(profiles), installed=path.parent.parent.is_dir())


def save(profiles: dict[str, dict]) -> PostMap:
    """profiles: name -> {"fanpages": IDs (list or text), "tiktok": handle or link, "max_per_day",
    "hours", "caption_lang"}. Page names are filled in from the Pages last found for that profile."""
    clean: dict[str, dict] = {}
    owner_page: dict[str, str] = {}
    owner_tiktok: dict[str, str] = {}
    for name, item in (profiles or {}).items():
        name = str(name).strip()
        if not name or not isinstance(item, dict):
            continue
        ids = page_ids(item.get("fanpages"))
        if len(ids) > MAX_PAGES:
            raise PostMapError(f"{name}: at most {MAX_PAGES} Pages")
        bad = [i for i in ids if not PAGE_ID_RE.match(i)]
        if bad:
            raise PostMapError(f"{name}: not a Page ID (digits only): {', '.join(bad)[:80]}")
        tiktok = tiktok_handle(item.get("tiktok"))
        if tiktok and not TIKTOK_RE.match(tiktok):
            raise PostMapError(f"{name}: not a TikTok username: {tiktok[:40]}")
        try:
            per_day = int(item.get("max_per_day") or 0)
        except (TypeError, ValueError):
            raise PostMapError(f"{name}: posts per day must be a whole number") from None
        if not 0 <= per_day <= MAX_PER_DAY:
            raise PostMapError(f"{name}: posts per day must be between 0 and {MAX_PER_DAY}")
        span = hours(item.get("hours"))
        lang = str(item.get("caption_lang") or "")
        if lang not in LANGS:
            raise PostMapError(f"{name}: unknown caption language {lang[:10]}")
        for i in ids:
            if i in owner_page:
                raise PostMapError(f"Page {i} is mapped to both {owner_page[i]} and {name}")
            owner_page[i] = name
        if tiktok:
            if tiktok in owner_tiktok:
                raise PostMapError(f"TikTok @{tiktok} is mapped to both {owner_tiktok[tiktok]} and {name}")
            owner_tiktok[tiktok] = name
        if not (ids or tiktok or per_day or span or lang):
            continue
        names = {p["id"]: p["name"] for p in known_pages(name)}
        clean[name] = {"fanpages": [{"id": i, "name": names.get(i, "")} for i in ids], "tiktok": tiktok,
                       "max_per_day": per_day, "hours": span, "caption_lang": lang}
    path = config_file()
    if not path.parent.parent.is_dir():
        raise PostMapError(f"social_post folder not found: {path.parent.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"profiles": clean}, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    logger.info("Posting map saved to %s (%d profiles)", path, len(clean))
    return current()


# ---------- account check (social_post/check_accounts.py) ----------

def check_file(profile: str):
    return data_dir() / f"account_check_{_safe(profile)}.json"


def check_result(profile: str) -> dict | None:
    """Last account check of a profile: {"running", "at", "fanpage": {...}, "tiktok": {...}} or None.
    A run that never finished (killed) counts as done after CHECK_STALE_SECONDS."""
    try:
        raw = json.loads(check_file(profile).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("running") and time.time() - float(raw.get("started") or 0) > CHECK_STALE_SECONDS:
        raw.update(running=False, error="Check did not finish")
    return raw


def start_check(profile: str) -> dict:
    """Start check_accounts.py for one profile in the background (opens the profile, posts nothing)."""
    script = data_dir().parent / "check_accounts.py"
    if not script.is_file():
        raise PostMapError(f"Not found: {script}")
    old = check_result(profile)
    if old and old.get("running"):
        raise PostMapError(f"{profile} is being checked already")
    data_dir().mkdir(parents=True, exist_ok=True)
    state = {"running": True, "started": time.time(), "at": time.strftime("%Y-%m-%d %H:%M")}
    check_file(profile).write_text(json.dumps(state), encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, str(script), "--profile", profile],
        cwd=script.parent,
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    logger.info("Account check started for %s", profile)
    return state
