# -*- coding: utf-8 -*-
"""
Doi Muse: 1 Muse lam chi huy (muc General cua nhom), giao viec cho cac Muse khac, theo doi tien do va cham ket qua.
Bot dung giua chuyen tin (Telegram khong cho bot doc tin cua bot khac, cac Muse cung khong thay nhau).

Cai dat: dashboard FoxProfile -> Doi Muse, luu muse_team.json canh file nay. Bot doc lai moi lan dung (ap dung ngay):
    {"mode": "solo" | "chief", "chief": "<profile>", "approval": "manual" | "auto", "roles": {"<profile>": "<vai tro>"},
     "excluded": ["<profile>"], "pass_score": 8, "max_rounds": 3, "max_new_per_hour": 20, "quiet_minutes": 3,
     "overdue_minutes": 30, "one_video": true, "show_failed_media": false, "reset_id": "<ma>",
     "setup": {"<profile>": {"lang": "vi", "context": "<bo nho dai han>"}}}
Doi = cac profile co topic, tru chi huy va cac profile trong "excluded".
setup: ngon ngu tra loi + ngu canh (bo nho dai han) tung Muse, ca chi huy. Bot gui cho Muse 1 lan ("Cap nhat bo nho
dai han"), gui lai khi chu sua hoac sau khi xoa du lieu Muse; viec moi chi gui cho Muse da nhan thiet lap.
reset_id: dashboard dat ma moi khi chu tick "Xoa du lieu Muse" luc luu -> bot reset Muse cua chi huy + ca doi 1 lan.

Giao thuc: dong [[lenh: ...]] trong tin cua Muse. Bot thuc hien, an dong do khoi Telegram.
    Chi huy:  [[giao: <profile> | <viec>]]               giao viec moi (bot danh so T1, T2...)
              [[giao: <profile> | <viec> | 5 video]]     viec nhieu video: Muse lam va nop tung video, dat moi lam tiep
              [[nhan: T3 | <noi dung>]]                  nhan them cho Muse dang lam viec T3 (tra loi cau hoi, bo sung)
              [[lamlai: T3 | <can sua gi>]]              chua dat, lam lai (toi da max_rounds lan)
              [[danhgia: T3 | 8/10 | <nhan xet>]]        cham diem: tu pass_score la dat, duoi thi bot tu cho lam lai
    Muse lam: [[xong: T3]]                               lam xong
              [[vuong: T3 | <ly do / cau hoi>]]          khong lam duoc / can hoi lai
Nhac ma viec da dat (VD "dung bo nhan vat T5") trong lenh giao / nhan / lamlai: bot dinh kem anh / video va mo ta da
duyet cua viec do cho Muse lam (tranh chi huy ta lai theo tri nho, sai lech).
"""

import json
import re
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "muse_team.json"
POST_MAP_FILE = HERE.parent / "social_post" / "data" / "post_map.json"  # Bang dang bai (dashboard FoxProfile)
POST_MODES = ("off", "ask", "auto")

# Thong so chinh tren dashboard: mac dinh va gioi han (giong foxprofile/repo/src/core/muse_team.py)
DEFAULTS = {"pass_score": 8, "max_rounds": 3, "max_new_per_hour": 20, "quiet_minutes": 3, "overdue_minutes": 30,
            "one_video": True, "show_failed_media": False}
LIMITS = {"pass_score": (1, 10), "max_rounds": (1, 10), "max_new_per_hour": (1, 200), "quiet_minutes": (1, 60),
          "overdue_minutes": (5, 600)}

MAX_PARTS = 20            # viec nhieu video: toi da 20 video
REPORT_MAX_CHARS = 3500
REPORT_MAX_FILES = 4
REPORT_FILE_MAX_BYTES = 30 * 1024 * 1024
REF_MAX_FILES = 4         # file tham chieu (tu viec da dat) dinh kem cho Muse lam
REF_REPORT_CHARS = 700
TASKS_KEEP = 100

CHIEF_VERBS = ("giao", "nhan", "lamlai", "danhgia")
WORKER_VERBS = ("xong", "vuong")
COMMAND_RE = re.compile(r"\[\[\s*([^\[\]:|\n]{2,20}?)\s*:\s*(.*?)\s*\]\]", re.DOTALL)
TASK_ID_RE = re.compile(r"^\s*T?\s*(\d{1,6})\s*$", re.IGNORECASE)
TASK_REF_RE = re.compile(r"(?<![\w/])T(\d{1,6})\b")
PARTS_RE = re.compile(r"^\s*(\d{1,2})\s*(?:video|clip|tập|tap)s?\s*$", re.IGNORECASE)
SCORE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:/\s*(\d+))?")
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
VIDEO_TASK_RE = re.compile(r"video|clip|phim|reel|tiktok", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
MUSE_FILE_RE = re.compile(r"https?://(?:www\.)?muse\.ai/files/[^\s<>\"')\]]+", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<![\w&])#[^\s#.,;:!?()\[\]\"']+")
ARTIFACT_NAME = "Tổng hợp video"
# Ngon ngu tra loi (ma giong LANGS trong foxprofile/repo/src/core/muse_team.py)
LANG_NAMES = {"vi": "tiếng Việt", "en": "tiếng Anh (English)", "zh": "tiếng Trung (中文)", "ja": "tiếng Nhật (日本語)",
              "ko": "tiếng Hàn (한국어)", "th": "tiếng Thái (ไทย)", "id": "tiếng Indonesia (Bahasa Indonesia)"}

STATUS_LABEL = {"duyet": "chờ chủ duyệt", "cho": "chờ gửi", "lam": "đang làm", "bao": "chờ chấm", "dat": "đạt",
                "bo": "đã bỏ", "can_xem": "cần chủ xem", "loi": "lỗi gửi"}
OPEN_STATUSES = ("duyet", "cho", "lam", "bao", "can_xem")
CLOSED_STATUSES = ("dat", "bo", "loi")


def _num(raw, key):
    lo, hi = LIMITS[key]
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULTS[key]
    return min(hi, max(lo, value))


def _setup(raw):
    """{profile: {"lang", "context"}}: bo ngon ngu la, bo muc trong."""
    out = {}
    for name, item in (raw.items() if isinstance(raw, dict) else []):
        if not isinstance(item, dict):
            continue
        lang = str(item.get("lang") or "").strip()
        lang = lang if lang in LANG_NAMES else ""
        context = "\n".join(str(item.get("context") or "").splitlines()).strip()
        if str(name).strip() and (lang or context):
            out[str(name).strip()] = {"lang": lang, "context": context}
    return out


def config():
    """Cai dat doi Muse. mode "chief" chi khi co ten chi huy."""
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    chief = str(raw.get("chief") or "").strip()
    roles = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    excluded = raw.get("excluded") if isinstance(raw.get("excluded"), list) else []
    cfg = {"mode": "chief" if raw.get("mode") == "chief" and chief else "solo",
           "chief": chief,
           "approval": "auto" if raw.get("approval") == "auto" else "manual",
           "task_lang": raw.get("task_lang") if raw.get("task_lang") in LANG_NAMES else "",
           # video dat: off = chi gui topic; ask = nut Dang theo kenh; auto = dua thang vao hang doi kenh mac dinh
           "post_mode": raw.get("post_mode") if raw.get("post_mode") in POST_MODES else "ask",
           "post_profile": str(raw.get("post_profile") or "").strip(),
           "roles": {str(k): " ".join(str(v).split()) for k, v in roles.items() if str(v).strip()},
           # profile bo tick tren dashboard: khong o trong doi (profile moi mac dinh vao doi)
           "excluded": {str(x).strip() for x in excluded if str(x).strip()},
           "setup": _setup(raw.get("setup")),
           "reset_id": str(raw.get("reset_id") or "")}
    for key in LIMITS:
        cfg[key] = _num(raw.get(key, DEFAULTS[key]), key)
    for key in ("one_video", "show_failed_media"):
        cfg[key] = bool(raw.get(key, DEFAULTS[key]))
    return cfg


def post_channels():
    """Bang dang bai: {profile: {"fanpages": [{id, name}], "tiktok", "caption_lang", ...}} cac profile co dich dang."""
    try:
        raw = json.loads(POST_MAP_FILE.read_text(encoding="utf-8")).get("profiles") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {str(k): v for k, v in raw.items()
            if isinstance(v, dict) and (v.get("fanpages") or v.get("tiktok"))}


def channel_label(name, entry):
    """'P1 — FB: Trang A (123), Trang B · TikTok @abc'."""
    pages = ", ".join(f"{p['name']} ({p['id']})" if p.get("name") else str(p["id"])
                      for p in entry.get("fanpages") or [])
    parts = ([f"FB: {pages}"] if pages else []) + ([f"TikTok @{entry['tiktok']}"] if entry.get("tiktok") else [])
    lang = LANG_NAMES.get(entry.get("caption_lang", ""), "")
    return f"{name} — {' · '.join(parts)}" + (f" · caption {lang}" if lang else "")


def caption_langs(cfg, worker):
    """Ngon ngu caption them can cho video Muse nay lam: caption_lang cua kenh se dang (kenh mac dinh, khong co thi
    moi kenh trong Bang dang bai), tru ngon ngu Muse dang lam viec."""
    if cfg["post_mode"] == "off":
        return []
    channels = post_channels()
    pick = [channels[cfg["post_profile"]]] if cfg["post_profile"] in channels else list(channels.values())
    own = (cfg["setup"].get(worker) or {}).get("lang") or cfg["task_lang"]
    out = []
    for entry in pick:
        code = entry.get("caption_lang") or ""
        if code in LANG_NAMES and code != own and code not in out:
            out.append(code)
    return out


def post_caption(info, lang):
    """Caption dang bai cho kenh: caption theo ngon ngu kenh (neu Muse co ghi), khong thi caption chung; + hashtag."""
    text = (info.get("captions") or {}).get(lang) or info.get("caption") or ""
    return "\n\n".join(x for x in (text.strip(), (info.get("hashtag") or "").strip()) if x)


def chief():
    cfg = config()
    return cfg["chief"] if cfg["mode"] == "chief" else None


def _verb(word):
    """'Đánh giá' / 'danh gia' / 'DanhGia' -> 'danhgia'."""
    plain = unicodedata.normalize("NFD", word.replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"[^a-z]", "", "".join(c for c in plain if unicodedata.category(c) != "Mn").lower())


def parse(text, verbs):
    """Cac lenh [[...]] trong text co dong tu thuoc verbs: [(verb, [tham so])]."""
    found = []
    for m in COMMAND_RE.finditer(text or ""):
        verb = _verb(m.group(1))
        if verb not in verbs:
            continue
        limit = 2 if verb == "danhgia" else 0 if verb == "xong" else 1
        args = [a.strip() for a in m.group(2).split("|", limit)] if limit else [m.group(2).strip()]
        found.append((verb, args))
    return found


def task_parts(text):
    """'<viec> | 5 video' -> ('<viec>', 5). Khong ghi so video -> (text, 1)."""
    head, sep, tail = (text or "").rpartition("|")
    m = PARTS_RE.match(tail) if sep else None
    if not m:
        return (text or "").strip(), 1
    return head.strip(), max(1, min(MAX_PARTS, int(m.group(1))))


def strip(text, verbs):
    """Bo cac lenh [[...]] (thuoc verbs) khoi text (chu thuong hoac HTML)."""
    return re.sub(r"\n{3,}", "\n\n", COMMAND_RE.sub(lambda m: "" if _verb(m.group(1)) in verbs else m.group(0),
                                                    text or "")).strip()


def task_id(raw):
    m = TASK_ID_RE.match(raw or "")
    return f"T{int(m.group(1))}" if m else None


def task_refs(text):
    """Ma viec nhac trong text: 'dung bo nhan vat T5 va T6' -> ['T5', 'T6']."""
    out = []
    for m in TASK_REF_RE.finditer(text or ""):
        tid = f"T{int(m.group(1))}"
        if tid not in out:
            out.append(tid)
    return out


def parse_score(raw):
    """'8/10', '8', '8.5 / 10', '80/100' -> diem tren thang 10 (float), khong doc duoc -> None."""
    m = SCORE_RE.search(raw or "")
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    scale = int(m.group(2)) if m.group(2) else 10
    if scale <= 0:
        return None
    value = value * 10 / scale
    return value if 0 <= value <= 10 else None


def score_label(score, raw=""):
    return f"{score:g}/10" if score is not None else (" ".join((raw or "").split()) or "—")


def short(text, n=120):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rstrip() + "…"


def is_video(path):
    return Path(path).suffix.lower() in VIDEO_EXT


def part_label(task):
    parts = task.get("parts", 1)
    return f"video {task.get('part', 1)}/{parts}" if parts > 1 else ""


def is_video_task(task):
    """Viec lam video: nhieu video, mo ta nhac video / clip / phim, hoac Muse da nop video."""
    return (task.get("parts", 1) > 1 or bool(VIDEO_TASK_RE.search(task.get("text") or ""))
            or any(is_video(f) for f in task.get("files") or []))


def _field(lines, *names):
    """Gia tri dong '<ten>: ...' (vd 'Caption: ...') trong bao cao, bo dau **, -, • o dau dong."""
    for line in lines:
        clean = re.sub(r"^[\s\-•*>#\d.)]*", "", line).replace("**", "").strip()
        head, sep, value = clean.partition(":")
        if sep and _verb(head) in names and value.strip():
            return value.strip()
    return ""


def video_info(task):
    """Link tai / caption / hashtag Muse lam ghi trong bao cao (cho dong cua trang tong hop video)."""
    text = "\n".join(task.get("report") or [])
    lines = text.splitlines()
    link_line = _field(lines, "linktai", "link", "linkvideo", "linktaivideo", "download", "downloadlink")
    link = (MUSE_FILE_RE.search(link_line) or URL_RE.search(link_line) or MUSE_FILE_RE.search(text))
    caption = _field(lines, "caption", "captionrieng", "captiondang", "chuthich")
    hashtag = _field(lines, "hashtag", "hashtags", "tag", "tags")
    if not hashtag:
        hashtag = " ".join(dict.fromkeys(m.group(0) for m in HASHTAG_RE.finditer(text)))
    # Caption theo ngon ngu kenh dang: dong "Caption (en): ..." / "Caption en: ..."
    captions = {code: value for code in LANG_NAMES if (value := _field(lines, f"caption{code}"))}
    return {"link": link.group(0).rstrip(".,;") if link else "", "caption": caption, "hashtag": hashtag,
            "captions": captions}


def summary_row(task, info, score=""):
    """1 dong chuan cho trang artifact tong hop video."""
    return " | ".join([task["id"], task["to"], part_label(task) or "video 1/1",
                       info["link"] or "(chưa có link tải)", info["caption"] or "(chưa có caption)",
                       info["hashtag"] or "(chưa có hashtag)", score or "chờ chấm"])


# ---------- noi dung gui cho Muse ----------

def lang_name(cfg, profile):
    """Ngon ngu Muse lam viec: ngon ngu rieng cua Muse (setup), khong co thi ngon ngu giao viec cua doi."""
    own = (cfg["setup"].get(profile) or {}).get("lang", "")
    return LANG_NAMES.get(own or cfg["task_lang"], "")


def setup_sig(cfg, profile):
    """Chu ky thiet lap (ngon ngu + ngu canh) cua 1 Muse; "" = khong co thiet lap."""
    item = cfg["setup"].get(profile)
    return json.dumps(["v1", item["lang"], item["context"]], ensure_ascii=False) if item else ""


def setup_text(cfg, profile, is_chief):
    """Tin cap nhat bo nho dai han cho 1 Muse (ngu canh + ngon ngu tra loi)."""
    item = cfg["setup"].get(profile) or {}
    lang, context = LANG_NAMES.get(item.get("lang", ""), ""), item.get("context", "")
    rule = f"từ giờ luôn trả lời, viết kịch bản, lời thoại và caption bằng {lang}." if lang else ""
    if not context:
        return f"Cập nhật bộ nhớ dài hạn: {rule}\n\nTrả lời ngắn: xác nhận đã lưu."
    if is_chief:
        scope = ("Các Muse trong đội KHÔNG biết thiết lập này: khi giao việc, ghi đủ các luật / thông tin trong thiết "
                 "lập mà việc đó cần (nhân vật, định dạng, thời lượng, ngôn ngữ...), và dùng thiết lập này để chấm.")
    else:
        scope = ("Đây là nền cố định cho mọi việc bot chuyển cho bạn ([Việc T...]). Nếu yêu cầu của một việc khác "
                 "thiết lập này thì làm theo việc đó và nói rõ chỗ khác trong báo cáo.")
    return ("Cập nhật bộ nhớ dài hạn như sau nhé (thiết lập cố định của chủ, áp dụng từ giờ):\n\n"
            f"{context}\n\n" + (f"Ngôn ngữ: {rule}\n\n" if rule else "") + f"{scope}\n\n"
            "Lưu toàn bộ thiết lập trên vào bộ nhớ dài hạn. Trả lời ngắn: xác nhận đã lưu và tóm tắt các ý chính "
            "trong tối đa 6 gạch đầu dòng. Chưa làm sản phẩm nào cho đến khi được giao việc.")


def briefing(cfg, workers):
    lines = [f"- {w}: {cfg['roles'].get(w) or 'chưa có vai trò cố định'}"
             + (f" (giao việc bằng {lang_name(cfg, w)})" if lang_name(cfg, w) else "")
             for w in workers] or ["- (chưa có Muse nào)"]
    team_lang = LANG_NAMES.get(cfg["task_lang"], "")
    if team_lang:
        lines.append(f"\nNgôn ngữ giao việc của đội: {team_lang}. Viết mọi lệnh giao / nhắn / làm lại và nhận xét chấm "
                     f"bằng {team_lang}; Muse nào ghi ngôn ngữ riêng ở trên thì dùng ngôn ngữ của Muse đó.")
    p, r = cfg["pass_score"], cfg["max_rounds"]
    video = ("• Việc làm video: thêm số video ở cuối lệnh giao, vd [[giao: tên Muse | mô tả việc | 5 video]]. Bot cho "
             "Muse làm và nộp TỪNG video một: mỗi báo cáo bạn nhận đúng 1 video để chấm; video đạt thì bot tự bảo Muse "
             "làm video tiếp, chưa đạt thì Muse làm lại chính video đó.\n" if cfg["one_video"] else "")
    return (
        "Từ giờ bạn là CHỈ HUY của một đội Muse. Chủ nhắn cho bạn qua nhóm Telegram; bot Muse2Tele chuyển tin giữa bạn "
        "và các Muse khác (các Muse không nhìn thấy nhau, chỉ nhận đúng phần việc bot chuyển).\n\n"
        "Đội của bạn:\n" + "\n".join(lines) + "\n\n"
        "Nhiệm vụ: nhận yêu cầu của chủ, chia thành việc rõ ràng, giao cho Muse phù hợp, theo dõi và chấm chất lượng "
        "kết quả. Không tự làm phần việc đã giao cho người khác.\n\n"
        "Cách ra lệnh: viết mỗi lệnh trên 1 dòng riêng, đúng dạng hai dấu ngoặc vuông dưới đây. Bot thực hiện lệnh và ẩn "
        "dòng đó khỏi Telegram. Không viết lại các mẫu này khi không định ra lệnh.\n"
        "• Giao việc mới: [[giao: tên Muse | mô tả việc]] — mô tả phải tự đủ thông tin (mục tiêu, yêu cầu, định dạng "
        "kết quả), vì Muse làm không thấy cuộc trò chuyện của bạn. Bot đánh số việc T1, T2...\n"
        + video +
        "• Nhắn thêm / trả lời Muse đang làm: [[nhan: mã việc | nội dung]]\n"
        f"• Yêu cầu làm lại: [[lamlai: mã việc | cần sửa gì]] (mỗi việc / mỗi video tối đa {r} lần)\n"
        "• Chấm: [[danhgia: mã việc | điểm/10 | nhận xét]]\n\n"
        f"Luật chấm: từ {p}/10 là ĐẠT. Dưới {p}/10 bot tự gửi điểm và nhận xét của bạn cho Muse làm lại (không cần "
        f"viết thêm [[lamlai]]); sau {r} lần chưa đạt bot dừng việc và báo chủ. Nhận xét phải nói rõ cần sửa gì.\n\n"
        "Chống sai lệch thông tin:\n"
        "• Muốn Muse dùng lại kết quả đã đạt (bộ nhân vật, ảnh mẫu, kịch bản...), ghi mã việc đó trong lệnh, vd \"dùng "
        "đúng bộ nhân vật T5\". Bot tự đính kèm ảnh/video và mô tả ĐÃ DUYỆT của T5 cho Muse. Đừng tả lại chi tiết theo "
        "trí nhớ (dễ sai màu tóc, trang phục...).\n"
        "• Điểm, trạng thái, số lần làm lại: dùng đúng số trong bảng việc bot gửi kèm mỗi báo cáo (bản chuẩn), không "
        "dùng trí nhớ.\n"
        "• Mỗi báo cáo chỉ chấm đúng việc / video trong báo cáo đó.\n\n"
        f"Trang tổng hợp video (bắt buộc): luôn giữ MỘT trang artifact tên \"{ARTIFACT_NAME}\", dạng bảng, mỗi video "
        "1 dòng với các cột: Mã việc | Muse tạo | Video (thứ tự) | Link tải video | Caption | Hashtag | Điểm | "
        "Trạng thái | Chỉ đạo tiếp. Mỗi báo cáo video bot gửi kèm \"dòng chuẩn\" (bot trích từ báo cáo của Muse): "
        "chép đúng dòng đó vào trang (video làm lại thì sửa dòng cũ, không thêm dòng trùng), rồi điền điểm, trạng "
        "thái, chỉ đạo khi chấm. Luôn cập nhật trang này TRƯỚC khi chấm và dựa vào nó để quyết định làm lại hay làm "
        "tiếp. Mỗi lần cập nhật, gửi link trang cho chủ.\n\n"
        "Trả lời ngắn: xác nhận đã hiểu, tạo trang tổng hợp video (đang trống) và liệt kê đội của bạn.")


def _footer(task, cfg):
    tid, parts = task["id"], task.get("parts", 1)
    if parts > 1:
        rule = (f"\n\nViệc này gồm {parts} video. Lúc này CHỈ làm video {task.get('part', 1)}/{parts}: làm xong thì "
                f"gửi đúng 1 video đó rồi DỪNG chờ chấm, không làm trước video sau. Video đạt thì bot báo bạn làm "
                f"video tiếp.")
    elif cfg["one_video"]:
        rule = "\n\nMỗi lần nộp chỉ gửi 1 video (bot chỉ chuyển video đầu tiên cho chỉ huy chấm)."
    else:
        rule = ""
    if is_video_task(task):
        rule += ("\n\nKhi nộp video, ghi đủ 3 dòng sau (bot chép vào trang tổng hợp của chỉ huy):\n"
                 "Link tải: <link tải công khai của video, dạng https://muse.ai/files/...>\n"
                 "Caption: <caption đăng kèm video>\n"
                 + "".join(f"Caption ({code}): <caption đó viết bằng {LANG_NAMES[code]}, cho kênh đăng bằng "
                           f"ngôn ngữ này>\n" for code in caption_langs(cfg, task.get("to", "")))
                 + "Hashtag: <các hashtag, cách nhau bởi dấu cách>")
    lang = lang_name(cfg, task.get("to", ""))
    if lang:
        rule += f"\n\nTrả lời và làm sản phẩm bằng {lang}."
    return (rule + f"\n\nKhi làm xong, viết dòng [[xong: {tid}]] ở cuối câu trả lời. Không làm được hoặc cần hỏi "
                   f"lại thì viết [[vuong: {tid} | lý do hoặc câu hỏi]].")


def worker_text(task, kind, text, cfg, prefix="", refs=""):
    tid, pl = task["id"], part_label(task)
    pl = f" — {pl}" if pl else ""
    head = {"giao": f"[Việc {tid} — Chỉ huy giao{pl}]",
            "tiep": f"[Việc {tid}{pl}]",
            "lamlai": f"[Việc {tid}{pl} — làm lại lần {task.get('round', 0)}/{cfg['max_rounds']}] Chưa đạt, cần sửa:",
            "nhan": f"[Việc {tid} — Chỉ huy nhắn]",
            "nhac": f"[Việc {tid} — Bot nhắc]"}[kind]
    return (prefix + f"{head}\n{text}" + (f"\n\n{refs}" if refs else "") + _footer(task, cfg)).strip()


def next_part_text(task, score, note):
    """Tin bot gui Muse khi video truoc dat: lam video tiep (nhac lai yeu cau goc cho Muse khong lech)."""
    done = task.get("part", 1) - 1
    return (f"Video {done} đạt {score}" + (f" — {note}" if note else "") + ".\n"
            f"Giờ làm video {task['part']}/{task['parts']}: tình huống / nội dung KHÁC các video đã làm, giữ nguyên "
            f"chuẩn đã đạt. Yêu cầu gốc của việc:\n{task['text']}")


def nudge_text(task, has_output):
    if has_output:
        return ("Bot chưa thấy dòng xong của bạn. Nếu đã xong, gửi kết quả cuối (đúng 1 video nếu là video) và ghi "
                f"[[xong: {task['id']}]]. Nếu đang làm dở thì làm tiếp cho xong rồi mới gửi.")
    return ("Bot chưa nhận được kết quả nào của bạn cho việc này. Nếu đang làm thì làm tiếp; xong thì gửi kết quả và "
            f"ghi [[xong: {task['id']}]]. Không làm được thì ghi [[vuong: {task['id']} | lý do]].")


def ref_block(refs):
    """refs: [(task, so file dinh kem)] -> doan mo ta tham chieu gui kem cho Muse lam."""
    if not refs:
        return ""
    lines = ["Tài liệu tham chiếu bot đính kèm (bản ĐÃ DUYỆT, dùng đúng như vậy, không tự đổi chi tiết):"]
    for t, n in refs:
        body = short("\n".join(t.get("passed_report") or t.get("report") or []), REF_REPORT_CHARS)
        lines.append(f"- {t['id']} ({t['to']}, đạt {t.get('score') or '—'}"
                     + (f", {n} file đính kèm" if n else "") + f"): {body or short(t['text'], 300)}")
    return "\n".join(lines)


def board(tasks, limit=15):
    """Bang viec: viec dang mo truoc, roi viec moi dong gan day."""
    items = sorted(tasks.values(), key=lambda t: (t["status"] not in OPEN_STATUSES, -t.get("updated", 0)))[:limit]
    if not items:
        return "(chưa có việc nào)"
    out = []
    for t in items:
        extra = f" · {part_label(t)}" if t.get("parts", 1) > 1 else ""
        scores = t.get("scores") or ([t["score"]] if t.get("score") else [])
        extra += f" · điểm {', '.join(scores)}" if scores else ""
        extra += f" · chưa đạt {t['round']} lần" if t.get("round") else ""
        extra += " · quá hạn" if t.get("overdue") and t["status"] == "lam" else ""
        out.append(f"{t['id']} {t['to']}: {STATUS_LABEL.get(t['status'], t['status'])}{extra} — {short(t['text'], 70)}")
    return "\n".join(out)


def report_text(task, tasks, why, cfg, note=""):
    body = "\n\n".join(task.get("report") or []).strip() or "(Muse không viết chữ nào)"
    if len(body) > REPORT_MAX_CHARS:
        body = body[:REPORT_MAX_CHARS].rstrip() + "\n…(đã cắt bớt, xem đủ trong topic " + task["to"] + ")"
    files = len(task.get("files") or [])
    p, left = cfg["pass_score"], cfg["max_rounds"] - task.get("round", 0)
    pl = part_label(task)
    last = task.get("parts", 1) <= task.get("part", 1)
    after = "bot đóng việc" if last else f"bot cho Muse làm video {task.get('part', 1) + 1}/{task['parts']}"
    summary = ""
    if is_video_task(task):
        info = video_info(task)
        missing = [name for name, key in (("link tải", "link"), ("caption", "caption"), ("hashtag", "hashtag"))
                   if not info[key]]
        summary = (f"\nDòng chuẩn cho trang \"{ARTIFACT_NAME}\" (cập nhật trang trước khi chấm):\n"
                   f"{summary_row(task, info)}\n"
                   + (f"Muse chưa ghi {', '.join(missing)}: ghi \"chưa có\" trong trang và yêu cầu Muse gửi bổ sung "
                      f"(nhận xét khi chấm hoặc [[nhan: {task['id']} | ...]]).\n" if missing else ""))
    return (f"[Báo cáo {task['id']} từ {task['to']}" + (f" — {pl}" if pl else "")
            + (f" — làm lại lần {task['round']}" if task.get("round") else "") + f"] {why}\n"
            f"Việc: {short(task['text'], 400)}\n\nKết quả:\n{body}\n"
            + (f"\n({files} ảnh/video/file kết quả đính kèm.)\n" if files else "\n(Không có ảnh/video đính kèm.)\n")
            + summary
            + (f"{note}\n" if note else "")
            + f"\nBảng việc hiện tại (bản chuẩn):\n{board(tasks)}\n\n"
            f"Chấm bằng [[danhgia: {task['id']} | điểm/10 | nhận xét]]. Từ {p}/10 là đạt ({after}); dưới {p}/10 bot "
            f"gửi nhận xét để Muse làm lại "
            + (f"(còn {left} lần)." if left > 0 else "— nhưng đã hết lượt làm lại: dưới mức này bot dừng việc, báo chủ.")
            + f" Muốn đổi yêu cầu thì dùng [[lamlai: {task['id']} | cần sửa gì]].")


def new_task(tasks, seq, to, text, parts=1):
    tid = f"T{seq}"
    now = time.time()
    tasks[tid] = {"id": tid, "to": to, "text": text, "status": "duyet", "created": now, "updated": now, "round": 0,
                  "queue": [], "report": [], "files": [], "done": "", "last_out": 0, "sent_at": 0, "score": "",
                  "note": "", "overdue": False, "fails": 0, "parts": parts, "part": 1, "scores": [],
                  "passed_files": [], "passed_report": [], "history": [], "nudged": False, "told": False}
    if len(tasks) > TASKS_KEEP:
        for old in sorted(tasks.values(), key=lambda t: t["updated"]):
            if len(tasks) <= TASKS_KEEP:
                break
            if old["status"] not in OPEN_STATUSES:
                tasks.pop(old["id"])
    return tasks[tid]
