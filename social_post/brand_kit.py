# -*- coding: utf-8 -*-
"""
Bo nhan dien kenh (brand kit) cho lenh /rebrand cua bot: Muse de xuat ten kenh, handle, tieu su, mo ta va 3 anh
(anh dai dien, anh bia Facebook, banner YouTube); rebrand.py dung no de tao Trang Facebook + kenh YouTube moi, sua ho so
TikTok va gan vao Bang dang bai. Dung chung cho muse_telebot.py va social_post\\rebrand.py (khong thu vien ngoai).

Muse tra loi 1 khoi chu:
  BRANDKIT <ma>
  {"name", "handles": [..3], "category", "bio", "description", "tiktok_name", "tiktok_bio", "tiktok_usernames": [..3]}
va 3 anh ten <ma>-avatar.png, <ma>-cover.png, <ma>-banner.png.

Luu trong Videos\\downloads\\channels\\<profile>\\<ma>\\: kit.json + avatar.<ext> + cover.<ext> + banner.<ext>.
"""

import json
import re
import secrets
import time
from pathlib import Path

MARK = "BRANDKIT"
IMAGES = ("avatar", "cover", "banner")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
HANDLE_RE = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
TIKTOK_RE = re.compile(r"^[a-z0-9._]{2,24}$")
# Kich thuoc dich (rebrand.py cat / doi co cho dung)
SIZES = {"avatar": (800, 800), "cover": (1640, 624), "banner": (2560, 1440)}


def new_id() -> str:
    return "B" + secrets.token_hex(3).upper()


def _clean(text: object, limit: int) -> str:
    return " ".join(str(text or "").replace("<", "").replace(">", "").split(" ")).strip()[:limit]


def _list(raw: object) -> list[str]:
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    return [str(x).strip().lstrip("@") for x in raw or [] if str(x).strip()]


def normalize(raw: dict) -> dict | None:
    """Bo nhan dien hop le (co ten + it nhat 1 handle YouTube dung dinh dang) hoac None."""
    if not isinstance(raw, dict):
        return None
    name = _clean(raw.get("name"), 75)
    handles = [h for h in _list(raw.get("handles") or raw.get("handle")) if HANDLE_RE.match(h)][:3]
    if not name or not handles:
        return None
    tiktok_users = [u.lower() for u in _list(raw.get("tiktok_usernames") or raw.get("tiktok_username"))
                    if TIKTOK_RE.match(u.lower())][:3]
    return {"name": name, "handles": handles, "category": _clean(raw.get("category"), 60) or "Sáng tạo nội dung số",
            "bio": _clean(raw.get("bio"), 255), "description": str(raw.get("description") or "").strip()[:1000],
            "tiktok_name": _clean(raw.get("tiktok_name") or name, 30), "tiktok_bio": _clean(raw.get("tiktok_bio"), 80),
            "tiktok_usernames": tiktok_users}


def parse_reply(text: str) -> tuple[str, dict] | None:
    """(ma, bo nhan dien) tu tin Muse co khoi 'BRANDKIT <ma>' + JSON, hoac None."""
    for m in re.finditer(MARK + r"\s*(B[0-9A-F]{6})?", text or "", re.I):
        start = text.find("{", m.end())
        if start < 0:
            continue
        try:
            raw, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            continue
        kit = normalize(raw)
        if kit:
            return (m.group(1) or "").upper(), kit
    return None


def image_slot(name: str, kid: str) -> str | None:
    """'avatar' / 'cover' / 'banner' theo ten anh Muse gui (<ma>-avatar.png...)."""
    m = re.search(re.escape(kid) + r"[\s_\-.]*(avatar|cover|banner)", name or "", re.I)
    return m.group(1).lower() if m else None


def folder(root: Path, profile: str, kid: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile)
    return root / safe / kid


def save_kit(dest: Path, kid: str, kit: dict, source: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "kit.json"
    path.write_text(json.dumps({"id": kid, **kit, "source": source, "at": time.strftime("%Y-%m-%d %H:%M")},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def save_image(dest: Path, slot: str, data: bytes, ext: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    ext = ext.lower() if ext.lower() in IMAGE_EXT else ".png"
    for old in dest.glob(f"{slot}.*"):
        old.unlink(missing_ok=True)
    path = dest / f"{slot}{ext}"
    path.write_bytes(data)
    return path


def images(dest: Path) -> dict[str, Path]:
    out = {}
    for slot in IMAGES:
        found = [p for p in dest.glob(f"{slot}.*") if p.suffix.lower() in IMAGE_EXT]
        if found:
            out[slot] = found[0]
    return out


def load(dest: Path) -> dict | None:
    try:
        raw = json.loads((dest / "kit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    kit = normalize(raw)
    if kit:
        kit["id"] = raw.get("id", "")
    return kit


def complete(dest: Path) -> bool:
    return load(dest) is not None and len(images(dest)) == len(IMAGES)


def daily_ledger(channels_dir: Path, profile: str) -> Path:
    """So cac kenh tao theo lich hang ngay (bot /kenhmoi): data\\channels\\<profile>.daily.json."""
    return channels_dir / f"{profile}.daily.json"


def load_daily(channels_dir: Path, profile: str) -> list[dict]:
    try:
        rows = json.loads(daily_ledger(channels_dir, profile).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def add_daily(channels_dir: Path, profile: str, row: dict) -> None:
    """Ghi / cap nhat 1 dong (theo ma bo nhan dien "kit")."""
    rows = [r for r in load_daily(channels_dir, profile) if r.get("kit") != row.get("kit")] + [row]
    channels_dir.mkdir(parents=True, exist_ok=True)
    daily_ledger(channels_dir, profile).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def prompt(kid: str, profile: str, note: str = "", current: list[str] = (), daily: bool = False) -> str:
    """daily: dot tao kenh hang ngay (bot /kenhmoi) -- them 1 Trang FB + 1 kenh YT moi, khong doi TikTok, kenh cu
    giu nguyen; current = cac kenh da co (ten moi phai khac)."""
    now = "\n".join(f"- {c}" for c in current)
    if daily:
        intro = (f"{MARK} {kid} — Hôm nay chủ cần thêm 1 Trang Facebook MỚI và 1 kênh YouTube MỚI cho profile "
                 f"{profile} (các kênh đã có giữ nguyên, TikTok không đổi). "
                 + (f"Các kênh đã có (tên, handle mới phải KHÁC hẳn):\n{now}\n" if now else ""))
    else:
        intro = (f"{MARK} {kid} — Chủ muốn REBRAND các kênh đăng video của bạn (profile {profile}): làm kênh mới trên "
                 "YouTube và Facebook, đổi hồ sơ TikTok, xoá các video TikTok cũ. "
                 + (f"Kênh hiện tại:\n{now}\n" if now else ""))
    return (
        intro
        + (f"Định hướng của chủ: {note}\n" if note else
           "Định hướng: dựa trên loại video bạn đang / sẽ làm cho chủ (nhân vật, thể loại, khán giả).\n")
        + "\nHãy làm BỘ NHẬN DIỆN KÊNH, gửi trong CÙNG MỘT lượt trả lời:\n\n"
        f"1. 3 ảnh, đính kèm trực tiếp trong chat, đặt đúng tên:\n"
        f"   - {kid}-avatar.png: ảnh đại diện vuông 800x800, logo / nhân vật chính, nhìn rõ khi thu nhỏ thành hình tròn\n"
        f"   - {kid}-cover.png: ảnh bìa Trang Facebook 1640x624\n"
        f"   - {kid}-banner.png: banner YouTube 2560x1440, chữ và chi tiết chính nằm trong vùng giữa 1546x423 (vùng "
        "luôn hiện trên điện thoại)\n"
        "   Cùng một phong cách, màu sắc, tên kênh; không dùng logo / nhân vật của thương hiệu khác.\n"
        f"2. Một khối chữ, dòng đầu giữ nguyên \"{MARK} {kid}\", ngay sau là JSON hợp lệ (không bọc ```):\n\n"
        f"{MARK} {kid}\n"
        '{"name": "...", "handles": ["...", "...", "..."], "category": "...", "bio": "...", "description": "...", '
        '"tiktok_name": "...", "tiktok_bio": "...", "tiktok_usernames": ["...", "...", "..."]}\n\n'
        "- name: tên kênh dùng chung cho Trang Facebook và kênh YouTube (dưới 50 ký tự)\n"
        "- handles: 3 handle YouTube theo thứ tự ưu tiên (3-30 ký tự: chữ không dấu, số, . _ -), handle càng riêng "
        "càng dễ còn trống\n"
        "- category: hạng mục Trang Facebook bằng tiếng Việt (vd Phim, Video, Sáng tạo nội dung số)\n"
        "- bio: tiểu sử Trang Facebook (dưới 255 ký tự)\n"
        "- description: mô tả kênh YouTube 3-6 câu (dưới 1000 ký tự)\n"
        + ("- tiktok_name, tiktok_bio: để \"\"; tiktok_usernames: để [] (lần này không đổi TikTok)\n" if daily else
           "- tiktok_name: tên hiển thị TikTok (dưới 30 ký tự); tiktok_bio: tiểu sử TikTok (dưới 80 ký tự)\n"
           "- tiktok_usernames: 3 username TikTok mới theo thứ tự ưu tiên (2-24 ký tự: a-z, số, . _), để [] nếu giữ "
           "username cũ\n")
    )
