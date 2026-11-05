# -*- coding: utf-8 -*-
"""
Tu dong dang bai cho cac profile FoxProfile da tick "Tu dong dang len fanpage / TikTok" tren dashboard.

Moi profile co 1 thu muc hang doi:  <SOCIAL_QUEUE_DIR>\\<ten profile>\\
(mac dinh SOCIAL_QUEUE_DIR = Muse2Tele\\Videos\\downloads\\social_queue, nam trong FOXPROFILE_UPLOAD_DIRS).
Bo file vao do la xong:
  - video (.mp4 .mov .webm .mkv .m4v): dang len TikTok (neu tick TikTok) va fanpage (neu tick Fanpage)
  - anh (.jpg .jpeg .png .webp): dang bai anh len fanpage (TikTok bo qua)
  - caption: file .txt cung ten (vd clip1.mp4 + clip1.txt); khong co thi dung ten file
  - pages.txt (tuy chon): moi dong 1 ten Trang can dang; khong co thi dang len MOI Trang profile quan ly
Dang xong file chuyen sang done\\, loi qua nhieu lan thi sang failed\\. Trang thai: social_post\\data\\auto_post_state.json.

Chay:  python auto_post.py            (vong lap, quet moi 60s)
       python auto_post.py --once     (quet 1 lan roi thoat)
       python auto_post.py --dry-run  (chay het cac buoc nhung KHONG bam Dang)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

import fanpage_jobs
from fanpage_jobs import BASE_DIR, DATA_DIR, LOG_DIR, ROOT_DIR

fanpage_jobs.load_env()

FOX_URL = os.environ.get("FOXPROFILE_URL", "http://127.0.0.1:8090").rstrip("/")
FOX_TOKEN = os.environ.get("FOXPROFILE_API_TOKEN", "")
QUEUE_DIR = Path(os.environ.get("SOCIAL_QUEUE_DIR") or ROOT_DIR / "Videos" / "downloads" / "social_queue").resolve()
STATE_FILE = DATA_DIR / "auto_post_state.json"
JOBS_DIR = DATA_DIR / "jobs"

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
STABLE_SECONDS = 30          # file phai dung yen bay nhieu giay (chep xong) moi dang
MAX_ATTEMPTS = 3             # so lan loi toi da moi dich (tiktok / fanpage) truoc khi bo
RUN_TIMEOUT = 3600           # 1 lan chay script dang bai toi da bay nhieu giay
EXIT_NOT_LOGGED_IN = 3
EXIT_FOX = (4, 5)            # FoxProfile chua san sang: thu lai sau, khong tinh lan loi


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "auto_post.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------- FoxProfile ----------

def enabled_profiles() -> list[dict]:
    """Profile co it nhat 1 o tick tu dong dang."""
    headers = {"Authorization": f"Bearer {FOX_TOKEN}"} if FOX_TOKEN else {}
    r = requests.get(f"{FOX_URL}/api/v1/profiles", headers=headers, timeout=15,
                     proxies={"http": None, "https": None})
    r.raise_for_status()
    return [p for p in r.json()["profiles"] if p.get("auto_post_fanpage") or p.get("auto_post_tiktok")]


def upload_roots() -> list[Path]:
    """FOXPROFILE_UPLOAD_DIRS (duong dan tuong doi tinh tu foxprofile\\data, nhu FoxProfile)."""
    base = ROOT_DIR / "foxprofile" / "data"
    out = []
    for d in os.environ.get("FOXPROFILE_UPLOAD_DIRS", "").split(os.pathsep):
        if d.strip():
            p = Path(d.strip()).expanduser()
            out.append((p if p.is_absolute() else base / p).resolve())
    return out


# ---------- Trang thai ----------

def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


DRY_RUN = False  # --dry-run: khong ghi trang thai, chay lai bao nhieu lan cung duoc


def save_state(state: dict) -> None:
    if DRY_RUN:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def due(target: dict, now: datetime) -> bool:
    return target["status"] == "pending" and (
        not target.get("next_at") or datetime.fromisoformat(target["next_at"]) <= now)


# ---------- Hang doi ----------

def queue_items(folder: Path) -> list[Path]:
    """File anh/video da chep xong, cu nhat truoc."""
    now = time.time()
    items = []
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
            try:
                if now - f.stat().st_mtime >= STABLE_SECONDS:
                    items.append(f)
            except OSError:
                continue
    return sorted(items, key=lambda f: f.stat().st_mtime)


def caption_of(item: Path) -> str:
    txt = item.with_suffix(".txt")
    if txt.is_file():
        try:
            text = txt.read_text(encoding="utf-8-sig").strip()
            if text:
                return text
        except OSError:
            pass
    return item.stem


def targets_for(item: Path, profile: dict) -> list[str]:
    is_video = item.suffix.lower() in VIDEO_EXT
    out = []
    if profile.get("auto_post_tiktok") and is_video:
        out.append("tiktok")
    if profile.get("auto_post_fanpage"):
        out.append("fanpage")
    return out


def finish(item: Path, ok: bool) -> None:
    """Chuyen file (va caption .txt) sang done\\ hoac failed\\."""
    dest = item.parent / ("done" if ok else "failed")
    dest.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (item, item.with_suffix(".txt")):
        if f.is_file():
            try:
                shutil.move(str(f), str(dest / f"{stamp}_{f.name}"))
            except OSError as e:
                log(f"Khong chuyen duoc {f.name} sang {dest.name}\\: {e}")
    log(f"{'XONG' if ok else 'THAT BAI'}: {item.parent.name}/{item.name} -> {dest.name}\\")


# ---------- Goi script dang bai ----------

def run_script(args: list[str]) -> int:
    cmd = [sys.executable, *args]
    log("Chay: " + " ".join(args))
    try:
        with (LOG_DIR / "auto_post.log").open("a", encoding="utf-8") as out:
            return subprocess.run(cmd, cwd=BASE_DIR, stdout=out, stderr=subprocess.STDOUT,
                                  timeout=RUN_TIMEOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
    except subprocess.TimeoutExpired:
        log(f"Qua {RUN_TIMEOUT}s, dung script")
        return 1


def fanpage_pages(profile: str, folder: Path) -> list[str]:
    wanted = folder / "pages.txt"
    if wanted.is_file():
        names = [ln.strip() for ln in wanted.read_text(encoding="utf-8-sig").splitlines()]
        return [n for n in names if n and not n.startswith("#")]
    cache = fanpage_jobs.pages_cache(profile)
    try:
        return [p["name"] for p in json.loads(cache.read_text(encoding="utf-8")) if p.get("asset_id")]
    except (OSError, ValueError, KeyError):
        return []


def post_tiktok(profile: str, item: Path, caption: str, dry: bool) -> int:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    cap_file = JOBS_DIR / f"{profile}__{item.stem}.caption.txt"
    cap_file.write_text(caption, encoding="utf-8")
    args = ["tiktok_post.py", "--profile", profile, "--folder", str(item.parent), "--file", item.name,
            "--caption-file", str(cap_file)]
    return run_script(args + (["--no-post"] if dry else []))


def post_fanpage(profile: str, item: Path, caption: str, dry: bool) -> int:
    """1 job / Trang trong file ke hoach rieng cua bai nay; chay lai thi Trang da dang duoc bo qua."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    plan = JOBS_DIR / f"{profile}__{item.stem}.jobs.json"
    if not plan.is_file():
        if not (item.parent / "pages.txt").is_file() and not fanpage_jobs.pages_cache(profile).is_file():
            code = run_script(["fanpage_post.py", "--profile", profile, "--list-pages"])
            if code != 0:
                return code
        pages = fanpage_pages(profile, item.parent)
        if not pages:
            log(f"'{profile}': khong co Trang nao (them pages.txt hoac kiem tra tai khoan quan ly Trang)")
            return 1
        is_video = item.suffix.lower() in VIDEO_EXT
        jobs = [{
            "page": name,
            "photo_files": [] if is_video else [str(item)],
            "photo_caption": "" if is_video else caption,
            **({"video_file": str(item), "video_caption": caption} if is_video else {}),
        } for name in pages]
        plan.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    args = ["fanpage_post.py", "--profile", profile, "--plan", str(plan), "--now"]
    code = run_script(args + (["--no-post"] if dry else []))
    if code == 0 and not dry:
        plan.unlink(missing_ok=True)
    return code


POSTERS = {"tiktok": post_tiktok, "fanpage": post_fanpage}


# ---------- Vong quet ----------

def process_profile(profile: dict, state: dict, dry: bool) -> None:
    name = profile["name"]
    folder = QUEUE_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    pstate = state.setdefault(name, {})
    items = queue_items(folder)
    for gone in set(pstate) - {i.name for i in items}:  # file da bi xoa / doi ten
        if not (folder / gone).exists():
            del pstate[gone]

    now = datetime.now()
    for item in items:
        wanted = targets_for(item, profile)
        entry = pstate.setdefault(item.name, {})
        for t in wanted:
            entry.setdefault(t, {"status": "pending", "attempts": 0})
        for t in [t for t in entry if t not in wanted]:  # o tick vua bi bo: khong dang nua
            del entry[t]
        if not entry:
            log(f"'{name}': {item.name} khong co dich nao phu hop (anh chi dang duoc len fanpage)")
            finish(item, ok=False)
            pstate.pop(item.name, None)
            continue

        caption = caption_of(item)
        for t, target in entry.items():
            if not due(target, now):
                continue
            log(f"=== {name}: {item.name} -> {t} ===")
            code = POSTERS[t](name, item, caption, dry)
            if code == 0:
                target["status"] = "done"
            elif code == EXIT_NOT_LOGGED_IN:
                target["next_at"] = (now + timedelta(minutes=30)).isoformat(timespec="minutes")
                target["error"] = "chua dang nhap"
                log(f"'{name}' chua dang nhap {t} -> thu lai sau 30 phut (mo profile va dang nhap)")
            elif code in EXIT_FOX:
                target["next_at"] = (now + timedelta(minutes=5)).isoformat(timespec="minutes")
                target["error"] = "FoxProfile chua san sang"
            else:
                target["attempts"] += 1
                target["error"] = f"ma loi {code}"
                if target["attempts"] >= MAX_ATTEMPTS:
                    target["status"] = "failed"
                else:
                    wait = 10 * target["attempts"]
                    target["next_at"] = (now + timedelta(minutes=wait)).isoformat(timespec="minutes")
                    log(f"'{name}' {t} loi {target['attempts']}/{MAX_ATTEMPTS} -> thu lai sau {wait} phut")
            save_state(state)

        if dry:
            log(f"--dry-run: {item.name} giu nguyen trong hang doi")
        elif all(t["status"] in ("done", "failed") for t in entry.values()):
            finish(item, ok=all(t["status"] == "done" for t in entry.values()))
            pstate.pop(item.name, None)
            save_state(state)
        return  # moi vong chi xu ly 1 bai / profile, de profile khac khong phai cho lau


def scan(dry: bool) -> None:
    try:
        profiles = enabled_profiles()
    except (requests.RequestException, ValueError, KeyError) as e:
        log(f"Khong doc duoc danh sach profile tu FoxProfile ({FOX_URL}): {e}")
        return
    state = load_state()
    for gone in set(state) - {p["name"] for p in profiles}:  # profile da bo tick / bi xoa
        state.pop(gone, None)
    for p in profiles:
        try:
            process_profile(p, state, dry)
        except Exception as e:  # 1 profile loi khong lam dung ca vong
            log(f"LOI o profile '{p['name']}': {e}")
    save_state(state)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tu dong dang bai cho cac profile da tick tren dashboard FoxProfile")
    ap.add_argument("--once", action="store_true", help="Quet 1 lan roi thoat")
    ap.add_argument("--interval", type=float, default=60, help="So giay giua 2 lan quet")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chay thu 1 vong: KHONG bam Dang, khong chuyen file, khong ghi trang thai")
    a = ap.parse_args()
    global DRY_RUN
    DRY_RUN = a.dry_run
    if a.dry_run:
        a.once = True

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    roots = upload_roots()
    if not any(QUEUE_DIR == r or QUEUE_DIR.is_relative_to(r) for r in roots):
        log(f"CANH BAO: {QUEUE_DIR} nam ngoai FOXPROFILE_UPLOAD_DIRS {[str(r) for r in roots]} "
            "-> FoxProfile se tu choi file. Sua o dashboard > Thu muc upload, hoac dat SOCIAL_QUEUE_DIR.")
    log(f"Tu dong dang bai: hang doi {QUEUE_DIR} (moi profile 1 thu muc con), FoxProfile {FOX_URL}")
    while True:
        scan(a.dry_run)
        if a.once:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
