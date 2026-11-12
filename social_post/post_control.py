# -*- coding: utf-8 -*-
"""
Dieu khien + xem trang thai AutoPost (auto_post.py) tu ben ngoai: bot Telegram (/dang) dung. Khong phu thuoc
Telegram; chi doc / ghi cac file trong social_post\\data:
  auto_post_state.json    trang thai tung video / dich (AutoPost ghi)
  auto_post_status.json   pid AutoPost + viec dang lam (AutoPost ghi)
  auto_post_events.jsonl  ket qua tung dich (AutoPost ghi, bot doc tiep tu offset)
  auto_post_control.json  {"paused": [profile | "*"], "retry": [profile]} (bot ghi, AutoPost doc moi vong)
  posted_history.json     lich su dang (dem bai hom nay)
"""

import html
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import post_kit

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
QUEUE_DIR = Path(os.environ.get("SOCIAL_QUEUE_DIR") or ROOT_DIR / "Videos" / "downloads" / "social_queue").resolve()
STATE_FILE = DATA_DIR / "auto_post_state.json"
STATUS_FILE = DATA_DIR / "auto_post_status.json"
EVENTS_FILE = DATA_DIR / "auto_post_events.jsonl"
CONTROL_FILE = DATA_DIR / "auto_post_control.json"
HISTORY_FILE = DATA_DIR / "posted_history.json"
START_BAT = ROOT_DIR / "start_autopost.bat"

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
TARGET_LABEL = {"tiktok": "TikTok", "fanpage": "Fanpage", "youtube": "YouTube"}
TARGET_ORDER = ("tiktok", "fanpage", "youtube")


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ---------- AutoPost co dang chay ----------

def _autopost_pids() -> list[int]:
    try:
        import psutil
    except ImportError:
        return []
    out = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if (p.info["name"] or "").lower().startswith("python") and any(
                    str(a).lower().endswith("auto_post.py") for a in (p.info["cmdline"] or [])[1:]):
                out.append(p.pid)
        except Exception:
            continue
    return out


def autopost_status() -> dict:
    """{"running": bool, "current": "<profile>/<file> -> <dich>" | "", "at": lan quet cuoi}."""
    st = _read(STATUS_FILE, {}) or {}
    running = bool(_autopost_pids())
    return {"running": running, "current": (st.get("current") or "") if running else "", "at": st.get("at") or ""}


def start_autopost() -> bool:
    """Mo AutoPost trong cua so rieng (nhu start_all.bat). False neu dang chay roi."""
    if _autopost_pids():
        return False
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(["cmd.exe", "/k", "title Muse2tele_AutoPost & \"" + str(START_BAT) + "\""],
                     cwd=str(ROOT_DIR), creationflags=flags, close_fds=True)
    return True


# ---------- File dieu khien ----------

def load_control() -> dict:
    data = _read(CONTROL_FILE, {})
    return data if isinstance(data, dict) else {}


def is_paused(profile: str | None) -> bool:
    paused = load_control().get("paused") or []
    return "*" in paused if not profile else ("*" in paused or profile in paused)


def set_paused(profile: str | None, paused: bool) -> None:
    """profile None = ca AutoPost ("*"). Bo tam dung 1 profile khi dang dung toan bo: chi bo cua profile do."""
    ctl = load_control()
    items = [p for p in ctl.get("paused") or [] if isinstance(p, str)]
    key = profile or "*"
    if paused and key not in items:
        items.append(key)
    if not paused:
        items = [p for p in items if p != key] if profile else []
    ctl["paused"] = items
    _write(CONTROL_FILE, ctl)


def request_retry(profile: str) -> None:
    ctl = load_control()
    retry = [p for p in ctl.get("retry") or [] if isinstance(p, str)]
    if profile not in retry:
        retry.append(profile)
    ctl["retry"] = retry
    _write(CONTROL_FILE, ctl)


# ---------- Su kien ----------

def read_events(offset: int | None) -> tuple[list[dict], int]:
    """Su kien moi tu offset (byte). offset None: bo qua cac su kien cu, tra offset cuoi file."""
    try:
        size = EVENTS_FILE.stat().st_size
    except OSError:
        return [], 0
    if offset is None or offset > size:  # lan dau / file da bi cat ngan
        return [], size if offset is None else 0
    with EVENTS_FILE.open("rb") as f:
        f.seek(offset)
        raw = f.read()
    end = raw.rfind(b"\n") + 1  # chi lay dong da ghi xong
    events = []
    for line in raw[:end].decode("utf-8", "replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events, offset + end


def event_text(ev: dict) -> str:
    """Tin HTML cho 1 su kien ('' = khong bao)."""
    name, target = html.escape(ev.get("file") or ""), TARGET_LABEL.get(ev.get("target"), ev.get("target") or "")
    who = html.escape(ev.get("profile") or "")
    detail = html.escape(ev.get("detail") or "")
    res = ev.get("result")
    if res == "done":
        return f"✅ Đã đăng <b>{name}</b> lên {target} ({who})" + (f"\n{detail}" if detail else "")
    if res == "retry":
        return f"⚠️ {name} → {target} ({who}): {detail}"
    if res == "failed":
        return (f"❌ {name} → {target} ({who}): {detail or 'lỗi'}, đã bỏ.\n"
                f"Đăng lại: <code>/dang {who} thulai</code>")
    if res == "wrong_account":
        return f"❌ {name} → {target} ({who}): tài khoản đang đăng nhập không khớp Bảng đăng bài, không đăng."
    return ""


# ---------- Bao cao ----------

def queue_files(profile: str) -> list[Path]:
    folder = QUEUE_DIR / profile
    if not folder.is_dir():
        return []
    items = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT
             and not post_kit.is_side_file(f) and not f.name.lower().startswith("error_")]
    return sorted(items, key=lambda f: f.stat().st_mtime)


def failed_files(profile: str) -> list[str]:
    folder = QUEUE_DIR / profile / "failed"
    if not folder.is_dir():
        return []
    return sorted(f.name for f in folder.iterdir() if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT
                  and not post_kit.is_side_file(f))


def posted_today(profile: str) -> dict:
    day = datetime.now().date().isoformat()
    out = {}
    for h in _read(HISTORY_FILE, []) or []:
        if h.get("profile") == profile and str(h.get("at", ""))[:10] == day:
            out.setdefault(h.get("platform"), set()).add(h.get("fp"))
    return {k: len(v) for k, v in out.items()}


def recent_events(profile: str, limit: int = 6) -> list[dict]:
    try:
        lines = EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-300:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("profile") == profile and ev.get("result") == "done":
            out.append(ev)
            if len(out) >= limit:
                break
    return out


def _target_line(target: str, info: dict) -> str:
    label = TARGET_LABEL.get(target, target)
    st = info.get("status")
    if st == "done":
        return f"{label} ✅"
    if st == "failed":
        return f"{label} ❌"
    err, nxt = info.get("error") or "", info.get("next_at") or ""
    when = nxt[11:16] if nxt and nxt > datetime.now().isoformat(timespec="minutes") else ""
    extra = ", ".join(x for x in (err, f"lúc {when}" if when else "") if x)
    return f"{label} ⏳" + (f" ({html.escape(extra)})" if extra else "")


def item_line(item: Path, entry: dict | None) -> str:
    name = html.escape(item.name)
    kit_note = ""
    if item.suffix.lower() in VIDEO_EXT:
        kit = post_kit.load_kit(item)
        if kit:
            kit_note = f"🧩 {html.escape(kit.get('title') or '')[:70]} ({len(post_kit.covers(item))} cover)"
        elif post_kit.request_path(item).exists():
            kit_note = "🧩 chờ Muse làm bộ đăng bài"
        else:
            kit_note = "🧩 chưa có bộ đăng bài"
    if entry:
        parts = " · ".join(_target_line(t, entry[t]) for t in TARGET_ORDER if t in entry)
    else:
        parts = "chờ tới lượt"
    return f"• <b>{name}</b> — {parts}" + (f"\n   {kit_note}" if kit_note else "")


def profile_report(profile: str, channel_label: str = "", max_items: int = 15) -> str:
    """Bao cao HTML cua 1 profile: AutoPost, hang doi tung video, loi, da dang hom nay."""
    ap = autopost_status()
    state = (_read(STATE_FILE, {}) or {}).get(profile) or {}
    lines = [f"📤 <b>Đăng bài {html.escape(profile)}</b>"]
    if channel_label:
        lines.append(html.escape(channel_label))
    if not ap["running"]:
        lines.append("AutoPost: 🔴 không chạy")
    elif is_paused(profile):
        lines.append("AutoPost: ⏸ đang tạm dừng profile này")
    elif ap["current"].startswith(profile + "/"):
        cur = ap["current"].split("/", 1)[1]
        file, _, target = cur.partition(" -> ")
        lines.append(f"AutoPost: 🟢 đang đăng {html.escape(file)} → {TARGET_LABEL.get(target, target)}")
    else:
        lines.append("AutoPost: 🟢 đang chạy" + (f" (đang làm {html.escape(ap['current'])})" if ap["current"] else ""))
    items = queue_files(profile)
    if items:
        lines.append(f"\n<b>Hàng đợi ({len(items)})</b>")
        lines += [item_line(i, state.get(i.name)) for i in items[:max_items]]
        if len(items) > max_items:
            lines.append(f"… và {len(items) - max_items} file nữa")
    else:
        lines.append("\nHàng đợi trống.")
    failed = failed_files(profile)
    if failed:
        lines.append(f"\n<b>Lỗi, đã bỏ ({len(failed)})</b>: " + ", ".join(html.escape(f) for f in failed[:8]))
    today = posted_today(profile)
    if today:
        lines.append("\nHôm nay đã đăng: " + " · ".join(f"{TARGET_LABEL.get(k, k)} {v}"
                                                         for k, v in sorted(today.items())))
    recent = recent_events(profile)
    if recent:
        lines.append("<b>Đăng gần đây</b>")
        for ev in recent:
            url = f" {html.escape(ev['detail'])}" if ev.get("detail") else ""
            lines.append(f"• {html.escape(ev['at'][5:16].replace('T', ' '))} {html.escape(ev['file'])} → "
                         f"{TARGET_LABEL.get(ev['target'], ev['target'])}{url}")
    return "\n".join(lines)


def overview(profiles: list[str]) -> str:
    """1 dong / profile cho /dang o General hoac chat rieng."""
    ap = autopost_status()
    head = ("AutoPost: 🔴 không chạy" if not ap["running"] else
            "AutoPost: ⏸ tạm dừng tất cả" if is_paused(None) else
            "AutoPost: 🟢 đang chạy" + (f" (đang đăng {html.escape(ap['current'])})" if ap["current"] else ""))
    state = _read(STATE_FILE, {}) or {}
    lines = ["📤 <b>Đăng bài</b>", head, ""]
    for p in profiles:
        items, failed, today = queue_files(p), failed_files(p), posted_today(p)
        waiting = sum(1 for i in items if any(t.get("status") == "pending"
                                              for t in ((state.get(p) or {}).get(i.name) or {"x": {"status": "pending"}}).values()))
        bits = [f"{waiting} chờ đăng"] + ([f"{len(failed)} lỗi"] if failed else []) + \
               ([f"hôm nay {sum(today.values())} bài"] if today else []) + (["⏸"] if is_paused(p) else [])
        lines.append(f"• <b>{html.escape(p)}</b>: {', '.join(bits)}")
    if not profiles:
        lines.append("Chưa có profile nào tick Tự động đăng / có hàng đợi.")
    return "\n".join(lines)
