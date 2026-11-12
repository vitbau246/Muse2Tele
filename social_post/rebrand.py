# -*- coding: utf-8 -*-
"""
Ap bo nhan dien kenh (brand_kit.py, do Muse lam theo lenh /rebrand cua bot) cho 1 profile FoxProfile:

  1. Chuan hoa 3 anh (avatar 800x800, bia Facebook 1640x624, banner YouTube 2560x1440).
  2. Luu cau hinh kenh cu thanh data\\channels\\<profile>.<thoi diem>.json, ghi cau hinh moi data\\channels\\<profile>.json.
  3. Tao Trang Facebook moi (create_channels.py --only facebook).
  4. Tao kenh YouTube moi, thu lan luot cac handle Muse de xuat (create_channels.py --only youtube).
  5. Sua ho so TikTok: ten, tieu su, anh dai dien, username moi neu con trong (tiktok_manage.py --edit-profile).
  6. Doc Page ID (asset_id Business Suite) cua Trang moi (fanpage_post.py --list-pages).
  7. Bang dang bai (FoxProfile API /settings/post-map): profile -> Trang moi, kenh YouTube moi, tai khoan TikTok.
  8. Bat tick Tu dong dang (Fanpage / TikTok / YouTube) cho phan da xong.
Video TikTok cu do bot xoa rieng (tiktok_manage.py --delete-all) ngay khi chu xac nhan /rebrand.

  python rebrand.py --profile Muse9 --kit-dir "Videos\\downloads\\channels\\Muse9\\B1A2B3C" [--dry-run]

--daily (dot tao kenh hang ngay cua bot, /kenhmoi): chi buoc 1, 3, 4, 6; cau hinh ghi vao <kit-dir>\\channels.json
(data\\channels\\<profile>.json -- kenh dang dang bai -- giu nguyen), ket qua them vao data\\channels\\<profile>.daily.json.

Chay lai voi cung --kit-dir thi lam tiep (Trang / kenh da tao ghi trong cau hinh, khong tao lai).
In dong REBRAND_RESULT=<json> va ghi <kit-dir>\\result.json.
Ma thoat: 0 = xong het, 1 = co buoc loi (xem result.json), 2 = thieu bo nhan dien / anh.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

import brand_kit
import fanpage_jobs

fanpage_jobs.load_env()
HERE = Path(__file__).resolve().parent
ROOT = fanpage_jobs.ROOT_DIR
CHANNELS = HERE / "data" / "channels"
FOX_URL = os.environ.get("FOXPROFILE_URL", "http://127.0.0.1:8090").rstrip("/")
FOX_TOKEN = os.environ.get("FOXPROFILE_API_TOKEN", "")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def run(args: list[str], timeout: int) -> tuple[int, str]:
    log("$ " + " ".join(args))
    try:
        p = subprocess.run([sys.executable, *args], cwd=HERE, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        log(f"  het {timeout}s, dung")
        return 1, ""
    out = (p.stdout or "") + (p.stderr or "")
    for line in out.strip().splitlines()[-12:]:
        log("  | " + line)
    return p.returncode, out


def fox(method: str, path: str, **kw):
    r = requests.request(method, f"{FOX_URL}/api/v1{path}", timeout=30,
                         headers={"Authorization": f"Bearer {FOX_TOKEN}"} if FOX_TOKEN else {}, **kw)
    if not r.ok:
        raise RuntimeError(f"FoxProfile {method} {path}: {r.status_code} {r.text[:200]}")
    return r.json()


# ---------- anh ----------

def prepare_images(kit_dir: Path) -> dict[str, Path]:
    """Cat / doi co 3 anh ve kich thuoc dich (cat giua, giu ty le). Khong co Pillow thi dung anh goc."""
    src = brand_kit.images(kit_dir)
    out_dir = kit_dir / "ready"
    out_dir.mkdir(exist_ok=True)
    try:
        from PIL import Image, ImageOps
    except ImportError:
        log("Khong co Pillow: dung anh goc Muse gui")
        return src
    out = {}
    for slot, path in src.items():
        w, h = brand_kit.SIZES[slot]
        with Image.open(path) as im:
            im = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.5))
            dest = out_dir / f"{slot}.png"
            im.save(dest, optimize=True)
            if dest.stat().st_size > 6 * 1024 * 1024:  # YouTube banner <= 6 MB
                dest.unlink()
                dest = out_dir / f"{slot}.jpg"
                im.save(dest, quality=90)
        out[slot] = dest
        log(f"Anh {slot}: {path.name} -> {dest.name} ({w}x{h})")
    return out


# ---------- cau hinh kenh ----------

def current_tiktok(profile: str, old: dict) -> str:
    try:
        entry = (fox("GET", "/settings/post-map").get("profiles") or {}).get(profile) or {}
    except (RuntimeError, requests.RequestException):
        entry = {}
    if entry.get("tiktok"):
        return entry["tiktok"]
    if (old.get("tiktok") or {}).get("account"):
        return old["tiktok"]["account"]
    try:
        return json.loads((HERE / "data" / f"tt_account_{profile}.json").read_text(encoding="utf-8"))["account"]
    except (OSError, ValueError, KeyError):
        return ""


def write_config(profile: str, kid: str, kit: dict, imgs: dict[str, Path], target: Path | None = None) -> tuple[Path, dict]:
    """target: ghi cau hinh moi vao day thay vi data/channels/<profile>.json (dry-run, --daily)."""
    real = CHANNELS / f"{profile}.json"
    CHANNELS.mkdir(parents=True, exist_ok=True)
    path = target or real
    old = json.loads(real.read_text(encoding="utf-8")) if real.is_file() else {}
    here = old if path == real else (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})
    if here.get("rebrand_id") == kid:  # chay lai: giu cac buoc da xong
        log(f"Cau hinh {path.name} da la cua {kid}: lam tiep")
        return path, here
    if old and not target:
        backup = real.with_name(f"{profile}.{datetime.now():%Y%m%d-%H%M}.json")
        shutil.copyfile(real, backup)
        log(f"Luu cau hinh kenh cu: {backup.name}")
    account = (old.get("facebook") or {}).get("account", "")
    data = {
        "rebrand_id": kid,
        "previous": {k: {"name": (old.get(k) or {}).get("name", ""), **((old.get(k) or {}).get("created") or {})}
                     for k in ("facebook", "youtube") if old.get(k)},
        "facebook": {"name": kit["name"], "category": kit["category"], "bio": kit["bio"],
                     "avatar": rel(imgs["avatar"]), "cover": rel(imgs["cover"]), **({"account": account} if account else {})},
        "youtube": {"name": kit["name"], "handle": kit["handles"][0], "handles": kit["handles"],
                    "description": kit["description"], "avatar": rel(imgs["avatar"]), "banner": rel(imgs["banner"]),
                    "links": [{"title": "Facebook", "url": "{facebook}"}]},
        "tiktok": {"account": current_tiktok(profile, old), "name": kit["tiktok_name"], "bio": kit["tiktok_bio"],
                   "usernames": kit["tiktok_usernames"], "avatar": rel(imgs["avatar"])},
    }
    if not account:
        log("Cau hinh cu khong ghi ten trang ca nhan Facebook ('account'): tao Trang xong trinh duyet co the dang "
            "dung voi tu cach Trang moi")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Ghi cau hinh kenh moi: {path}")
    return path, data


def reload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- cac buoc ----------

def step_facebook(profile: str, cfg_path: Path, dry: bool) -> str:
    if (reload(cfg_path)["facebook"].get("created") or {}).get("url"):
        return "da tao truoc"
    code, out = run(["create_channels.py", "--profile", profile, "--config", str(cfg_path), "--only", "facebook"]
                    + (["--dry-run"] if dry else []), 1200)
    created = reload(cfg_path)["facebook"].get("created") or {}
    if dry:
        return "dry-run" if code == 0 else f"loi (ma {code})"
    if code != 0 or not created.get("url"):
        raise RuntimeError(f"tao Trang Facebook loi (ma {code})")
    return created["url"]


def step_youtube(profile: str, cfg_path: Path, dry: bool) -> str:
    data = reload(cfg_path)
    created = data["youtube"].get("created") or {}
    if created.get("channel_id"):
        return created.get("url", "da tao truoc")
    handles = data["youtube"].get("handles") or [data["youtube"]["handle"]]
    for handle in handles:
        data = reload(cfg_path)
        data["youtube"]["handle"] = handle
        save(cfg_path, data)
        code, out = run(["create_channels.py", "--profile", profile, "--config", str(cfg_path), "--only", "youtube"]
                        + (["--dry-run"] if dry else []), 1200)
        created = reload(cfg_path)["youtube"].get("created") or {}
        if dry:
            return "dry-run" if code == 0 else f"loi (ma {code})"
        if created.get("channel_id"):
            if code != 0:  # kenh da tao, buoc anh / mo ta loi: thu lai 1 lan
                code, _ = run(["create_channels.py", "--profile", profile, "--config", str(cfg_path), "--only", "youtube",
                                "--refresh"], 900)
                if code != 0:
                    return created["url"] + " (chua gan duoc anh / mo ta, chay lai create_channels --refresh)"
            return created["url"]
        if re.search(r"can xac minh|xac minh|verify|CAPTCHA", out, re.I):
            raise RuntimeError("YouTube doi xac minh (SDT / CAPTCHA): lam tay")
        log(f"YouTube: handle @{handle} khong tao duoc, thu handle tiep")
    raise RuntimeError(f"khong tao duoc kenh YouTube voi cac handle {handles}")


def step_tiktok(profile: str, cfg_path: Path, dry: bool) -> str:
    t = reload(cfg_path)["tiktok"]
    if not t.get("account"):
        raise RuntimeError("khong biet tai khoan TikTok cua profile (Bang dang bai / tt_account trong)")
    if t.get("done"):
        return "@" + t["account"]
    args = ["tiktok_manage.py", "--profile", profile, "--edit-profile", "--expect-account", t["account"],
            "--name", t["name"], "--bio", t["bio"], "--avatar", str(ROOT / t["avatar"])]
    if t.get("usernames"):
        args += ["--username", ",".join(t["usernames"])]
    code, out = run(args + (["--dry-run"] if dry else []), 900)
    if code != 0:
        raise RuntimeError(f"sua ho so TikTok loi (ma {code})")
    if dry:
        return "dry-run"
    accounts = re.findall(r"TIKTOK_ACCOUNT=(\S+)", out)
    data = reload(cfg_path)
    data["tiktok"].update(account=accounts[-1] if accounts else t["account"], done=datetime.now().isoformat("T", "minutes"))
    save(cfg_path, data)
    rejected = re.findall(r"TIKTOK_USERNAME_REJECTED=(\S+)", out)
    return "@" + data["tiktok"]["account"] + (f" (username da co nguoi dung: {', '.join(rejected)})" if rejected else "")


def step_page_id(profile: str, cfg_path: Path, before: set[str]) -> str:
    data = reload(cfg_path)
    created = data["facebook"].get("created") or {}
    if created.get("business_asset_id"):
        return created["business_asset_id"]
    code, _ = run(["fanpage_post.py", "--profile", profile, "--list-pages"], 600)
    try:
        pages = json.loads(fanpage_jobs.pages_cache(profile).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pages = []
    same = [p for p in pages if p.get("name") == data["facebook"]["name"] and p.get("asset_id")]
    fresh = [p for p in same if str(p["asset_id"]) not in before] or same
    if not fresh:
        raise RuntimeError(f"khong thay Trang '{data['facebook']['name']}' trong Business Suite (ma {code})")
    asset = str(fresh[0]["asset_id"])
    created["business_asset_id"] = asset
    data["facebook"]["created"] = created
    save(cfg_path, data)
    return asset


def step_post_map(profile: str, page_id: str, yt_handle: str, tiktok: str) -> dict:
    current = fox("GET", "/settings/post-map").get("profiles") or {}
    entry = dict(current.get(profile) or {"max_per_day": 0, "hours": "", "caption_lang": ""})
    if page_id:
        entry["fanpages"] = [{"id": page_id}]
    if yt_handle:
        entry["youtube"] = yt_handle
    if tiktok:
        entry["tiktok"] = tiktok
    current[profile] = entry
    fox("PUT", "/settings/post-map", json={"profiles": current})
    return entry


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Ap bo nhan dien kenh moi cho 1 profile (lenh /rebrand, /kenhmoi)")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--kit-dir", required=True)
    ap.add_argument("--dry-run", action="store_true", help="dien form, khong bam tao / luu, khong sua Bang dang bai")
    ap.add_argument("--daily", action="store_true",
                    help="dot tao kenh hang ngay: chi tao Trang FB + kenh YT moi (cau hinh trong kit-dir), khong doi "
                         "TikTok / Bang dang bai / Tu dong dang, ghi vao data/channels/<profile>.daily.json")
    a = ap.parse_args()
    kit_dir = Path(a.kit_dir)
    kit_dir = (kit_dir if kit_dir.is_absolute() or kit_dir.exists() else ROOT / kit_dir).resolve()
    kit = brand_kit.load(kit_dir)
    if not kit or not brand_kit.complete(kit_dir):
        log(f"Thieu bo nhan dien hoac anh trong {kit_dir}")
        return 2
    kid = kit.get("id") or kit_dir.name
    result = {"profile": a.profile, "kit": kid, "name": kit["name"], "dry_run": a.dry_run, "daily": a.daily,
              "steps": {}, "errors": {}}

    def step(name, fn, *args):
        try:
            result["steps"][name] = fn(*args)
            log(f"== {name}: {result['steps'][name]}")
        except Exception as e:  # moi buoc doc lap: loi 1 buoc van lam cac buoc sau
            result["errors"][name] = str(e)
            log(f"== {name}: LOI {e}")
        return result["steps"].get(name)

    imgs = prepare_images(kit_dir)
    target = kit_dir / "channels_dryrun.json" if a.dry_run else kit_dir / "channels.json" if a.daily else None
    cfg_path, _ = write_config(a.profile, kid, kit, imgs, target)
    try:
        before = {str(p.get("asset_id")) for p in
                  json.loads(fanpage_jobs.pages_cache(a.profile).read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        before = set()
    step("facebook", step_facebook, a.profile, cfg_path, a.dry_run)
    step("youtube", step_youtube, a.profile, cfg_path, a.dry_run)
    if not a.daily:
        step("tiktok", step_tiktok, a.profile, cfg_path, a.dry_run)
    if a.daily and not a.dry_run:
        if "facebook" not in result["errors"]:
            step("page_id", step_page_id, a.profile, cfg_path, before)
        data = reload(cfg_path)
        fb, yt = data["facebook"].get("created") or {}, data["youtube"].get("created") or {}
        brand_kit.add_daily(CHANNELS, a.profile, {
            "kit": kid, "name": kit["name"], "at": datetime.now().isoformat("T", "minutes"),
            "facebook": fb.get("url", ""), "page_id": fb.get("business_asset_id", ""),
            "youtube": yt.get("url", ""), "channel_id": yt.get("channel_id", ""),
            "handle": data["youtube"]["handle"] if yt.get("channel_id") else "", "config": rel(cfg_path)})
    elif not a.dry_run:
        page_id = step("page_id", step_page_id, a.profile, cfg_path, before) if "facebook" not in result["errors"] else ""
        data = reload(cfg_path)
        yt = data["youtube"]["handle"] if (data["youtube"].get("created") or {}).get("channel_id") else ""
        tt = data["tiktok"]["account"] if "tiktok" not in result["errors"] else ""
        if page_id or yt or tt:
            step("post_map", step_post_map, a.profile, page_id or "", yt, tt)
            if "post_map" not in result["errors"]:
                step("auto_post", lambda: fox("PATCH", f"/profiles/{a.profile}", json={
                    "auto_post_fanpage": bool(page_id), "auto_post_tiktok": bool(tt), "auto_post_youtube": bool(yt)})
                    and {"fanpage": bool(page_id), "tiktok": bool(tt), "youtube": bool(yt)})
    result["at"] = datetime.now().isoformat("T", "seconds")
    (kit_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("REBRAND_RESULT=" + json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
