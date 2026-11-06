# -*- coding: utf-8 -*-
"""
Kiem tra tai khoan dang nhap o 1 profile FoxProfile so voi "Bang dang bai" (data\\post_map.json), KHONG dang gi:
  - Facebook: quet lai cac Trang tai khoan quan ly (fanpage_post.py --list-pages), doi chieu Page ID da map.
  - TikTok: doc @username dang dang nhap (tiktok_post.py --check-account), doi chieu tai khoan da map.
Ket qua ghi vao data\\account_check_<profile>.json (dashboard FoxProfile > Bang dang bai > nut Kiem tra doc file nay).

  python check_accounts.py --profile P1
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

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


def check_tiktok(profile: str, expected: str) -> dict:
    code, out = run(["tiktok_post.py", "--profile", profile, "--check-account", "--expect-account", expected])
    m = re.findall(r"TIKTOK_ACCOUNT=(\S*)", out)
    account = m[-1] if m else ""
    if code == 0:
        return {"status": "ok" if expected else "found", "account": account, "expected": expected, "message": ""}
    if code == 6:
        return {"status": "mismatch", "account": account, "expected": expected,
                "message": f"Đang đăng nhập @{account}, bảng ghi @{expected}"}
    return {"status": status_of(code), "account": account, "expected": expected, "message": last_error(out)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Kiem tra tai khoan Facebook / TikTok cua 1 profile, khong dang gi")
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
    except Exception as e:  # luon ghi ket qua de dashboard khong cho mai
        result["error"] = f"{type(e).__name__}: {e}"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
