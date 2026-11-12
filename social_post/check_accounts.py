# -*- coding: utf-8 -*-
"""
Kiem tra tai khoan dang nhap o 1 profile FoxProfile so voi "Bang dang bai" (data\\post_map.json), KHONG dang gi:
  - Facebook: quet lai cac Trang tai khoan quan ly (fanpage_post.py --list-pages), doi chieu Page ID da map.
  - TikTok: doc @username dang dang nhap (tiktok_post.py --check-account), doi chieu tai khoan da map.
  - YouTube: liet ke kenh tai khoan Google quan ly (youtube_post.py --list-channels), doi chieu @kenh da map.
Tai khoan TikTok / kenh YouTube tim thay duoc luu vao data/tt_account_<profile>.json, data/yt_channels_<profile>.json
de dashboard goi y (nhu fb_pages_<profile>.json cua Facebook).
Ket qua ghi vao data\\account_check_<profile>.json (dashboard FoxProfile > Bang dang bai > nut Kiem tra doc file nay).
O nao cua profile trong post_map.json con trong ma chi co 1 lua chon (1 Trang / tai khoan TikTok / 1 kenh) thi duoc
dien luon (fill_map), ket qua "filled" liet ke cac muc da dien.

  python check_accounts.py --profile P1
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

import fanpage_jobs
from fanpage_jobs import BASE_DIR, DATA_DIR

RUN_TIMEOUT = 900
EXIT_NOT_LOGGED_IN = 3
EXIT_FOX = (4, 5)


def safe(profile: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in profile)


def run(args: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run([sys.executable, *args], cwd=BASE_DIR, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, f"Qua {RUN_TIMEOUT}s"


def last_error(out: str) -> str:
    lines = [ln.strip() for ln in out.splitlines() if "LOI" in ln or "DUNG" in ln]
    return (lines[-1] if lines else out.strip().splitlines()[-1] if out.strip() else "")[:300]


def status_of(code: int) -> str:
    return "not_logged_in" if code == EXIT_NOT_LOGGED_IN else "fox_unavailable" if code in EXIT_FOX else "error"


def check_fanpage(profile: str, mapped_ids: list[str]) -> dict:
    code, out = run(["fanpage_post.py", "--profile", profile, "--list-pages"])
    if code != 0:
        return {"status": status_of(code), "message": last_error(out), "found": [], "missing": mapped_ids}
    try:
        pages = json.loads(fanpage_jobs.pages_cache(profile).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pages = []
    found = [{"id": str(p["asset_id"]), "name": p.get("name", "")} for p in pages if p.get("asset_id")]
    missing = [i for i in mapped_ids if i not in {p["id"] for p in found}]
    return {"status": "mismatch" if missing else "ok", "found": found, "missing": missing, "mapped": mapped_ids,
            "message": f"Tài khoản không quản lý Trang: {', '.join(missing)}" if missing else ""}


def save_cache(name: str, profile: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{name}_{safe(profile)}.json").write_text(
        json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), **data}, ensure_ascii=False, indent=1), encoding="utf-8")


def check_tiktok(profile: str, expected: str) -> dict:
    code, out = run(["tiktok_post.py", "--profile", profile, "--check-account", "--expect-account", expected])
    m = re.findall(r"TIKTOK_ACCOUNT=(\S*)", out)
    account = m[-1] if m else ""
    if account:
        save_cache("tt_account", profile, {"account": account})
    if code == 0:
        return {"status": "ok" if expected else "found", "account": account, "expected": expected, "message": ""}
    if code == 6:
        return {"status": "mismatch", "account": account, "expected": expected,
                "message": f"Đang đăng nhập @{account}, bảng ghi @{expected}"}
    return {"status": status_of(code), "account": account, "expected": expected, "message": last_error(out)}


def check_youtube(profile: str, expected: str) -> dict:
    """youtube_post.py --list-channels tu luu data/yt_channels_<profile>.json."""
    code, out = run(["youtube_post.py", "--profile", profile, "--list-channels"])
    m = re.findall(r"YOUTUBE_CHANNELS=(.*)", out)
    try:
        channels = json.loads(m[-1]) if m else []
    except ValueError:
        channels = []
    base = {"channels": channels, "expected": expected}
    if code != 0:
        return {**base, "status": status_of(code), "message": last_error(out)}
    handles = {c["handle"].lower() for c in channels}
    if not expected:
        return {**base, "status": "found", "message": ""}
    if expected.lower() in handles:
        return {**base, "status": "ok", "message": ""}
    return {**base, "status": "mismatch",
            "message": f"Tài khoản không quản lý kênh @{expected} (có: {', '.join('@' + c['handle'] for c in channels) or 'không kênh nào'})"}


TIKTOK_RE = re.compile(r"^[a-z0-9._]{2,24}$")      # nhu foxprofile core/post_map.py
YOUTUBE_RE = re.compile(r"^[\w.-]{3,30}$")


def fill_map(profile: str, result: dict) -> list[str]:
    """Dien vao post_map.json cac o con TRONG cua profile tu ket qua kiem tra: Fanpage neu tai khoan chi quan ly dung
    1 Trang (nhieu Trang thi de chu chon, khong bao gio dang len moi Trang), TikTok = tai khoan dang dang nhap, YouTube
    neu chi co dung 1 kenh. Bo qua muc da gan cho profile khac (moi Trang / tai khoan / kenh chi thuoc 1 profile).
    O da co gia tri thi giu nguyen. Tra ve cac muc da dien."""
    path = DATA_DIR / "post_map.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, ValueError):
        return []  # file hong: khong ghi de
    profiles = raw.get("profiles") if isinstance(raw, dict) else None
    if not isinstance(profiles, dict):
        profiles = {}
    others = [e for n, e in profiles.items() if n != profile and isinstance(e, dict)]
    taken_pages = {str(p.get("id")) for e in others for p in e.get("fanpages") or [] if isinstance(p, dict)}
    taken_tt = {str(e.get("tiktok") or "").lower() for e in others}
    taken_yt = {str(e.get("youtube") or "").lower() for e in others}
    entry = profiles.get(profile) if isinstance(profiles.get(profile), dict) else {}
    entry = {"fanpages": [], "tiktok": "", "youtube": "", "max_per_day": 0, "hours": "", "caption_lang": "", **entry}
    filled = []

    fb = result.get("fanpage") or {}
    found = fb.get("found") or []
    if not entry["fanpages"] and fb.get("status") == "ok" and len(found) == 1 and found[0]["id"] not in taken_pages:
        entry["fanpages"] = [{"id": found[0]["id"], "name": found[0].get("name", "")}]
        filled.append(f"Fanpage {found[0].get('name') or found[0]['id']}")

    tt = result.get("tiktok") or {}
    account = str(tt.get("account") or "").lstrip("@").lower()
    if (not entry["tiktok"] and tt.get("status") in ("ok", "found") and TIKTOK_RE.match(account)
            and account not in taken_tt):
        entry["tiktok"] = account
        filled.append(f"TikTok @{account}")

    yt = result.get("youtube") or {}
    channels = yt.get("channels") or []
    handle = unicodedata.normalize("NFC", str(channels[0].get("handle") or "")) if len(channels) == 1 else ""
    if (not entry["youtube"] and yt.get("status") in ("ok", "found") and YOUTUBE_RE.match(handle)
            and handle.lower() not in taken_yt):
        entry["youtube"] = handle
        filled.append(f"YouTube @{handle}")

    if filled:
        profiles[profile] = entry
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({**(raw if isinstance(raw, dict) else {}), "profiles": profiles},
                                  indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    return filled


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Kiem tra tai khoan Facebook / TikTok / YouTube cua 1 profile, khong dang gi")
    ap.add_argument("--profile", required=True)
    a = ap.parse_args()
    fanpage_jobs.load_env()
    out_file = DATA_DIR / f"account_check_{safe(a.profile)}.json"
    started = time.time()
    try:
        entry = json.loads((DATA_DIR / "post_map.json").read_text(encoding="utf-8")).get("profiles", {}).get(
            a.profile) or {}
    except (OSError, ValueError, AttributeError):
        entry = {}
    result = {"running": False, "started": started, "at": time.strftime("%Y-%m-%d %H:%M")}
    try:
        result["fanpage"] = check_fanpage(a.profile, [str(p["id"]) for p in entry.get("fanpages") or []])
        result["tiktok"] = check_tiktok(a.profile, str(entry.get("tiktok") or ""))
        result["youtube"] = check_youtube(a.profile, str(entry.get("youtube") or "").lstrip("@"))
        result["filled"] = fill_map(a.profile, result)
    except Exception as e:  # luon ghi ket qua de dashboard khong cho mai
        result["error"] = f"{type(e).__name__}: {e}"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
