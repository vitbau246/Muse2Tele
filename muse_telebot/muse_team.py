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
reset_targets: Muse can xoa (vd chi cac Muse vua doi ngu canh); trong = chi huy + ca doi.
detached: {"<profile>": {"id": "<ma>", "wipe": bool}} -- Muse da TACH khoi doi (dashboard nut Tach / lenh /tach): bot
bo moi viec dang mo cua Muse do (ca viec dang lam, khac bo tick chi bo viec chua bat dau), 1 lan / ma; wipe thi xoa du
lieu Muse (qua reset_targets), khong thi nhan Muse "da roi doi" (leave_text). Tick lai vao doi thi dashboard bo muc nay.
reset_full: bo ca du lieu doi (viec, video mau, kich ban; bo nhan vat khoa chuyen vao thu muc luu tru) -- chu bam
"Reset doi" (moi thiet lap da ve mac dinh) hoac doi sang mau ngu canh khac (bo nhan vat cu khong con dung).

Giao thuc: dong [[lenh: ...]] trong tin cua Muse. Bot thuc hien, an dong do khoi Telegram.
    Chi huy:  [[giao: <profile> | <viec>]]               giao viec moi (bot danh so T1, T2...)
              [[giao: Muse2, Muse3 | <viec>]]            giao cung 1 viec cho nhieu Muse (moi Muse 1 ma viec);
                                                         "ca doi" = moi Muse trong doi
              [[giao: <profile> | <viec> | 5 video]]     viec nhieu video: Muse lam va nop tung video, dat moi lam tiep
              [[giao: <profile> | <viec> | 4 doan]]      video dai chia doan: Muse nop tung doan, bot kem khung cuoi
                                                         doan truoc cho doan sau, du doan dat thi bot noi thanh 1 video
              [[kichban: M1 | <phan kich da doi vai>]]   chot kich ban cho video mau M1 (ban v1, v2...): giao "theo video
                                                         mau M1" thi bot tu kem ban moi nhat, chi huy khong chep lai
              [[nhan: T3 | <noi dung>]]                  nhan them cho Muse dang lam viec T3 (tra loi cau hoi, bo sung)
              [[lamlai: T3 | <can sua gi>]]              chua dat, lam lai (toi da max_rounds lan)
              [[danhgia: T3 | 8/10 | <nhan xet>]]        cham diem: tu pass_score la dat, duoi thi bot tu cho lam lai
    Muse lam: [[xong: T3]]                               lam xong
              [[vuong: T3 | <ly do / cau hoi>]]          khong lam duoc / can hoi lai
Nhac ma viec da dat (VD "dung bo nhan vat T5") trong lenh giao / nhan / lamlai: bot dinh kem anh / video va mo ta da
duyet cua viec do cho Muse lam (tranh chi huy ta lai theo tri nho, sai lech).
Video mau (video_sample.py): chu gui link / file video cho chi huy -> bot tai ve, dat ma M1, M2... Chi huy phan tich
thanh phan canh, chot [[kichban: M1 | ...]], giao "theo video mau M1": bot dinh kem kich ban chot + video + anh ghep
cho Muse lam, kem bo nhan vat da duyet neu lenh chua nhac bo nao. Bo nhan vat dat duoc bot luu co dinh vao
<UPLOAD_DIR>/nhan_vat/<Muse>/<ma viec>/ (khong bi don, moi Muse nhieu bo; bo tao cho video mau nao thi gan voi mau do),
xem locked_sets / pick_lock.
Kiem tra ky thuat (video_sample.check): video nop bi trung file cu, khong co tieng, sai khung, sai thoi luong -> bot tra
lai Muse lam lai ngay (toi da QC_RETURNS lan / video, khong tinh vao luot cham), khong ton luot cua chi huy.
Buoc tao hinh (stage "hinh"): viec lam video theo video mau da chot kich ban -> bot chia 2 buoc. Buoc 1 Muse chi nop anh
tao hinh (moi nhan vat x moi giai doan trang phuc / toc, sua tu anh bo nhan vat khoa, + boi canh), chi huy cham so voi
bo khoa; dat thi bot giu anh (look_files) va cho lam buoc 2 = video, moi lan gui kem lai cac anh do. Bao cao video bot
kem anh ghep khung hinh ket qua (moi o 1 giay) + anh tao hinh de chi huy so tung giay (lech mat / toc / ao).
(2026-11-08: M1 lam theo bo nhan vat chan dung toc xoa -> Muse tu che toc bui + vay be / ao thun tung canh, mat Me doi
o canh gian du / canh xa; chi huy van cham 9/10 vi chi xem video.)
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
REF_MAX_FILES = 8         # file tham chieu (bo nhan vat, video mau + anh ghep) dinh kem cho Muse lam
REF_REPORT_CHARS = 700
TASKS_KEEP = 100

CHIEF_VERBS = ("giao", "nhan", "lamlai", "danhgia", "kichban")
WORKER_VERBS = ("xong", "vuong")
COMMAND_RE = re.compile(r"\[\[\s*([^\[\]:|\n]{2,20}?)\s*:\s*(.*?)\s*\]\]", re.DOTALL)
TASK_ID_RE = re.compile(r"^\s*T?\s*(\d{1,6})\s*$", re.IGNORECASE)
TASK_REF_RE = re.compile(r"(?<![\w/])T(\d{1,6})\b")
PARTS_RE = re.compile(r"^\s*(\d{1,2})\s*(video|clip|tập|tap|đoạn|doan|phần|phan|segment|part)s?\s*$", re.IGNORECASE)
SEGMENT_WORDS = ("đoạn", "doan", "phần", "phan", "segment", "part")
SAMPLE_ID_RE = re.compile(r"^\s*M(\d{1,4})\s*$", re.IGNORECASE)
ALL_WORKERS = ("cadoi", "tatca", "all", "team", "moinguoi")
QC_RETURNS = 2            # moi video: bot tu tra lai toi da 2 lan vi loi ky thuat roi moi dua chi huy
LOOK_MAX_FILES = 5        # buoc tao hinh: toi da 5 anh (vua cho tham chieu buoc video: 5 anh + video mau + 2 anh ghep)
LOOK_SKIP_WORDS = ("botaohinh", "khongtaohinh", "boquataohinh", "skiplook")  # chi huy ghi de bo buoc tao hinh
LOOK_LOCK_MAX = 3         # bao cao buoc tao hinh: kem toi da 3 anh bo nhan vat khoa de chi huy so mat
SCRIPT_MAX_CHARS = 12000
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
           "detached": {str(k).strip(): {"id": str(v.get("id") or ""), "wipe": bool(v.get("wipe"))}
                        for k, v in (raw.get("detached") if isinstance(raw.get("detached"), dict) else {}).items()
                        if isinstance(v, dict) and v.get("id") and str(k).strip()},
           "reset_id": str(raw.get("reset_id") or ""),
           "reset_full": bool(raw.get("reset_full")),
           "reset_targets": [str(x).strip() for x in (raw.get("reset_targets") if isinstance(raw.get("reset_targets"),
                                                                                             list) else [])
                             if str(x).strip()]}
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
        limit = 2 if verb == "danhgia" else 0 if verb == "xong" else 1  # kichban: [M1, kich ban]
        args = [a.strip() for a in m.group(2).split("|", limit)] if limit else [m.group(2).strip()]
        found.append((verb, args))
    return found


def task_parts(text):
    """'<viec> | 5 video' -> ('<viec>', 5, False); '<viec> | 4 doan' -> ('<viec>', 4, True) (doan cua 1 video dai,
    bot noi lai). Khong ghi so -> (text, 1, False)."""
    head, sep, tail = (text or "").rpartition("|")
    m = PARTS_RE.match(tail) if sep else None
    if not m:
        return (text or "").strip(), 1, False
    n = max(1, min(MAX_PARTS, int(m.group(1))))
    return head.strip(), n, n > 1 and m.group(2).lower() in SEGMENT_WORDS


def targets(raw, workers):
    """'Muse2, Muse3' / 'Muse2 + Muse3' / 'Muse2 va Muse3' / 'ca doi' -> ([Muse trong doi], [ten khong co])."""
    if _verb(raw) in ALL_WORKERS:
        return list(workers), []
    found, bad = [], []
    for name in re.split(r"\s*(?:,|;|\+|&|\bvà\b|\band\b)\s*", raw or ""):
        if not name.strip():
            continue
        w = next((w for w in workers if w.casefold() == name.strip().casefold()), None)
        if w and w not in found:
            found.append(w)
        elif not w:
            bad.append(name.strip())
    return found, bad


def sample_id(raw):
    m = SAMPLE_ID_RE.match(raw or "")
    return f"M{int(m.group(1))}" if m else None


# Tin Muse tu gui (meo dung san pham, gioi thieu tinh nang) lan vao bao cao viec (2026-11-08: T28, T29 nhan
# "🗓️ Mẹo 1: Lên lịch một việc..." kem anh crons.png thay vi ket qua).
NOISE_RE = re.compile(r"^\W{0,6}(?:mẹo|meo|tip|tips|mẹo nhỏ)\s*(?:số\s*)?\d{1,2}\s*[:：.\-–—]", re.IGNORECASE)


def is_noise(text):
    first = next((line for line in (text or "").splitlines() if line.strip()), "")
    return bool(NOISE_RE.match(first.strip()))


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


FAMILY = "bố, mẹ, con gái, con trai"
CHARACTER_TASK_WORDS = ("nhanvat", "character")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


LOCK_SOURCE_FILE = "nguon.txt"  # trong thu muc bo nhan vat khoa: ma viec da tao bo (vd T5)
LOCK_INFO_FILE = "info.json"    # {"source": "T30", "samples": ["M2"], "text": "<mo ta viec>"}


def is_character_set(task):
    """Viec da dat tao bo nhan vat: mo ta nhac 'nhan vat' va ket qua chi gom anh (>= 2 anh, khong video). Chi xet ten
    file (viec tao tu ban bot cu chi co "files", file co the da bi don)."""
    files = task.get("passed_files") or task.get("files") or []
    plain = _verb(task.get("text") or "")
    return (task.get("status") == "dat" and len(files) >= 2
            and all(Path(f).suffix.lower() in IMAGE_EXT for f in files)
            and any(w in plain for w in CHARACTER_TASK_WORDS))


def character_sets(tasks):
    """Viec tao bo nhan vat da dat: {Muse: ma viec moi nhat cua Muse do}."""
    found = sorted((t for t in tasks.values() if is_character_set(t)), key=lambda t: t.get("updated", 0))
    return {t["to"]: t["id"] for t in found}


def sample_refs(text):
    """Ma video mau nhac trong text (giong video_sample.sample_refs, tranh import vong)."""
    out = []
    for m in re.finditer(r"(?<![\w/])M(\d{1,4})\b", text or ""):
        if f"M{int(m.group(1))}" not in out:
            out.append(f"M{int(m.group(1))}")
    return out


def _images(d):
    return sorted(str(f) for f in d.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXT) if d.is_dir() else []


def migrate_locks(root):
    """Ban cu luu 1 bo / Muse ngay trong root/<Muse>/ (bo moi ghi de bo cu): chuyen vao root/<Muse>/<ma viec>/."""
    root = Path(root)
    if not root.is_dir():
        return
    for d in root.iterdir():
        imgs = _images(d)
        if not imgs:
            continue
        src = d / LOCK_SOURCE_FILE
        tid = (src.read_text(encoding="utf-8").strip() if src.is_file() else "") or "cu"
        dest = d / tid
        dest.mkdir(parents=True, exist_ok=True)
        for f in imgs:
            Path(f).replace(dest / Path(f).name)
        if src.is_file():
            src.replace(dest / LOCK_SOURCE_FILE)


def save_lock(root, task):
    """Luu bo nhan vat vua dat vao root/<Muse>/<ma viec>/ (giu cac bo khac cua Muse). Tra ve thu muc | None."""
    import shutil
    images = [f for f in task.get("passed_files") or [] if Path(f).is_file() and Path(f).suffix.lower() in IMAGE_EXT]
    if len(images) < 2:
        return None
    folder = Path(root) / task["to"] / task["id"]
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    for f in images:
        shutil.copy2(f, folder / Path(f).name)
    (folder / LOCK_SOURCE_FILE).write_text(task["id"], encoding="utf-8")
    (folder / LOCK_INFO_FILE).write_text(json.dumps({"source": task["id"], "samples": sample_refs(task.get("text")),
                                                     "text": short(task.get("text"), 300)}, ensure_ascii=False),
                                         encoding="utf-8")
    return folder


def locked_sets(root, tasks=None):
    """Bo nhan vat khoa: {Muse: [{"files", "source", "samples", "text", "at", "owner"}]} (bo moi nhat truoc).
    samples = video mau ma bo duoc tao rieng cho (vd bo dong vat cho M2); [] = bo chung (gia dinh).
    tasks: bo luu tu ban cu chua co info.json thi lay mo ta viec goc de biet bo gan voi video mau nao."""
    out = {}
    root = Path(root)
    if not root.is_dir():
        return out
    migrate_locks(root)
    for sub in (x for d in root.iterdir() if d.is_dir() for x in d.iterdir() if x.is_dir()):
        src = sub / LOCK_SOURCE_FILE
        tid = src.read_text(encoding="utf-8").strip() if src.is_file() else ""
        if tasks and tid in tasks and not (sub / LOCK_INFO_FILE).is_file():
            t = tasks[tid]
            (sub / LOCK_INFO_FILE).write_text(json.dumps({"source": tid, "samples": sample_refs(t.get("text")),
                                                          "text": short(t.get("text"), 300)}, ensure_ascii=False),
                                              encoding="utf-8")
    for d in root.iterdir():
        if not d.is_dir():
            continue
        sets = []
        for sub in d.iterdir():
            files = _images(sub)
            if not files:
                continue
            info = {}
            try:
                info = json.loads((sub / LOCK_INFO_FILE).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            src = sub / LOCK_SOURCE_FILE
            sets.append({"files": files, "owner": d.name,
                         "source": info.get("source") or (src.read_text(encoding="utf-8").strip() if src.is_file()
                                                          else sub.name),
                         "samples": list(info.get("samples") or []), "text": info.get("text") or "",
                         "at": max(Path(f).stat().st_mtime for f in files)})
        if sets:
            out[d.name] = sorted(sets, key=lambda x: x["at"], reverse=True)
    return out


def pick_lock(locks, worker, samples=()):
    """Bo nhan vat cho worker lam viec theo video mau samples: bo cua worker tao rieng cho mau do > bo cua doi tao
    rieng cho mau do (vd bo dong vat M2 dung chung ca doi) > bo chung (gia dinh) cua worker > bo chung moi nhat cua
    doi. None neu doi chua co bo nao."""
    samples = set(samples)
    mine = locks.get(worker) or []
    team = sorted((x for sets in locks.values() for x in sets), key=lambda x: x["at"], reverse=True)
    for pool, bound in ((mine, True), (team, True), (mine, False), (team, False)):
        hit = next((x for x in pool if (samples & set(x["samples"]) if bound else not x["samples"])), None)
        if hit:
            return hit
    return None


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


def wants_look(text, scripts):
    """Viec lam video theo video mau da chot kich ban (vd "Lam video theo video mau M1") -> True: bot chia buoc tao
    hinh truoc. Viec tao bo nhan vat cho mau ("tao bo nhan vat cho video mau M2") hoac chi huy ghi "bo tao hinh": False."""
    plain = _verb(text or "")
    if not any(sid in (scripts or {}) for sid in sample_refs(text)) or any(w in plain for w in LOOK_SKIP_WORDS):
        return False
    return "theovideomau" in plain or "theomau" in plain or "lamlaivideo" in plain


def lock_refs(files, script_text, limit=LOOK_LOCK_MAX):
    """Anh bo nhan vat khoa cua cac nhan vat co trong kich ban (ten file 'Me_23_tuoi.webp' -> 'Me' co trong kich ban),
    khong khop ten nao thi lay cac anh dau."""
    def words(s):  # 'Mẹ_23 tuổi' -> 'me 23 tuoi'
        s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
        s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
        return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())
    script = f" {words(script_text)} "
    hit = []
    for f in files:
        name = re.split(r"\s\d", words(Path(f).stem) + " 0")[0].strip()  # bo phan tuoi: 'con gai 4 tuoi' -> 'con gai'
        if name and f" {name} " in script:
            hit.append(f)
    return (hit or list(files))[:limit]


def part_label(task):
    if task.get("stage") == "hinh":
        return "bước 1 tạo hình"
    parts = task.get("parts", 1)
    if parts <= 1:
        return ""
    return f"{'đoạn' if task.get('segment') else 'video'} {task.get('part', 1)}/{parts}"


def is_video_task(task):
    """Viec lam video: nhieu video / doan, mo ta nhac video / clip / phim, hoac Muse da nop video."""
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
    """1 dong chuan cho trang artifact tong hop video. Link tai khong bat buoc: bot da giu file video."""
    return " | ".join([task["id"], task["to"], part_label(task) or "video 1/1",
                       info["link"] or "(bot giữ file)", info["caption"] or "(chưa có caption)",
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
                 "thiết lập này thì làm theo việc đó và nói rõ chỗ khác trong báo cáo. Riêng việc làm lại video theo "
                 "video mẫu + kịch bản chốt: được phép và BẮT BUỘC bám đúng kịch bản đó (không áp dụng luật tự sáng "
                 "tác / không sao chép). Quy trình trong thiết lập chỉ áp dụng KHI được giao việc: bạn chỉ làm khi bot "
                 "chuyển việc, xong việc thì dừng, không tự làm bước tiếp theo, không tự đề xuất hay sản xuất gì thêm.")
    return ("Cập nhật bộ nhớ dài hạn như sau nhé (thiết lập cố định của chủ, áp dụng từ giờ):\n\n"
            f"{context}\n\n" + (f"Ngôn ngữ: {rule}\n\n" if rule else "") + f"{scope}\n\n"
            "Lưu toàn bộ thiết lập trên vào bộ nhớ dài hạn. Trả lời ngắn: xác nhận đã lưu và tóm tắt các ý chính "
            "trong tối đa 6 gạch đầu dòng. Chưa làm sản phẩm nào cho đến khi được giao việc.")


def leave_text():
    """Tin cho Muse vua tach khoi doi ma khong xoa du lieu: bo boi canh doi trong bo nho dai han."""
    return ("Cập nhật bộ nhớ dài hạn: bạn KHÔNG còn trong đội Muse nữa. Từ giờ không có chỉ huy, bot không chuyển việc "
            "[Việc T...] cho bạn, và bạn không dùng các dòng lệnh [[xong: ...]] / [[vuong: ...]] nữa. Việc đội đang làm "
            "dở đã bị huỷ: dừng lại, không làm tiếp. Bỏ vai trò, ngữ cảnh và quy trình của đội khỏi bộ nhớ dài hạn; "
            "từ giờ làm việc trực tiếp với chủ qua chat này.\n\nTrả lời ngắn: xác nhận đã lưu.")


def lock_label(lock):
    kind = (f"riêng cho video mẫu {', '.join(lock['samples'])}" if lock["samples"]
            else "bộ chung (dàn nhân vật chính)")
    return f"{lock['source']} của {lock['owner']} — {kind}, {len(lock['files'])} ảnh"


def lock_lines(workers, locks):
    """Dong 'bo nhan vat khoa' tung Muse cho chi huy (locks: locked_sets())."""
    lines = []
    for w in workers:
        own = locks.get(w) or []
        if own:
            lines.append(f"  - {w}: " + "; ".join(lock_label(x) for x in own))
        else:
            fallback = pick_lock(locks, w)
            lines.append(f"  - {w}: chưa có bộ riêng" + (f" — bot kèm bộ {lock_label(fallback)}" if fallback else ""))
    return lines


def sample_lines(samples, scripts):
    """Video mau dang co + kich ban chot (cho chi huy)."""
    out = []
    for sid, s in sorted((samples or {}).items(), key=lambda x: int(x[0][1:]))[-8:]:
        dur = (s.get("meta") or {}).get("duration") or 0
        sc = (scripts or {}).get(sid)
        out.append(f"  - {sid}" + (f" ({dur:.0f} giây)" if dur else "")
                   + (f": kịch bản chốt bản v{sc['v']}" if sc else ": CHƯA chốt kịch bản"))
    return out


def sample_rules(workers, locks, samples=None, scripts=None):
    """Luat 'Lam video theo video mau' cho chi huy: danh gia kha thi, phan kich, chot kich ban, giao ca doi."""
    lock = ("Bộ nhân vật KHOÁ bot đang giữ (ảnh đã duyệt, bot tự đính kèm khi giao theo video mẫu):\n"
            + "\n".join(lock_lines(workers, locks))) if locks else (
        "Đội CHƯA có bộ nhân vật nào được khoá: trước khi làm video theo mẫu, giao 1 Muse tạo bộ ảnh nhân vật (mỗi "
        "ảnh 1 nhân vật, chính diện, rõ mặt, trang phục cố định) và chấm đạt bộ đó; bot khoá bộ đạt cho các việc sau.")
    have = sample_lines(samples, scripts)
    return (
        "LÀM VIDEO THEO VIDEO MẪU (chủ gửi link / file, vd reel Facebook / TikTok):\n"
        "• Bot tự tải video, đặt mã M1, M2... và gửi bạn video gốc + ảnh ghép khung hình (góc trái mỗi ô ghi giây) "
        "+ thời lượng. Link không tải được thì bot báo, nhờ chủ gửi file.\n"
        "• Bước 1 — Đánh giá khả thi (báo chủ trước khi giao):\n"
        "  Mức A, đảm bảo: tới 40 giây, tối đa 3 nhân vật chính đã có bộ khoá, tối đa 3 bối cảnh, hành động đời thường, "
        "thoại ngắn → giao 1 video.\n"
        "  Mức B, làm được nếu chia đoạn: 40–150 giây, hoặc nhiều cảnh / hành động nhanh / hoạt hình 3D / 4 nhân vật → "
        "giao kèm \"| N đoạn\", mỗi đoạn 15–30 giây, cắt ở chỗ chuyển cảnh.\n"
        "  Mức C, không đảm bảo: trên 150 giây, đám đông, chữ dài trên màn hình phải đúng chính tả, hát nhép, người "
        "thật / người nổi tiếng, nội dung nhạy cảm (gợi dục, đồ lót, bạo lực, trẻ em gặp nguy) → Muse dễ từ chối hoặc "
        "lỗi: đề xuất chủ rút gọn hoặc đổi tiền đề an toàn hơn rồi mới giao.\n"
        "• Bước 2 — Phân kịch (viết cho chủ duyệt): bối cảnh cố định (địa điểm, đồ vật, ánh sáng); từng nhịp theo giây: "
        "cỡ cảnh / góc máy, ai làm gì, biểu cảm, thoại nguyên văn, âm thanh, chữ trên màn hình; TRANG PHỤC + KIỂU TÓC "
        "từng nhân vật theo từng giai đoạn (\"giữ nguyên từ giây X đến Y\"); khung hình, tổng thời lượng; mức B thì ghi "
        "rõ đoạn 1: 0–25s, đoạn 2: 25–50s...\n"
        "• Bước 3 — Đổi vai: mặc định thay mọi nhân vật bằng DÀN NHÂN VẬT CỐ ĐỊNH trong thiết lập chủ cài cho bạn "
        f"(mục NHÂN VẬT; chưa có thiết lập thì dùng gia đình {FAMILY}); mẫu ít người thì chỉ dùng "
        "người cần, nhiều người thì gộp hoặc bỏ vai, không thêm người lạ. Chủ muốn giữ dạng nhân vật của mẫu (vd động "
        "vật): giao 1 Muse tạo bộ nhân vật và ghi \"cho video mẫu M2\" trong lời giao — bộ đạt được bot khoá gắn với "
        "M2 và tự kèm cho MỌI Muse làm M2.\n"
        "• Bước 4 — Chủ duyệt phân kịch → [[kichban: M1 | toàn bộ phân kịch đã đổi vai]] → [[giao: cả đội | Làm video "
        "theo video mẫu M1]] (thêm \"| N đoạn\" nếu mức B). KHÔNG chép kịch bản vào lời giao: bot tự kèm kịch bản chốt "
        "mới nhất + video mẫu + ảnh ghép + bộ nhân vật của từng Muse. Chủ sửa kịch bản → chốt bản mới bằng [[kichban]] "
        "rồi mới giao lại / yêu cầu làm lại.\n"
        "• Bot tự chia mỗi việc theo video mẫu thành 2 BƯỚC (chấm từng bước, bạn không cần ghi gì thêm):\n"
        "  Bước 1 — TẠO HÌNH: Muse chỉ nộp ảnh — mỗi nhân vật × mỗi giai đoạn trang phục / tóc 1 ảnh (toàn thân + cận "
        "mặt), sửa từ ảnh bộ nhân vật khoá, + ảnh bối cảnh. Bot kèm ảnh bộ khoá trong báo cáo: chấm mặt giống bộ khoá, "
        "tóc + trang phục đúng kịch bản, đủ giai đoạn.\n"
        "  Bước 2 — VIDEO: bot gửi lại ảnh tạo hình đã đạt, Muse tạo mọi cảnh từ các ảnh đó.\n"
        "  Muốn bỏ bước tạo hình (vd việc gấp, mẫu không có người): ghi \"bỏ tạo hình\" trong lời giao.\n"
        "• Chấm video: báo cáo có ẢNH GHÉP KHUNG HÌNH KẾT QUẢ (bot cắt, mỗi ô 1 giây, góc trái ghi giây) + ảnh tạo hình "
        "đã duyệt. So TỪNG Ô với ảnh tạo hình: mặt, kiểu tóc, quần áo, vóc người; ô nào khác (dù 1 cảnh) → ghi giây đó, "
        "tối đa 7/10. Đừng tin phần Muse tự khai \"đã QA, đồng nhất\": chỉ tin ảnh ghép. Rồi so mẫu + kịch bản: đủ từng "
        "nhịp, giữ cú twist, phụ đề đúng thoại, không còn logo / watermark / tên kênh của video gốc. Thiếu nhịp hoặc lệch "
        "nhân vật thì chưa đạt.\n"
        + (("Video mẫu đang có:\n" + "\n".join(have) + "\n") if have else "")
        + lock)


def briefing(cfg, workers, locks=None, samples=None, scripts=None):
    locks = locks or {}
    lines = [f"- {w}: {cfg['roles'].get(w) or 'chưa có vai trò cố định'}"
             + (f" (giao việc bằng {lang_name(cfg, w)})" if lang_name(cfg, w) else "")
             for w in workers] or ["- (chưa có Muse nào)"]
    team_lang = LANG_NAMES.get(cfg["task_lang"], "")
    if team_lang:
        lines.append(f"\nNgôn ngữ giao việc của đội: {team_lang}. Viết mọi lệnh giao / nhắn / làm lại và nhận xét chấm "
                     f"bằng {team_lang}; Muse nào ghi ngôn ngữ riêng ở trên thì dùng ngôn ngữ của Muse đó.")
    p, r = cfg["pass_score"], cfg["max_rounds"]
    video = ("• Nhiều video khác nhau: thêm số video ở cuối, vd [[giao: tên Muse | mô tả việc | 5 video]]. Muse nộp "
             "TỪNG video; đạt thì bot tự bảo làm video tiếp, chưa đạt thì làm lại chính video đó.\n"
             if cfg["one_video"] else "")
    return (
        "Từ giờ bạn là CHỈ HUY của một đội Muse. Chủ nhắn cho bạn qua nhóm Telegram; bot Muse2Tele chuyển tin giữa bạn "
        "và các Muse khác (các Muse không nhìn thấy nhau, chỉ nhận đúng phần việc bot chuyển).\n\n"
        "Đội của bạn:\n" + "\n".join(lines) + "\n\n"
        "Nhiệm vụ: nhận yêu cầu của chủ, chia thành việc rõ ràng, giao cho Muse phù hợp, theo dõi và chấm chất lượng. "
        "Không tự làm phần việc đã giao cho người khác. CHỈ giao việc mới khi chủ yêu cầu; thấy cần làm thêm gì thì đề "
        "xuất, chủ đồng ý mới giao. Việc đạt thì dừng, chờ chủ.\n\n"
        "LỆNH: mỗi lệnh 1 dòng riêng, đúng dạng hai dấu ngoặc vuông. Bot thực hiện và ẩn dòng đó khỏi Telegram. Không "
        "viết các mẫu này khi không định ra lệnh.\n"
        "• Giao việc: [[giao: tên Muse | mô tả việc]] — mô tả tự đủ thông tin (Muse làm không thấy cuộc trò chuyện của "
        "bạn). Cùng 1 việc cho nhiều Muse: [[giao: Muse2, Muse3 | ...]] hoặc [[giao: cả đội | ...]] — mỗi Muse 1 mã "
        "việc T1, T2..., tự dùng bộ nhân vật của mình.\n"
        + video +
        "• Video dài chia đoạn: [[giao: tên Muse | mô tả | 4 đoạn]] — Muse làm và nộp từng đoạn theo kịch bản; bot gửi "
        "kèm khung hình cuối của đoạn trước để đoạn sau nối liền; đủ đoạn đạt thì bot tự nối thành 1 video gửi chủ.\n"
        "• Chốt kịch bản cho video mẫu: [[kichban: M1 | toàn bộ phân kịch]] — bot lưu bản v1, v2... và tự kèm bản mới "
        "nhất mỗi khi giao \"theo video mẫu M1\".\n"
        "• Nhắn thêm / trả lời Muse đang làm: [[nhan: mã việc | nội dung]]\n"
        f"• Yêu cầu làm lại: [[lamlai: mã việc | cần sửa gì]] (mỗi việc / mỗi video tối đa {r} lần)\n"
        "• Chấm: [[danhgia: mã việc | điểm/10 | nhận xét]]\n\n"
        f"Luật chấm: từ {p}/10 là ĐẠT. Dưới {p}/10 bot tự gửi nhận xét cho Muse làm lại (không cần thêm [[lamlai]]); "
        f"sau {r} lần chưa đạt bot dừng việc và báo chủ. Nhận xét phải nói rõ cần sửa gì, ở giây nào.\n\n"
        "Bot tự đo kỹ thuật mọi video nộp (máy đo, tin hơn mắt): trùng file đã nộp, không có tiếng, sai khung dọc / "
        "ngang, sai thời lượng so với mẫu → bot trả Muse làm lại ngay, bạn không phải chấm. Báo cáo nào cũng có dòng "
        "\"Bot đo: ...\": dùng đúng số đó; không chấm đạt video bot ghi KHÔNG có tiếng.\n\n"
        "Chống sai lệch: muốn Muse dùng lại kết quả đã đạt (bộ nhân vật, ảnh, kịch bản...) thì ghi mã việc, vd \"dùng "
        "đúng bộ nhân vật T5\" — bot đính kèm bản ĐÃ DUYỆT; đừng tả lại theo trí nhớ. Điểm, trạng thái, số lần làm lại: "
        "dùng bảng việc bot gửi kèm mỗi báo cáo. Mỗi báo cáo chỉ chấm đúng việc / video trong báo cáo đó.\n\n"
        + sample_rules(workers, locks, samples, scripts) + "\n\n"
        f"Trang tổng hợp video: giữ MỘT trang artifact tên \"{ARTIFACT_NAME}\", dạng bảng, mỗi video 1 dòng: Mã việc | "
        "Muse tạo | Video (thứ tự) | Link tải | Caption | Hashtag | Điểm | Trạng thái | Chỉ đạo tiếp. Mỗi báo cáo video "
        "bot gửi kèm \"dòng chuẩn\": chép đúng dòng đó vào trang (làm lại thì sửa dòng cũ), điền điểm khi chấm. Gửi link "
        "trang cho chủ khi cập nhật.\n\n"
        "Trả lời ngắn: xác nhận đã hiểu, liệt kê đội và các video mẫu đang có.")


LOOK_RULE = (
    "\n\nVIỆC NÀY LÀM 2 BƯỚC, CHẤM TỪNG BƯỚC. LÚC NÀY CHỈ LÀM BƯỚC 1 — TẠO HÌNH, CHƯA LÀM VIDEO:\n"
    "1. Đọc kịch bản chốt, liệt kê mỗi nhân vật × mỗi giai đoạn trang phục / kiểu tóc (vd Mẹ váy be tóc búi; Mẹ áo "
    "thun trắng tóc búi; Bố áo khoác đen).\n"
    "2. Mỗi mục làm 1 ẢNH TẠO HÌNH dọc 9:16, nền trơn sáng, ghép trong cùng 1 ảnh: toàn thân chính diện + cận mặt "
    "chính diện + cận mặt nghiêng 3/4. Tạo bằng cách CHỈNH SỬA ảnh bộ nhân vật bot đính kèm: giữ nguyên khuôn mặt "
    "(mắt, mũi, miệng, dáng mặt, tuổi, vóc người), chỉ đổi tóc + trang phục đúng kịch bản. KHÔNG vẽ người mới từ chữ. "
    "Mọi mục của cùng 1 nhân vật phải cùng 1 khuôn mặt.\n"
    "3. Còn chỗ thì thêm 1 ảnh ghép các bối cảnh trong kịch bản (mỗi vị trí 1 ô, đúng đồ vật, màu, ánh sáng).\n"
    f"4. Nộp tối đa {LOOK_MAX_FILES} ảnh, tên file theo nội dung (vd Me_vay_be.png), mỗi ảnh 1 dòng mô tả. KHÔNG nộp "
    "video ở bước này.\n"
    "Đạt bước 1 thì bot gửi lại đúng các ảnh này và cho làm bước 2 (video): mọi cảnh trong video phải tạo từ các ảnh "
    "này, nên làm kỹ.")


def look_done_text(task, score, note):
    """Tin bot gui Muse khi buoc tao hinh dat: lam buoc 2 = video, tao moi canh tu anh tao hinh."""
    seg = (f" Video chia {task['parts']} đoạn: lúc này làm ĐOẠN 1/{task['parts']}." if task.get("segment")
           and task.get("parts", 1) > 1 else "")
    return (f"Bước 1 (tạo hình) đạt {score}" + (f" — {note}" if note else "") + ".\n"
            f"Giờ làm BƯỚC 2 — VIDEO theo kịch bản chốt.{seg} Bot đính kèm lại các ảnh tạo hình đã duyệt. Cách làm "
            "để mặt, tóc, quần áo không đổi giữa các cảnh:\n"
            "- Mỗi cảnh: tạo ẢNH ĐẦU CẢNH bằng cách chỉnh sửa ảnh tạo hình đúng giai đoạn (giữ nguyên mặt, tóc, quần "
            "áo; chỉ đổi tư thế, biểu cảm, góc máy, bối cảnh), rồi tạo video cảnh đó TỪ ảnh đầu cảnh. Không tạo nhân "
            "vật từ chữ, không dùng ảnh nhân vật nào khác.\n"
            "- Cảnh có biểu cảm mạnh (giận, sốc, la hét), cảnh xa / nghiêng, cảnh 2 người hay làm đổi mặt: so kỹ với "
            "ảnh tạo hình, lệch thì tạo lại.\n"
            "- Trước khi nộp: xem mỗi giây 1 khung đặt cạnh ảnh tạo hình. Bot cũng cắt mỗi giây 1 khung gửi chỉ huy so "
            "từng giây, lệch 1 cảnh là chưa đạt.\n"
            f"Yêu cầu gốc của việc:\n{task['text']}")


def _footer(task, cfg, target=None):
    tid, parts = task["id"], task.get("parts", 1)
    if task.get("stage") == "hinh":
        rule = LOOK_RULE
        lang = lang_name(cfg, task.get("to", ""))
        if lang:
            rule += f"\n\nTrả lời và làm sản phẩm bằng {lang}."
        return (rule + f"\n\nKhi làm xong, viết dòng [[xong: {tid}]] ở cuối câu trả lời. Không làm được hoặc cần hỏi "
                       f"lại thì viết [[vuong: {tid} | lý do hoặc câu hỏi]].\n\n" + STOP_RULE)
    if parts > 1 and task.get("segment"):
        rule = (f"\n\nVideo này chia {parts} đoạn. Lúc này CHỈ làm ĐOẠN {task.get('part', 1)}/{parts} theo kịch bản "
                f"(đúng mốc giây của đoạn này): nộp đúng 1 file video của đoạn đó rồi DỪNG chờ chấm. Cùng nhân vật, "
                f"trang phục, tóc, bối cảnh, ánh sáng, khung hình với các đoạn trước; bot sẽ nối các đoạn đạt thành 1 "
                f"video, nên KHÔNG thêm intro / outro / logo / phụ đề tiêu đề ở đầu hay cuối đoạn.")
    elif parts > 1:
        rule = (f"\n\nViệc này gồm {parts} video. Lúc này CHỈ làm video {task.get('part', 1)}/{parts}: làm xong thì "
                f"gửi đúng 1 video đó rồi DỪNG chờ chấm, không làm trước video sau. Video đạt thì bot báo bạn làm "
                f"video tiếp.")
    elif cfg["one_video"]:
        rule = "\n\nMỗi lần nộp chỉ gửi 1 video (bot chỉ chuyển video đầu tiên cho chỉ huy chấm)."
    else:
        rule = ""
    if is_video_task(task):
        need = ["có tiếng (thoại / nhạc / tiếng động)"]
        if target and target.get("shape"):
            need.append(f"khung {target['shape']} như video mẫu")
        if target and target.get("duration") and not task.get("segment"):
            need.append(f"dài khoảng {target['duration']:.0f} giây")
        rule += (f"\n\nBot tự đo video trước khi chuyển chỉ huy: phải {', '.join(need)}, và là file MỚI (không nộp lại "
                 f"file cũ). Sai là bot trả lại ngay.")
        rule += ("\n\nKhi nộp video, ghi thêm (bot chép vào trang tổng hợp):\n"
                 "Caption: <caption đăng kèm video>\n"
                 + "".join(f"Caption ({code}): <caption đó viết bằng {LANG_NAMES[code]}, cho kênh đăng bằng "
                           f"ngôn ngữ này>\n" for code in caption_langs(cfg, task.get("to", "")))
                 + "Hashtag: <các hashtag, cách nhau bởi dấu cách>\n"
                 "Link tải: <nếu có link https://muse.ai/files/..., không có thì bỏ dòng này>")
    lang = lang_name(cfg, task.get("to", ""))
    if lang:
        rule += f"\n\nTrả lời và làm sản phẩm bằng {lang}."
    return (rule + f"\n\nKhi làm xong, viết dòng [[xong: {tid}]] ở cuối câu trả lời. Không làm được hoặc cần hỏi "
                   f"lại thì viết [[vuong: {tid} | lý do hoặc câu hỏi]].\n\n" + STOP_RULE)


# Muse lam viec tu lam tiep sau khi xong viec (2026-11-07: Muse2, Muse8 xong ho so nhan vat thi tu de xuat y tuong
# tap dau, tim trend, tao file, hoi chu chon de "lam tiep duoc ngay" -- chu chua giao gi).
STOP_RULE = ("Chỉ làm đúng phần việc này. Ghi [[xong]] xong thì DỪNG HẲN: không tự làm bước tiếp theo trong quy trình "
             "của bạn, không tự đề xuất / chuẩn bị ý tưởng, kịch bản, ảnh hay video mới, không tự nhắn thêm. Chờ bot "
             "chuyển việc mới.")


def worker_text(task, kind, text, cfg, prefix="", refs="", target=None):
    tid, pl = task["id"], part_label(task)
    pl = f" — {pl}" if pl else ""
    head = {"giao": f"[Việc {tid} — Chỉ huy giao{pl}]",
            "tiep": f"[Việc {tid}{pl}]",
            "lamlai": f"[Việc {tid}{pl} — làm lại lần {task.get('round', 0)}/{cfg['max_rounds']}] Chưa đạt, cần sửa:",
            "qc": f"[Việc {tid}{pl} — bot trả lại vì lỗi kỹ thuật] Video vừa nộp chưa được chuyển chỉ huy:",
            "nhan": f"[Việc {tid} — Chỉ huy nhắn]",
            "nhac": f"[Việc {tid} — Bot nhắc]"}[kind]
    return (prefix + f"{head}\n{text}" + (f"\n\n{refs}" if refs else "") + _footer(task, cfg, target)).strip()


def next_part_text(task, score, note):
    """Tin bot gui Muse khi video / doan truoc dat: lam tiep (nhac lai yeu cau goc cho Muse khong lech)."""
    done = task.get("part", 1) - 1
    if task.get("segment"):
        return (f"Đoạn {done} đạt {score}" + (f" — {note}" if note else "") + ".\n"
                f"Giờ làm ĐOẠN {task['part']}/{task['parts']} theo đúng mốc giây của đoạn này trong kịch bản. Bot đính "
                f"kèm khung hình cuối của đoạn {done}: khung đầu đoạn này phải nối liền khung đó (cùng nhân vật, trang "
                f"phục, tóc, bối cảnh, ánh sáng, góc máy hợp lý). Yêu cầu gốc của việc:\n{task['text']}")
    return (f"Video {done} đạt {score}" + (f" — {note}" if note else "") + ".\n"
            f"Giờ làm video {task['part']}/{task['parts']}: tình huống / nội dung KHÁC các video đã làm, giữ nguyên "
            f"chuẩn đã đạt. Yêu cầu gốc của việc:\n{task['text']}")


def qc_text(problems, line, left):
    return ("Bot đo video bạn vừa nộp: " + line + ".\nLỗi phải sửa:\n" + "\n".join(f"- {p}" for p in problems)
            + f"\nLàm lại video MỚI cho đúng (vẫn theo đúng yêu cầu và kịch bản của việc), rồi nộp lại. "
              f"Bot còn trả lại tối đa {left} lần vì lỗi kỹ thuật, sau đó chuyển chỉ huy chấm như hiện trạng.")


def nudge_text(task, has_output):
    if has_output:
        return ("Bot chưa thấy dòng xong của bạn. Nếu đã xong, gửi kết quả cuối (đúng 1 video nếu là video) và ghi "
                f"[[xong: {task['id']}]]. Nếu đang làm dở thì làm tiếp cho xong rồi mới gửi.")
    return ("Bot chưa nhận được kết quả nào của bạn cho việc này. Nếu đang làm thì làm tiếp; xong thì gửi kết quả và "
            f"ghi [[xong: {task['id']}]]. Không làm được thì ghi [[vuong: {task['id']} | lý do]].")


def ref_block(refs, samples=(), scripts=(), extra=()):
    """refs: [(task, so file)], samples: [(video mau, so file)], scripts: [(ma mau, kich ban)], extra: [dong chu]
    -> doan mo ta tham chieu gui kem cho Muse lam."""
    lines = []
    for sid, sc in scripts:
        lines.append(f"KỊCH BẢN CHỐT cho video mẫu {sid} (bản v{sc['v']}, chủ đã duyệt — làm ĐÚNG bản này, bỏ mọi bản cũ "
                     f"nếu có):\n{sc['text']}\n")
    if refs:
        lines.append("Tài liệu tham chiếu bot đính kèm (bản ĐÃ DUYỆT, dùng đúng như vậy, không tự đổi chi tiết):")
    for t, n in refs:
        body = short("\n".join(t.get("passed_report") or t.get("report") or []), REF_REPORT_CHARS)
        lines.append(f"- {t['id']} ({t['to']}, đạt {t.get('score') or '—'}"
                     + (f", {n} file đính kèm" if n else "") + f"): {body or short(t['text'], 300)}")
    for s, n in samples:
        meta = s.get("meta") or {}
        lines.append(f"Video mẫu {s['id']} bot đính kèm ({n} file: video gốc"
                     + (" + ảnh ghép khung hình, góc trái mỗi ô ghi giây" if n > 1 else "") + ")"
                     + (f", dài {meta['duration']:.0f} giây" if meta.get("duration") else "")
                     + ". Xem kỹ video để làm đúng nhịp, góc máy, hành động; chỉ thay nhân vật như kịch bản / lời giao. "
                       "Không lấy logo, chữ thương hiệu, watermark, tên kênh của video gốc.")
    lines += list(extra)
    return "\n".join(lines).strip()


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


def report_text(task, tasks, why, cfg, note="", scripts=None):
    body = "\n\n".join(task.get("report") or []).strip() or "(Muse không viết chữ nào)"
    if len(body) > REPORT_MAX_CHARS:
        body = body[:REPORT_MAX_CHARS].rstrip() + "\n…(đã cắt bớt, xem đủ trong topic " + task["to"] + ")"
    files = len(task.get("files") or [])
    p, left = cfg["pass_score"], cfg["max_rounds"] - task.get("round", 0)
    pl = part_label(task)
    last = task.get("parts", 1) <= task.get("part", 1)
    unit = "đoạn" if task.get("segment") else "video"
    look = task.get("stage") == "hinh"
    after = ("bot giữ các ảnh này và cho Muse làm bước 2 (video)" if look
             else "bot nối các đoạn thành 1 video và đóng việc" if last and task.get("segment") else "bot đóng việc"
             if last else f"bot cho Muse làm {unit} {task.get('part', 1) + 1}/{task['parts']}")
    summary = ""
    if look:
        summary = ("\nCHẤM BƯỚC TẠO HÌNH: đạt khi đủ ảnh cho mỗi nhân vật × mỗi giai đoạn trang phục / tóc trong kịch "
                   "bản, mặt từng nhân vật giống ảnh bộ nhân vật khoá (bot đính kèm sau ảnh của Muse) và giống nhau "
                   "giữa các ảnh, tóc + trang phục đúng kịch bản, không logo / chữ. Mặt khác bộ khoá hoặc thiếu giai "
                   "đoạn → chưa đạt, ghi rõ ảnh nào sai gì.\n")
    elif is_video_task(task):
        info = video_info(task)
        missing = [name for name, key in (("caption", "caption"), ("hashtag", "hashtag")) if not info[key]]
        summary = (f"\nDòng chuẩn cho trang \"{ARTIFACT_NAME}\":\n{summary_row(task, info)}\n"
                   + (f"Muse chưa ghi {', '.join(missing)}: ghi \"chưa có\" trong trang, nhắc Muse bổ sung khi chấm.\n"
                      if missing else ""))
    qc = "".join(f"Bot đo: {x}\n" for x in task.get("qc") or [])
    used = task.get("script") or {}
    script_line = ""
    for sid, v in used.items():
        cur = (scripts or {}).get(sid)
        script_line += (f"Làm theo kịch bản chốt {sid} bản v{v}"
                        + (f" — LƯU Ý: kịch bản đã có bản mới v{cur['v']}, chấm theo bản v{v} Muse nhận hoặc yêu cầu "
                           f"làm lại theo bản mới" if cur and cur["v"] != v else "") + ".\n")
    return (f"[Báo cáo {task['id']} từ {task['to']}" + (f" — {pl}" if pl else "")
            + (f" — làm lại lần {task['round']}" if task.get("round") else "") + f"] {why}\n"
            f"Việc: {short(task['text'], 400)}\n" + script_line + f"\nKết quả:\n{body}\n"
            + (f"\n({files} ảnh/video/file kết quả đính kèm.)\n" if files else "\n(Không có ảnh/video đính kèm.)\n")
            + qc + summary
            + (f"{note}\n" if note else "")
            + f"\nBảng việc hiện tại (bản chuẩn):\n{board(tasks)}\n\n"
            f"Chấm bằng [[danhgia: {task['id']} | điểm/10 | nhận xét]]. Từ {p}/10 là đạt ({after}); dưới {p}/10 bot "
            f"gửi nhận xét để Muse làm lại "
            + (f"(còn {left} lần)." if left > 0 else "— nhưng đã hết lượt làm lại: dưới mức này bot dừng việc, báo chủ.")
            + f" Muốn đổi yêu cầu thì dùng [[lamlai: {task['id']} | cần sửa gì]].")


def new_task(tasks, seq, to, text, parts=1, segment=False, stage=""):
    tid = f"T{seq}"
    now = time.time()
    tasks[tid] = {"id": tid, "to": to, "text": text, "status": "duyet", "created": now, "updated": now, "round": 0,
                  "queue": [], "report": [], "files": [], "done": "", "last_out": 0, "sent_at": 0, "score": "",
                  "note": "", "overdue": False, "fails": 0, "parts": parts, "part": 1, "scores": [],
                  "passed_files": [], "passed_report": [], "history": [], "nudged": False, "told": False,
                  "segment": bool(segment and parts > 1), "part_videos": {}, "qc": [], "qc_returns": 0,
                  "script": {}, "target": {}, "stage": stage, "look_files": []}
    if len(tasks) > TASKS_KEEP:
        for old in sorted(tasks.values(), key=lambda t: t["updated"]):
            if len(tasks) <= TASKS_KEEP:
                break
            if old["status"] not in OPEN_STATUSES:
                tasks.pop(old["id"])
    return tasks[tid]
