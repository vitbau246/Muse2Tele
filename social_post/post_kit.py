# -*- coding: utf-8 -*-
"""
Bo dang bai (post kit) cua 1 video trong hang doi dang: tieu de, mo ta, hashtag, caption tung nen tang, 3 tieu de +
3 anh cover de thu nghiem. Do Muse lam: auto_post.py thay video chua co bo dang bai thi KHONG dang, ghi file yeu cau;
bot Telegram (muse_telebot.py) doc yeu cau, gui Muse (kem vai khung hinh cua video), nhan tra loi va ghi bo dang bai.
Dung chung cho social_post\\auto_post.py va muse_telebot\\muse_telebot.py (khong phu thuoc thu vien ngoai).

Canh video <stem>.mp4 trong social_queue\\<profile>\\:
  <stem>.post.json          bo dang bai {"kit_id", "title", "titles": [<=3], "description", "hashtags": [...],
                            "tiktok", "facebook", "source", "at"}
  <stem>.cover1.jpg .. 3    anh cover (YouTube: 1 anh = thumbnail, 2-3 anh = Thu nghiem A/B)
  <stem>.kit_request.json   yeu cau dang cho Muse {"kit_id", "video", "profile", "muse", "targets", "at"}

Muse tra loi 1 khoi chu:
  POSTKIT <kit_id>
  {"title": "...", "titles": ["...", "...", "..."], "description": "...", "hashtags": ["#..."], "tiktok": "...",
   "facebook": "..."}
va 3 anh ten <kit_id>-a.jpg, <kit_id>-b.jpg, <kit_id>-c.jpg.
"""

import hashlib
import json
import re
import time
from pathlib import Path

KIT_SUFFIX = ".post.json"
REQUEST_SUFFIX = ".kit_request.json"
MARK = "POSTKIT"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
COVER_RE = re.compile(r"\.cover\d+$", re.I)  # <stem>.coverN: anh cover di kem video, khong la bai rieng
TITLE_MAX, DESC_MAX, TIKTOK_MAX, FB_MAX = 100, 5000, 2200, 5000
COVERS_WANTED = 3


def kit_path(video: Path) -> Path:
    return video.with_name(video.stem + KIT_SUFFIX)


def request_path(video: Path) -> Path:
    return video.with_name(video.stem + REQUEST_SUFFIX)


def kit_id(video: Path) -> str:
    """Ma ngan, on dinh theo ten file: Muse dat ten anh theo ma nay (K + 6 ky tu)."""
    return "K" + hashlib.sha1(video.name.encode("utf-8")).hexdigest()[:6].upper()


def is_side_file(path: Path) -> bool:
    """File di kem video (cover / bo dang bai / yeu cau), khong phai 1 bai dang rieng."""
    name = path.name.lower()
    return bool(COVER_RE.search(path.stem)) or name.endswith(KIT_SUFFIX) or name.endswith(REQUEST_SUFFIX)


def covers(video: Path) -> list[Path]:
    """Anh cover cua video: <stem>.coverN.<anh>, toi da 3 anh so nho nhat."""
    found = [f for f in video.parent.glob(video.stem.replace("[", "[[]") + ".cover*")
             if f.suffix.lower() in IMAGE_EXT and COVER_RE.search(f.stem)]
    return sorted(found, key=lambda f: int(COVER_RE.search(f.stem).group(0)[6:]))[:COVERS_WANTED]


def side_files(video: Path) -> list[Path]:
    """Moi file di kem video (caption .txt, bo dang bai, yeu cau, cover) de chuyen cung video sang done\\ / failed\\."""
    return [p for p in (video.with_suffix(".txt"), kit_path(video), request_path(video), *covers(video)) if p.is_file()]


def _clean(text: object, limit: int) -> str:
    return str(text or "").replace("<", "").replace(">", "").strip()[:limit]


def normalize(raw: dict) -> dict | None:
    """Bo dang bai hop le (co tieu de + mo ta) hoac None."""
    if not isinstance(raw, dict):
        return None
    title = _clean(raw.get("title"), TITLE_MAX)
    titles = [_clean(t, TITLE_MAX) for t in raw.get("titles") or [] if _clean(t, TITLE_MAX)]
    title = title or (titles[0] if titles else "")
    description = _clean(raw.get("description"), DESC_MAX)
    if not title or not description:
        return None
    if title not in titles:
        titles.insert(0, title)
    tags = raw.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.split()
    hashtags = []
    for t in tags:
        t = "#" + str(t).strip().lstrip("#").replace(" ", "")
        if len(t) > 1 and t not in hashtags:
            hashtags.append(t)
    return {"kit_id": str(raw.get("kit_id") or ""), "title": title, "titles": titles[:3], "description": description,
            "hashtags": hashtags[:15], "tiktok": _clean(raw.get("tiktok"), TIKTOK_MAX),
            "facebook": _clean(raw.get("facebook"), FB_MAX)}


def parse_reply(text: str) -> dict | None:
    """Tim khoi 'POSTKIT <ma>' + JSON trong tin Muse. Tra ve bo dang bai (kem kit_id neu co) hoac None."""
    for m in re.finditer(MARK + r"\s*(K[0-9A-F]{6})?", text or "", re.I):
        start = text.find("{", m.end())
        if start < 0:
            continue
        try:
            raw, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            continue
        kit = normalize(raw)
        if kit:
            kit["kit_id"] = (m.group(1) or kit["kit_id"] or "").upper()
            return kit
    return None


def load_kit(video: Path) -> dict | None:
    try:
        raw = json.loads(kit_path(video).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    kit = normalize(raw)
    if kit:
        kit["source"], kit["at"] = raw.get("source", ""), raw.get("at", "")
    return kit


def save_kit(video: Path, kit: dict, source: str) -> Path:
    path = kit_path(video)
    data = {**kit, "kit_id": kit.get("kit_id") or kit_id(video), "source": source,
            "at": time.strftime("%Y-%m-%d %H:%M")}
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def cover_slot(name: str, kid: str) -> int | None:
    """So thu tu cover (1-3) theo ten anh Muse gui: '<kid>-a.jpg' / '<kid>_b.png' / '<kid>-cover-3.jpg'."""
    m = re.search(re.escape(kid) + r"[\s_\-.]*(?:cover)?[\s_\-.]*([abc123])\b", name or "", re.I)
    if not m:
        return None
    c = m.group(1).lower()
    return "abc".index(c) + 1 if c in "abc" else int(c)


def save_cover(video: Path, slot: int, data: bytes, ext: str) -> Path:
    ext = ext.lower() if ext.lower() in IMAGE_EXT else ".jpg"
    for old in video.parent.glob(video.stem.replace("[", "[[]") + f".cover{slot}.*"):
        old.unlink(missing_ok=True)
    path = video.with_name(f"{video.stem}.cover{slot}{ext}")
    path.write_bytes(data)
    return path


def write_request(video: Path, profile: str, targets: list[str], muse: str = "") -> Path:
    path = request_path(video)
    if not path.exists():
        path.write_text(json.dumps({"kit_id": kit_id(video), "video": str(video), "profile": profile, "muse": muse,
                                    "targets": targets, "at": time.strftime("%Y-%m-%d %H:%M")},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def read_request(path: Path) -> dict | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) and raw.get("kit_id") and raw.get("video") else None


def captions(kit: dict) -> dict:
    """Noi dung tung nen tang tu bo dang bai."""
    tags = " ".join(kit.get("hashtags") or [])
    desc = kit["description"] + (f"\n\n{tags}" if tags else "")
    return {
        "youtube_title": kit["title"],
        "youtube_description": desc,
        "tiktok": kit.get("tiktok") or (kit["title"] + (f" {tags}" if tags else "")),
        "facebook": kit.get("facebook") or f"{kit['title']}\n\n{desc}",
    }


PLATFORM_NAMES = {"youtube": "YouTube", "fanpage": "Facebook", "tiktok": "TikTok"}
PLATFORM_ORDER = ("tiktok", "fanpage", "youtube")
JSON_TEMPLATE = ('{"title": "...", "titles": ["...", "...", "..."], "description": "...", "hashtags": ["#...", "#..."], '
                 '"tiktok": "...", "facebook": "..."}')


def platforms_label(targets: list[str]) -> str:
    return ", ".join(PLATFORM_NAMES.get(t, t) for t in targets) or "mạng xã hội"


def _covers_spec(kid: str) -> str:
    return (f"3 ảnh cover khung 16:9, 1280x720, JPG hoặc PNG, mỗi ảnh dưới 2 MB, 3 hướng khác nhau rõ rệt để YouTube "
            f"thử nghiệm A/B (vd cận cảnh cảm xúc nhân vật / khoảnh khắc hoành tráng nhất / bí ẩn gây tò mò), dùng đúng "
            f"nhân vật và bối cảnh của video, chữ to dễ đọc trên điện thoại. Đặt tên file {kid}-a.jpg, {kid}-b.jpg, "
            f"{kid}-c.jpg và đính kèm ảnh trực tiếp trong chat.")


def _fields_spec() -> str:
    return (f"- title: tiêu đề YouTube chính (dưới {TITLE_MAX} ký tự, gây tò mò); titles: 3 tiêu đề khác nhau để thử "
            "nghiệm, tiêu đề đầu = title\n"
            "- description: mô tả YouTube 2-4 câu; hashtags: 3-8 hashtag\n"
            "- tiktok: caption TikTok ngắn kèm hashtag (dưới 300 ký tự)\n"
            "- facebook: nội dung bài đăng Facebook\n")


def prompt(kid: str, video_name: str, duration: str, frames: int, targets: list[str], lang: str = "",
           extra: str = "", remembered: bool = False) -> str:
    """Yeu cau Muse lam bo dang bai cho 1 video. remembered: Muse da luu quy tac bo dang bai vao bo nho dai han
    (memory_rule) -> nhac ngan, van ghi dinh dang khoi POSTKIT (bot can doc dung)."""
    head = (f"Chuẩn bị đăng video \"{video_name}\"{f' ({duration})' if duration else ''} lên {platforms_label(targets)}. "
            + (f"{extra} " if extra else "")
            + (f"Ảnh đính kèm là {frames} khung hình trích từ video. " if frames else ""))
    block = f"{MARK} {kid}\n{JSON_TEMPLATE}\n"
    if remembered:
        return (f"{MARK} {kid} — {head}Làm bộ đăng bài cho video này theo quy tắc bộ đăng bài trong bộ nhớ dài hạn: "
                f"3 ảnh cover {kid}-a.jpg, {kid}-b.jpg, {kid}-c.jpg (16:9, 1280x720) + khối chữ:\n\n{block}\n"
                + (f"Viết chữ bằng {lang}. " if lang else "")
                + "Gửi khối chữ và 3 ảnh trong cùng lượt trả lời.")
    return (
        head + "Hãy làm bộ đăng bài cho video này:\n\n"
        f"1. {_covers_spec(kid)}\n"
        f"2. Một khối chữ đúng định dạng dưới đây (giữ nguyên dòng {MARK} {kid}, JSON hợp lệ):\n\n"
        f"{block}\n"
        + _fields_spec()
        + (f"Viết chữ bằng {lang}.\n" if lang else "")
        + "\nGửi khối chữ và 3 ảnh trong cùng lượt trả lời."
    )


# ---------- Bo nho dai han cua Muse: quy tac bo dang bai ----------
# Bot gui 1 lan vao bo nho dai han cua Muse nao se duoc nho lam bo dang bai (profile tick "Tu dong dang" + Muse lam
# video cho doi co dang video), gui lai khi doi nen tang / kenh, sau khi reset Muse; bo tick het thi nhan Muse bo quy tac.
MEMORY_VERSION = "v1"


def memory_sig(targets: list[str], channels: list[str]) -> str:
    """Chu ky quy tac da gui; "" = khong can quy tac (khong dang tu dong)."""
    return json.dumps([MEMORY_VERSION, list(targets), list(channels)], ensure_ascii=False) if targets else ""


def memory_rule(targets: list[str], channels: list[str]) -> str:
    """Tin cap nhat bo nho dai han: quy tac bo dang bai (tieu de, mo ta, hashtag, 3 cover) cho cac nen tang targets.
    channels: mo ta kenh se dang (vd 'YouTube @Kenh', 'Trang Facebook "Ten"') de Muse viet dung giong kenh."""
    where = platforms_label(targets)
    lines = "\n".join(f"- {c}" for c in channels)
    return (
        "Cập nhật bộ nhớ dài hạn (thiết lập cố định của chủ, áp dụng từ giờ, thay cho quy tắc bộ đăng bài trước đó):\n\n"
        f"Chủ đã bật TỰ ĐỘNG ĐĂNG video lên {where}. Video chỉ được đăng khi có BỘ ĐĂNG BÀI do bạn làm: tiêu đề, "
        "mô tả, hashtag, caption từng nền tảng và 3 ảnh cover.\n"
        + (f"Kênh sẽ đăng:\n{lines}\n" if lines else "")
        + f"\nMỗi khi bot gửi tin có dòng \"{MARK} <mã>\" (mã dạng K + 6 ký tự, kèm vài khung hình của video), trả lời "
        "trong CÙNG MỘT lượt gồm:\n"
        f"1. {_covers_spec('<mã>')}\n"
        f"2. Một khối chữ, dòng đầu giữ nguyên \"{MARK} <mã>\", ngay sau là JSON hợp lệ (không bọc trong ``` và không "
        f"thêm chữ vào giữa):\n{MARK} <mã>\n{JSON_TEMPLATE}\n"
        + _fields_spec()
        + "Nội dung phải đúng nhân vật, bối cảnh, ngôn ngữ của video; không hứa hẹn sai sự thật, không giật tít gây "
        "hiểu lầm. Không tự làm bộ đăng bài khi chưa có yêu cầu kèm mã.\n\n"
        "Lưu quy tắc trên vào bộ nhớ dài hạn. Trả lời ngắn: xác nhận đã lưu."
    )


def memory_off() -> str:
    return ("Cập nhật bộ nhớ dài hạn: chủ đã TẮT tự động đăng video. Bỏ quy tắc bộ đăng bài (" + MARK + ") khỏi bộ nhớ "
            "dài hạn; chỉ làm tiêu đề, mô tả, cover khi chủ hoặc bot yêu cầu trực tiếp.\n\nTrả lời ngắn: xác nhận đã lưu.")
