# -*- coding: utf-8 -*-
"""
Lay video tu Google Drive cua 1 profile FoxProfile (Drive rieng tu, chi tai duoc qua trinh duyet da dang nhap) vao
hang doi dang bai cua profile do (Videos\\downloads\\social_queue\\<profile>\\). Bot Telegram (/dang ... drive) goi.

  python drive_fetch.py --profile Muse9 --search "LONG TAM Tap 8"
      -> moi file video tim thay 1 dong:  RESULT {"id": "...", "name": "..."}
  python drive_fetch.py --profile Muse9 --get <file id> --name "LONG TAM Tap 8 - ... .mp4"
      -> tai ve, chep vao hang doi:       SAVED <duong dan trong hang doi>

Lam tren 1 tab rieng (dong khi xong). Trong luc lam ghi data\\browser_busy_<profile>.json de AutoPost khong mo / dong
tab cua cung profile (FoxProfile chon tab theo so thu tu: dong tab o giua lam lech so cua script kia).
File > 100 MB: Drive hien form "van tai xuong" -> gui form neu dung id (form cu con sot lai se tai nham file truoc).

Ma thoat: 0 OK, 1 loi, 2 khong tim thay, 5 FoxProfile chua san sang, 7 AutoPost dang dung trinh duyet cua profile.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote

import fox_common
from fox_common import FoxError, FoxProfileBrowser, log
from fanpage_jobs import DATA_DIR, ROOT_DIR

QUEUE_DIR = Path(os.environ.get("SOCIAL_QUEUE_DIR") or ROOT_DIR / "Videos" / "downloads" / "social_queue").resolve()
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
STATUS_FILE = DATA_DIR / "auto_post_status.json"
DOWNLOAD_TIMEOUT = 20 * 60
EXIT_NOT_FOUND, EXIT_FOX, EXIT_BUSY = 2, 5, 7


def busy_file(profile: str) -> Path:
    return DATA_DIR / f"browser_busy_{profile}.json"


def autopost_on(profile: str) -> str:
    """Viec AutoPost dang lam tren profile nay ("" neu khong)."""
    try:
        cur = json.loads(STATUS_FILE.read_text(encoding="utf-8")).get("current") or ""
    except (OSError, ValueError, AttributeError):
        return ""
    return cur if cur.startswith(profile + "/") else ""


def slug(name: str) -> str:
    """'LONG TAM Tap 8 - Ke La.mp4' -> 'long-tam-tap-8-ke-la.mp4' (ASCII, khong dau cach)."""
    stem, ext = os.path.splitext(name)
    flat = unicodedata.normalize("NFKD", stem.replace("đ", "d").replace("Đ", "D"))
    flat = "".join(c for c in flat if not unicodedata.combining(c)).lower()
    flat = re.sub(r"[^a-z0-9]+", "-", flat).strip("-")[:70] or "video"
    return flat + (ext.lower() or ".mp4")


def download_dir(fb: FoxProfileBrowser) -> Path:
    return Path(fb._call("GET", "/settings", timeout=15).json()["download_dir"])


def open_tab(fb: FoxProfileBrowser, url: str) -> None:
    tabs = fb.tab_new(url)
    fb.tab = next((t["index"] for t in tabs if t["active"]), len(tabs) - 1)


def search(fb: FoxProfileBrowser, query: str) -> list[dict]:
    open_tab(fb, "https://drive.google.com/drive/search?q=" + quote(query))
    script = """() => { const seen = new Set(), out = [];
      for (const e of document.querySelectorAll('[data-id]')) {
        const id = e.getAttribute('data-id'), name = (e.innerText || '').trim().split('\\n')[0].trim();
        if (!id || id.length < 20 || !name || seen.has(id)) continue;
        seen.add(id); out.push({id, name});
      } return out; }"""
    found = []
    deadline = time.time() + 40
    while time.time() < deadline:
        time.sleep(3)
        try:
            if "accounts.google.com" in fb.url():
                raise fox_common.NotLoggedIn("Drive chua dang nhap")
            found = [r for r in fox_common.eval_retry(fb, script) or [] if r["name"].lower().endswith(VIDEO_EXT)]
        except FoxError as e:
            if e.status not in (400, 422):
                raise
        if found:
            time.sleep(2)  # danh sach co the con dang do them
            found = [r for r in fox_common.eval_retry(fb, script) or [] if r["name"].lower().endswith(VIDEO_EXT)]
            break
    # Drive tim rat rong ("Tap 7" ra ca tap 1-7): co file chua du moi tu khoa thi chi giu cac file do
    words = set(slug(query + ".x")[:-2].split("-"))
    exact = [r for r in found if words <= set(os.path.splitext(slug(r["name"]))[0].split("-"))]
    return sorted(exact or found, key=lambda r: r["name"])


def fetch(fb: FoxProfileBrowser, file_id: str, name: str, profile: str) -> Path:
    dl = download_dir(fb)
    before = {p.name for p in dl.glob("*")} if dl.is_dir() else set()
    open_tab(fb, "about:blank")
    try:
        fb.navigate(f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t")
    except FoxError as e:
        if "download is starting" not in e.detail.lower():
            raise
    time.sleep(4)
    try:  # file lon: trang canh bao khong quet duoc virus -> gui form neu dung id
        form_id = fox_common.eval_retry(fb, "() => { const f = document.querySelector('form#download-form');"
                                            " const i = f && f.querySelector('input[name=id]'); return i ? i.value : null; }")
        if form_id == file_id:
            fox_common.eval_retry(fb, "() => document.querySelector('form#download-form').submit()")
            log("File lon: da xac nhan tai xuong")
        elif form_id:
            raise RuntimeError(f"Form tai xuong cua file khac ({form_id}), khong tai")
    except FoxError as e:
        if e.status not in (400, 422):
            raise
    stem = os.path.splitext(name)[0] if name else ""
    log(f"Dang tai {name or file_id} vao {dl}")
    deadline, last = time.time() + DOWNLOAD_TIMEOUT, None
    while time.time() < deadline:
        time.sleep(3)
        new = [p for p in dl.glob("*") if p.name not in before and p.is_file()
               and p.suffix.lower() in VIDEO_EXT and (not stem or p.name.startswith(stem))]
        if new:
            got = max(new, key=lambda p: p.stat().st_mtime)
            size = got.stat().st_size
            if last == (got, size) and size > 0:
                break
            last = (got, size)
    else:
        raise RuntimeError(f"Qua {DOWNLOAD_TIMEOUT // 60} phut chua tai xong")
    folder = QUEUE_DIR / profile
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / slug(name or got.name)
    if dest.exists() or any((folder / sub).glob(f"*_{dest.name}") for sub in ("done", "failed")
                            if (folder / sub).is_dir()):
        raise FileExistsError(f"{dest.name} da co trong hang doi / da dang cua {profile}")
    tmp = dest.with_name(dest.name + ".part")  # chep xong moi doi ten: AutoPost khong lay file dang chep do
    shutil.copyfile(got, tmp)
    os.replace(tmp, dest)
    return dest


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Lay video tu Google Drive cua profile vao hang doi dang bai")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--search")
    ap.add_argument("--get", help="Drive file id")
    ap.add_argument("--name", default="", help="Ten file tren Drive (dat ten trong hang doi)")
    ap.add_argument("--wait-busy", type=int, default=600, help="Cho AutoPost xong viec tren profile toi da (giay)")
    a = ap.parse_args()
    if not (a.search or a.get):
        ap.error("can --search hoac --get")

    deadline = time.time() + a.wait_busy
    while autopost_on(a.profile):
        if time.time() > deadline:
            log(f"AutoPost dang dung trinh duyet cua {a.profile}: {autopost_on(a.profile)}")
            return EXIT_BUSY
        time.sleep(10)
    busy = busy_file(a.profile)
    busy.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}), encoding="utf-8")
    fb = FoxProfileBrowser(a.profile, log=log)
    try:
        if not fb.is_running():
            fox_common.launch_with_retry(fb)
        if a.search:
            found = search(fb, a.search)
            for r in found:
                print("RESULT " + json.dumps(r, ensure_ascii=False), flush=True)
            log(f"Tim thay {len(found)} video cho '{a.search}'")
            return 0 if found else EXIT_NOT_FOUND
        dest = fetch(fb, a.get, a.name, a.profile)
        print(f"SAVED {dest}", flush=True)
        return 0
    except fox_common.NotLoggedIn as e:
        log(f"LOI: {e}")
        return fox_common.EXIT_NOT_LOGGED_IN
    except FoxError as e:
        log(f"LOI FoxProfile: {e}")
        return EXIT_FOX if e.status in (0, 404, 409, 503) else 1
    except Exception as e:
        log(f"LOI: {e}")
        return 1
    finally:
        tab, fb.tab = fb.tab, None
        if tab is not None:
            try:
                if len(fb.tabs()) > 1:
                    fb.tab_close(tab)
            except FoxError:
                pass
        busy.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
