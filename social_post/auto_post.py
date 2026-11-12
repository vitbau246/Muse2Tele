# -*- coding: utf-8 -*-
"""
Tu dong dang bai cho cac profile FoxProfile da tick "Tu dong dang len fanpage / TikTok / kenh YouTube" tren dashboard.

Moi profile co 1 thu muc hang doi:  <SOCIAL_QUEUE_DIR>\\<ten profile>\\
(mac dinh SOCIAL_QUEUE_DIR = Muse2Tele\\Videos\\downloads\\social_queue, nam trong FOXPROFILE_UPLOAD_DIRS).
Bo file vao do la xong:
  - video (.mp4 .mov .webm .mkv .m4v): dang len TikTok, fanpage, kenh YouTube (theo o tick)
  - anh cover YouTube: <ten video>.cover1.jpg .. .cover3.jpg (png / webp cung duoc) canh video: 1 anh = thumbnail,
    2-3 anh = YouTube "Thu nghiem va so sanh". Anh cover khong dang thanh bai anh len fanpage.
  - YouTube: dong dau caption = tieu de, phan con lai = mo ta; kenh = handle trong Bang dang bai
  - anh (.jpg .jpeg .png .webp): dang bai anh len fanpage (TikTok bo qua)
  - caption: file .txt cung ten (vd clip1.mp4 + clip1.txt); khong co thi dung ten file
  - Trang / tai khoan dang: theo "Bang dang bai" tren dashboard (social_post\\data\\post_map.json): profile -> Page ID
    Facebook + tai khoan TikTok. Chua map thi KHONG dang (cho 30 phut roi xem lai); tai khoan dang nhap o profile
    khong khop (Trang khong thuoc tai khoan, TikTok khac @) thi bo dich do ngay, khong thu lai.
  - Bang dang bai con co: so bai toi da / ngay va khung gio dang (vd 11-13, 19-23) cho tung profile; chua toi luot
    thi hen lai. Cung 1 video (dau van tay noi dung, doi ten van nhan ra) khong dang 2 lan len cung Trang / tai khoan
    TikTok (lich su: data\\posted_history.json, giu 90 ngay).
  - pages.txt (tuy chon): moi dong 1 ten Trang hoac Page ID de chi dang len mot phan cac Trang da map
Dang xong file chuyen sang done\\, loi qua nhieu lan thi sang failed\\. Trang thai: social_post\\data\\auto_post_state.json.

Chay:  python auto_post.py            (vong lap, quet moi 60s)
       python auto_post.py --once     (quet 1 lan roi thoat)
       python auto_post.py --dry-run  (chay het cac buoc nhung KHONG bam Dang)
"""

import argparse
import hashlib
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
import post_kit
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
EXIT_WRONG_ACCOUNT = 6       # Trang / tai khoan TikTok dang nhap khong khop bang dang bai: bo ngay
EXIT_DUPLICATE = 100         # (noi bo) dich da dang video nay truoc day: coi nhu xong, khong bao "da dang"
MAP_FILE = DATA_DIR / "post_map.json"
UNMAPPED_WAIT_MIN = 30
HISTORY_FILE = DATA_DIR / "posted_history.json"  # [{fp, profile, platform, key, at}]: chong trung + dem moi ngay
HISTORY_KEEP_DAYS = 90
# Dieu khien tu bot Telegram (/dang): {"paused": [profile | "*"], "retry": [profile]}. retry: dua video trong failed\
# ve hang doi va dang lai ngay cac dich dang cho; doc xong thi xoa khoi danh sach.
CONTROL_FILE = DATA_DIR / "auto_post_control.json"
# Bot doc: {"pid", "at" (lan quet cuoi), "current": "<profile>/<file> -> <dich>" | ""}
STATUS_FILE = DATA_DIR / "auto_post_status.json"
# Moi ket qua 1 dich (dang xong / loi / bo) 1 dong JSON; bot gui ve topic cua profile
EVENTS_FILE = DATA_DIR / "auto_post_events.jsonl"
EVENTS_MAX_BYTES = 512 << 10


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
    return [p for p in r.json()["profiles"]
            if p.get("auto_post_fanpage") or p.get("auto_post_tiktok") or p.get("auto_post_youtube")]


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


def _write_json(path: Path, data) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load_control() -> dict:
    try:
        data = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def is_paused(profile: str, control: dict) -> bool:
    paused = control.get("paused") or []
    return "*" in paused or profile in paused


def take_retries(control: dict) -> list[str]:
    """Profile bot yeu cau dang lai ngay (xoa khoi file dieu khien sau khi doc)."""
    wanted = [p for p in control.get("retry") or [] if isinstance(p, str)]
    if wanted and not DRY_RUN:
        fresh = load_control()
        fresh["retry"] = [p for p in fresh.get("retry") or [] if p not in wanted]
        _write_json(CONTROL_FILE, fresh)
    return wanted


BUSY_MAX_SECONDS = 30 * 60


def browser_busy(profile: str) -> bool:
    """drive_fetch.py dang dung trinh duyet cua profile (mo / dong tab): luot nay khong dang de khong lech so tab."""
    path = DATA_DIR / f"browser_busy_{profile}.json"
    try:
        at = float(json.loads(path.read_text(encoding="utf-8")).get("at") or 0)
    except (OSError, ValueError, AttributeError, TypeError):
        return False
    if time.time() - at > BUSY_MAX_SECONDS:  # script chet giua chung
        path.unlink(missing_ok=True)
        return False
    return True


def write_status(current: str = "") -> None:
    if DRY_RUN:
        return
    try:
        _write_json(STATUS_FILE, {"pid": os.getpid(), "at": datetime.now().isoformat(timespec="seconds"),
                                  "current": current})
    except OSError:
        pass


def add_event(profile: str, item: Path, target: str, result: str, detail: str = "") -> None:
    """result: done / retry / failed / skipped / wrong_account."""
    if DRY_RUN:
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if EVENTS_FILE.is_file() and EVENTS_FILE.stat().st_size > EVENTS_MAX_BYTES:
            lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-200:]
            EVENTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with EVENTS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "profile": profile,
                                "file": item.name, "target": target, "result": result, "detail": detail},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def restore_failed(folder: Path) -> list[str]:
    """Dua video (va file di kem) trong failed\\ ve hang doi, bo tien to thoi gian finish() da gan."""
    failed = folder / "failed"
    if not failed.is_dir():
        return []
    back = []
    for f in sorted(failed.iterdir()):
        if not f.is_file():
            continue
        name = f.name[16:] if len(f.name) > 16 and f.name[:15].replace("-", "").isdigit() and f.name[15] == "_" \
            else f.name
        dest = folder / name
        if dest.exists():
            continue
        try:
            shutil.move(str(f), str(dest))
            os.utime(dest)  # moi nhat -> dang sau cac bai dang cho; STABLE_SECONDS van ap dung
        except OSError as e:
            log(f"Khong dua duoc {f.name} ve hang doi: {e}")
            continue
        if dest.suffix.lower() in VIDEO_EXT | IMAGE_EXT and not post_kit.is_side_file(dest):
            back.append(name)
    return back


def apply_retry(name: str, folder: Path, pstate: dict) -> None:
    back = restore_failed(folder)
    for entry in pstate.values():
        for target in entry.values():
            if target["status"] == "failed":
                target.update(status="pending", attempts=0)
            if target["status"] == "pending":
                target["next_at"] = ""
                target["error"] = ""
    log(f"'{name}': bot yeu cau dang lai ngay" + (f" (dua ve tu failed\\: {', '.join(back)})" if back else ""))


def due(target: dict, now: datetime) -> bool:
    return target["status"] == "pending" and (
        not target.get("next_at") or datetime.fromisoformat(target["next_at"]) <= now)


# ---------- Hang doi ----------

covers_of = post_kit.covers  # <stem>.coverN.<anh> canh video, toi da 3 anh
# Video phai co bo dang bai do Muse lam (tieu de, mo ta, hashtag, caption tung nen tang, 3 cover thu nghiem) moi
# dang: chua co thi ghi yeu cau cho bot Telegram nho Muse lam (post_kit.py). AUTO_POST_REQUIRE_KIT=0 de tat.
REQUIRE_KIT = os.environ.get("AUTO_POST_REQUIRE_KIT", "1").strip() != "0"
KIT_RECHECK_MIN = 3        # chua co bo dang bai: xem lai sau bay nhieu phut
KIT_COVER_WAIT_MIN = 60    # co bo dang bai nhung YouTube chua du 3 cover: cho them toi da bay nhieu phut


def queue_items(folder: Path) -> list[Path]:
    """File anh/video da chep xong, cu nhat truoc (anh cover YouTube di kem video, khong la 1 bai)."""
    now = time.time()
    items = []
    for f in folder.iterdir():
        if f.name.lower().startswith("error_"):  # anh chup loi cua script dang (ban cu luu canh video)
            continue
        if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT and not post_kit.is_side_file(f):
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
    if profile.get("auto_post_youtube") and is_video:
        out.append("youtube")
    return out


def finish(item: Path, ok: bool) -> None:
    """Chuyen file (va caption .txt) sang done\\ hoac failed\\."""
    dest = item.parent / ("done" if ok else "failed")
    dest.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for f in (item, *post_kit.side_files(item)):
        if f.is_file():
            try:
                shutil.move(str(f), str(dest / f"{stamp}_{f.name}"))
            except OSError as e:
                log(f"Khong chuyen duoc {f.name} sang {dest.name}\\: {e}")
    log(f"{'XONG' if ok else 'THAT BAI'}: {item.parent.name}/{item.name} -> {dest.name}\\")


# ---------- Goi script dang bai ----------

LAST_OUTPUT = ""  # output cua lan chay script gan nhat (doc YOUTUBE_URL...)


def run_script(args: list[str]) -> int:
    global LAST_OUTPUT
    cmd = [sys.executable, *args]
    log("Chay: " + " ".join(args))
    log_file = LOG_DIR / "auto_post.log"
    start = log_file.stat().st_size if log_file.is_file() else 0
    try:
        with log_file.open("a", encoding="utf-8") as out:
            return subprocess.run(cmd, cwd=BASE_DIR, stdout=out, stderr=subprocess.STDOUT,
                                  timeout=RUN_TIMEOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
    except subprocess.TimeoutExpired:
        log(f"Qua {RUN_TIMEOUT}s, dung script")
        return 1
    finally:
        try:
            with log_file.open("rb") as f:
                f.seek(start)
                LAST_OUTPUT = f.read(1 << 20).decode("utf-8", "replace")
        except OSError:
            LAST_OUTPUT = ""


def output_value(prefix: str) -> str:
    """Gia tri dong '<prefix> ...' cuoi cung trong output cua lan chay script gan nhat."""
    found = [ln.split(prefix, 1)[1].strip() for ln in LAST_OUTPUT.splitlines() if prefix in ln]
    return found[-1] if found else ""


def mapped(profile: str) -> dict:
    """Muc cua profile trong bang dang bai: {"fanpages": [{"id", "name"}], "tiktok": "handle"} (doc lai moi lan)."""
    try:
        entry = json.loads(MAP_FILE.read_text(encoding="utf-8")).get("profiles", {}).get(profile) or {}
    except (OSError, ValueError, AttributeError):
        entry = {}
    pages = [p for p in entry.get("fanpages") or [] if isinstance(p, dict) and str(p.get("id", "")).isdigit()]
    try:
        per_day = max(0, int(entry.get("max_per_day") or 0))
    except (TypeError, ValueError):
        per_day = 0
    return {"fanpages": pages, "tiktok": str(entry.get("tiktok") or "").lstrip("@").lower(),
            "youtube": str(entry.get("youtube") or "").lstrip("@"),
            "max_per_day": per_day, "hours": windows(entry.get("hours"))}


# ---------- Khung gio, gioi han moi ngay, chong dang trung ----------

def windows(raw) -> list[tuple[int, int]]:
    """'11-13, 19-23' -> [(11, 13), (19, 23)]; [] = luc nao cung dang. 22-2 la qua nua dem."""
    out = []
    for part in str(raw or "").replace(";", ",").split(","):
        a, sep, b = part.strip().partition("-")
        if sep and a.strip().isdigit() and b.strip().isdigit() and int(a) != int(b):
            out.append((int(a) % 24, int(b) % 25))
    return out


def in_window(spans: list[tuple[int, int]], when: datetime) -> bool:
    h = when.hour
    return not spans or any((a <= h < b) if a < b else (h >= a or h < b) for a, b in spans)


def next_window(spans: list[tuple[int, int]], after: datetime) -> datetime:
    """Luc som nhat tu 'after' nam trong khung gio dang (dau gio)."""
    if in_window(spans, after):
        return after
    start = after.replace(minute=0, second=0, microsecond=0)
    for i in range(1, 49):
        t = start + timedelta(hours=i)
        if in_window(spans, t):
            return t
    return after


def fingerprint(item: Path) -> str:
    """Dau van tay file (kich thuoc + 4MB dau + 4MB cuoi): cung video doi ten / chep lai van nhan ra."""
    size = item.stat().st_size
    h = hashlib.sha1(str(size).encode())
    with item.open("rb") as f:
        h.update(f.read(4 << 20))
        if size > 8 << 20:
            f.seek(-(4 << 20), os.SEEK_END)
            h.update(f.read())
    return h.hexdigest()


def load_history() -> list[dict]:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def record_posts(profile: str, platform: str, fp: str, keys: list[str]) -> None:
    """Ghi lich su dang (de chong trung + dem gioi han moi ngay). Giu HISTORY_KEEP_DAYS ngay."""
    if DRY_RUN or not keys:
        return
    now = datetime.now()
    cut = (now - timedelta(days=HISTORY_KEEP_DAYS)).isoformat()
    hist = [h for h in load_history() if h.get("at", "") >= cut]
    hist += [{"fp": fp, "profile": profile, "platform": platform, "key": k, "at": now.isoformat(timespec="minutes")}
             for k in keys]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_name(HISTORY_FILE.name + ".tmp")
    tmp.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, HISTORY_FILE)


def posted_keys(fp: str) -> set[str]:
    """Cac dich (fb:<page id> / tt:<username>) da dang video nay."""
    return {h["key"] for h in load_history() if h.get("fp") == fp}


def posted_today(profile: str, platform: str, when: datetime) -> int:
    """So bai (video khac nhau) profile da dang len nen tang nay trong ngay."""
    day = when.date().isoformat()
    return len({h["fp"] for h in load_history()
                if h.get("profile") == profile and h.get("platform") == platform and h.get("at", "")[:10] == day})


def fanpage_pages(profile: str, folder: Path) -> list[dict]:
    """Cac Trang da map cho profile [{id, name}]; co pages.txt thi chi giu Trang co ten / ID ghi trong do."""
    pages = mapped(profile)["fanpages"]
    names = {p["id"]: p.get("name") or "" for p in pages}
    try:  # ten Trang moi nhat tu lan quet gan day (bang dang bai co the chua co ten)
        for p in json.loads(fanpage_jobs.pages_cache(profile).read_text(encoding="utf-8")):
            if str(p.get("asset_id")) in names and p.get("name"):
                names[str(p["asset_id"])] = p["name"]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    out = [{"id": i, "name": n or i} for i, n in names.items()]
    wanted = folder / "pages.txt"
    if wanted.is_file():
        keys = {ln.strip().casefold() for ln in wanted.read_text(encoding="utf-8-sig").splitlines()
                if ln.strip() and not ln.strip().startswith("#")}
        out = [p for p in out if p["id"] in keys or p["name"].casefold() in keys]
    return out


def post_tiktok(profile: str, item: Path, caption: str, dry: bool) -> int:
    handle = mapped(profile)["tiktok"]
    fp = fingerprint(item)
    if f"tt:{handle}" in posted_keys(fp):
        log(f"'{profile}': {item.name} da dang len TikTok @{handle} truoc day (trung video) -> bo qua")
        return EXIT_DUPLICATE
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    cap_file = JOBS_DIR / f"{profile}__{item.stem}.caption.txt"
    cap_file.write_text(caption, encoding="utf-8")
    args = ["tiktok_post.py", "--profile", profile, "--folder", str(item.parent), "--file", item.name,
            "--caption-file", str(cap_file), "--expect-account", handle]
    code = run_script(args + (["--no-post"] if dry else []))
    if code == 0 and not dry:
        record_posts(profile, "tiktok", fp, [f"tt:{handle}"])
    return code


def plan_done_pages(plan: Path, is_video: bool) -> list[str]:
    """Page ID cac job trong file ke hoach da dang xong (video: video_status, anh: photo_status)."""
    try:
        jobs = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    key = "video_status" if is_video else "photo_status"
    return [str(j["page_id"]) for j in jobs if j.get("page_id") and j.get(key) == "done"]


def post_fanpage(profile: str, item: Path, caption: str, dry: bool) -> int:
    """1 job / Trang trong file ke hoach rieng cua bai nay; chay lai thi Trang da dang duoc bo qua.
    Trang da dang dung video nay truoc day (lich su) cung bo qua."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    plan = JOBS_DIR / f"{profile}__{item.stem}.jobs.json"
    pages = fanpage_pages(profile, item.parent)
    if not pages:
        log(f"'{profile}': khong co Trang nao duoc map (dashboard > Bang dang bai) hoac pages.txt loai het")
        return 1
    fp = fingerprint(item)
    is_video = item.suffix.lower() in VIDEO_EXT
    done_before = posted_keys(fp)
    dup = [p for p in pages if f"fb:{p['id']}" in done_before]
    if dup:
        log(f"'{profile}': {item.name} da dang len {', '.join(p['name'] for p in dup)} truoc day (trung) -> bo qua")
        pages = [p for p in pages if p not in dup]
    if not pages:
        plan.unlink(missing_ok=True)
        return EXIT_DUPLICATE
    code, planned = _post_fanpage_plan(profile, item, caption, dry, plan, pages, is_video)
    if not dry:
        record_posts(profile, "fanpage", fp, [f"fb:{i}" for i in (
            planned if code == 0 else plan_done_pages(plan, is_video))])
        if code == 0:
            plan.unlink(missing_ok=True)
    return code


def _job(p: dict, item: Path, caption: str, is_video: bool) -> dict:
    return {
        "page": p["name"],
        "page_id": p["id"],
        "photo_files": [] if is_video else [str(item)],
        "photo_caption": "" if is_video else caption,
        **({"video_file": str(item), "video_caption": caption} if is_video else {}),
    }


def _post_fanpage_plan(profile: str, item: Path, caption: str, dry: bool, plan: Path, pages: list[dict],
                       is_video: bool) -> tuple[int, list[str]]:
    """Chay fanpage_post.py voi file ke hoach (tao moi / loc lai ke hoach cu): (ma thoat, Page ID trong ke hoach)."""
    if plan.is_file():
        # Ke hoach cu (co the tao truoc khi co bang dang bai): chi giu Trang da map, gan Page ID cho tung job
        by_id = {p["id"]: p for p in pages}
        by_name = {p["name"].casefold(): p for p in pages}
        kept = []
        for j in json.loads(plan.read_text(encoding="utf-8")):
            p = by_id.get(str(j.get("page_id") or "")) or (None if j.get("page_id") else by_name.get(j["page"].casefold()))
            if p:
                kept.append({**j, "page": p["name"], "page_id": p["id"]})
            else:
                log(f"'{profile}': bo job cu cho Trang '{j.get('page')}' (khong co trong bang dang bai)")
        have = {j["page_id"] for j in kept}
        kept += [_job(p, item, caption, is_video) for p in pages if p["id"] not in have]  # Trang moi map them
        jobs = kept
    else:
        jobs = [_job(p, item, caption, is_video) for p in pages]
    plan.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    planned = [j["page_id"] for j in jobs]
    args = ["fanpage_post.py", "--profile", profile, "--plan", str(plan), "--now"]
    code = run_script(args + (["--no-post"] if dry else []))
    return code, planned


def post_youtube(profile: str, item: Path, caption: str, dry: bool) -> int:
    handle = mapped(profile)["youtube"]
    fp = fingerprint(item)
    if f"yt:{handle.lower()}" in posted_keys(fp):
        log(f"'{profile}': {item.name} da dang len YouTube @{handle} truoc day (trung video) -> bo qua")
        return EXIT_DUPLICATE
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    cap_file = JOBS_DIR / f"{profile}__{item.stem}.youtube.txt"
    cap_file.write_text(caption, encoding="utf-8")
    covers = covers_of(item)
    args = ["youtube_post.py", "--profile", profile, "--folder", str(item.parent), "--file", item.name,
            "--caption-file", str(cap_file), "--expect-channel", handle]
    if covers:
        args += ["--thumbs", *[str(c) for c in covers]]
    code = run_script(args + (["--no-post"] if dry else []))
    if code == 0 and not dry:
        record_posts(profile, "youtube", fp, [f"yt:{handle.lower()}"])
    return code


POSTERS = {"tiktok": post_tiktok, "fanpage": post_fanpage, "youtube": post_youtube}
UNMAPPED = {"fanpage": ("fanpages", "Trang Facebook"), "tiktok": ("tiktok", "tai khoan TikTok"),
            "youtube": ("youtube", "kenh YouTube")}


# ---------- Bo dang bai (Muse lam) ----------

def kit_wait(profile: str, item: Path, entry: dict, kit: dict | None, now: datetime) -> str:
    """Ly do chua dang (rong = dang duoc): chua co bo dang bai -> ghi yeu cau cho bot nho Muse; YouTube chua du 3
    cover -> cho them KIT_COVER_WAIT_MIN phut tu luc co bo dang bai."""
    pending = [t for t, v in entry.items() if v["status"] == "pending"]
    if not pending:
        return ""
    if not kit:
        req = post_kit.request_path(item)
        if not req.exists():
            post_kit.write_request(item, profile, pending)
            log(f"'{profile}': {item.name} chua co bo dang bai (tieu de, mo ta, cover) -> nho Muse lam "
                f"(ma {post_kit.kit_id(item)}), CHUA dang")
        return "cho bo dang bai tu Muse"
    have = len(covers_of(item))
    if "youtube" in pending and have < post_kit.COVERS_WANTED:
        try:
            since = datetime.strptime(kit.get("at") or "", "%Y-%m-%d %H:%M")
        except ValueError:
            since = now
        if now - since < timedelta(minutes=KIT_COVER_WAIT_MIN):
            return f"cho cover ({have}/{post_kit.COVERS_WANTED})"
        log(f"'{profile}': {item.name} moi co {have} cover sau {KIT_COVER_WAIT_MIN} phut -> dang voi so cover dang co")
    return ""


# ---------- Vong quet ----------

def request_kits(name: str, profile: dict, items: list[Path]) -> None:
    """Moi video trong hang doi chua co bo dang bai: ghi yeu cau ngay (khong doi toi luot dang) de Muse lam truoc."""
    if not REQUIRE_KIT or DRY_RUN:
        return
    for item in items:
        if item.suffix.lower() not in VIDEO_EXT or post_kit.request_path(item).exists() or post_kit.load_kit(item):
            continue
        targets = targets_for(item, profile)
        if targets:
            post_kit.write_request(item, name, targets)
            log(f"'{name}': {item.name} chua co bo dang bai -> nho Muse lam truoc (ma {post_kit.kit_id(item)})")


def process_profile(profile: dict, state: dict, dry: bool, retry: bool = False) -> None:
    name = profile["name"]
    folder = QUEUE_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    pstate = state.setdefault(name, {})
    if retry and not dry:
        apply_retry(name, folder, pstate)
        save_state(state)
    items = queue_items(folder)
    for gone in set(pstate) - {i.name for i in items}:  # file da bi xoa / doi ten
        if not (folder / gone).exists():
            del pstate[gone]
    request_kits(name, profile, items)

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
        kit = None
        if REQUIRE_KIT and item.suffix.lower() in VIDEO_EXT:
            kit = post_kit.load_kit(item)
            wait = kit_wait(name, item, entry, kit, now)
            if wait:
                for target in entry.values():
                    if target["status"] == "pending":
                        target["next_at"] = (now + timedelta(minutes=KIT_RECHECK_MIN)).isoformat(timespec="minutes")
                        target["error"] = wait
                save_state(state)
                continue  # video khac (da co bo dang bai) van dang duoc
        caps = post_kit.captions(kit) if kit else None
        for t, target in entry.items():
            if not due(target, now):
                continue
            entry_map = mapped(name)
            if not entry_map[UNMAPPED[t][0]]:
                target["next_at"] = (now + timedelta(minutes=UNMAPPED_WAIT_MIN)).isoformat(timespec="minutes")
                target["error"] = "chua map trong Bang dang bai"
                log(f"'{name}' chua map {UNMAPPED[t][1]} "
                    f"(dashboard > Bang dang bai) -> KHONG dang, xem lai sau {UNMAPPED_WAIT_MIN} phut")
                save_state(state)
                continue
            # Khung gio dang + gioi han bai moi ngay (Bang dang bai): chua toi luot thi hen lai, khong tinh lan loi
            wait_until = None
            if not in_window(entry_map["hours"], now):
                wait_until, why = next_window(entry_map["hours"], now), "ngoai khung gio dang"
            elif entry_map["max_per_day"] and posted_today(name, t, now) >= entry_map["max_per_day"]:
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_until = next_window(entry_map["hours"], tomorrow)
                why = f"da du {entry_map['max_per_day']} bai/ngay"
            if wait_until:
                target["next_at"] = wait_until.isoformat(timespec="minutes")
                target["error"] = why
                log(f"'{name}' {t}: {item.name} {why} -> hen {target['next_at']}")
                save_state(state)
                continue
            log(f"=== {name}: {item.name} -> {t} ===")
            text = caption
            if caps:  # YouTube: dong dau = tieu de, con lai = mo ta (youtube_post.py)
                text = {"tiktok": caps["tiktok"], "fanpage": caps["facebook"],
                        "youtube": caps["youtube_title"] + "\n" + caps["youtube_description"]}[t]
            write_status(f"{name}/{item.name} -> {t}")
            try:
                code = POSTERS[t](name, item, text, dry)
            finally:
                write_status()
            if code in (0, EXIT_DUPLICATE):
                target["status"] = "done"
                add_event(name, item, t, "done" if code == 0 else "skipped",
                          output_value("YOUTUBE_URL:") if code == 0 and t == "youtube" else "")
            elif code == EXIT_WRONG_ACCOUNT:
                target["status"] = "failed"
                target["error"] = "tai khoan dang nhap khong khop Bang dang bai"
                log(f"'{name}' {t}: tai khoan / Trang dang nhap KHONG khop Bang dang bai -> bo, khong dang")
                add_event(name, item, t, "wrong_account")
            elif code == EXIT_NOT_LOGGED_IN:
                target["next_at"] = (now + timedelta(minutes=30)).isoformat(timespec="minutes")
                target["error"] = "chua dang nhap"
                log(f"'{name}' chua dang nhap {t} -> thu lai sau 30 phut (mo profile va dang nhap)")
                add_event(name, item, t, "retry", "chưa đăng nhập, thử lại sau 30 phút")
            elif code in EXIT_FOX:
                target["next_at"] = (now + timedelta(minutes=5)).isoformat(timespec="minutes")
                target["error"] = "FoxProfile chua san sang"
            else:
                target["attempts"] += 1
                target["error"] = f"ma loi {code}"
                if target["attempts"] >= MAX_ATTEMPTS:
                    target["status"] = "failed"
                    add_event(name, item, t, "failed", f"lỗi {MAX_ATTEMPTS} lần")
                else:
                    wait = 10 * target["attempts"]
                    target["next_at"] = (now + timedelta(minutes=wait)).isoformat(timespec="minutes")
                    log(f"'{name}' {t} loi {target['attempts']}/{MAX_ATTEMPTS} -> thu lai sau {wait} phut")
                    add_event(name, item, t, "retry",
                              f"lỗi lần {target['attempts']}/{MAX_ATTEMPTS}, thử lại lúc {target['next_at'][11:16]}")
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
    control = load_control()
    retries = set(take_retries(control))
    for p in profiles:
        if is_paused(p["name"], control) or browser_busy(p["name"]):
            continue
        try:
            process_profile(p, state, dry, retry=p["name"] in retries)
        except Exception as e:  # 1 profile loi khong lam dung ca vong
            log(f"LOI o profile '{p['name']}': {e}")
    save_state(state)
    write_status()


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
