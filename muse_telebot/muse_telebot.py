# -*- coding: utf-8 -*-
"""
Bot Telegram <-> muse.ai qua FoxProfile.

  - Moi doi Muse 1 nhom Telegram bat Chu de (Topics); /setup trong nhom gan nhom voi 1 doi (hoac tao doi moi). Moi
    profile thuoc 1 doi, co 1 topic trong nhom cua doi (ten = ten profile). Doi mac dinh nhan profile chua thuoc doi nao.
  - Profile dang mo va da dang nhap muse.ai ma chua co topic: bot tu tao topic (topics_loop).
  - Telegram -> Muse: tin / anh / video / gif / file / audio trong topic duoc go vao main chat muse.ai cua profile
    (muse_sync.py), nguyen van. Album gom thanh 1 tin. Reply 1 tin thi trich tin goc o dau.
  - Muse -> Telegram: bot doc tra loi cua Muse tren trang (chu + anh/video/file) va gui ve topic (relay ngay sau khi
    gui tin; watch moi WATCH_INTERVAL giay cho tin Muse tu viet / go tren web). Dong "[[nút: A | B]]" cuoi tin thanh
    nut bam; bam nut thi lua chon duoc gui lai vao Muse.
  - /reset (chu bot): bam nut xac nhan -> xoa toan bo du lieu Muse cua profile (Settings -> Data controls -> Reset
    <ten agent>, bot tu doc ten agent), xoa topic cu, tao topic moi cung ten, dat ten agent = ten profile.
    /reset o muc General (Muse chi huy) / "/reset <chi huy>": reset CA DOI -- chon mau ngu canh (lay tu dashboard) hoac
    giu ngu canh dang co; bot luu qua API dashboard (reset_data) roi tu xoa + gui lai ngu canh (ask_team_reset).
  - /tach (chu bot, che do co chi huy): trong topic 1 Muse thanh vien / "/tach <ten>" / o General chon tu danh sach ->
    tach Muse khoi doi (API dashboard /settings/muse-team/detach), chon xoa du lieu Muse hoac giu (bot nhan Muse bo boi
    canh doi). Bot huy moi viec dang mo cua Muse do (team_detach), gioi thieu lai doi cho chi huy.
  - Ten agent: agent con ten mac dinh "Muse" thi khi tao topic / /gan bot gui "Change your name to <profile>".
  - Khoi dong / /start: bot kiem tra tung buoc cau hinh va huong dan nguoi dung; canh bao profile dung IP Viet Nam.

Trang thai (muse_telebot_state.json, bot tu tao):
    {"admin": <user id chu bot>, "teams": {"<ma doi>": {"group": <chat id nhom>, "topics": {"<profile>": <topic id>},
     "tasks": {"T1": viec cua doi Muse}, "task_seq": N, "team_pending": {...}, "team_brief": "..."}} (TEAM_KEYS),
     "delivered": {"<profile>": [id tin Muse da chuyen]}, "watched": ["<profile>"]}
    File ban 1 nhom (khoa doi o ngoai cung) duoc doc la doi "default".
Doi Muse (1 Muse chi huy o muc General giao viec cho cac Muse khac): xem muse_team.py, cai tren dashboard FoxProfile.

.env (thu muc goc Muse2tele): TELEGRAM_BOT_TOKEN, MUSE_UPLOAD_DIR (phai nam trong FOXPROFILE_UPLOAD_DIRS),
    MUSE_SAVE_VIDEOS (1 = mac dinh / 0) + MUSE_SAVE_VIDEO_DIR: luu ban sao moi video Muse gui vao
    <thu muc>/<profile>/ (mac dinh E:/Videos/Downloaded), sua tren dashboard FoxProfile, ap dung ngay.
"""

import contextvars
import ctypes
import functools
import hashlib
import html
import io
import json
import logging
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import SimpleNamespace

import requests
import telebot
from dotenv import dotenv_values, load_dotenv
from telebot import types
from telebot.apihelper import ApiTelegramException

import muse_auto
import muse_sync
import muse_team
import video_sample
from muse_sync import HERE

sys.path.insert(0, str(HERE.parent / "social_post"))
import post_kit  # noqa: E402  (bo dang bai, dung chung voi social_post/auto_post.py)
import brand_kit  # noqa: E402  (bo nhan dien kenh cho /rebrand, dung chung voi social_post/rebrand.py)
import post_control  # noqa: E402  (trang thai / dieu khien AutoPost cho /dang)

TITLE = "Muse2tele_Bot"
ROOT = HERE.parent
ENV_FILE = ROOT / ".env"
load_dotenv(HERE / ".env")
load_dotenv(ENV_FILE)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
# Duong dan tuyet doi: FoxProfile chay o thu muc khac (foxprofile\data), duong dan tuong doi se tro sai cho.
UPLOAD_DIR = (HERE / os.environ.get("MUSE_UPLOAD_DIR", str(ROOT / "Videos" / "downloads" / "muse_telebot"))).resolve()
STATE_FILE = HERE / "muse_telebot_state.json"
TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024  # getFile cua Bot API
TG_FETCH_TIMEOUT = (15, 60)  # (ket noi, moi lan doc) khi tai file tu Telegram
TG_FETCH_TOTAL_SECONDS = 300
TG_FETCH_ATTEMPTS = 3
RESEND_DIR = UPLOAD_DIR / "gui_lai"  # ban sao file cua tin cuoi gui vao tung Muse (doi soat gui lai kem file)
TG_UPLOAD_LIMIT = 50 * 1024 * 1024  # gui file qua Bot API
# Tu dong luu video Muse gui (dashboard FoxProfile -> Thu muc upload): .env doc lai moi khi file doi.
VIDEO_SAVE_DEFAULT_DIR = "E:/Videos/Downloaded"
VIDEO_SAVE_LIMIT = 1024 * 1024 * 1024  # dang luu video: tai ca video qua 50 MB (khong gui duoc Telegram) toi muc nay
MEDIA_UPLOAD_TIMEOUT = 300
MEDIA_UPLOAD_ATTEMPTS = 2
ALBUM_WAIT_SECONDS = 2
REPLY_QUOTE_MAX = 150
CONTENT_TYPES = ["text", "photo", "video", "animation", "document", "audio", "voice", "video_note"]
RELAY_INTERVAL = 1.5
RELAY_IDLE_POLLS = 3  # bao nhieu lan lien tiep Muse ranh + khong con tin cho chuyen thi coi la xong luot
RELAY_START_GRACE = 30
RELAY_MAX_SECONDS = 2 * 3600
RELAY_MAX_ERRORS = 15
# Tin "Muse dang lam gi" trong topic (dong trang thai duoi ten agent, xem muse_sync.STATUS_JS): sua tai cho khi trang
# thai doi, toi da 1 lan moi ACTIVITY_EDIT_GAP giay / chat (Telegram gioi han ~20 tin / phut / nhom); het trang thai
# va Muse ranh chung ACTIVITY_CLEAR_SECONDS giay thi xoa (dong trang thai hay tat thoang qua giua 2 buoc).
ACTIVITY_EDIT_GAP = 5
ACTIVITY_CLEAR_SECONDS = 10
APPROVAL_RE = re.compile(r"approv", re.I)  # dong trang thai "Needs approval": Muse cho nguoi bam Allow / Deny
APPROVAL_ALERT_SECONDS = 20  # muse_auto quet moi 5 giay: con cho qua chung nay giay la bot khong tu duyet duoc
WATCH_INTERVAL = 5
WATCH_WORKERS = 4
WATCH_RETRY_SECONDS = 60
DELIVERED_KEEP = 200
MEDIA_RELOAD_SECONDS = 20
MEDIA_RELOAD_GAP = 90
MEDIA_MISSING_WAIT = 240
# Muse hay hien 1 file o 2 tin (VD tin tra loi nhung video + tin rieng chi co khung dinh kem cung file, Muse8
# 2026-11-10): cung noi dung trong 1 chat trong chung nay giay chi chuyen 1 lan
MEDIA_DEDUP_SECONDS = 1800
MEDIA_DEDUP_KEEP = 50
UNRENDERED_WAIT = 60  # tin Muse chua render (khung rong): cho toi da chung nay giay roi bo qua
TOPICS_CHECK_SECONDS = 30  # quet profile moi dang nhap Muse
IP_CHECK_SECONDS = 6 * 3600  # kiem tra lai IP cac profile
UPDATE_CHECK_SECONDS = 6 * 3600  # hoi FoxProfile co ban Muse2Tele moi tren GitHub khong
STALL_RETRY_SECONDS = 60
STALL_GIVE_UP_SECONDS = 30 * 60
WATCH_HANG_SECONDS = 180
MUSE_DOWN_TEXT = "⏳ Muse đang gặp lỗi, bot sẽ tự gửi lại tin này khi Muse hoạt động trở lại."
CHOSEN_DATA = "muse_bridge_chosen"
RESET_DATA = "muse_reset:"  # + "go:<profile>" / "no"
DETACH_DATA = "tdetach:"  # + "ask:<profile>" (chon tu danh sach) / "w:<profile>" (tach + xoa) / "k:<profile>" / "no"
TEAM_RESET_DATA = "treset:"  # + "t:<mau>" / "keep" / "chief" / "no"; xac nhan: "go:t:<mau>" / "go:keep"
LINK_DATA = "muse_link:"  # + "<profile>" / "" (huy): nut chon profile cua /gan
APPROVE_DATA = "muse_allow:"  # + "<profile>": nut Cho phep tren tin bao Muse cho duyet
BUTTONS_RE = re.compile(r"\[\[\s*(?:nút|nut|buttons?)\s*:\s*(.+?)\s*\]\]", re.IGNORECASE | re.DOTALL)
KIND_LABEL = {"image": "ảnh", "video": "video"}
VN_WARNING = ("🚫 <b>CẢNH BÁO: profile <code>{profile}</code> đang vào Muse bằng IP Việt Nam</b> ({ip}, {country}).\n"
              "Muse có thể chặn hoặc khoá tài khoản khi dùng IP Việt Nam. Hãy mở FoxProfile, sửa profile này, gắn "
              "<b>proxy nước ngoài</b> (Mỹ, Singapore, Nhật...), rồi tắt và mở lại profile.")

LOG_FILE = HERE / "muse_telebot.log"
_root = logging.getLogger("muse")
_root.setLevel(logging.INFO)
# Giu log ~1 tieng gan nhat: moi 10 phut sang file moi (muse_telebot.log.YYYY-mm-dd_HH-MM), giu 6 file cu.
for _handler in (TimedRotatingFileHandler(LOG_FILE, when="M", interval=10, backupCount=6, encoding="utf-8"),
                 logging.StreamHandler()):
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _root.addHandler(_handler)
logger = logging.getLogger("muse.telebot")
telebot.logger.setLevel(logging.INFO)  # loi polling (409, mang...) hien ra console / log
for _handler in _root.handlers:
    telebot.logger.addHandler(_handler)

bot = telebot.TeleBot(TOKEN, parse_mode=None, threaded=False) if TOKEN else None
jobs = queue.Queue()
profile_queues = {}
profile_queues_lock = threading.Lock()
busy_keys = set()  # profile dang xu ly 1 lenh (profile_worker): doi soat bo qua
relays = {}
relay_lock = threading.Lock()
activity = {}  # chat key -> tin trang thai dang hien (show_activity)
approvals = {}  # chat key -> Muse dang cho duyet + tin bao (watch_approval); chung activity_lock
activity_lock = threading.Lock()
state_lock = threading.RLock()  # update_state giu khoa trong khi goi load_state / save_state
stalled = {}
stalled_lock = threading.Lock()
ip_results = {}  # profile -> (ip, quoc gia, la VN)
ip_warned = {}  # profile -> luc canh bao IP VN gan nhat


# ---------- trang thai ----------

# Windows: os.replace / doc file loi "Access is denied" (WinError 5) khi dung luc do 1 luong / chuong trinh khac
# (antivirus, script doc state...) dang mo file (2026-11-07: "Loi xu ly tin: PermissionError ... state.tmp ->
# state.json"). Doc / ghi trong bot di qua state_lock (RLock) nen khong tu dung nhau; voi chuong trinh ngoai: thu lai.
STATE_IO_SECONDS = 10
STATE_IO_PAUSE = 0.03


def _state_io(action):
    deadline = time.time() + STATE_IO_SECONDS
    while True:
        try:
            return action()
        except PermissionError:
            if time.time() >= deadline:
                raise
            time.sleep(STATE_IO_PAUSE)


# Trang thai nhieu doi: state["teams"][<ma doi>] giu cac khoa rieng cua doi (TEAM_KEYS: nhom, topic, viec, video mau...);
# cac khoa con lai (admin, delivered, watched, last_sent, sent_media...) dung chung, theo profile. load_state() tra ve
# trang thai cua doi dang xu ly (muse_team.TEAM) da tron voi khoa chung, save_state() tach lai. File cua ban 1 nhom (khoa
# doi o cap ngoai cung) duoc doc la doi mac dinh, ghi lai theo dang moi o lan luu dau tien.
TEAM_KEYS = ("group", "group_title", "topics", "tasks", "task_seq", "team_pending", "team_pseq", "team_post_seq",
             "team_posts", "team_setup", "team_reset", "team_detached", "team_brief", "scripts", "samples",
             "sample_seq")


def _read_raw():
    """File trang thai (dang nhieu doi). Chua co file: {"teams": {}}. File dang bi khoa qua lau: bao loi (KHONG tra
    rong -- update_state se ghi de mat het trang thai)."""
    with state_lock:
        try:
            raw = json.loads(_state_io(lambda: STATE_FILE.read_text(encoding="utf-8")))
        except FileNotFoundError:
            raw = {}
        except ValueError:
            logger.error(f"{STATE_FILE.name} hong (khong phai JSON), bat dau trang thai moi")
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    if not isinstance(raw.get("teams"), dict):  # ban 1 nhom: khoa doi o ngoai cung = doi mac dinh
        legacy = {k: raw.pop(k) for k in TEAM_KEYS if k in raw}
        raw["teams"] = {muse_team.DEFAULT_TEAM: legacy} if legacy else {}
    return raw


def load_state(tid=None):
    """Trang thai cua doi tid (mac dinh: doi dang xu ly) tron voi cac khoa chung."""
    with state_lock:
        raw = _read_raw()
        view = {k: v for k, v in raw.items() if k != "teams"}
        view.update(raw["teams"].get(tid or muse_team.current_team()) or {})
        return view


def save_state(state, tid=None):
    with state_lock:
        raw = _read_raw()
        teams = raw.pop("teams")
        teams[tid or muse_team.current_team()] = {k: v for k, v in state.items() if k in TEAM_KEYS}
        out = {k: v for k, v in state.items() if k not in TEAM_KEYS and k != "teams"}
        out["teams"] = teams
        tmp = STATE_FILE.with_suffix(".tmp")
        _state_io(lambda: tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8"))
        _state_io(lambda: os.replace(tmp, STATE_FILE))


def update_state(change, tid=None):
    with state_lock:
        state = load_state(tid)
        result = change(state)
        save_state(state, tid)
        return result


def team_states():
    """{ma doi: trang thai rieng cua doi} (doc thang file, khong tron khoa chung)."""
    return _read_raw()["teams"]


def admin_id():
    return load_state().get("admin")


def group_id():
    return load_state().get("group")


def team_of_group(chat_id):
    """Doi gan voi nhom Telegram chat_id (None neu nhom chua gan doi nao)."""
    ids = muse_team.team_ids()
    return next((tid for tid, st in team_states().items() if tid in ids and st.get("group") == chat_id), None)


def team_of_profile(profile):
    """Doi cua 1 profile: doi co topic cua profile, khong thi doi liet ke / chon profile lam chi huy, khong nua thi doi
    mac dinh."""
    ids = muse_team.team_ids()
    for tid, st in team_states().items():
        if tid in ids and profile in (st.get("topics") or {}):
            return tid
    for t in muse_team.raw_teams():
        if profile in (t.get("profiles") or []) or (profile and str(t.get("chief") or "").strip() == profile):
            return t["id"]
    return muse_team.default_team()


def topics():
    """profile -> topic id (nhom cua doi dang xu ly)."""
    return {p: int(t) for p, t in (load_state().get("topics") or {}).items()}


def chat_of(profile, topic):
    """Chat muse (main chat cua profile) map voi 1 topic. Muse chi huy (doi Muse, muse_team.py): tin cua no ve muc
    General cua nhom ("<nhom>/" = khong co topic)."""
    tg = f"{group_id()}/" if profile == muse_team.chief() else f"{group_id()}/{topic}"
    return {"profile": profile, "url": muse_sync.MUSE_URL, "tg": tg, "key": profile, "team": muse_team.current_team()}


def mapped_chats():
    """Cac chat dang dong bo (moi doi da gan nhom): profile co topic, them Muse chi huy (o muc General) neu no chua co
    topic. Moi profile chi 1 chat (doi dau tien co no)."""
    chats, seen = [], set()
    for tid in muse_team.team_ids():
        with muse_team.in_team(tid):
            if not group_id():
                continue
            mapped, chief = topics(), muse_team.chief()
            mine = [chat_of(p, t) for p, t in mapped.items()]
            if chief and chief not in mapped:
                mine.append(chat_of(chief, None))
        for c in mine:
            if c["key"] not in seen:
                seen.add(c["key"])
                chats.append(c)
    return chats


def topic_of(m):
    return m.message_thread_id if getattr(m, "is_topic_message", False) else None


def target_for(m):
    """Chat muse nhan tin m: topic cua 1 profile trong nhom cua doi dang xu ly (hoac muc General: chi huy)."""
    if m.chat.id != group_id():
        return None
    topic = topic_of(m)
    if topic is None:  # muc General: Muse chi huy (che do doi Muse), khong co thi khong gan Muse nao
        chief = muse_team.chief()
        return chat_of(chief, None) if chief else None
    profile = next((p for p, t in topics().items() if t == topic), None)
    return chat_of(profile, topic) if profile else None


def is_admin(user):
    return bool(user) and user.id == admin_id()


def spawn(target, *args, team=None):
    """Chay target trong luong moi, giu doi dang xu ly (luong moi khong tu thua huong contextvar)."""
    ctx = contextvars.copy_context()

    def run():
        if team:
            with muse_team.in_team(team):
                target(*args)
        else:
            target(*args)
    threading.Thread(target=ctx.run, args=(run,), daemon=True).start()


def put_job(job):
    """Xep viec vao hang doi chung, ghi doi dang xu ly (profile_worker chay viec trong doi do)."""
    key = (job.get("chat") or {}).get("key") or job.get("key") or job.get("profile")
    job.setdefault("team", (job.get("chat") or {}).get("team") or (team_of_profile(key) if key else None))
    jobs.put(job)


class PerTeam:
    """Bien trong bo nho rieng tung doi (vd team_inflight): moi doi 1 ban, theo doi dang xu ly."""

    def __init__(self, factory):
        self._factory, self._items = factory, {}

    def here(self):
        tid = muse_team.current_team()
        if tid not in self._items:
            self._items[tid] = self._factory()
        return self._items[tid]

    def __getattr__(self, name):
        return getattr(self.here(), name)

    def __getitem__(self, key):
        return self.here()[key]

    def __setitem__(self, key, value):
        self.here()[key] = value

    def __contains__(self, key):
        return key in self.here()

    def __and__(self, other):
        return self.here() & set(other)

    def __rand__(self, other):
        return set(other) & self.here()


def team_dir():
    """Thu muc du lieu doi (ket qua viec, video mau, bo nhan vat, luu tru reset): doi mac dinh dung thang UPLOAD_DIR
    (giu duong dan cu), doi khac UPLOAD_DIR/doi/<ma doi>."""
    tid = muse_team.current_team()
    return UPLOAD_DIR if tid == muse_team.DEFAULT_TEAM else UPLOAD_DIR / "doi" / tid


def char_dir():
    """Bo nhan vat khoa cua doi: <Muse>/<ma viec>/ anh bo nhan vat dat + nguon.txt (khong bi don)."""
    return team_dir() / "nhan_vat"


# ---------- Telegram -> Muse ----------

def react(m, emoji):
    if getattr(m, "from_user", None) and m.from_user.is_bot:
        return False
    if not hasattr(m, "message_id"):  # target gia (watch / hoi link): khong co tin de tha reaction
        return False
    try:
        bot.set_message_reaction(m.chat.id, m.message_id, [types.ReactionTypeEmoji(emoji)])
        return True
    except Exception as e:
        logger.debug(f"Khong dat duoc reaction {emoji}: {e}")
        return False


def notify(text, parse_mode=None):
    """Bao cho chu bot (chat rieng)."""
    admin = admin_id()
    if not admin:
        return
    try:
        bot.send_message(admin, text[:4000], parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Khong gui duoc thong bao cho chu bot: {e}")


def message_file(m):
    kind = m.content_type
    if kind == "photo":
        return m.photo[-1], f"photo_{m.message_id}.jpg"
    obj = getattr(m, kind, None) if kind in CONTENT_TYPES[1:] else None
    if obj is None:
        return None, ""
    default_ext = {"video": ".mp4", "animation": ".mp4", "voice": ".ogg", "video_note": ".mp4", "audio": ".mp3"}
    name = getattr(obj, "file_name", None) or f"{kind}_{m.message_id}{default_ext.get(kind, '')}"
    return obj, re.sub(r'[\\/:*?"<>|]', "_", name)


def download(m, folder):
    obj, name = message_file(m)
    if obj is None:
        return ""
    size = getattr(obj, "file_size", 0) or 0
    if size > TG_DOWNLOAD_LIMIT:
        raise RuntimeError(f"{name} ({size / 1048576:.1f} MB) vượt giới hạn 20MB của Telegram Bot")
    info = bot.get_file(obj.file_id)
    if "." not in name:
        name += Path(info.file_path).suffix
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    tg_fetch(info.file_path, path)
    return str(path)


def tg_fetch(file_path, dest):
    """Tai file tu Telegram, co gioi han thoi gian va thu lai. bot.download_file cua telebot goi requests KHONG co
    timeout: 2026-11-09 09:01 mang Telegram chap chon, tai video cho Muse8 treo mai, ca hang doi Muse8 dung tu do."""
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    last = None
    for attempt in range(TG_FETCH_ATTEMPTS):
        if attempt:
            time.sleep(3 * attempt)
        tmp = dest.with_name(dest.name + ".part")
        try:
            deadline = time.time() + TG_FETCH_TOTAL_SECONDS
            with requests.get(url, stream=True, timeout=TG_FETCH_TIMEOUT) as r:
                if r.status_code != 200:
                    last = f"HTTP {r.status_code}"
                    continue
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if time.time() > deadline:
                            raise TimeoutError(f"quá {TG_FETCH_TOTAL_SECONDS}s chưa tải xong")
                        f.write(chunk)
            os.replace(tmp, dest)
            return
        except (requests.RequestException, TimeoutError, OSError) as e:
            last = f"{type(e).__name__}: {(str(e).replace(TOKEN, '***') if TOKEN else str(e))[:200]}"
            logger.warning(f"Tai file Telegram lan {attempt + 1}/{TG_FETCH_ATTEMPTS} loi: {last}")
        finally:
            Path(tmp).unlink(missing_ok=True)
    raise RuntimeError(f"tải từ Telegram lỗi sau {TG_FETCH_ATTEMPTS} lần ({last})")


def with_reply_context(m, text):
    ref = getattr(m, "reply_to_message", None)
    if not ref or (topic_of(m) and ref.message_id == m.message_thread_id):  # tin trong topic "reply" tin mo topic
        return text
    quoted = " ".join((ref.text or ref.caption or "").split())
    if not quoted:
        quoted = {"photo": "[ảnh]", "video": "[video]", "animation": "[gif]"}.get(ref.content_type, "[tệp]")
    if len(quoted) > REPLY_QUOTE_MAX:
        quoted = quoted[:REPLY_QUOTE_MAX].rstrip() + "..."
    return f'(Trả lời tin: "{quoted}") {text}'.strip()


def process(batch, retry=False):
    """Gui 1 tin (album / lan bam nut) vao Muse roi chuyen tra loi ve topic. Tra ve False neu tin con trong hang cho."""
    first, chat, tap = batch[0]["m"], batch[0]["chat"], batch[0]["kind"] == "tap"
    if not retry:
        with stalled_lock:
            s = stalled.get(chat["key"])
            if s:
                s["batches"].append(batch)
        if s:
            hold_notice(batch)
            return False
    text = "\n".join(j["text"] for j in batch if j["text"])
    if not tap:
        text = with_reply_context(first, text)
    folder = UPLOAD_DIR / f"{first.chat.id}_{first.message_id}"
    files, errors, seen, muse_down = [], [], set(), False
    try:
        for j in batch:
            if tap:
                break
            try:
                path = download(j["m"], folder)
                if path:
                    files.append(path)
            except Exception as e:
                errors.append(f"{j['m'].content_type}: {e}")
        if errors:  # thieu file: khong gui rieng phan chu (Muse se tra loi "chua thay video"), bao chu gui lai
            logger.warning(f"Msg {first.message_id} -> {chat['key']}: khong tai duoc file, khong gui: {errors}")
            for j in batch:
                react(j["m"], "👎")
            safe_reply(first, "⚠️ Bot không tải được file từ Telegram nên CHƯA gửi gì cho Muse:\n"
                              + "\n".join(errors) + "\nBạn gửi lại tin này (kèm file) giúp nhé.")
            return True
        if not tap:  # link video (Facebook / TikTok...) / file video gui chi huy: tai ve thanh video mau M<n>
            note, extra = attach_samples(batch, chat, text, files)
            text, files = ((text + "\n\n" + note).strip() if note else text), files + extra
        if files or text.strip():
            base = batch[0].setdefault("base", set())
            ok, result = muse_sync.send(chat, text, files, seen=seen, base=base)
            # ok None = loi file / cau hinh upload: Muse van chay, giu tin lai thu mai chi lam ket ca topic.
            muse_down = ok is False and not errors
            if ok is None:
                notify(f"⚠️ Bot không đưa được file từ Telegram vào Muse ({chat['key']}).\n{result}\n\n"
                       f"Kiểm tra FOXPROFILE_UPLOAD_DIRS / MUSE_UPLOAD_DIR trong .env rồi khởi động lại "
                       f"FoxProfile và bot. Gõ /start để bot tự kiểm tra lại.")
        else:
            ok, result = False, "không có gì để gửi"
        if ok:
            remember_sent(chat, first, text, files, seen)  # truoc khi xoa folder: giu ban sao file de gui lai
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    logger.info(f"Msg {first.message_id} -> {chat['key']}: {result}")
    if muse_down:
        if not retry:
            stall(batch, result)
        return False
    if not tap:
        for j in batch:
            react(j["m"], "👍" if ok else "👎")
    if ok:
        if retry:
            safe_reply(first, "✅ Muse đã hoạt động lại, tin này đã được gửi.")
        relay(chat, first, seen)
        return True
    safe_reply(first, f"⚠️ Chưa gửi được cho Muse: {result}")
    return True


def attach_samples(batch, chat, text, files):
    """Link video trong tin (moi chat) va file video chu gui chi huy: bot tai / chep thanh video mau M<n> (video_sample.py),
    lam anh ghep khung hinh. Tra ve (doan chu noi them vao tin, file dinh kem them). Ket qua giu trong batch: gui lai
    tin (Muse tam loi) khong tai lai."""
    if batch[0].get("samples") is not None:
        return batch[0]["samples"]
    first, is_chief = batch[0]["m"], chat["key"] == muse_team.chief()
    if not muse_team.config()["video"]:  # doi khong dung skill video: khong tai video mau
        batch[0]["samples"] = ("", [])
        return batch[0]["samples"]
    links = video_sample.find_links(text)
    sources = [(url, None) for url in links] + [(None, f) for f in files if is_chief and muse_team.is_video(f)]
    notes, extra = [], []
    for url, video_file in sources:
        def alloc(state):
            state["sample_seq"] = state.get("sample_seq", 0) + 1
            return f"M{state['sample_seq']}"
        sid = update_state(alloc)
        folder = team_dir() / "mau" / sid
        try:
            sample = video_sample.build(sid, folder, url=url or "", video_file=video_file)
        except Exception as e:
            shutil.rmtree(folder, ignore_errors=True)
            reason = str(e) if isinstance(e, video_sample.SampleError) else f"{type(e).__name__}: {e}"
            logger.warning(f"Video mau {sid} ({url or video_file}) loi: {reason}")
            if url:
                notes.append(f"[Bot: không tải được video từ link {url} ({reason}). Đừng đoán nội dung video; "
                             f"nhờ chủ gửi thẳng file video.]")
                safe_reply(first, f"⚠️ Không tải được video từ link: {reason}\n"
                                  f"Gửi thẳng file video (dưới 20 MB) nếu muốn Muse xem video này.")
            continue
        update_state(lambda s, x=sample: video_sample.register(s, x))
        n = len(sample["sheets"])
        logger.info(f"Video mau {sid}: {url or video_file} -> {sample['video']} ({n} anh ghep)")
        notes.append(video_sample.describe(sample, is_chief))
        # file chu gui da nam trong files: chi them anh ghep; link: them ca video
        extra += sample["sheets"] if video_file else video_sample.files(sample, 1 + n)
        meta = sample["meta"]
        if meta.get("no_video"):
            head = (f"🎬 Video mẫu {sid}: video dài"
                    + (f" {video_sample.clock(meta['duration'])}" if meta.get("duration") else "")
                    + " / nặng nên bot không tải cả video, chỉ gửi Muse thông tin"
                    + (f" + {n} ảnh ghép khung hình rải đều cả video" if n else "")
                    + " để Muse tự quyết định.")
        else:
            head = (f"🎬 Video mẫu {sid}: đã tải"
                    + (f", {meta['duration']:.0f} giây" if meta.get("duration") else "")
                    + (f", {n} ảnh ghép khung hình" if n else "") + ". Gửi kèm cho Muse.")
        safe_reply(first, head
                          + (f" Chỉ huy giao việc \"theo video mẫu {sid}\" thì bot gửi kèm cho Muse làm." if is_chief
                             else ""))
    batch[0]["samples"] = ("\n\n".join(notes), extra)
    return batch[0]["samples"]


def remember_sent(chat, m, text, files=(), seen=()):
    """Ghi tin cuoi da gui vao Muse de doi soat (reconcile_loop kiem tra no con tren Muse khong). File tai tu Telegram
    (thu muc tam, xoa ngay sau khi gui) duoc chep vao RESEND_DIR/<profile>/ de doi soat gui lai CA file: 2026-11-09
    tin video cho Muse8 hien roi mat, ban gui lai chi co chu -> Muse8 tra loi "chua thay video dinh kem".
    prior: id cac tin co tren Muse truoc khi gui (tin chi co file, khong co chu: nhan ra bang tin nguoi dung moi)."""
    keep = RESEND_DIR / chat["key"]
    kept = []
    try:
        shutil.rmtree(keep, ignore_errors=True)
        for f in files:
            src = Path(f)
            if team_dir() / "mau" in src.parents or not src.is_file():  # video mau: da luu co dinh, khong chep
                kept.append(str(src))
                continue
            keep.mkdir(parents=True, exist_ok=True)
            dst = keep / src.name
            shutil.copy2(src, dst)
            kept.append(str(dst))
    except OSError as e:
        logger.warning(f"{chat['key']}: khong giu duoc file de doi soat gui lai: {e}")
    entry = {"mid": m.message_id, "chat_id": m.chat.id, "topic": topic_of(m), "text": text, "files": kept,
             "media": muse_sync.has_media(kept), "prior": sorted(seen) if kept else [],
             "at": time.time(), "verified": False, "resends": 0}
    update_state(lambda s: s.setdefault("last_sent", {}).__setitem__(chat["key"], entry))


def safe_reply(m, text):
    if not hasattr(m, "message_id"):  # target gia (watch / hoi link): gui vao topic, khong reply
        try:
            send_text(m, html.escape(text))
        except Exception:
            logger.exception("Khong gui duoc tin vao topic")
        return
    try:
        bot.reply_to(m, text)
    except Exception:
        logger.exception("Khong tra loi duoc tin")


def hold_notice(batch, result=""):
    safe_reply(batch[0]["m"], MUSE_DOWN_TEXT + (f"\n{result}" if result else ""))


def stall(batch, result):
    key = batch[0]["chat"]["key"]
    with stalled_lock:
        new = key not in stalled
        s = stalled.setdefault(key, {"batches": [], "since": time.time()})
        s["batches"].insert(0, batch)
    hold_notice(batch, result)
    if new:
        schedule_stalled(key)


def schedule_stalled(key):
    t = threading.Timer(STALL_RETRY_SECONDS, lambda: jobs.put({"kind": "stalled", "key": key}))
    t.daemon = True
    t.start()


def run_stalled(key):
    while True:
        with stalled_lock:
            s = stalled.get(key)
            if not s or not s["batches"]:
                stalled.pop(key, None)
                return
            batch = s["batches"][0]
        if process(batch, retry=True):
            with stalled_lock:
                s["batches"].pop(0)
            continue
        if time.time() - s["since"] < STALL_GIVE_UP_SECONDS:
            schedule_stalled(key)
            return
        with stalled_lock:
            batches = stalled.pop(key, {"batches": []})["batches"]
        for b in batches:
            safe_reply(b[0]["m"], "❌ Muse vẫn đang lỗi, tin này chưa gửi được. Bạn nhắn lại sau ít phút nhé.")
            if b[0]["kind"] != "tap":
                for j in b:
                    react(j["m"], "👎")
        return


def profile_queue_for(key):
    with profile_queues_lock:
        work = profile_queues.get(key)
        if work is None:
            work = profile_queues[key] = queue.Queue()
            threading.Thread(target=profile_worker, args=(work,), daemon=True).start()
        return work


def worker():
    """Phan phoi cong viec toi hang doi rieng cua tung profile."""
    while True:
        job = jobs.get()
        key = job["key"] if job["kind"] == "stalled" else job["chat"]["key"]
        profile_queue_for(key).put(job)


def profile_worker(work):
    """Xu ly tuan tu cong viec cua mot profile; gom cac phan cua album thanh mot tin."""
    pending = None
    while True:
        job, pending = pending or work.get(), None
        batch = [job]
        group = job["m"].media_group_id if job["kind"] == "msg" else None
        while group:
            try:
                nxt = work.get(timeout=ALBUM_WAIT_SECONDS)
            except queue.Empty:
                break
            if nxt["kind"] == "msg" and nxt["m"].media_group_id == group and nxt["m"].chat.id == job["m"].chat.id:
                batch.append(nxt)
            else:
                pending = nxt
                break
        busy_key = (job.get("chat") or {}).get("key") or job.get("key") or job.get("profile")
        busy_keys.add(busy_key)
        # viec chay trong doi da xep no (hoac doi cua profile): trang thai, nhom, cai dat dung doi
        token = muse_team.TEAM.set(job.get("team") or team_of_profile(busy_key))
        try:
            if job["kind"] == "stalled":
                run_stalled(job["key"])
            elif job["kind"] == "reset":
                run_reset(job)
            elif job["kind"] == "name":
                name_agent(job["profile"], job["topic"])
            elif job["kind"] == "team_send":
                run_team_send(job)
            elif job["kind"] == "team_report":
                run_team_report(job)
            elif job["kind"] == "team_brief":
                run_team_brief(job)
            elif job["kind"] == "team_setup":
                run_team_setup(job)
            elif job["kind"] == "team_reset":
                run_team_reset(job)
            elif job["kind"] == "link_rule":
                run_link_rule(job)
            elif job["kind"] == "postkit_rule":
                run_postkit_rule(job)
            elif job["kind"] == "brandkit":
                run_brandkit(job)
            elif job["kind"] == "post_kit":
                run_post_kit(job)
            elif job["kind"] == "ask":
                seen = set()
                ok, result = muse_sync.send(job["chat"], job["text"], seen=seen)
                logger.info(f"Nho Muse gui link tai {job['chat']['key']}: {result}")
                if ok:
                    relay(job["chat"], job["target"], seen)
            else:
                process(batch)
        except Exception as e:
            logger.exception("Loi xu ly tin")
            if job["kind"] == "stalled":
                schedule_stalled(job["key"])
                continue
            if "m" in job:
                safe_reply(job["m"], f"⚠️ Lỗi xử lý tin: {type(e).__name__}: {e}")
        finally:
            busy_keys.discard(busy_key)
            muse_team.TEAM.reset(token)


def enqueue(m, chat, text, kind="msg"):
    logger.info(f"Nhan TG {m.message_id} ({kind}/{getattr(m, 'content_type', '?')}) -> {chat['key']}: {text[:150]!r}")
    put_job({"kind": kind, "m": m, "chat": chat, "text": text})
    if kind == "msg":
        react(m, "👀")


def choose(c):
    """Bam nut cua Muse: khoa ban phim va gui lua chon vao Muse."""
    m = c.message
    chat = target_for(m)
    if chat is None:
        bot.answer_callback_query(c.id, "Topic này không còn kết nối với Muse.")
        return
    rows = m.reply_markup.keyboard if m.reply_markup else []
    label = next((b.text for row in rows for b in row if b.callback_data == c.data), c.data)
    bot.answer_callback_query(c.id, f"Đã gửi cho Muse: {label}")
    try:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(f"✅ {label}", callback_data=CHOSEN_DATA))
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=kb)
    except Exception:
        logger.exception("Khong khoa duoc ban phim")
    question = " ".join((m.text or m.caption or "").split())
    if len(question) > REPLY_QUOTE_MAX * 2:
        question = question[:REPLY_QUOTE_MAX * 2].rstrip() + "..."
    enqueue(m, chat, f'Tôi chọn "{label}" (trả lời tin: "{question}")', kind="tap")


# ---------- Muse -> Telegram (relay: ngay sau khi gui tin) ----------

def relay(chat, m, seen):
    with relay_lock:
        r = relays.get(chat["key"])
        if r:
            r["targets"].append(m)
            r["since"] = time.time()
            return
        relays[chat["key"]] = r = {"targets": [m], "seen": set(seen), "since": time.time(), "waiting": {},
                                   "reloaded": 0}
    spawn(relay_loop, chat, r, team=chat.get("team"))


def plain(html_text):
    return html.unescape(re.sub(r"<[^>]+>", "", html_text))


def html_chunks(text):
    chunks, cur = [], ""
    for block in text.split("\n\n"):
        if len(block) > 4000:
            if cur:
                chunks.append(cur)
                cur = ""
            raw = plain(block)
            chunks += [html.escape(raw[i:i + 3500]) for i in range(0, len(raw), 3500)]
        elif cur and len(cur) + 2 + len(block) > 4000:
            chunks.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    return chunks + ([cur] if cur else [])


def send_text(target, text, kb=None, parse_mode="HTML"):
    chunks = html_chunks(text) if parse_mode == "HTML" else [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for i, chunk in enumerate(chunks):
        args = dict(message_thread_id=topic_of(target), reply_markup=kb if i == len(chunks) - 1 else None,
                    link_preview_options=types.LinkPreviewOptions(is_disabled=True))
        try:
            bot.send_message(target.chat.id, chunk, parse_mode=parse_mode, **args)
        except ApiTelegramException as e:
            if parse_mode != "HTML" or e.error_code != 400 or "thread not found" in str(e).lower():
                raise
            logger.info(f"Telegram tu choi HTML ({e}), gui chu thuong")
            bot.send_message(target.chat.id, plain(chunk), **args)


TooLarge = muse_sync.MediaTooLarge  # file qua gioi han 50 MB cua Telegram


# Link tai tam cua Muse toi da 48 gio (2026-11-12): khong doi han dai hon, Muse se loay hoay / tu choi.
ASK_LINK = ("Các file sau không gửi được qua Telegram:\n{lines}\nHãy tạo link tải tạm thời (chọn hạn dài nhất có thể) "
            "cho từng file rồi gửi lại link (dạng https://...), không cần đính kèm lại file.")
# Muse gui lai file (khong phai link) ma van loi -> khong hoi mai: cung 1 file trong 1 chat chi hoi 1 lan / chung nay giay
ASK_LINK_GAP = 6 * 3600
ASK_LINK_KEEP = 100


def media_label(kind, title=""):
    """Ten loai file de bao (anh / video / audio / file); kind "missing" thi doan theo duoi file trong tieu de."""
    if kind == "missing":
        kind = {"image": "image", "video": "video", "audio": "audio"}.get(
            (mimetypes.guess_type(title)[0] or "").split("/")[0], "file")
    return KIND_LABEL.get(kind, "audio" if kind == "audio" else "file")


def ask_link(chat, target, items):
    """Anh / video / file cua Muse khong gui duoc ve Telegram: nho Muse gui link tai tam (toi da 48 gio) cho tung file.
    items: [(loai, tieu de, ly do)]. Xep vao worker cua profile (giu thu tu, khong chan relay). Bo cac file vua hoi
    trong ASK_LINK_GAP. Tra ve so file da nho."""
    now = time.time()

    def pick(state):
        asked = [x for x in state.setdefault("asked_links", {}).get(chat["key"], [])
                 if now - x.get("t", 0) < ASK_LINK_GAP]
        known = {x.get("title") for x in asked}
        fresh = [it for it in items if it[1] not in known]
        asked += [{"title": it[1], "t": now} for it in fresh]
        state["asked_links"][chat["key"]] = asked[-ASK_LINK_KEEP:]
        return fresh
    fresh = update_state(pick)
    if fresh:
        lines = "\n".join(f'- {label.capitalize()} "{title}" ({why})' for label, title, why in fresh)
        put_job({"kind": "ask", "chat": chat, "target": target, "text": ASK_LINK.format(lines=lines)})
    else:
        logger.info(f"{chat['key']}: da nho Muse gui link cac file nay roi, khong hoi lai")
    return len(fresh)


_video_save_cache = {"mtime": None, "dir": None}


def video_save_dir():
    """Thu muc goc luu video Muse (MUSE_SAVE_VIDEOS / MUSE_SAVE_VIDEO_DIR trong .env), None neu dang tat."""
    try:
        mtime = ENV_FILE.stat().st_mtime
    except OSError:
        mtime = 0
    if mtime != _video_save_cache["mtime"]:
        env = {}
        if mtime:
            try:
                env = dotenv_values(ENV_FILE)
            except Exception:
                logger.exception("Khong doc duoc .env (luu video)")
        on = (env.get("MUSE_SAVE_VIDEOS") or "1").strip().lower() not in ("0", "false", "no", "off")
        folder = (env.get("MUSE_SAVE_VIDEO_DIR") or "").strip() or VIDEO_SAVE_DEFAULT_DIR
        _video_save_cache.update(mtime=mtime, dir=Path(folder).expanduser() if on else None)
    return _video_save_cache["dir"]


def save_video(profile, data, name):
    """Luu 1 video Muse vao <thu muc luu video>/<profile>/<ten>. Cung ten cung dung luong (VD gui Telegram loi, thu
    lai) thi khong ghi lai. Tra ve duong dan, None neu tat hoac loi (loi khong chan viec gui Telegram)."""
    base = video_save_dir()
    if base is None:
        return None
    try:
        folder = base / re.sub(r'[\\/:*?"<>|]+', "_", profile).strip(". ")
        folder.mkdir(parents=True, exist_ok=True)
        stem, ext, n = Path(name).stem or "video", Path(name).suffix or ".mp4", 1
        path = folder / f"{stem}{ext}"
        while path.exists():
            if path.stat().st_size == len(data):
                logger.info(f"{profile}: video {path.name} da luu truoc do ({path})")
                return path
            n += 1
            path = folder / f"{stem}_{n}{ext}"
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        logger.info(f"{profile}: da luu video {path} ({len(data) // 1024} KB)")
        return path
    except OSError as e:
        logger.warning(f"{profile}: khong luu duoc video {name} vao {base}: {e}")
        return None


def send_media(target, kind, data, name, caption):
    chat_id, topic = target.chat.id, topic_of(target)
    if len(data) > TG_UPLOAD_LIMIT:
        raise TooLarge(f"{len(data) / 1048576:.0f} MB, vượt giới hạn 50 MB của Telegram")

    def upload(send, **kw):
        for attempt in range(MEDIA_UPLOAD_ATTEMPTS):
            try:
                return send(chat_id, types.InputFile(io.BytesIO(data), file_name=name), caption=caption,
                            message_thread_id=topic, timeout=MEDIA_UPLOAD_TIMEOUT, **kw)
            except requests.exceptions.ConnectionError as e:
                if attempt == MEDIA_UPLOAD_ATTEMPTS - 1:
                    raise
                logger.warning(f"Tai {name} len Telegram loi ({e}), thu lai")
    if kind == "video":
        return upload(bot.send_video, supports_streaming=True)
    if kind in ("image", "audio"):
        try:
            return upload(bot.send_photo) if kind == "image" else upload(bot.send_audio)
        except ApiTelegramException as e:
            logger.info(f"send {kind} {name}: {e}; gui dang file")
    return upload(bot.send_document)


def report_failed(chat, target, key, failed, text=""):
    """Bao cac anh / video / file khong gui duoc ve Telegram (1 tin) va nho Muse gui link tai tam (48 gio). text: chu
    cua tin Muse: file da co link ngay trong tin (quy tac LINK_RULE_TEXT: ten file + link) thi khong hoi lai."""
    linked = [it for it in failed if "http" in text and it[1] and it[1] in text]
    todo = [it for it in failed if it not in linked]
    asked = 0
    if chat and todo:
        try:
            asked = ask_link(chat, target, todo)
        except Exception:
            logger.exception(f"{key}: khong nho duoc Muse gui link")
    lines = "\n".join(f"• {html.escape(label.capitalize())} <b>{html.escape(title)}</b>: {html.escape(why)}"
                      + (" (link tải có trong tin của Muse ở trên)" if (label, title, why) in linked else "")
                      for label, title, why in failed)
    tail = ("" if not todo
            else "Bot đã nhờ Muse gửi link tải tạm (hạn tối đa 48 giờ), link sẽ hiện ở đây." if asked
            else "Bot đã nhờ Muse gửi link cho các file này trước đó." if chat
            else "Nhắn Muse gửi link tải nhé.")
    try:
        send_text(target, f"⚠️ <b>Không gửi được qua Telegram:</b>\n{lines}" + (f"\n{tail}" if tail else ""))
    except Exception:
        logger.exception("Khong bao duoc file gui loi")


def send_reply(fox, msg, target, key, chat=None):
    """Gui 1 tin cua Muse (chu + nut bam + anh/video/file) ve topic."""
    logger.info(f"Gui ve TG {key}: tin Muse {msg['id'][:30]} ({len(msg.get('text') or '')} ky tu, "
                f"{len(msg.get('media') or [])} anh/video/file): {(msg.get('text') or '')[:100]!r}")
    text, kb = msg.get("html") or html.escape(msg["text"]), None
    try:
        postkit_take_text(key, msg.get("text") or "")
    except Exception:
        logger.exception(f"{key}: loi doc bo dang bai")
    try:
        brandkit_take_text(key, msg.get("text") or "")
    except Exception:
        logger.exception(f"{key}: loi doc bo nhan dien kenh")
    # Doi Muse: lenh [[...]] cua chi huy / Muse dang lam viec duoc thuc hien va an khoi Telegram
    role, cmds = team_role(key), []
    if role == "worker" and muse_team.is_noise(msg["text"]):  # meo / quang cao tinh nang Muse tu gui: khong la ket qua
        logger.info(f"{key}: tin Muse tu gui (meo / gioi thieu), khong tinh vao bao cao viec")
        role = None
    # Muse dang lam viec cho doi: anh / video chua duoc chi huy duyet thi giu lai (gui chi huy cham), khong len Telegram
    hold = role == "worker" and not muse_team.config()["show_failed_media"]
    held_tid, held_kept, held_dropped = None, 0, {}
    if role:
        verbs = muse_team.CHIEF_VERBS if role == "chief" else muse_team.WORKER_VERBS
        cmds = muse_team.parse(msg["text"], verbs)
        if cmds:
            text = muse_team.strip(text, verbs)
        if role == "worker":
            team_capture_text(key, muse_team.strip(BUTTONS_RE.sub("", msg["text"]), verbs), cmds)
    found = BUTTONS_RE.search(msg["text"])
    labels = msg.get("choices") or []
    if found:
        labels = [x.strip() for x in found.group(1).split("|") if x.strip()]
        text = BUTTONS_RE.sub("", text).strip()
    if labels:
        text = text or "👇 Bạn chọn:"
        kb = types.InlineKeyboardMarkup()
        for i, label in enumerate(labels[:12]):
            kb.add(types.InlineKeyboardButton(label[:60], callback_data=f"mb:{i}"))
    try:
        if text:
            send_text(target, text, kb)
    finally:
        if role == "chief" and cmds:
            team_chief_commands(cmds)
    failed = []  # (loai, tieu de, ly do): khong gui duoc ve Telegram -> bao + nho Muse gui link tai tam
    profile = (chat or {}).get("profile") or key
    for a in msg["media"]:
        digest = saved = None
        kind = a["kind"] if a["kind"] in KIND_LABEL or a["kind"] == "audio" else "file"
        title = re.sub(r"^Open (?:generated|animated) (?:image|video)\s*", "", a["title"]).strip()
        base = re.sub(r'[\\/:*?"<>|\s]+', "_", title)[:60] or f"muse_{kind}"
        # Audio Muse khong co src: bot bam Play de Muse nap file (muse_sync.fetch_audio), can vi tri khung (pos)
        grab_audio = kind == "audio" and not a["src"] and a.get("pos") is not None
        if not a["src"] and a["kind"] != "file" and not grab_audio:
            logger.info(f"{key}: khong tai duoc {a['kind']} {title!r} (lost={a.get('lost')})")
            why = ("Muse báo file not found" if a["kind"] == "missing" and a.get("lost")
                   else f"Muse không nạp được file sau {MEDIA_MISSING_WAIT // 60} phút" if a["kind"] == "missing"
                   else "bot không tải được file từ trang Muse")
            failed.append((media_label(a["kind"], title), title or base, why))
            continue
        try:
            if a["kind"] == "file":
                content = muse_sync.fetch_file(fox, msg["id"], a.get("name") or "", a.get("title") or "")
                if content is None:
                    raise ValueError("khung xem file cua Muse khong co noi dung chu")
                data, mime = content.encode("utf-8"), a.get("mime") or "text/plain"
            elif grab_audio:
                data, mime = muse_sync.fetch_audio(fox, msg["id"], a["pos"], a.get("size") or 0,
                                                   a.get("path") or "", a.get("preview") or "")
                mime = mime or a.get("mime") or "audio/mpeg"
            else:
                limit = VIDEO_SAVE_LIMIT if kind == "video" and video_save_dir() else TG_UPLOAD_LIMIT
                data, mime = muse_sync.fetch_media(fox, a["src"], limit)
            if kind == "video" and not mime.startswith("video/"):
                raise ValueError(f"tai ve {mime or 'rong'} ({len(data)} byte), khong phai video")
            name = re.sub(r'[\\/:*?"<>|\s]+', "_", a.get("name") or "")
            if not name:  # tieu de da co duoi dung loai (VD "abc.mp4"): khong them lan nua ("abc.mp4.mp4")
                same = mimetypes.guess_type(base)[0] == (mime or "").split(";")[0].strip()
                name = base if same else base + (mimetypes.guess_extension(mime) or "")
            digest = hashlib.md5(data).hexdigest()
            if not claim_media(key, digest):
                logger.info(f"{key}: {kind} {name} ({len(data) // 1024} KB) trung file vua chuyen, bo qua")
                continue
            if kind == "video":
                saved = save_video(profile, data, name)
            if kind == "image":
                try:
                    postkit_take_image(key, name, data)
                except Exception:
                    logger.exception(f"{key}: loi luu cover bo dang bai")
                try:
                    brandkit_take_image(key, name, data)
                except Exception:
                    logger.exception(f"{key}: loi luu anh bo nhan dien kenh")
            if role == "worker":
                tid, why = team_capture_file(key, data, name)
                if hold and tid and why != "big":  # qua lon de dua chi huy: van gui len Telegram
                    held_tid = tid
                    if why:
                        held_dropped[why] = held_dropped.get(why, 0) + 1
                    else:
                        held_kept += 1
                    logger.info(f"{key}: giu {kind} {name} cho {tid} ({why or 'gui chi huy cham'}), khong gui TG")
                    continue
            send_media(target, kind, data, name, title[:1000] or None)
            logger.info(f"{key}: da gui {kind} {name} ({len(data) // 1024} KB) ve TG")
            del data
        except Exception as e:
            if digest and not isinstance(e, TooLarge):  # chua toi Telegram: ban trung sau (neu co) van duoc thu gui
                release_media(key, digest)
            linked = (a.get("src") or "").startswith("http")  # co link tai cong khai: gui link, khong can hoi Muse
            fetch_fail = isinstance(e, (muse_sync.FoxError, TimeoutError))
            why = (str(e) if isinstance(e, TooLarge)
                   else "bot tải file qua trình duyệt Muse bị quá thời gian" if fetch_fail
                   else "lỗi mạng khi tải lên Telegram" if isinstance(e, requests.RequestException)
                   else f"Telegram từ chối: {e.description}" if isinstance(e, ApiTelegramException)
                   else f"lỗi {type(e).__name__}")
            if saved:
                why += f" (đã lưu trên máy: {saved})"
            expected = isinstance(e, (TooLarge, requests.RequestException, ApiTelegramException)) or fetch_fail
            logger.warning(f"{key}: {kind} {title or base} khong gui duoc ({type(e).__name__}: {e})",
                           exc_info=not expected)  # loi la: giu traceback de sua
            if linked:
                try:
                    send_text(target, f"⚠️ {media_label(kind).capitalize()} <b>{html.escape(title or base)}</b>: "
                                      f"{html.escape(why)}. Tải tại: <a href=\"{html.escape(a['src'])}\">link</a>")
                except Exception:
                    logger.exception("Khong bao duoc loi gui file")
                continue
            failed.append((media_label(kind), title or base, why))
    if failed:
        report_failed(chat, target, key, failed, msg.get("text") or "")
    if held_tid:
        try:
            send_text(target, held_note(held_tid, held_kept, held_dropped))
        except Exception:
            logger.exception("Khong bao duoc anh / video bot giu lai")


def deliver_new(fox, chat, r, target, busy):
    """Gui ve Telegram cac tin moi cua Muse da viet xong. Tra ve True neu con tin dang viet / dang tai."""
    # Tin da chuyen (ghi trong state) bo qua ngay: sau khi bot khoi dong lai r["seen"] rong, tin cu khong chu luc Muse
    # dang ban se lam vong nay dung cho mai, khong toi duoc tin moi phia sau.
    delivered = set((load_state().get("delivered") or {}).get(chat["key"], []))
    msgs = muse_sync.messages(fox)
    for i, msg in enumerate(msgs):
        if msg["role"] != "assistant" or msg["id"] in r["seen"]:
            continue
        if msg["id"] in delivered:
            r["seen"].add(msg["id"])
            continue
        # Muse doi khi bo lai 1 khung "dang viet" khong bao gio xong (Muse2 2026-11-06: khung rong treo 2 tieng, chan
        # moi tin phia sau). Muse da ranh va co tin moi hon phia sau -> khung do da chet, khong cho no nua.
        if msg["streaming"] and (busy or not any(m["role"] == "assistant" for m in msgs[i + 1:])):
            return True
        stuck = [a for a in msg["media"] if not a["src"] and a["kind"] in KIND_LABEL]
        unfound = any(a["kind"] == "missing" and not a.get("lost") for a in msg["media"])
        waited = time.time() - r["waiting"].setdefault(msg["id"], time.time()) if stuck or unfound else 0
        # O luoi chua hien (pending, xem muse_sync.MESSAGES_JS): cho toi MEDIA_MISSING_WAIT roi gui phan da co + bao thieu
        loading = bool(stuck) and not (all(a.get("pending") for a in stuck) and waited >= MEDIA_MISSING_WAIT)
        if loading or unfound and waited < MEDIA_MISSING_WAIT:
            if waited > MEDIA_RELOAD_SECONDS and time.time() - r["reloaded"] > MEDIA_RELOAD_GAP:
                logger.info(f"{chat['key']}: anh/video chua nap sau {waited:.0f}s, tai lai trang")
                r["reloaded"] = time.time()
                muse_sync.reload_chat(fox, chat["url"])
            return True
        if not msg["text"] and not msg["media"] and not msg.get("choices"):
            if busy:
                return True
            # Tin chua render (ao hoa ngoai vung nhin, VD the Space): cuon toi no, vong sau doc lai
            if msg.get("unrendered") and \
                    time.time() - r["waiting"].setdefault(msg["id"], time.time()) < UNRENDERED_WAIT:
                muse_sync.scroll_to(fox, msg["id"])
                return True
            r["seen"].add(msg["id"])
            continue
        r["seen"].add(msg["id"])
        if not claim(chat["key"], msg["id"]):
            continue
        try:
            send_reply(fox, msg, target, chat["key"], chat)
            activity_moved(chat["key"])
        except Exception as e:
            if "thread not found" in str(e).lower() and chat["tg"].rpartition("/")[2]:  # da xoa topic: bo map, tao lai
                forget_topic(chat["profile"], int(chat["tg"].rpartition("/")[2]))
                return False
            logger.exception(f"Khong chuyen duoc tin {msg['id']} ve Telegram")
    return False


def relay_loop(chat, r):
    start, since, busy_seen, idle, errors = time.time(), None, False, 0, 0
    fox, error = None, ""
    while True:
        time.sleep(RELAY_INTERVAL)
        now = time.time()
        with relay_lock:
            if r["since"] != since:
                since, busy_seen, idle = r["since"], False, 0
            target = r["targets"][-1]
        try:
            fox = fox or muse_sync.chat_browser(chat)
            st = muse_sync.status(fox)
            busy = st["busy"]
            pending = deliver_new(fox, chat, r, target, busy)
            show_activity(chat, target, st)
            watch_approval(chat, target, st)
            errors = 0
        except Exception as e:
            busy, pending, errors, error = None, True, errors + 1, f"{type(e).__name__}: {e}"
            logger.warning(f"Relay {chat['key']}: {error}")
        if busy:
            busy_seen, idle = True, 0
        elif busy is False and not pending:
            idle += 1
        done = idle >= RELAY_IDLE_POLLS and (busy_seen or now - since >= RELAY_START_GRACE)
        if done or errors >= RELAY_MAX_ERRORS or now - start >= RELAY_MAX_SECONDS:
            with relay_lock:
                if r["since"] != since:
                    continue
                relays.pop(chat["key"], None)
                targets = list(r["targets"])
            break
        send_action(target, st if errors == 0 else None)
    minutes = int((time.time() - start) // 60)
    logger.info(f"{chat['key']}: Muse {'xong' if done else 'chua xong'} sau {time.time() - start:.0f}s")
    # Xong luot: con dong trang thai (Muse lam viec nen, VD tai file len Drive) thi giu tin, watch cap nhat tiep
    if done and not (activity.get(chat["key"]) or {}).get("text_now"):
        clear_activity(chat["key"])
    for m in targets:
        if done:
            react(m, "👌")
        else:
            why = f"không đọc được trả lời của Muse ({error})" if errors else "Muse vẫn đang làm"
            safe_reply(m, f"⏳ {why} sau {minutes} phút, bot ngừng chờ. Câu trả lời đến sau vẫn sẽ được gửi về đây.")


# ---------- Muse dang lam gi: 1 tin trang thai / chat, sua tai cho ----------

def activity_text(st):
    """Noi dung tin trang thai (HTML) tu muse_sync.status, "" neu khong co dong trang thai."""
    line = " ".join(x for x in (st["icon"], st["status"]) if x)
    return f"⚙️ <b>{html.escape(st['name'] or 'Muse')}</b>: {html.escape(line)}" if st["status"] else ""


def _remember_activity(key, where):
    """Ghi (chat_id, message_id) tin trang thai vao state de bot khoi dong lai con xoa duoc (None = bo ghi)."""
    def put(state):
        saved = state.setdefault("activity_msgs", {})
        if where:
            saved[key] = list(where)
        else:
            saved.pop(key, None)
    try:
        update_state(put)
    except Exception:
        logger.exception("Khong ghi duoc tin trang thai vao state")


def _delete_activity_msg(chat_id, mid):
    try:
        bot.delete_message(chat_id, mid)
    except Exception as e:
        logger.debug(f"Khong xoa duoc tin trang thai {mid}: {e}")


def show_activity(chat, target, st):
    """Hien viec Muse dang lam (dong trang thai duoi ten agent tren muse.ai) trong topic cua chat: 1 tin, sua khi
    trang thai doi; Muse ranh va het trang thai thi xoa. Goi moi vong relay / watch (2 vong khong chay cung luc cho 1
    chat). Khong bao loi: tin trang thai chi de xem."""
    key, now, text = chat["key"], time.time(), activity_text(st)
    with activity_lock:
        a = activity.setdefault(key, {"mid": None, "chat_id": None, "topic": None, "text": "", "at": 0,
                                      "moved": False, "quiet": None})
        a["text_now"] = text
    if not text:
        if a["mid"] and not st["busy"]:
            a["quiet"] = a["quiet"] or now
            if now - a["quiet"] >= ACTIVITY_CLEAR_SECONDS:
                clear_activity(key)
        return
    a["quiet"] = None
    here = bool(a["mid"]) and a["chat_id"] == target.chat.id and a["topic"] == topic_of(target)
    if here and not a["moved"] and text == a["text"]:
        return
    if now - a["at"] < ACTIVITY_EDIT_GAP:
        return
    a["at"] = now
    try:
        if here and not a["moved"]:
            bot.edit_message_text(text, a["chat_id"], a["mid"], parse_mode="HTML")
        else:  # chua co tin / Muse vua tra loi (tin cu bi day len tren): gui tin moi o cuoi, xoa tin cu
            m = bot.send_message(target.chat.id, text, parse_mode="HTML", message_thread_id=topic_of(target),
                                 disable_notification=True)
            if a["mid"]:
                _delete_activity_msg(a["chat_id"], a["mid"])
            a.update(mid=m.message_id, chat_id=target.chat.id, topic=topic_of(target), moved=False)
            _remember_activity(key, (target.chat.id, m.message_id))
        a["text"] = text
    except ApiTelegramException as e:
        if "not modified" in str(e).lower():
            a["text"] = text
        elif "not found" in str(e).lower():  # tin trang thai bi xoa tay: lan sau gui lai
            a["mid"] = None
        else:
            logger.debug(f"{key}: khong cap nhat duoc tin trang thai: {e}")
    except Exception as e:
        logger.debug(f"{key}: khong cap nhat duoc tin trang thai: {e}")


# Dong "<bot> is typing..." cua Telegram chi nhan cac hanh dong co san (khong dat chu tuy y): chon hanh dong hop voi
# dong trang thai cua Muse (tieng Anh), khong khop thi "typing". Thu tu: khop truoc thang.
ACTION_RULES = [
    (re.compile(r"\bupload\w*\b.*\b(video|clip)s?\b|\b(video|clip)s?\b.*\bupload", re.I), "upload_video"),
    (re.compile(r"upload|download|drive|file|export|sav(e|ing)|zip", re.I), "upload_document"),
    (re.compile(r"video|clip|animat|scene|film|footage|render|finale|motion", re.I), "record_video"),
    (re.compile(r"image|photo|picture|portrait|thumbnail|illustrat|draw|sketch|poster|frame", re.I), "upload_photo"),
    (re.compile(r"audio|voice|music|song|sound|narrat|speech", re.I), "record_voice"),
]


def chat_action(st):
    """Hanh dong Telegram (sendChatAction) gan nhat voi viec Muse dang lam."""
    text = (st or {}).get("status") or ""
    return next((action for rx, action in ACTION_RULES if rx.search(text)), "typing")


def send_action(target, st):
    """Hien "<bot> is typing / sending photo / recording video..." trong topic (Telegram giu ~5 giay)."""
    try:
        bot.send_chat_action(target.chat.id, chat_action(st), message_thread_id=topic_of(target))
    except Exception as e:
        logger.debug(f"send_chat_action: {e}")


# ---------- Muse cho duyet ma bot khong tu bam Allow duoc: bao (co chuong) + nut Cho phep ----------
# Dong trang thai "Needs approval" thuong chi hien vai giay roi muse_auto tu bam Allow (Muse4 2026-11-10). Con hien
# qua APPROVAL_ALERT_SECONDS (tu duyet dang tat, profile ban qua lau, hoac nut duyet khac mau) thi bao nguoi dung.

def approval_text(a, done=False):
    name, ctx = html.escape(a["name"]), html.escape(a["ctx"] or "")
    if done:
        return f"✅ <b>{name}</b> đã hết chờ duyệt." + (f"\n<i>{ctx}</i>" if ctx else "")
    why = ("Tự bấm Allow đang <b>tắt</b> (gõ /allow_on để bật)." if not muse_auto.enabled()
           else "Bot chưa tự bấm Allow được.")
    return (f"🔐 <b>{name} đang chờ bạn duyệt</b>" + (f"\n<i>{ctx}</i>" if ctx else "")
            + f"\n{why} Bấm <b>Cho phép</b> bên dưới, hoặc duyệt trên web Muse.")


def watch_approval(chat, target, st):
    """Goi moi vong relay / watch: Muse chua het "Needs approval" sau APPROVAL_ALERT_SECONDS thi gui 1 tin co
    chuong + nut Cho phep; het cho duyet thi sua tin do thanh "da het cho duyet"."""
    key, now = chat["key"], time.time()
    waiting = bool(APPROVAL_RE.search(st["status"]))
    with activity_lock:
        a = approvals.get(key)
        if not waiting:
            approvals.pop(key, None)
        elif not a:
            a = approvals[key] = {"since": now, "mid": None, "chat_id": None, "ctx": "", "name": "", "profile": ""}
    if not waiting:
        if a and a["mid"]:
            try:
                bot.edit_message_text(approval_text(a, done=True), a["chat_id"], a["mid"], parse_mode="HTML",
                                      reply_markup=None)
            except Exception as e:
                logger.debug(f"{key}: khong sua duoc tin cho duyet: {e}")
        return
    if a["mid"] or now - a["since"] < APPROVAL_ALERT_SECONDS:
        return
    lock = muse_sync.lock_for(chat["profile"])
    if not lock.acquire(blocking=False):  # profile dang ban (gui tin, reset...): vong sau doc
        return
    try:
        ctx = muse_auto.approve_once(chat["profile"], click=False) or ""
    except Exception as e:
        logger.debug(f"{key}: khong doc duoc yeu cau duyet: {e}")
        ctx = ""
    finally:
        lock.release()
    a.update(ctx=ctx, name=st["name"] or chat["profile"], profile=chat["profile"])
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Cho phép", callback_data=APPROVE_DATA + chat["profile"]))
    try:
        m = bot.send_message(target.chat.id, approval_text(a), parse_mode="HTML", reply_markup=kb,
                             message_thread_id=topic_of(target))
        a.update(mid=m.message_id, chat_id=target.chat.id)
        logger.info(f"{key}: Muse cho duyet qua {APPROVAL_ALERT_SECONDS}s, da bao Telegram ({ctx[:150]})")
    except Exception as e:
        a["since"] = now  # gui loi: thu lai sau
        logger.warning(f"{key}: khong bao duoc Muse cho duyet: {e}")


def on_approve_button(c):
    """Nut Cho phep tren tin bao cho duyet: bam Allow tren Muse cua profile."""
    m, profile = c.message, c.data[len(APPROVE_DATA):]
    if not (is_admin(c.from_user) or m.chat.id == group_id()):
        bot.answer_callback_query(c.id, "Bạn không có quyền duyệt.")
        return
    bot.answer_callback_query(c.id, f"Đang bấm Allow trên {profile}...")

    def run():
        try:
            with muse_sync.lock_for(profile):
                ctx = muse_auto.approve_once(profile)
        except Exception as e:
            logger.warning(f"Nut Cho phep {profile}: {type(e).__name__}: {e}")
            ctx, error = None, f"{type(e).__name__}"
        else:
            error = ""
        if ctx:
            logger.info(f"Cho phep (Telegram) {profile}: {ctx}")
            with activity_lock:  # tin nay da xong: vong watch khong sua de len, yeu cau sau (neu co) bao tin moi
                for a in approvals.values():
                    if a["mid"] == m.message_id:
                        a.update(mid=None, since=time.time())
            text, kb = f"✅ Đã cho phép trên <b>{html.escape(profile)}</b>.\n<i>{html.escape(ctx)}</i>", None
        else:
            text = (f"⚠️ Không bấm được Allow trên <b>{html.escape(profile)}</b>"
                    + (f" (lỗi {html.escape(error)})" if error else
                       ": không thấy nút Allow (có thể đã được duyệt, hoặc yêu cầu dạng khác)")
                    + ". Mở web Muse để duyệt.")
            kb = m.reply_markup  # giu nut de bam lai
        try:
            bot.edit_message_text(text, m.chat.id, m.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.debug(f"Khong sua duoc tin cho duyet: {e}")
    spawn(run)


def activity_moved(key):
    """Bot vua chuyen 1 tin cua Muse vao topic: tin trang thai (neu con) se duoc gui lai o cuoi."""
    with activity_lock:
        if (activity.get(key) or {}).get("mid"):
            activity[key]["moved"] = True


def clear_activity(key):
    """Xoa tin trang thai cua chat key (Muse da xong)."""
    with activity_lock:
        a = activity.pop(key, None)
    if a and a["mid"]:
        _delete_activity_msg(a["chat_id"], a["mid"])
        _remember_activity(key, None)


def clear_stale_activity():
    """Luc khoi dong: xoa cac tin trang thai con sot tu lan chay truoc (bot tat giua chung)."""
    try:
        saved = load_state().get("activity_msgs") or {}
    except Exception:
        logger.exception("Khong doc duoc tin trang thai cu")
        return
    for chat_id, mid in saved.values():
        _delete_activity_msg(chat_id, mid)
    if saved:
        update_state(lambda state: state.pop("activity_msgs", None))


def claim_media(key, digest):
    """Ghi nhan file (md5 noi dung) sap chuyen ve Telegram tu chat key. False neu cung file vua chuyen trong
    MEDIA_DEDUP_SECONDS (Muse hien 1 file o 2 tin; relay va watch dung chung)."""
    def add(state):
        now = time.time()
        recent = [x for x in state.setdefault("sent_media", {}).get(key, [])
                  if now - x.get("t", 0) < MEDIA_DEDUP_SECONDS][-MEDIA_DEDUP_KEEP:]
        state["sent_media"][key] = recent
        if any(x.get("md5") == digest for x in recent):
            return False
        recent.append({"md5": digest, "t": now})
        return True
    return update_state(add)


def release_media(key, digest):
    """Bo ghi nhan claim_media khi gui loi (de ban trung sau do con co the gui)."""
    def drop(state):
        lst = (state.get("sent_media") or {}).get(key) or []
        state.setdefault("sent_media", {})[key] = [x for x in lst if x.get("md5") != digest]
    try:
        update_state(drop)
    except Exception:
        logger.exception("Khong bo duoc ghi nhan file gui loi")


def claim(key, mid):
    """Ghi nhan tin mid da chuyen ve Telegram. False neu da chuyen roi (relay va watch dung chung)."""
    def add(state):
        ids = state.setdefault("delivered", {}).setdefault(key, [])
        if mid in ids:
            return False
        ids.append(mid)
        del ids[:-DELIVERED_KEEP]
        return True
    return update_state(add)


# ---------- Muse -> Telegram (watch: moi topic) ----------

def tg_target(tg):
    chat_id, _, topic = tg.partition("/")
    return SimpleNamespace(chat=SimpleNamespace(id=int(chat_id)), message_thread_id=int(topic) if topic else None,
                           is_topic_message=bool(topic))


def watch_chat(chat, r, tabs):
    profile = chat["profile"]
    fox = muse_sync.FoxProfileBrowser(profile, log=logger.info)
    with muse_sync.lock_for(profile):
        if profile not in tabs:
            tabs[profile] = [t["url"] for t in fox.tabs()] if fox.profile_exists() and fox.is_running() else None
        if tabs[profile] is None:  # profile dang tat: khong tu mo; mo lai thi vong sau gui bu
            clear_activity(chat["key"])
            return
        if not any(muse_sync.same_url(u, chat["url"]) for u in tabs[profile]):
            fox.open_tab(chat["url"])
            tabs[profile].append(chat["url"])
        fox.tab = chat["url"]
    if chat["key"] not in load_state().get("watched", []):  # topic moi: tin dang co coi nhu da chuyen
        ids = [m["id"] for m in muse_sync.messages(fox) if m["role"] == "assistant"]

        def start(state):
            known = state.setdefault("delivered", {}).setdefault(chat["key"], [])
            known += [i for i in ids if i not in known]
            del known[:-DELIVERED_KEEP]
            state.setdefault("watched", []).append(chat["key"])
        update_state(start)
        r["seen"].update(ids)
        logger.info(f"Theo doi {chat['key']} -> topic {chat['tg']}")
        return
    st = muse_sync.status(fox)
    target = tg_target(chat["tg"])
    deliver_new(fox, chat, r, target, st["busy"])
    show_activity(chat, target, st)
    watch_approval(chat, target, st)
    if st["status"] or st["busy"]:  # Muse dang lam (ke ca viec nen, khong qua relay): hien "is ..." trong topic
        send_action(target, st)


def watch_loop():
    runs, errors, hung, active = {}, {}, {}, {}
    with ThreadPoolExecutor(max_workers=WATCH_WORKERS, thread_name_prefix="muse-watch") as pool:
        while True:
            time.sleep(WATCH_INTERVAL)
            for key, (chat, future) in list(active.items()):
                if not future.done():
                    continue
                active.pop(key)
                r = runs[key]
                try:
                    future.result()
                    errors.pop(key, None)
                    hung.pop(chat["profile"], None)
                except Exception as e:
                    r["retry"] = time.time() + WATCH_RETRY_SECONDS
                    error = f"{type(e).__name__}: {e}"
                    if errors.get(key) != error:
                        logger.warning(f"Theo doi {key}: {error}")
                    errors[key] = error
                    if is_hang(e):
                        since = hung.setdefault(chat["profile"], time.time())
                        if time.time() - since >= WATCH_HANG_SECONDS and muse_sync.can_restart(chat["profile"]):
                            hung.pop(chat["profile"], None)
                            recover(chat["profile"], error)

            chats = mapped_chats()
            if not chats:
                continue
            keys = {c["key"] for c in chats}
            if any(k not in keys for k in load_state().get("watched", [])):
                update_state(lambda state: state.__setitem__("watched", [k for k in state["watched"] if k in keys]))
            for chat in chats:
                key = chat["key"]
                with relay_lock:
                    if key in relays:
                        continue
                if key in active:
                    continue
                r = runs.setdefault(key, {"seen": set(), "waiting": {}, "reloaded": 0, "retry": 0})
                if time.time() < r["retry"]:
                    continue
                active[key] = (chat, pool.submit(run_in_team, chat["team"], watch_chat, chat, r, {}))


def run_in_team(tid, fn, *args):
    with muse_team.in_team(tid):
        return fn(*args)


def is_hang(e):
    text = str(e).lower()
    return isinstance(e, muse_sync.FoxError) and (e.status == 504 or "timeout" in text or "timed out" in text)


def recover(profile, why):
    try:
        with muse_sync.lock_for(profile):
            muse_sync.restart_profile(profile, why)
        notify(f"🔄 Trình duyệt của profile {profile} bị treo, bot đã tự khởi động lại.")
    except Exception as e:
        logger.exception(f"Khong khoi dong lai duoc {profile}")
        notify(f"⚠️ Trình duyệt của profile {profile} bị treo, khởi động lại lỗi: {type(e).__name__}: {e}")


# ---------- tu tao topic cho profile + canh bao IP Viet Nam ----------

def forget_topic(profile, topic=None):
    """Bo map profile -> topic. topic: chi bo neu profile van map voi topic nay (luong cu gui vao topic da bi thay
    sau khi reset thi khong duoc xoa map topic moi)."""
    def drop(state):
        mapped = (state.get("topics") or {}).get(profile)
        if mapped is None or (topic is not None and int(mapped) != topic):
            return False
        state["topics"].pop(profile)
        state["watched"] = [k for k in state.get("watched", []) if k != profile]
        return True
    if update_state(drop):
        logger.info(f"Topic cua {profile} khong con, se tao lai")


# ---------- gan topic <-> profile thu cong (/gan) ----------

def topic_name(m):
    """Ten topic chua tin m (lay tu tin he thong "tao topic" ma Telegram gan vao reply_to_message), None neu khong
    biet (tin la reply 1 tin khac, hoac topic da doi ten sau khi tao)."""
    ref = getattr(m, "reply_to_message", None)
    created = getattr(ref, "forum_topic_created", None) if ref else None
    return created.name if created else None


def link_topic(profile, topic):
    """Gan topic cho profile: bo map cu cua profile va cua topic (1 profile - 1 topic). Tin Muse dang co coi nhu da
    chuyen (watch_chat bat dau lai). Tra ve (topic cu cua profile, profile cu cua topic)."""
    def change(state):
        mapped = state.setdefault("topics", {})
        old_topic = mapped.get(profile)
        old_profile = next((p for p, t in mapped.items() if int(t) == topic and p != profile), None)
        if old_profile:
            mapped.pop(old_profile)
        mapped[profile] = topic
        state["watched"] = [k for k in state.get("watched", []) if k not in (profile, old_profile)]
        return old_topic, old_profile
    old = update_state(change)
    logger.info(f"Gan thu cong {profile} -> topic {topic} (topic cu {old[0]}, profile cu cua topic {old[1]})")
    return old


def do_link(chat_id, topic, profile):
    old_topic, old_profile = link_topic(profile, topic)
    p = html.escape(profile)
    notes = []
    if old_topic and old_topic != topic:
        notes.append(f"Topic cũ của {p} không còn nhận tin của Muse.")
    if old_profile:
        notes.append(f"Topic này không còn gắn với profile {html.escape(old_profile)}; bot sẽ tạo topic mới cho "
                     f"{html.escape(old_profile)} khi profile đó mở và đăng nhập Muse.")
    bot.send_message(chat_id, f"🔗 <b>Đã gán topic này với profile {p}.</b>\nNhắn tin vào đây để làm việc với Muse của "
                              f"profile {p}." + ("\n" + "\n".join(notes) if notes else ""),
                     parse_mode="HTML", message_thread_id=topic)
    spawn(check_ip, profile, topic)
    queue_name_agent(profile, topic)


def choose_profile(m, topic, profiles, why):
    mapped = topics()
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for p in profiles:
        if len(f"{LINK_DATA}{p}".encode()) > 64:  # gioi han callback_data
            continue
        mark = "✅ " if mapped.get(p) == topic else "🔗 " if p in mapped else ""
        buttons.append(types.InlineKeyboardButton(f"{mark}{p}", callback_data=f"{LINK_DATA}{p}"))
    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton("Huỷ", callback_data=LINK_DATA))
    bot.send_message(m.chat.id, f"{why}\nChọn profile để gán với topic này:\n<i>✅ đang gán với topic này · 🔗 đã có "
                                f"topic khác (chọn thì chuyển sang topic này)</i>",
                     parse_mode="HTML", reply_markup=kb, message_thread_id=topic)


def on_link_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới gán được topic.")
        return
    try:
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
    except Exception:
        logger.debug("Khong go duoc nut gan topic", exc_info=True)
    profile, topic = c.data[len(LINK_DATA):], topic_of(m)
    if not profile:
        bot.answer_callback_query(c.id, "Đã huỷ.")
        return
    if m.chat.id != group_id() or topic is None:
        bot.answer_callback_query(c.id, "Nhóm này không còn gắn với bot.")
        return
    if profile not in muse_sync.fox_profiles():
        bot.answer_callback_query(c.id, f"Profile {profile} không còn trong FoxProfile.")
        return
    bot.answer_callback_query(c.id, f"Đã gán {profile}")
    do_link(m.chat.id, topic, profile)


# ---------- /tach: tach 1 Muse thanh vien khoi doi ----------
# Bot luu qua API dashboard (POST /settings/muse-team/detach): Muse vao "excluded", bo vai tro + thiet lap doi, ghi
# "detached" -> team_detach huy viec dang mo + nhan Muse bo boi canh doi; wipe thi xoa du lieu Muse (reset_targets).

def detach_check(profile):
    """Loi (HTML) neu khong tach duoc profile khoi doi, None neu duoc."""
    chief, workers = team_reset_people()
    p = html.escape(profile)
    if not chief:
        return "Đội Muse đang ở chế độ Độc lập, không có đội để tách Muse ra."
    if profile == chief:
        return (f"<b>{p}</b> là chỉ huy, không tách được. Đổi chỉ huy trên dashboard FoxProfile → Đội Muse trước, "
                f"hoặc chuyển đội sang Độc lập.")
    if profile not in workers:
        return f"<b>{p}</b> không ở trong đội. Thành viên: {html.escape(', '.join(workers)) or '—'}."
    if len(workers) == 1:
        return (f"<b>{p}</b> là thành viên cuối cùng của đội. Muốn bỏ đội thì chuyển sang <b>Độc lập</b> trên "
                f"dashboard FoxProfile → Đội Muse.")
    if len(f"{DETACH_DATA}ask:{profile}".encode()) > 64:  # gioi han callback_data cua Telegram
        return "Tên profile quá dài, bot không tạo được nút xác nhận. Tách Muse này trên dashboard FoxProfile."
    return None


def ask_detach(m, profile):
    """Buoc 1: canh bao + chon tach co xoa du lieu Muse hay giu."""
    chief, _ = team_reset_people()
    p = html.escape(profile)
    tasks = [t["id"] for t in (load_state().get("tasks") or {}).values()
             if t["to"] == profile and t["status"] in muse_team.OPEN_STATUSES]
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("✂️ Tách + xoá dữ liệu Muse", callback_data=f"{DETACH_DATA}w:{profile}"),
           types.InlineKeyboardButton("✂️ Tách, giữ dữ liệu Muse", callback_data=f"{DETACH_DATA}k:{profile}"),
           types.InlineKeyboardButton("Huỷ", callback_data=f"{DETACH_DATA}no"))
    bot.send_message(m.chat.id,
                     f"✂️ <b>Tách {p} khỏi đội Muse?</b>\n\nChỉ huy <b>{html.escape(chief)}</b> không giao việc cho "
                     f"{p} nữa (bot giới thiệu lại đội cho chỉ huy); vai trò và ngữ cảnh đội của {p} bị bỏ"
                     + (f"; <b>huỷ các việc đang mở</b>: {', '.join(tasks)}" if tasks else "") + ".\n\n"
                     f"• <b>Tách + xoá dữ liệu Muse</b>: xoá vĩnh viễn chat, file, artifact của {p} và tin trong topic "
                     f"(bot tạo lại topic), để Muse không còn nhớ gì của đội. <b>Không hoàn tác.</b>\n"
                     f"• <b>Tách, giữ dữ liệu</b>: bot nhắn {p} bỏ bối cảnh đội khỏi bộ nhớ dài hạn.\n\n"
                     f"Cho vào đội lại: dashboard FoxProfile → Đội Muse → tick lại {p}.",
                     parse_mode="HTML", reply_markup=kb, message_thread_id=topic_of(m))


def on_detach_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới tách được Muse khỏi đội.")
        return
    action, _, profile = c.data[len(DETACH_DATA):].partition(":")
    if profile and m.chat.type == "private":
        muse_team.TEAM.set(team_of_profile(profile))  # chi trong lan bam nay (teamed dat lai sau)

    def done(text):
        try:
            bot.edit_message_text(text, m.chat.id, m.message_id, parse_mode="HTML", reply_markup=None)
        except Exception:
            logger.debug("Khong sua duoc tin tach Muse", exc_info=True)
    if action == "no":
        bot.answer_callback_query(c.id, "Đã huỷ.")
        done("Đã huỷ tách Muse khỏi đội.")
        return
    err = detach_check(profile)
    if err:
        bot.answer_callback_query(c.id, "Không tách được.")
        done("⚠️ " + err)
        return
    if action == "ask":
        bot.answer_callback_query(c.id)
        done(f"✂️ Tách {html.escape(profile)}:")
        ask_detach(m, profile)
        return
    wipe = action == "w"
    try:
        fox_api("POST", "/settings/muse-team/detach", json={"profile": profile, "wipe": wipe}, params=team_param())
    except Exception as e:
        logger.exception("Doi Muse: loi tach Muse tu Telegram")
        bot.answer_callback_query(c.id, "Lỗi, chưa tách.")
        done(f"❌ Chưa tách {html.escape(profile)}: {html.escape(str(e))}")
        return
    logger.warning(f"Doi Muse: tach {profile} tu Telegram (xoa du lieu: {wipe})")
    bot.answer_callback_query(c.id, "Đã tách.")
    done(f"✂️ <b>Đã lệnh tách {html.escape(profile)} khỏi đội.</b> Trong ~{TEAM_LOOP_SECONDS}s bot huỷ các việc đang "
         f"mở của Muse này" + (", xoá dữ liệu Muse (tạo lại topic)" if wipe else ", nhắn Muse bỏ bối cảnh đội")
         + " và giới thiệu lại đội cho chỉ huy (báo ở General).")


# ---------- reset Muse cua 1 profile ----------

def ask_reset(m, profile):
    """Buoc 1: canh bao + nut Tiep tuc / Huy."""
    data = f"{RESET_DATA}go:{profile}"
    if len(data.encode()) > 64:  # gioi han callback_data cua Telegram
        bot.reply_to(m, "Tên profile quá dài, bot không tạo được nút xác nhận. Đổi tên profile ngắn hơn rồi thử lại.")
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"🗑 Xoá Muse của {profile}", callback_data=data),
           types.InlineKeyboardButton("Huỷ", callback_data=f"{RESET_DATA}no"))
    p = html.escape(profile)
    bot.send_message(m.chat.id, f"⚠️ <b>Reset Muse của profile {p}?</b>\n\nThao tác này <b>xoá vĩnh viễn toàn bộ dữ liệu "
                                f"Muse</b> của profile: lịch sử chat, file, artifact và các task đang chạy. Toàn bộ tin "
                                f"nhắn trong topic <b>{p}</b> cũng bị xoá (bot tạo lại topic mới cùng tên). Xong bot đặt "
                                f"tên agent Muse là <b>{p}</b>.\n\n<b>Không thể hoàn tác.</b>",
                     parse_mode="HTML", reply_markup=kb, message_thread_id=topic_of(m))


def on_reset_button(c):
    """Buoc 2: bam nut xac nhan -> xep viec reset vao hang doi cua profile (bot tu doc ten agent tren Muse)."""
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới reset được Muse.")
        return
    try:
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
    except Exception:
        logger.debug("Khong go duoc nut reset", exc_info=True)
    action = c.data[len(RESET_DATA):]
    if action == "no":
        bot.answer_callback_query(c.id, "Đã huỷ.")
        bot.send_message(m.chat.id, "Đã huỷ reset.", message_thread_id=topic_of(m))
        return
    profile = action.removeprefix("go:")
    if profile not in muse_sync.fox_profiles():
        bot.answer_callback_query(c.id, f"Profile {profile} không còn trong FoxProfile.")
        return
    bot.answer_callback_query(c.id, f"Đang reset Muse của {profile}...")
    bot.send_message(m.chat.id, f"⏳ Đang reset Muse của profile {html.escape(profile)}... (có thể mất vài phút)",
                     parse_mode="HTML", message_thread_id=topic_of(m))
    put_job({"kind": "reset", "m": m, "chat": {"key": profile, "profile": profile}, "profile": profile})


# ---------- /reset o muc General (chi huy): reset ca doi roi thiet lap lai theo mau ngu canh chu chon ----------
# Mau ngu canh nam o dashboard FoxProfile (foxprofile/repo/src/core/muse_team.py TEMPLATES). Bot doc / luu qua API
# /settings/muse-team (dung duong dashboard dung) voi reset_data: team_tick thay reset_id moi -> team_start_reset nhu
# khi chu luu tren dashboard: xoa du lieu Muse chi huy + ca doi, xong gui lai ngon ngu + ngu canh moi, gioi thieu doi.

def team_param():
    """?team=<ma doi dang xu ly> cho API /settings/muse-team cua dashboard."""
    return {"team": muse_team.current_team()}


def fox_api(method, path, **kw):
    base = os.environ.get("FOXPROFILE_URL", "http://127.0.0.1:8090").rstrip("/")
    token = os.environ.get("FOXPROFILE_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.request(method, f"{base}/api/v1{path}", headers=headers, timeout=30, **kw)
    except requests.RequestException as e:
        raise RuntimeError(f"không kết nối được FoxProfile ({base}): {type(e).__name__}") from e
    if not r.ok:
        try:
            detail = r.json().get("detail") or r.text
        except ValueError:
            detail = r.text
        raise RuntimeError(f"FoxProfile báo lỗi {r.status_code}: {str(detail)[:300]}")
    return r.json()


def team_templates():
    """(cai dat doi tren dashboard, cac mau ngu canh, id mau chi huy dang dung hoac "")."""
    team = fox_api("GET", "/settings/muse-team", params=team_param())
    tps = [t for t in team.get("templates") or []
           if t.get("id") and len(f"{TEAM_RESET_DATA}go:t:{t['id']}".encode()) <= 64]  # gioi han callback_data
    chief_ctx = ((team.get("setup") or {}).get(team.get("chief")) or {}).get("context", "").strip()
    current = next((t["id"] for t in tps if chief_ctx and chief_ctx == (t.get("chief") or "").strip()), "")
    return team, tps, current


def team_reset_people():
    """(chi huy, thanh vien) theo cai dat doi; khong o che do chi huy: ("", [])."""
    cfg = muse_team.config()
    chief = cfg["chief"] if cfg["mode"] == "chief" else ""
    return chief, (team_workers(chief) if chief else [])


def team_reset_busy():
    """Dot xoa du lieu doi dang chay / chua bat dau (dashboard hoac Telegram)."""
    cfg = muse_team.config()
    return "reset" in team_inflight or bool(cfg["reset_id"] and load_state().get("team_reset") != cfg["reset_id"])


def ask_team_reset(m):
    """Buoc 1: chon mau ngu canh cho doi sau khi xoa (hoac giu ngu canh dang co / chi reset chi huy)."""
    chief, workers = team_reset_people()
    try:
        _, tps, current = team_templates()
    except Exception as e:
        bot.reply_to(m, f"⚠️ Bot không đọc được mẫu ngữ cảnh từ FoxProfile: {e}")
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    for t in tps:
        kb.add(types.InlineKeyboardButton(("✅ " if t["id"] == current else "✨ ") + t["label"]
                                          + (" (đang dùng)" if t["id"] == current else ""),
                                          callback_data=f"{TEAM_RESET_DATA}t:{t['id']}"))
    kb.add(types.InlineKeyboardButton("📌 Giữ ngữ cảnh đang có", callback_data=f"{TEAM_RESET_DATA}keep"))
    kb.row(types.InlineKeyboardButton(f"Chỉ reset {chief}"[:60], callback_data=f"{TEAM_RESET_DATA}chief"),
           types.InlineKeyboardButton("Huỷ", callback_data=f"{TEAM_RESET_DATA}no"))
    people = html.escape(", ".join(workers)) or "— (chưa có thành viên)"
    bot.send_message(m.chat.id,
                     f"♻️ <b>Reset cả đội Muse?</b>\nChỉ huy <b>{html.escape(chief)}</b> + thành viên: {people}.\n\n"
                     f"Bot xoá dữ liệu Muse (chat, file, artifact, task) của tất cả, rồi tự gửi lại <b>ngữ cảnh</b> "
                     f"(bộ nhớ dài hạn) cho từng Muse và giới thiệu lại đội cho chỉ huy.\n\n"
                     f"<b>Chọn ngữ cảnh</b> cho đội sau khi reset:",
                     parse_mode="HTML", reply_markup=kb, message_thread_id=topic_of(m))


def apply_team_reset(choice):
    """Luu cai dat doi qua API dashboard: mau (choice "t:<id>") dien ngu canh chi huy / thanh vien (+ vai tro con
    trong), dat reset_data cho chi huy + ca doi; doi mau thi reset_team_data (bo viec, video mau, kich ban, cat bo
    nhan vat). "keep": giu ngu canh, chi xoa du lieu Muse. Tra ve ten ngu canh."""
    team, tps, _ = team_templates()
    chief, workers = team_reset_people()
    if not chief or team.get("mode") != "chief" or team.get("chief") != chief:
        raise RuntimeError("đội không còn ở chế độ có chỉ huy")
    setup = {p: dict(v) for p, v in (team.get("setup") or {}).items()}
    roles = dict(team.get("roles") or {})
    label, full, skill_id = "ngữ cảnh đang có", False, ""
    if choice.startswith("t:"):
        tp = next((t for t in tps if t["id"] == choice[2:]), None)
        if not tp:
            raise RuntimeError(f"không còn mẫu {choice[2:]} trên dashboard")
        for p, text in [(chief, tp["chief"])] + [(w, tp["member"]) for w in workers]:
            item = setup.setdefault(p, {})
            item["context"], item["lang"] = text, item.get("lang") or "vi"
        for w in workers:
            if tp.get("member_role") and not roles.get(w, "").strip():
                roles[w] = tp["member_role"]
        label, full, skill_id = tp["label"], True, tp["id"]
    fox_api("PUT", "/settings/muse-team", params=team_param(), json={
        "mode": "chief", "chief": chief, "approval": team.get("approval") or "manual", "roles": roles,
        "excluded": team.get("excluded") or [], "setup": setup,
        "reset_data": True, "reset_targets": [], "reset_team_data": full, **({"skill": skill_id} if skill_id else {})})
    logger.warning(f"Doi Muse: reset doi tu Telegram ({chief} + {workers}), ngu canh: {label}, full={full}")
    return label, full


def on_team_reset_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới reset được Muse.")
        return
    action = c.data[len(TEAM_RESET_DATA):]
    chief, workers = team_reset_people()

    def done(text, kb=None):
        try:
            bot.edit_message_text(text, m.chat.id, m.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception:
            logger.debug("Khong sua duoc tin reset doi", exc_info=True)
    if action == "no":
        bot.answer_callback_query(c.id, "Đã huỷ.")
        done("Đã huỷ reset đội.")
        return
    if not chief:
        bot.answer_callback_query(c.id, "Đội không còn ở chế độ có chỉ huy.")
        done("⚠️ Đội không còn ở chế độ có chỉ huy, không reset.")
        return
    if action == "chief":
        bot.answer_callback_query(c.id)
        done(f"Chỉ reset chỉ huy {html.escape(chief)}:")
        ask_reset(m, chief)
        return
    if action.startswith("go:"):
        choice = action[3:]
        if team_reset_busy():
            bot.answer_callback_query(c.id, "Đang có đợt xoá dữ liệu đội chưa xong.")
            done("⏳ Đang có đợt xoá dữ liệu đội chưa xong, bot không reset thêm. Đợi báo xong rồi gõ lại /reset.")
            return
        try:
            label, full = apply_team_reset(choice)
        except Exception as e:
            logger.exception("Doi Muse: loi reset doi tu Telegram")
            bot.answer_callback_query(c.id, "Lỗi, chưa reset.")
            done(f"❌ Chưa reset đội: {html.escape(str(e))}")
            return
        bot.answer_callback_query(c.id, "Đang reset cả đội...")
        done(f"♻️ <b>Đã lệnh reset cả đội</b> ({html.escape(', '.join([chief] + workers))}), ngữ cảnh: "
             f"<b>{html.escape(label)}</b>.\nTrong ~{TEAM_LOOP_SECONDS}s bot bắt đầu xoá dữ liệu Muse; xong bot tự gửi "
             f"ngữ cảnh cho từng Muse và giới thiệu lại đội cho chỉ huy (báo ở đây)."
             + ("\nĐổi mẫu: việc, video mẫu, kịch bản chốt bị bỏ; bộ nhân vật khoá cũ cất vào thư mục lưu trữ."
                if full else ""))
        return
    # buoc 2: xac nhan lua chon
    try:
        _, tps, _ = team_templates()
    except Exception as e:
        bot.answer_callback_query(c.id, "Lỗi đọc mẫu ngữ cảnh.")
        done(f"⚠️ Bot không đọc được mẫu ngữ cảnh từ FoxProfile: {html.escape(str(e))}")
        return
    tp = next((t for t in tps if action == f"t:{t['id']}"), None)
    if action != "keep" and not tp:
        bot.answer_callback_query(c.id, "Mẫu này không còn.")
        return
    bot.answer_callback_query(c.id)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🗑 Xoá và thiết lập lại", callback_data=f"{TEAM_RESET_DATA}go:{action}"),
           types.InlineKeyboardButton("Huỷ", callback_data=f"{TEAM_RESET_DATA}no"))
    who = html.escape(", ".join([chief] + workers))
    what = (f"Ngữ cảnh mới: <b>{html.escape(tp['label'])}</b> (chỉ huy nhận phần chỉ huy, mỗi thành viên nhận phần "
            f"thành viên). Bot cũng <b>bỏ mọi việc, video mẫu, kịch bản chốt</b> và cất bộ nhân vật khoá cũ vào thư mục "
            f"lưu trữ." if tp else
            "Giữ <b>ngữ cảnh đang có</b> của từng Muse. Việc đang mở bị bỏ; video mẫu, kịch bản chốt, bộ nhân vật khoá "
            "được giữ.")
    done(f"⚠️ <b>Xác nhận reset cả đội</b>\nXoá <b>vĩnh viễn</b> dữ liệu Muse của: {who} (kèm tin trong topic của "
         f"thành viên).\n{what}\n\n<b>Không thể hoàn tác.</b>", kb)


def name_agent(profile, topic, only_default=True):
    """Dat ten agent Muse = ten profile ("Change your name to <profile>"), tra loi cua Muse chuyen vao topic.
    only_default: chi doi khi agent dang mang ten mac dinh (khong ro la agent cua profile nao). Chay trong hang doi
    cua profile (giu thu tu voi tin khac)."""
    try:
        name = muse_sync.agent_name(profile) if only_default else None
    except Exception as e:
        logger.warning(f"Khong doc duoc ten agent {profile}: {type(e).__name__}: {e}")
        return
    if only_default and (name is None or name.casefold() != muse_sync.DEFAULT_AGENT_NAME.casefold()
                         or name == profile):
        logger.info(f"Ten agent {profile}: {name!r} -- khong doi")
        return
    chat = chat_of(profile, topic) if topic else {"profile": profile, "url": muse_sync.MUSE_URL, "key": profile}
    seen = set()
    ok, result = muse_sync.send(chat, muse_sync.rename_agent_text(profile), seen=seen)
    logger.info(f"Doi ten agent {profile} ({name!r} -> {profile}): {result}")
    if ok and topic:
        relay(chat, tg_target(chat["tg"]), seen)


def queue_name_agent(profile, topic):
    """Xep viec dat ten agent (neu dang ten mac dinh) vao hang doi cua profile."""
    put_job({"kind": "name", "chat": {"key": profile, "profile": profile}, "profile": profile, "topic": topic})


def run_reset(job):
    """Reset Muse tren web (muse_sync.reset_muse), xong thi xoa topic cu, tao topic moi cung ten va dat ten agent =
    ten profile."""
    profile, m = job["profile"], job["m"]
    try:
        ok, result = muse_sync.reset_muse(profile)
    except Exception as e:
        ok, result = False, f"lỗi {type(e).__name__}: {e}"
    logger.warning(f"Reset Muse {profile}: ok={ok} {result}")
    if not ok:
        react(m, "👎")
        safe_reply(m, f"❌ Chưa reset Muse của profile {profile}: {result}")
        return
    with stalled_lock:  # tin cu dang cho gui lai: Muse da xoa sach, khong gui nua
        stalled.pop(profile, None)
    old = topics().get(profile)
    new, note = reset_topic(profile)
    text = f"✅ {result}\n{note}"
    if m.chat.id == group_id() and topic_of(m) == old and new != old:  # tin yeu cau nam trong topic da xoa
        notify(f"✅ Reset Muse của profile {profile}: {result}\n{note}")
    else:
        react(m, "👌")
        safe_reply(m, text)
    name_agent(profile, new, only_default=False)  # vua reset: agent ve ten mac dinh, dat luon ten profile


def reset_topic(profile):
    """Xoa topic cua profile (xoa het tin trong do) va tao topic moi cung ten. Tra ve (topic moi, ghi chu)."""
    def clear_delivered(state):  # Muse da reset: tin moi cua Muse (ke ca loi chao) se duoc chuyen vao topic moi
        state.setdefault("delivered", {})[profile] = []
        (state.get("last_sent") or {}).pop(profile, None)  # doi soat khong gui lai tin cu vao Muse vua xoa sach
    shutil.rmtree(RESEND_DIR / profile, ignore_errors=True)
    forget_link_rule(profile)  # bo nho dai han cua Muse da xoa: gui lai quy tac gui link
    forget_postkit_rule(profile)  # va quy tac bo dang bai
    group, old = group_id(), topics().get(profile)
    if not group or old is None:
        update_state(clear_delivered)
        return None, "Profile này chưa có topic trong nhóm."
    try:
        bot.delete_forum_topic(group, old)
    except ApiTelegramException as e:
        update_state(clear_delivered)
        logger.warning(f"Khong xoa duoc topic {old} cua {profile}: {e}")
        return old, (f"⚠️ Bot không xoá được tin nhắn trong topic ({e.description}). Cấp cho bot quyền "
                     f"Xoá tin nhắn (Delete messages) trong nhóm, hoặc tự xoá topic: bot sẽ tạo lại topic mới.")
    try:
        new = bot.create_forum_topic(group, profile[:128]).message_thread_id
    except Exception as e:
        logger.warning(f"Da xoa topic {old} nhung khong tao duoc topic moi cho {profile}: {e}")
        forget_topic(profile, old)  # sync_topics se tao lai
        return None, "Đã xoá topic cũ. Bot sẽ tự tạo lại topic trong vài phút."

    def swap(state):
        state.setdefault("topics", {})[profile] = new
        clear_delivered(state)
    update_state(swap)
    logger.info(f"Reset {profile}: topic {old} -> {new}")
    bot.send_message(group, f"♻️ <b>Muse của profile {html.escape(profile)} đã được reset.</b>\nDữ liệu Muse và tin nhắn "
                            f"cũ trong topic đã được xoá. Nhắn tin vào topic này để bắt đầu lại.",
                     parse_mode="HTML", message_thread_id=new)
    return new, "Đã xoá topic cũ (cùng toàn bộ tin nhắn) và tạo topic mới cùng tên."


def check_ip(profile, topic=None, force=False):
    """Kiem tra IP profile dung vao Muse; IP Viet Nam thi canh bao trong topic va cho chu bot."""
    try:
        ip, country, is_vn = muse_sync.ip_check(profile)
    except Exception as e:
        logger.warning(f"Kiem tra IP {profile} loi: {type(e).__name__}: {e}")
        return None
    old = ip_results.get(profile)
    ip_results[profile] = (ip, country, is_vn)
    logger.info(f"IP {profile}: {ip} ({country}){' -- VIET NAM!' if is_vn else ''}")
    recent = time.time() - ip_warned.get(profile, 0) < 300  # tranh canh bao trung (khoi dong + tao topic cung luc)
    if is_vn and not recent and (force or not old or not old[2]):
        ip_warned[profile] = time.time()
        text = VN_WARNING.format(profile=html.escape(profile), ip=html.escape(ip), country=html.escape(country))
        logger.warning(plain(text))
        if topic and group_id():
            try:
                bot.send_message(group_id(), text, parse_mode="HTML", message_thread_id=topic)
            except Exception as e:
                logger.warning(f"Khong gui duoc canh bao IP vao topic {profile}: {e}")
        notify(text, parse_mode="HTML")
    return ip_results[profile]


def sync_topics():
    """Doi dang xu ly: profile thuoc nhom cua doi (muse_team.group_profiles), dang mo + da dang nhap Muse ma chua co
    topic: tao topic ten = ten profile. Profile da chuyen sang doi khac: bo topic o nhom nay (doi kia tao topic moi)."""
    group = group_id()
    if not group:
        return
    existing = muse_sync.fox_profiles()
    mapped = topics()
    for profile in [p for p in mapped if p not in existing]:  # profile da xoa khoi FoxProfile
        forget_topic(profile)
        notify(f"ℹ️ Profile {profile} không còn trong FoxProfile, bot ngừng đồng bộ topic của nó.")
    mine = set(muse_team.group_profiles(existing))
    for profile in [p for p in mapped if p in existing and p not in mine]:  # chu chuyen profile sang doi khac
        try:
            bot.send_message(group, f"➡️ <b>Profile {html.escape(profile)} đã chuyển sang đội khác</b> (dashboard "
                                    f"FoxProfile → Đội Muse). Topic này không còn nhận tin của Muse.",
                             parse_mode="HTML", message_thread_id=mapped[profile])
        except Exception as e:
            logger.debug(f"Khong bao duoc chuyen doi {profile}: {e}")
        forget_topic(profile)
        logger.info(f"Profile {profile} chuyen khoi doi {muse_team.current_team()}")
    mapped = topics()
    here = muse_team.current_team()
    ids = muse_team.team_ids()
    elsewhere = {p for tid, st in team_states().items() if tid != here and tid in ids for p in (st.get("topics") or {})}
    chief = muse_team.chief()
    for profile in existing:
        # Muse chi huy dung muc General, khong can topic rieng; topic o doi cu chua bo: doi vong sau
        if profile in mapped or profile == chief or profile not in mine or profile in elsewhere:
            continue
        try:
            if not muse_sync.muse_ready(profile):
                continue
        except Exception as e:
            logger.debug(f"Kiem tra dang nhap {profile}: {e}")
            continue
        topic = bot.create_forum_topic(group, profile[:128]).message_thread_id
        update_state(lambda state: state.setdefault("topics", {}).__setitem__(profile, topic))
        logger.info(f"Profile {profile} -> topic {topic}")
        bot.send_message(group, f"✅ <b>Profile {html.escape(profile)} đã kết nối Muse.</b>\n"
                                f"Nhắn tin, gửi ảnh / video / file vào topic này để làm việc với Muse của profile này. "
                                f"Câu trả lời của Muse (kể cả khi bạn gõ trên web) sẽ hiện ở đây.",
                         parse_mode="HTML", message_thread_id=topic)
        check_ip(profile, topic, force=True)
        queue_name_agent(profile, topic)


def check_update():
    """Bao chu bot 1 lan cho moi ban moi tren GitHub (FoxProfile kiem tra, xem GET /api/v1/update)."""
    try:
        info = muse_sync.FoxProfileBrowser("", log=logger.debug)._call("GET", "/update", timeout=60).json()
    except Exception as e:
        logger.debug(f"Kiem tra cap nhat loi: {e}")
        return
    remote = info.get("remote") or {}
    sha = remote.get("sha")
    if not info.get("available") or not sha or info.get("busy"):
        return
    if not update_state(lambda s: s.get("update_notified") != sha and s.update(update_notified=sha) is None):
        return
    changes = info.get("changes") or [remote.get("message", "")]
    lines = "\n".join(f"• {html.escape(c)}" for c in changes[:10] if c)
    notify(f"🆕 <b>Đã có phiên bản mới của Muse2Tele</b> ({html.escape(remote.get('date', '')[:10])})\n{lines}\n\n"
           f"Mở dashboard FoxProfile và bấm <b>Xem thay đổi &amp; cập nhật</b>. Dữ liệu (profile, .env, video, "
           f"cài đặt) được giữ nguyên; FoxProfile, bot và AutoPost sẽ tự khởi động lại.", parse_mode="HTML")


# ---------- doi soat dinh ky: tin cuoi tren Muse <-> Telegram ----------

RECONCILE_SECONDS = 30   # moi 30s, profile khong xu ly lenh nao thi doi soat
RECONCILE_GRACE = 45     # tin TG vua gui < 45s thi chua xet (Muse co the chua hien)
RECONCILE_RESEND_MAX = 2


def _idle(key):
    with profile_queues_lock:
        work = profile_queues.get(key)
    with relay_lock:
        relaying = key in relays
    with stalled_lock:
        waiting = key in stalled
    return key not in busy_keys and not (work and work.qsize()) and not relaying and not waiting


def _on_muse(msgs, ls):
    """Tin TG cuoi (last_sent) co tren Muse: cung chu, va co anh / video neu tin co. Tin chi co file: tin nguoi dung
    moi (khong co trong prior) kem anh / video."""
    want, media, prior = muse_sync._flat(ls.get("text"))[:60], ls.get("media"), set(ls.get("prior") or ())
    return any(m["role"] == "user" and not m.get("failed") and (m.get("attached") or not media)
               and (want in muse_sync._flat(m.get("text")) if want else m["id"] not in prior)
               for m in msgs)


def reconcile_chat(chat, runs):
    """(trang thai Muse->TG, trang thai TG->Muse) cua 1 profile; gui bu ben thieu."""
    key = chat["key"]
    fox = muse_sync.FoxProfileBrowser(chat["profile"], log=logger.debug)
    if not fox.profile_exists() or not fox.is_running():
        return "tat", "tat"
    fox.tab = chat["url"]
    msgs = muse_sync.messages(fox)
    state = load_state()
    # Muse -> Telegram: tin cuoi cua Muse (co noi dung, viet xong) da chuyen chua
    muse_tg = "-"
    done = [m for m in msgs if m["role"] == "assistant" and (m["text"] or m["media"]) and not m["streaming"]]
    if done:
        last = done[-1]
        if last["id"] in (state.get("delivered") or {}).get(key, []):
            muse_tg = "ok"
        else:
            muse_tg = "THIEU"
            logger.warning(f"Doi soat {key}: tin cuoi Muse {last['id'][:30]} chua co tren TG -> gui bu")
            r = runs.setdefault(key, {"seen": set(), "waiting": {}, "reloaded": 0, "retry": 0})
            deliver_new(fox, chat, r, tg_target(chat["tg"]), muse_sync.is_busy(fox))
    # Telegram -> Muse: tin cuoi ban gui da co tren Muse chua
    ls = (state.get("last_sent") or {}).get(key)
    files = [f for f in (ls or {}).get("files") or [] if Path(f).is_file()]
    # tin chi co file: chi xet duoc khi co anh / video (Muse hien trong bong tin) va biet cac tin co truoc khi gui
    checkable = ls and (ls.get("text") or (ls.get("media") and ls.get("prior")))
    if not checkable or ls.get("verified"):
        return muse_tg, "ok" if ls else "-"
    if time.time() - ls["at"] < RECONCILE_GRACE:
        return muse_tg, "cho"
    found = _on_muse(msgs, ls)
    if not found:  # trang co the dang o tab khac / tin tam: tai lai trang (du lieu that tren server) roi xem lai
        muse_sync.reload_chat(fox, chat["url"])
        found = _on_muse(muse_sync.messages(fox), ls)
    if found:
        update_state(lambda s: s["last_sent"][key].update(verified=True))
        logger.info(f"Doi soat {key}: tin TG {ls['mid']} da co tren Muse")
        return muse_tg, "ok"
    target = SimpleNamespace(chat=SimpleNamespace(id=ls["chat_id"]), message_thread_id=ls["topic"],
                             is_topic_message=bool(ls["topic"]))
    lost = len(ls.get("files") or []) - len(files)
    if ls.get("resends", 0) >= RECONCILE_RESEND_MAX or lost:  # mat file: gui lai chi co chu se sai y
        update_state(lambda s: s["last_sent"][key].update(verified=True))
        logger.error(f"Doi soat {key}: tin TG {ls['mid']} van khong co tren Muse sau {ls.get('resends', 0)} lan gui lai")
        what = f"{len(ls.get('files') or [])} file" if ls.get("files") else ""
        safe_reply(target, f"⚠️ Muse vẫn chưa nhận tin này sau {ls.get('resends', 0)} lần gửi lại, bạn gửi lại giúp"
                           + (f" (kèm {what}; video lớn thì thử nén nhỏ lại hoặc gửi link)" if what else "") + ": "
                           + (ls.get("text") or "")[:300])
        return muse_tg, "BO"
    logger.warning(f"Doi soat {key}: tin TG {ls['mid']} KHONG co tren Muse -> gui lai (lan {ls.get('resends', 0) + 1})"
                   + (f" kem {len(files)} file" if files else ""))
    seen = set()
    ok, result = muse_sync.send(chat, ls.get("text") or "", files, seen=seen)
    logger.info(f"Gui lai TG {ls['mid']} -> {key}: {result}")
    update_state(lambda s: s["last_sent"][key].update(resends=ls.get("resends", 0) + 1, at=time.time(),
                                                      prior=sorted(seen) if files else []))
    if ok:
        safe_reply(target, "🔁 Muse chưa nhận tin trước của bạn" + (f" (kèm {len(files)} file)" if files else "")
                   + ", bot đã gửi lại.")
        relay(chat, target, seen)
    return muse_tg, "GUI LAI" if ok else "LOI"


# ---------- quy tac mac dinh: Muse gui link tai tam sau moi file ----------
# muse.ai khong co cai dat "custom instructions" (Settings chi co General, Connectors, Permissions..., kiem tra
# 2026-11-10) nen bot gui quy tac vao bo nho dai han cua tung Muse: 1 lan khi Muse ranh, gui lai sau khi reset (reset
# xoa bo nho) hoac khi doi LINK_RULE_VERSION. Da gui: state "link_rule" {profile: phien ban}.
LINK_RULE_VERSION = "v2"  # v2 (2026-11-11): bo yeu cau "con han it nhat 3 ngay"
LINK_RULE_TEXT = ("Cập nhật bộ nhớ dài hạn (thiết lập cố định của chủ, áp dụng từ giờ cho mọi việc, thay cho thiết lập "
                  "gửi link tải trước đó): mỗi khi gửi ảnh, video, audio hay file cho chủ, ngay sau file hãy gửi kèm "
                  "link tải tạm thời cho từng file, mỗi link một dòng ghi rõ tên file (dạng https://...). Vẫn đính "
                  "kèm file như bình thường; link là bản dự phòng khi file không tải được qua Telegram. File nào không "
                  "tạo được link thì nói rõ file đó.\n\nTrả lời ngắn: xác nhận đã lưu.")
link_rule_inflight = set()  # profile da xep viec gui quy tac, chua chay xong


def link_rule_due(profile):
    return (load_state().get("link_rule") or {}).get(profile) != LINK_RULE_VERSION


def forget_link_rule(profile):
    update_state(lambda s: (s.get("link_rule") or {}).pop(profile, None))


def queue_link_rule(chat):
    """Goi tu vong doi soat (profile dang ranh): chua gui quy tac thi xep viec vao hang doi cua profile."""
    profile = chat["profile"]
    if profile in link_rule_inflight or not link_rule_due(profile):
        return
    link_rule_inflight.add(profile)
    put_job({"kind": "link_rule", "chat": chat, "team": chat.get("team")})


def run_link_rule(job):
    """Gui quy tac gui link vao Muse neu Muse dang ranh han (khong tra loi, khong viec nen, khong lam viec doi);
    chua ranh thi thoi, vong doi soat sau xep lai. Cau xac nhan cua Muse chuyen vao topic."""
    chat = job["chat"]
    profile = chat["profile"]
    try:
        if not link_rule_due(profile):
            return
        if any(t["to"] == profile and t["status"] in ("lam", "bao") for t in (load_state().get("tasks") or {}).values()):
            return  # dang lam viec doi: tin chen vao se lan vao bao cao viec
        st = muse_sync.status(muse_sync.chat_browser(chat))
        if st["busy"] or st["status"]:
            return
        seen = set()
        ok, result = muse_sync.send(chat, LINK_RULE_TEXT, seen=seen)
        logger.info(f"Quy tac gui link tai tam -> {profile}: {result}")
        if ok:
            update_state(lambda s: s.setdefault("link_rule", {}).__setitem__(profile, LINK_RULE_VERSION))
            relay(chat, tg_target(chat["tg"]), seen)
    finally:
        link_rule_inflight.discard(profile)


# ---------- quy tac bo dang bai trong bo nho dai han cua Muse (post_kit.memory_rule) ----------
# Muse nao se duoc nho lam bo dang bai (tieu de, mo ta, hashtag, 3 cover) thi luu san quy tac + dinh dang POSTKIT vao bo
# nho dai han: Muse cua profile da tick "Tu dong dang" (Fanpage / TikTok / YouTube) va co kenh trong Bang dang bai, va
# Muse lam video cho doi co dang video (khong phai chi huy). Gui khi Muse ranh; gui lai khi doi nen tang / kenh, sau khi
# reset Muse; bo tick het thi nhan Muse bo quy tac. Da gui: state "postkit_rule" {profile: post_kit.memory_sig}.
POST_TARGET_KEYS = (("fanpage", "fanpages"), ("tiktok", "tiktok"), ("youtube", "youtube"))  # cung thu tu auto_post_flags
postkit_rule_inflight = set()


def postkit_rule_sent(profile):
    return (load_state().get("postkit_rule") or {}).get(profile, "")


def forget_postkit_rule(profile):
    update_state(lambda s: (s.get("postkit_rule") or {}).pop(profile, None))


def postkit_channel_lines(entry, targets):
    lang = muse_team.LANG_NAMES.get(entry.get("caption_lang", ""), "")
    tail = f" (chữ: {lang})" if lang else ""
    out = []
    if "fanpage" in targets:
        out += [f"Trang Facebook \"{p.get('name') or p['id']}\"{tail}" for p in entry.get("fanpages") or []]
    if "tiktok" in targets:
        out.append(f"TikTok @{entry['tiktok']}{tail}")
    if "youtube" in targets:
        out.append(f"YouTube @{entry['youtube']}{tail}")
    return out


def postkit_rule_wanted(profile, flags):
    """([nen tang], [mo ta kenh]) ma Muse cua profile se phai lam bo dang bai. Goi trong doi cua chat."""
    channels = muse_team.post_channels()
    pick = [profile]
    cfg = muse_team.config()
    if (cfg["mode"] == "chief" and cfg["post_mode"] != "off" and profile != cfg["chief"]
            and profile not in cfg["excluded"]):  # tho cua doi: video dat dua vao hang doi kenh, tho lam bo dang bai
        pick += [cfg["post_profile"]] if cfg["post_profile"] in channels else list(channels)
    targets, lines = set(), []
    for p in dict.fromkeys(pick):
        entry, ticks = channels.get(p), flags.get(p)
        if not entry or not ticks:
            continue
        on = [t for (t, k), tick in zip(POST_TARGET_KEYS, ticks) if tick and entry.get(k)]
        targets.update(on)
        lines += [x for x in postkit_channel_lines(entry, on) if x not in lines]
    return [t for t in post_kit.PLATFORM_ORDER if t in targets], lines


def queue_postkit_rule(chat, flags):
    """Goi tu vong doi soat (trong doi cua chat): quy tac can gui khac quy tac da gui thi xep viec."""
    profile = chat["profile"]
    targets, lines = postkit_rule_wanted(profile, flags)
    sig = post_kit.memory_sig(targets, lines)
    if profile in postkit_rule_inflight or sig == postkit_rule_sent(profile):
        return
    postkit_rule_inflight.add(profile)
    put_job({"kind": "postkit_rule", "chat": chat, "team": chat.get("team"), "sig": sig, "targets": targets,
             "lines": lines})


def run_postkit_rule(job):
    """Gui quy tac bo dang bai (hoac tin bo quy tac) vao bo nho dai han cua Muse khi Muse ranh han."""
    chat, sig = job["chat"], job["sig"]
    profile = chat["profile"]
    try:
        if sig == postkit_rule_sent(profile):
            return
        if any(t["to"] == profile and t["status"] in ("lam", "bao") for t in (load_state().get("tasks") or {}).values()):
            return  # dang lam viec doi: tin chen vao se lan vao bao cao viec
        st = muse_sync.status(muse_sync.chat_browser(chat))
        if st["busy"] or st["status"]:
            return
        text = post_kit.memory_rule(job["targets"], job["lines"]) if sig else post_kit.memory_off()
        seen = set()
        ok, result = muse_sync.send(chat, text, seen=seen)
        logger.info(f"Quy tac bo dang bai ({', '.join(job['targets']) or 'tat'}) -> {profile}: {result}")
        if ok:
            update_state(lambda s: s.setdefault("postkit_rule", {}).__setitem__(profile, sig))
            relay(chat, tg_target(chat["tg"]), seen)
    finally:
        postkit_rule_inflight.discard(profile)


def postkit_remembered(profile, targets):
    """Muse da luu quy tac bo dang bai cho du cac nen tang cua yeu cau nay."""
    try:
        saved = json.loads(postkit_rule_sent(profile) or "[]")
    except ValueError:
        return False
    return len(saved) == 3 and saved[0] == post_kit.MEMORY_VERSION and set(targets or []) <= set(saved[1])


# ---------- bo dang bai: nho Muse lam tieu de, mo ta, caption, 3 cover truoc khi dang (social_post/post_kit.py) ----------
# auto_post.py thay video trong hang doi dang chua co bo dang bai thi ghi <stem>.kit_request.json va CHUA dang. Bot quet
# cac yeu cau nay moi vong doi soat, gui Muse (Muse ghi trong yeu cau, mac dinh profile cua hang doi) kem vai khung hinh
# cua video, roi doc tra loi cua Muse (khoi "POSTKIT <ma>" + anh <ma>-a/b/c) va ghi bo dang bai canh video.
# State "post_kits": {ma: {"video", "key", "sent", "sends", "done", "noted"}}.
POSTKIT_FRAMES = 5
POSTKIT_RESEND_SECONDS = 3 * 3600
POSTKIT_MAX_SENDS = 2
postkit_inflight = set()


def postkit_requests():
    """[(duong dan yeu cau, noi dung)] trong moi thu muc hang doi dang."""
    out = []
    if not SOCIAL_QUEUE_DIR.is_dir():
        return out
    for req in SOCIAL_QUEUE_DIR.glob("*/*" + post_kit.REQUEST_SUFFIX):
        data = post_kit.read_request(req)
        if data:
            out.append((req, data))
    return out


def postkit_complete(video):
    return post_kit.load_kit(video) is not None and len(post_kit.covers(video)) >= post_kit.COVERS_WANTED


def scan_postkit_requests(chats):
    """Goi tu vong doi soat: xep viec nho Muse lam bo dang bai cho cac yeu cau chua gui / qua lau chua xong."""
    by_profile = {c["profile"]: c for c in chats}
    kits = load_state().get("post_kits") or {}
    for req, data in postkit_requests():
        kid, video = data["kit_id"], Path(data["video"])
        if not video.is_file() or postkit_complete(video):
            req.unlink(missing_ok=True)
            continue
        muse = data.get("muse") or data.get("profile") or req.parent.name
        chat = by_profile.get(muse)
        info = kits.get(kid) or {}
        if not chat:
            if not info.get("noted"):
                general_send(f"⚠️ Video <b>{html.escape(video.name)}</b> trong hàng đợi đăng của "
                             f"{html.escape(req.parent.name)} chưa có bộ đăng bài (tiêu đề, mô tả, cover) và "
                             f"{html.escape(muse)} không phải Muse có topic nên bot không nhờ làm được. Tự đặt "
                             f"<code>{html.escape(video.stem)}.post.json</code> + cover cạnh video, hoặc ghi "
                             f"\"muse\" trong {html.escape(req.name)}.")
                update_state(lambda s: s.setdefault("post_kits", {}).setdefault(kid, {}).__setitem__("noted", True))
            continue
        due = not info.get("sent") or (time.time() - info["sent"] > POSTKIT_RESEND_SECONDS
                                       and info.get("sends", 0) < POSTKIT_MAX_SENDS)
        if not due or kid in postkit_inflight or not _idle(chat["key"]):
            continue
        postkit_inflight.add(kid)
        put_job({"kind": "post_kit", "chat": chat, "kit_id": kid, "req": str(req), "team": chat.get("team")})


def postkit_frames(video, kid):
    """POSTKIT_FRAMES khung hinh rai deu trong video (jpg, rong 960) de Muse biet noi dung. Tra ([file], giay)."""
    ffmpeg = video_sample.ffmpeg_exe()
    if not ffmpeg:
        return [], 0
    seconds = video_sample.probe_duration(video, ffmpeg)
    folder = UPLOAD_DIR / "post_kit" / kid
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(POSTKIT_FRAMES):
        at = seconds * (i + 0.5) / POSTKIT_FRAMES if seconds else i * 5
        dest = folder / f"{kid}-frame{i + 1}.jpg"
        try:
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at:.1f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "3", str(dest)],
                           capture_output=True, timeout=60)
        except Exception as e:
            logger.warning(f"Bo dang bai {kid}: khong trich duoc khung hinh {i + 1}: {e}")
        if dest.is_file():
            out.append(dest)
    return out, seconds


def run_post_kit(job):
    chat, kid, req = job["chat"], job["kit_id"], Path(job["req"])
    try:
        data = post_kit.read_request(req)
        if not data:
            return
        video = Path(data["video"])
        st = muse_sync.status(muse_sync.chat_browser(chat))
        if st["busy"] or st["status"]:
            return  # Muse dang lam: vong doi soat sau gui
        frames, seconds = postkit_frames(video, kid)
        duration = f"{int(seconds) // 60}:{int(seconds) % 60:02d}" if seconds else ""
        entry = muse_team.post_channels().get(req.parent.name) or {}
        lang = muse_team.LANG_NAMES.get(entry.get("caption_lang", ""), "")
        note = ""
        txt = video.with_suffix(".txt")
        if txt.is_file():
            note = "Thông tin sẵn có về video: " + " ".join(txt.read_text(encoding="utf-8-sig").split())[:400]
        targets = data.get("targets") or []
        text = post_kit.prompt(kid, video.name, duration, len(frames), targets, lang, note,
                               remembered=postkit_remembered(chat["profile"], targets))
        seen = set()
        ok, result = muse_sync.send(chat, text, files=[str(f) for f in frames], seen=seen)
        logger.info(f"Nho {chat['key']} lam bo dang bai {kid} ({video.name}): {result}")
        if not ok:
            return

        def mark(state):
            k = state.setdefault("post_kits", {}).setdefault(kid, {})
            k.update(video=str(video), key=chat["key"], sent=time.time(), sends=k.get("sends", 0) + 1, done=False)
        update_state(mark)
        relay(chat, tg_target(chat["tg"]), seen)
    finally:
        postkit_inflight.discard(kid)


def _pending_kits(key):
    return {kid: k for kid, k in (load_state().get("post_kits") or {}).items()
            if k.get("key") == key and not k.get("done") and k.get("video")}


def postkit_finish_check(kid, video, key):
    if not postkit_complete(video):
        return
    post_kit.request_path(video).unlink(missing_ok=True)
    update_state(lambda s: s.setdefault("post_kits", {}).setdefault(kid, {}).__setitem__("done", True))
    kit = post_kit.load_kit(video)
    logger.info(f"Bo dang bai {kid} du: {video}")
    try:
        general_send(f"✅ Đã nhận bộ đăng bài <b>{html.escape(video.name)}</b> từ {html.escape(key)}: "
                     f"{html.escape(kit['title'])} ({len(kit['titles'])} tiêu đề, "
                     f"{len(post_kit.covers(video))} cover). AutoPost sẽ đăng.")
    except Exception:
        logger.exception("Khong bao duoc bo dang bai")


def postkit_take_text(key, text):
    """Tin Muse co khoi POSTKIT: ghi bo dang bai cho video dang cho (theo ma, hoac yeu cau duy nhat cua Muse nay)."""
    if "POSTKIT" not in (text or "").upper():
        return
    pending = _pending_kits(key)
    if not pending:
        return
    kit = post_kit.parse_reply(text)
    if not kit:
        logger.warning(f"{key}: co POSTKIT nhung JSON khong hop le (thieu tieu de / mo ta)")
        return
    kid = kit["kit_id"] if kit["kit_id"] in pending else (next(iter(pending)) if len(pending) == 1 else "")
    if not kid:
        logger.warning(f"{key}: POSTKIT {kit['kit_id']!r} khong khop yeu cau nao ({list(pending)})")
        return
    video = Path(pending[kid]["video"])
    if not video.is_file():
        return
    kit["kit_id"] = kid
    post_kit.save_kit(video, kit, key)
    logger.info(f"{key}: da ghi bo dang bai {kid} -> {post_kit.kit_path(video)}")
    postkit_finish_check(kid, video, key)


def postkit_take_image(key, name, data):
    """Anh cover Muse gui (ten <ma>-a/b/c): luu thanh <stem>.cover1..3 canh video."""
    for kid, k in _pending_kits(key).items():
        slot = post_kit.cover_slot(name, kid)
        video = Path(k["video"])
        if slot and 1 <= slot <= post_kit.COVERS_WANTED and video.is_file():
            path = post_kit.save_cover(video, slot, data, Path(name).suffix)
            logger.info(f"{key}: cover {slot} cua bo dang bai {kid} -> {path}")
            postkit_finish_check(kid, video, key)
            return


# ---------- /rebrand: doi nhan dien kenh cua 1 profile (social_post/brand_kit.py, rebrand.py, tiktok_manage.py) ----------
# /rebrand [profile] [dinh huong] -> chu xac nhan -> bot (1) tam tat Tu dong dang cua profile, (2) xoa moi video TikTok cu
# (tiktok_manage.py --delete-all, dung tai khoan trong Bang dang bai), (3) nho Muse cua profile lam bo nhan dien
# (khoi "BRANDKIT <ma>" + anh <ma>-avatar/cover/banner). Du bo -> rebrand.py: tao Trang Facebook + kenh YouTube moi, sua
# ho so TikTok, gan Bang dang bai, bat lai Tu dong dang. State "rebrands" {profile: {...}}, "rebrand_ask" {profile: ghi chu}.
REBRAND_DATA = "rebrand:"  # + "go:<profile>" / "no" / "stop:<profile>"
BRAND_DIR = ROOT / "Videos" / "downloads" / "channels"
SOCIAL_DIR = ROOT / "social_post"
REBRAND_RESEND_SECONDS = 2 * 3600
REBRAND_MAX_SENDS = 2
REBRAND_ACTIVE = ("kit", "apply")
rebrand_inflight = set()
rebrand_lock = threading.Lock()


def rebrands():
    return load_state().get("rebrands") or {}


def set_rebrand(profile, **kw):
    update_state(lambda s: s.setdefault("rebrands", {}).setdefault(profile, {}).update(kw))


def rebrand_say(profile, text, kb=None):
    r = rebrands().get(profile) or {}
    try:
        if r.get("chat_id"):
            bot.send_message(r["chat_id"], text[:4000], parse_mode="HTML", reply_markup=kb,
                             message_thread_id=r.get("thread"),
                             link_preview_options=types.LinkPreviewOptions(is_disabled=True))
            return
    except Exception as e:
        logger.warning(f"Rebrand {profile}: khong gui duoc vao chat lenh: {e}")
    general_send(text, kb) or notify(text, "HTML")


def rebrand_tiktok_account(profile):
    entry = muse_team.post_channels().get(profile) or {}
    if entry.get("tiktok"):
        return entry["tiktok"]
    try:
        return json.loads((SOCIAL_DIR / "data" / f"tt_account_{profile}.json").read_text(encoding="utf-8"))["account"]
    except (OSError, ValueError, KeyError):
        return ""


def social_run(args, timeout):
    """Chay 1 script social_post; tra (ma thoat, output). Ma -1 = het gio."""
    try:
        p = subprocess.run([sys.executable, *args], cwd=SOCIAL_DIR, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        return -1, ""
    out = (p.stdout or "") + (p.stderr or "")
    logger.info(f"social_post {args[0]} -> {p.returncode}: {out.strip()[-600:]}")
    return p.returncode, out


def last_log_line(out):
    lines = [x for x in out.strip().splitlines() if "LOI" in x or "DUNG" in x]
    return (lines or out.strip().splitlines() or [""])[-1][-200:]


def ask_rebrand(m, profile, note):
    data = f"{REBRAND_DATA}go:{profile}"
    if len(data.encode()) > 64:
        bot.reply_to(m, "Tên profile quá dài, bot không tạo được nút xác nhận.")
        return
    r = rebrands().get(profile) or {}
    if r.get("stage") in REBRAND_ACTIVE:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⛔ Dừng rebrand", callback_data=f"{REBRAND_DATA}stop:{profile}"))
        what = "tạo kênh mới hằng ngày" if r.get("mode") == "daily" else "rebrand"
        bot.reply_to(m, f"🔁 {html.escape(profile)} đang {what} (mã {r.get('id')}, bước "
                        f"{'chờ Muse gửi bộ nhận diện' if r['stage'] == 'kit' else 'tạo kênh / gắn tự động đăng'}).",
                     parse_mode="HTML", reply_markup=kb)
        return
    update_state(lambda s: s.setdefault("rebrand_ask", {}).__setitem__(profile, note))
    entry = muse_team.post_channels().get(profile) or {}
    tiktok = rebrand_tiktok_account(profile)
    now = "\n".join(f"• {html.escape(x)}" for x in postkit_channel_lines(entry, ["fanpage", "tiktok", "youtube"])) \
        or "• (chưa có trong Bảng đăng bài)"
    p = html.escape(profile)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"🔁 Rebrand {profile}", callback_data=data),
           types.InlineKeyboardButton("Huỷ", callback_data=f"{REBRAND_DATA}no"))
    bot.send_message(
        m.chat.id,
        f"⚠️ <b>Rebrand kênh của {p}?</b>\n\nKênh hiện tại:\n{now}\n\n"
        f"Khi xác nhận, bot sẽ:\n"
        f"1. Tạm <b>tắt Tự động đăng</b> của {p}.\n"
        f"2. <b>Xoá TẤT CẢ video trên TikTok</b> "
        + (f"@{html.escape(tiktok)}" if tiktok else "(chưa biết tài khoản: bỏ qua bước này)")
        + " — <b>không thể hoàn tác</b>.\n"
        f"3. Nhờ Muse {p} làm bộ nhận diện kênh: tên, handle, tiểu sử, mô tả, ảnh đại diện, ảnh bìa, banner"
        + (f" (định hướng: <i>{html.escape(note)}</i>)" if note else "") + ".\n"
        f"4. Có bộ nhận diện: tạo <b>Trang Facebook mới</b> + <b>kênh YouTube mới</b> (Trang / kênh cũ giữ nguyên "
        f"nhưng không đăng nữa), đổi tên, tiểu sử, ảnh TikTok (và username nếu còn trống), gắn vào Bảng đăng bài rồi "
        f"bật lại Tự động đăng.",
        parse_mode="HTML", reply_markup=kb, message_thread_id=topic_of(m))


def on_rebrand_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới rebrand được.")
        return
    try:
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
    except Exception:
        logger.debug("Khong go duoc nut rebrand", exc_info=True)
    action = c.data[len(REBRAND_DATA):]
    if action == "no":
        bot.answer_callback_query(c.id, "Đã huỷ.")
        bot.send_message(m.chat.id, "Đã huỷ rebrand.", message_thread_id=topic_of(m))
        return
    if action.startswith("stop:"):
        profile = action[5:]
        set_rebrand(profile, stage="cancelled")
        bot.answer_callback_query(c.id, "Đã dừng.")
        bot.send_message(m.chat.id, f"⛔ Đã dừng rebrand {html.escape(profile)} (bước đang chạy dở vẫn chạy nốt; "
                                    f"Tự động đăng vẫn đang tắt, bật lại trên dashboard).", parse_mode="HTML",
                         message_thread_id=topic_of(m))
        return
    profile = action.removeprefix("go:")
    if profile not in muse_sync.fox_profiles():
        bot.answer_callback_query(c.id, f"Profile {profile} không còn trong FoxProfile.")
        return
    if (rebrands().get(profile) or {}).get("stage") in REBRAND_ACTIVE:
        bot.answer_callback_query(c.id, "Đang rebrand rồi.")
        return
    bot.answer_callback_query(c.id, f"Bắt đầu rebrand {profile}...")
    note = (load_state().get("rebrand_ask") or {}).get(profile, "")
    start_rebrand(profile, note, m.chat.id, topic_of(m))


def start_rebrand(profile, note, chat_id, thread, mode="rebrand"):
    """mode "daily": dot tao kenh hang ngay (/kenhmoi) -- chi nho Muse lam bo nhan dien roi tao Trang FB + kenh YT
    moi; khong tat Tu dong dang, khong xoa TikTok, khong doi Bang dang bai."""
    kid = brand_kit.new_id()
    if mode == "daily":
        update_state(lambda s: s.setdefault("rebrands", {}).__setitem__(profile, {
            "id": kid, "stage": "kit", "mode": "daily", "note": note, "chat_id": chat_id, "thread": thread,
            "at": time.time(), "sent": 0, "sends": 0, "wipe": "skip"}))
        logger.info(f"Kenh moi hang ngay {profile} {kid}: bat dau (dinh huong {note!r})")
        return kid
    flags = auto_post_flags(profile)
    tiktok = rebrand_tiktok_account(profile)
    update_state(lambda s: s.setdefault("rebrands", {}).__setitem__(profile, {
        "id": kid, "stage": "kit", "note": note, "chat_id": chat_id, "thread": thread, "at": time.time(),
        "sent": 0, "sends": 0, "old_flags": list(flags) if flags else None, "tiktok": tiktok,
        "wipe": "running" if tiktok else "skip"}))
    lines = [f"🔁 <b>Rebrand {html.escape(profile)}</b> (mã {kid}) bắt đầu."]
    try:
        fox_api("PATCH", f"/profiles/{profile}",
                json={"auto_post_fanpage": False, "auto_post_tiktok": False, "auto_post_youtube": False})
        lines.append("• Đã tạm tắt Tự động đăng.")
    except Exception as e:
        lines.append(f"• ⚠️ Chưa tắt được Tự động đăng: {html.escape(str(e))}")
    lines.append(f"• Đang xoá video TikTok @{html.escape(tiktok)}..." if tiktok
                 else "• Không có tài khoản TikTok trong Bảng đăng bài: bỏ qua bước xoá video.")
    lines.append(f"• Bot sẽ nhờ Muse {html.escape(profile)} làm bộ nhận diện khi Muse rảnh.")
    rebrand_say(profile, "\n".join(lines))
    logger.info(f"Rebrand {profile} {kid}: bat dau (TikTok @{tiktok or '-'}, dinh huong {note!r})")
    if tiktok:
        spawn(rebrand_wipe_tiktok, profile, tiktok)


def rebrand_wipe_tiktok(profile, account):
    code, out = social_run(["tiktok_manage.py", "--profile", profile, "--delete-all", "--expect-account", account],
                           3 * 3600)
    posts = re.findall(r"TIKTOK_POSTS=(\[.*?\])", out)
    total = len(json.loads(posts[0])) if posts else None
    if code == 0:
        set_rebrand(profile, wipe="done")
        rebrand_say(profile, f"🗑 TikTok @{html.escape(account)}: " + (
            f"đã xoá hết {total} video." if total else "không có video nào để xoá."))
    else:
        set_rebrand(profile, wipe="failed")
        why = {6: "tài khoản đang đăng nhập khác Bảng đăng bài — không xoá gì", 3: "profile chưa đăng nhập TikTok",
               -1: "quá 3 giờ chưa xong"}.get(code, html.escape(last_log_line(out)))
        rebrand_say(profile, f"⚠️ Xoá video TikTok @{html.escape(account)} chưa xong: {why}. Ảnh chụp lỗi trong "
                             f"<code>social_post\\logs</code>; xoá nốt bằng tay hoặc chạy lại "
                             f"<code>tiktok_manage.py --profile {html.escape(profile)} --delete-all --expect-account "
                             f"{html.escape(account)}</code>.")
    rebrand_check(profile)


def rebrand_dir(profile, kid):
    return brand_kit.folder(BRAND_DIR, profile, kid)


def scan_rebrands(chats):
    """Goi tu vong doi soat: nho Muse lam bo nhan dien (gui lai neu qua lau), kiem tra bo da du."""
    by_profile = {c["profile"]: c for c in chats}
    for profile, r in rebrands().items():
        if r.get("stage") != "kit":
            continue
        if rebrand_check(profile):
            continue
        chat = by_profile.get(profile)
        if not chat:
            if not r.get("noted"):
                rebrand_say(profile, f"⚠️ Muse {html.escape(profile)} chưa có topic trong nhóm nên bot không nhờ làm "
                                     f"bộ nhận diện được. Gõ /gan trong topic của {html.escape(profile)}.")
                set_rebrand(profile, noted=True)
            continue
        if r.get("sends", 0) >= REBRAND_MAX_SENDS and time.time() - r.get("sent", 0) > REBRAND_RESEND_SECONDS:
            set_rebrand(profile, stage="failed")
            if r.get("mode") == "daily":
                rebrand_say(profile, f"❌ Kênh mới hằng ngày {html.escape(profile)} ({r['id']}): Muse chưa gửi đủ bộ "
                                     f"nhận diện sau {REBRAND_MAX_SENDS} lần nhờ. Bỏ qua đợt này.")
            else:
                rebrand_say(profile, f"❌ Rebrand {html.escape(profile)} ({r['id']}): Muse chưa gửi đủ bộ nhận diện "
                                     f"sau {REBRAND_MAX_SENDS} lần nhờ. Tự động đăng vẫn đang tắt. Gõ lại /rebrand để "
                                     f"thử lại.")
            continue
        due = not r.get("sent") or time.time() - r["sent"] > REBRAND_RESEND_SECONDS
        if due and profile not in rebrand_inflight and _idle(chat["key"]):
            rebrand_inflight.add(profile)
            put_job({"kind": "brandkit", "chat": chat, "team": chat.get("team")})


def run_brandkit(job):
    chat = job["chat"]
    profile = chat["profile"]
    try:
        r = rebrands().get(profile) or {}
        if r.get("stage") != "kit":
            return
        st = muse_sync.status(muse_sync.chat_browser(chat))
        if st["busy"] or st["status"]:
            return  # Muse dang lam: vong doi soat sau gui
        entry = muse_team.post_channels().get(profile) or {}
        daily = r.get("mode") == "daily"
        current = postkit_channel_lines(entry, ["fanpage", "youtube"] if daily else ["fanpage", "tiktok", "youtube"])
        if daily:
            current += daily_channel_lines(profile)
        text = brand_kit.prompt(r["id"], profile, r.get("note", ""), current, daily=daily)
        seen = set()
        ok, result = muse_sync.send(chat, text, seen=seen)
        logger.info(f"Rebrand {profile}: nho Muse lam bo nhan dien {r['id']}: {result}")
        if ok:
            set_rebrand(profile, sent=time.time(), sends=r.get("sends", 0) + 1)
            relay(chat, tg_target(chat["tg"]), seen)
            rebrand_say(profile, f"📨 Đã nhờ Muse {html.escape(profile)} làm bộ nhận diện kênh (lần {r.get('sends', 0) + 1}"
                                 f"). Có đủ chữ + 3 ảnh là bot tự tạo kênh.")
    finally:
        rebrand_inflight.discard(profile)


def brandkit_take_text(key, text):
    """Tin Muse co khoi BRANDKIT: ghi bo nhan dien cho lan rebrand dang cho cua profile."""
    if brand_kit.MARK not in (text or "").upper():
        return
    r = rebrands().get(key) or {}
    if r.get("stage") != "kit":
        return
    found = brand_kit.parse_reply(text)
    if not found:
        logger.warning(f"{key}: co BRANDKIT nhung JSON khong hop le (thieu ten / handle)")
        return
    kid, kit = found
    if kid and kid != r["id"]:
        logger.warning(f"{key}: BRANDKIT {kid} khong khop lan rebrand {r['id']}")
        return
    path = brand_kit.save_kit(rebrand_dir(key, r["id"]), r["id"], kit, key)
    logger.info(f"{key}: da ghi bo nhan dien {r['id']} -> {path}")
    rebrand_check(key)


def brandkit_take_image(key, name, data):
    r = rebrands().get(key) or {}
    if r.get("stage") != "kit":
        return
    slot = brand_kit.image_slot(name, r["id"])
    if not slot:
        m = re.search(r"(avatar|cover|banner)", name or "", re.I)  # Muse quen ma trong ten file
        slot = m.group(1).lower() if m else None
    if slot:
        path = brand_kit.save_image(rebrand_dir(key, r["id"]), slot, data, Path(name).suffix)
        logger.info(f"{key}: anh {slot} cua bo nhan dien {r['id']} -> {path}")
        rebrand_check(key)


def rebrand_check(profile):
    """Bo nhan dien du (chu + 3 anh) va da xoa xong TikTok -> chay rebrand.py. True neu da chuyen sang buoc apply."""
    with rebrand_lock:  # luong xoa TikTok va luong nhan anh cung goi: chi 1 luong chuyen sang apply
        return _rebrand_check(profile)


def _rebrand_check(profile):
    r = rebrands().get(profile) or {}
    if r.get("stage") != "kit" or not brand_kit.complete(rebrand_dir(profile, r["id"])):
        return False
    if r.get("wipe") == "running":
        if not r.get("kit_ready"):
            set_rebrand(profile, kit_ready=True)
            rebrand_say(profile, f"✅ Đã nhận đủ bộ nhận diện từ {html.escape(profile)}; chờ xoá xong video TikTok rồi "
                                 f"tạo kênh.")
        return False
    set_rebrand(profile, stage="apply")
    kit = brand_kit.load(rebrand_dir(profile, r["id"])) or {}
    rebrand_say(profile, f"✅ Bộ nhận diện <b>{html.escape(kit.get('name', ''))}</b> (YouTube "
                         f"{', '.join('@' + h for h in kit.get('handles', []))}). Đang tạo Trang Facebook + kênh "
                         + ("YouTube mới... (10-20 phút)" if r.get("mode") == "daily" else
                            "YouTube, sửa hồ sơ TikTok... (10-30 phút)"))
    spawn(run_rebrand_apply, profile)
    return True


def run_rebrand_apply(profile):
    r = rebrands().get(profile) or {}
    folder = rebrand_dir(profile, r["id"])
    daily = r.get("mode") == "daily"
    code, out = social_run(["rebrand.py", "--profile", profile, "--kit-dir", str(folder)]
                           + (["--daily"] if daily else []), 3 * 3600)
    m = re.findall(r"REBRAND_RESULT=(\{.*\})", out)
    try:
        res = json.loads(m[-1]) if m else {}
    except ValueError:
        res = {}
    steps, errors = res.get("steps") or {}, res.get("errors") or {}
    if code == -1:
        errors["rebrand"] = "quá 3 giờ chưa xong"
    elif not res:
        errors["rebrand"] = last_log_line(out) or f"mã thoát {code}"
    label = {"facebook": "Trang Facebook", "youtube": "Kênh YouTube", "tiktok": "TikTok", "page_id": "Page ID",
             "post_map": "Bảng đăng bài", "auto_post": "Tự động đăng", "rebrand": "rebrand.py"}
    title = "Kênh mới hằng ngày" if daily else "Rebrand"
    lines = [f"{'🎉' if not errors else '⚠️'} <b>{title} {html.escape(profile)}</b> ({r['id']}) "
             f"{'xong' if not errors else 'xong một phần'}:"]
    for k, v in steps.items():
        if k == "post_map" and isinstance(v, dict):
            v = " · ".join(x for x in (", ".join("FB " + str(p.get("id")) for p in v.get("fanpages") or []),
                                       f"TikTok @{v['tiktok']}" if v.get("tiktok") else "",
                                       f"YouTube @{v['youtube']}" if v.get("youtube") else "") if x)
        elif k == "auto_post" and isinstance(v, dict):
            v = "bật " + (", ".join(n for n, on in v.items() if on) or "—")
        lines.append(f"• {label.get(k, k)}: {html.escape(str(v))}")
    for k, v in errors.items():
        lines.append(f"• ❌ {label.get(k, k)}: {html.escape(str(v))}")
    if errors:
        lines.append(f"Chạy tiếp phần lỗi: <code>python social_post\\rebrand.py --profile {html.escape(profile)} "
                     f"--kit-dir \"{html.escape(str(folder))}\"{' --daily' if daily else ''}</code> (bước đã xong "
                     f"không làm lại).")
    set_rebrand(profile, stage="done" if not errors else "failed", result=res)
    rebrand_say(profile, "\n".join(lines))
    if not errors and not daily:
        forget_postkit_rule(profile)  # kenh moi: gui lai quy tac bo dang bai theo kenh moi


# ---------- /kenhmoi: lich tao Trang Facebook + kenh YouTube moi cho moi profile ----------
# State chung "daily_channels": {"on", "next_at" (epoch), "note", "profiles" ([] = moi profile FoxProfile), "last"}.
# Den gio: moi profile (co topic, khong dang rebrand / tao kenh do) -> start_rebrand(mode="daily"): Muse lam bo nhan
# dien, rebrand.py --daily tao Trang + kenh (khong doi TikTok / Bang dang bai / Tu dong dang). Dot sau = dot nay + 24h30ph
# (gio chay tu dich 30 phut moi ngay). Bot tat qua lau: bo cac dot da lo, giu nhip 24h30ph tinh tu moc cu.
DAILY_INTERVAL = 24 * 3600 + 30 * 60
CHANNELS_DIR = SOCIAL_DIR / "data" / "channels"


def daily_cfg():
    return load_state().get("daily_channels") or {}


def set_daily(**kw):
    update_state(lambda s: s.setdefault("daily_channels", {}).update(kw))


def daily_channel_lines(profile, limit=30):
    """Cac kenh da tao theo lich cua profile (de Muse dat ten khac)."""
    rows = brand_kit.load_daily(CHANNELS_DIR, profile)[-limit:]
    return [r["name"] + (f" (YouTube @{r['handle']})" if r.get("handle") else "") for r in rows if r.get("name")]


def fmt_at(ts):
    return time.strftime("%H:%M %d/%m", time.localtime(ts))


def daily_next_slot(next_at, now):
    """Moc dau tien sau now theo nhip DAILY_INTERVAL tinh tu next_at."""
    while next_at <= now:
        next_at += DAILY_INTERVAL
    return next_at


def daily_first_at(hhmm):
    """Epoch cua lan toi gio HH:MM (hom nay neu chua qua, khong thi ngay mai); hhmm rong: ngay bay gio."""
    now = time.time()
    if not hhmm:
        return now
    h, mi = (int(x) for x in hhmm.split(":"))
    t = time.localtime(now)
    at = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, h, mi, 0, 0, 0, -1))
    return at if at > now else at + 24 * 3600


def scan_daily_channels(chats):
    """Goi tu vong doi soat: den gio thi bat dau 1 dot tao kenh cho moi profile, hen dot sau +24h30ph."""
    d = daily_cfg()
    now = time.time()
    if not d.get("on") or not d.get("next_at") or now < d["next_at"]:
        return
    nxt = daily_next_slot(d["next_at"], now)
    set_daily(next_at=nxt)
    start_daily_round(chats, d.get("note", ""), d.get("profiles") or [], nxt)


def start_daily_round(chats, note, only, nxt=None):
    by_profile = {c["profile"]: c for c in chats}
    try:
        names = muse_sync.fox_profiles()
    except Exception as e:
        logger.warning(f"Kenh moi hang ngay: khong doc duoc danh sach profile FoxProfile: {e}")
        names = list(by_profile)
    started, skipped = [], []
    for profile in only or names:
        if profile not in names:
            skipped.append(f"{profile}: không còn trong FoxProfile")
            continue
        chat = by_profile.get(profile)
        if not chat:
            skipped.append(f"{profile}: chưa có topic (gõ /gan) nên không nhờ Muse được")
            continue
        r = rebrands().get(profile) or {}
        if r.get("stage") in REBRAND_ACTIVE:
            skipped.append(f"{profile}: đang {'tạo kênh' if r.get('mode') == 'daily' else 'rebrand'} dở "
                           f"(mã {r.get('id')})")
            continue
        target = tg_target(chat["tg"])
        kid = start_rebrand(profile, note, target.chat.id, target.message_thread_id, mode="daily")
        started.append(f"{profile} ({kid})")
    now = time.time()
    set_daily(last={"at": now, "started": started, "skipped": skipped})
    lines = [f"🗓 <b>Đợt tạo kênh mới</b> {fmt_at(now)}: nhờ {len(started)} Muse làm bộ nhận diện, có đủ là bot tạo "
             f"Trang Facebook + kênh YouTube mới (báo trong topic từng profile)."]
    lines += [f"• {html.escape(x)}" for x in started]
    lines += [f"• ⏭ {html.escape(x)}" for x in skipped]
    if nxt:
        lines.append(f"Đợt sau: <b>{fmt_at(nxt)}</b> (+24h30ph).")
    logger.info(f"Kenh moi hang ngay: bat dau {started}, bo qua {skipped}, dot sau {fmt_at(nxt) if nxt else '-'}")
    notify("\n".join(lines), "HTML")
    return started, skipped


def daily_status_text():
    d = daily_cfg()
    lines = ["🗓 <b>Tạo kênh mới hằng ngày</b> (Trang Facebook + kênh YouTube, mỗi đợt cách nhau 24h30ph)",
             f"• Trạng thái: <b>{'BẬT' if d.get('on') else 'TẮT'}</b>"
             + (f", đợt sau <b>{fmt_at(d['next_at'])}</b>" if d.get("on") and d.get("next_at") else ""),
             f"• Profile: {html.escape(', '.join(d.get('profiles') or [])) or 'tất cả'}",
             f"• Định hướng: {html.escape(d.get('note') or '— (Muse tự chọn theo video đang làm)')}"]
    last = d.get("last")
    if last:
        lines.append(f"• Đợt gần nhất {fmt_at(last['at'])}: {len(last.get('started') or [])} profile"
                     + (f", bỏ qua {len(last['skipped'])}" if last.get("skipped") else ""))
    stage_vi = {"kit": "chờ Muse gửi bộ nhận diện", "apply": "đang tạo kênh", "done": "xong", "failed": "lỗi",
                "cancelled": "đã dừng"}
    for profile, r in sorted(rebrands().items()):
        if r.get("mode") != "daily":
            continue
        made = len(brand_kit.load_daily(CHANNELS_DIR, profile))
        lines.append(f"  - {html.escape(profile)}: {r.get('id')} {stage_vi.get(r.get('stage'), r.get('stage'))}"
                     f" · đã tạo {made} bộ kênh")
    lines.append("\nLệnh: <code>/kenhmoi bat [HH:MM]</code> · <code>/kenhmoi tat</code> · <code>/kenhmoi ngay</code> · "
                 "<code>/kenhmoi chon Muse8 Muse9</code> (hoặc <code>tatca</code>) · "
                 "<code>/kenhmoi huong định hướng</code> (<code>-</code> để xoá)")
    return "\n".join(lines)


def kenhmoi_command(m):
    arg = m.text.partition(" ")[2].strip()
    sub, _, rest = arg.partition(" ")
    sub, rest = sub.casefold(), rest.strip()
    reply = lambda text: bot.reply_to(m, text, parse_mode="HTML")  # noqa: E731
    if sub in ("bat", "bật", "on"):
        if rest and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", rest):
            reply("Giờ dạng HH:MM, vd <code>/kenhmoi bat 08:00</code> (bỏ trống = chạy đợt đầu ngay).")
            return
        first = daily_first_at(rest)
        set_daily(on=True, next_at=first)
        reply(f"✅ Đã bật. Đợt đầu <b>{fmt_at(first)}</b>, sau đó mỗi 24h30ph "
              f"({fmt_at(first + DAILY_INTERVAL)}, {fmt_at(first + 2 * DAILY_INTERVAL)}, ...).")
    elif sub in ("tat", "tắt", "off"):
        set_daily(on=False)
        reply("⏸ Đã tắt lịch tạo kênh mới. Đợt đang chạy dở vẫn chạy nốt.")
    elif sub in ("ngay", "now"):
        d = daily_cfg()
        nxt = time.time() + DAILY_INTERVAL if d.get("on") else None
        if nxt:
            set_daily(next_at=nxt)  # nhip moi tinh tu bay gio
        started, _ = start_daily_round(mapped_chats(), d.get("note", ""), d.get("profiles") or [], nxt)
        reply(f"▶️ Đã bắt đầu 1 đợt cho {len(started)} profile (chi tiết gửi chat riêng)."
              + (f" Đợt sau {fmt_at(nxt)}." if nxt else " Lịch đang tắt: chỉ chạy đợt này."))
    elif sub in ("chon", "chọn"):
        if rest.casefold() in ("", "tatca", "tất cả", "all"):
            set_daily(profiles=[])
            reply("Áp dụng cho <b>tất cả</b> profile FoxProfile.")
            return
        all_names = muse_sync.fox_profiles()
        want = [x for x in re.split(r"[,\s]+", rest) if x]
        names = [next((p for p in all_names if p.casefold() == w.casefold()), None) for w in want]
        bad = [w for w, n in zip(want, names) if not n]
        if bad:
            reply(f"Không có profile: {html.escape(', '.join(bad))}. Các profile: {html.escape(', '.join(all_names))}")
            return
        set_daily(profiles=names)
        reply(f"Chỉ tạo kênh cho: <b>{html.escape(', '.join(names))}</b>.")
    elif sub in ("huong", "hướng"):
        set_daily(note="" if rest in ("", "-") else rest[:300])
        reply("Đã lưu định hướng." if rest not in ("", "-") else "Đã xoá định hướng (Muse tự chọn).")
    else:
        reply(daily_status_text())


def reconcile_loop():
    runs = {}
    while True:
        time.sleep(RECONCILE_SECONDS)
        chats = mapped_chats()
        if not chats:
            continue
        summary = []
        flags = auto_post_flags_all()  # None: khong hoi duoc FoxProfile -> khong doi quy tac bo dang bai luot nay
        for chat in chats if flags is not None else []:  # truoc yeu cau bo dang bai: Muse luu quy tac truoc
            if _idle(chat["key"]):
                try:
                    run_in_team(chat["team"], queue_postkit_rule, chat, flags)
                except Exception as e:
                    logger.warning(f"Quy tac bo dang bai {chat['key']}: {type(e).__name__}: {e}")
        try:
            scan_postkit_requests(chats)
        except Exception as e:
            logger.warning(f"Bo dang bai: {type(e).__name__}: {e}")
        try:
            scan_daily_channels(chats)
        except Exception as e:
            logger.warning(f"Kenh moi hang ngay: {type(e).__name__}: {e}")
        try:
            scan_rebrands(chats)
        except Exception as e:
            logger.warning(f"Rebrand: {type(e).__name__}: {e}")
        try:
            relay_autopost_events()
        except Exception as e:
            logger.warning(f"Su kien AutoPost: {type(e).__name__}: {e}")
        for chat in chats:
            key = chat["key"]
            if not _idle(key):
                summary.append(f"{key}=ban")
                continue
            try:
                run_in_team(chat["team"], queue_link_rule, chat)
            except Exception as e:
                logger.warning(f"Quy tac gui link {key}: {type(e).__name__}: {e}")
            try:
                a, b = run_in_team(chat["team"], reconcile_chat, chat, runs)
                summary.append(f"{key}={a}/{b}")
            except Exception as e:
                summary.append(f"{key}=loi")
                logger.warning(f"Doi soat {key} loi: {type(e).__name__}: {e}")
        logger.info("Doi soat (Muse->TG / TG->Muse): " + ", ".join(summary))


def topics_loop():
    last_ip = 0
    last_update = time.time() - UPDATE_CHECK_SECONDS + 120  # lan dau: 2 phut sau khi bot chay
    while True:
        for tid in muse_team.team_ids():
            try:
                run_in_team(tid, sync_topics)
            except Exception as e:
                logger.warning(f"Tu tao topic loi (doi {tid}): {type(e).__name__}: {e}")
        if time.time() - last_ip >= IP_CHECK_SECONDS:
            last_ip = time.time()
            for tid in muse_team.team_ids():
                with muse_team.in_team(tid):
                    for profile, topic in topics().items():
                        check_ip(profile, topic)
        if time.time() - last_update >= UPDATE_CHECK_SECONDS:
            last_update = time.time()
            check_update()
        time.sleep(TOPICS_CHECK_SECONDS)


# ---------- doi Muse: 1 Muse chi huy (muc General) giao viec, theo doi tien do, cham ket qua (xem muse_team.py) ----------
# Viec (state "tasks"): duyet (cho chu bam Gui) -> cho (xep hang) -> lam (da gui cho Muse lam) -> bao (bao cao da gui
# chi huy, cho cham) -> dat / lam lai (ve cho) / bo / can_xem / loi. Moi Muse lam 1 viec mot luc; team_loop gui tin
# tiep theo khi Muse ranh. Moi viec di qua hang doi cua profile (giu thu tu voi tin nguoi dung go).
# Viec nhieu video (parts > 1): Muse nop tung video, chi huy cham; dat (>= pass_score) moi lam video tiep.
# Anh / video cua Muse lam viec chua duoc duyet: bot giu lai (gui chi huy cham), khong gui len Telegram; dat moi gui
# vao topic cua Muse do (tru khi dashboard bat show_failed_media). /ketqua T8 xem ngay.
# File ket qua: UPLOAD_DIR/team/<ma viec>/p<video>r<lan lam lai>/; vong chua dat xoa khi viec dong, ca thu muc xoa sau
# TEAM_FILES_KEEP_DAYS ngay (file viec dat dung lam tham chieu cho viec sau).

TEAM_DATA = "team:"  # + "ok:<ma duyet>" / "no:<ma duyet>": nut Gui / Bo khi duyet tay
POST_DATA = "tpost:"  # + "<ma>:<so thu tu kenh>" / "<ma>:x": nut Dang video dat qua 1 kenh (Bang dang bai) / Bo
POST_PENDING_KEEP = 50
SOCIAL_QUEUE_DIR = Path(os.environ.get("SOCIAL_QUEUE_DIR") or ROOT / "Videos" / "downloads" / "social_queue").resolve()
TEAM_LOOP_SECONDS = 10
TEAM_RETRY_SECONDS = 120
TEAM_FAILS = 3
TEAM_PENDING_KEEP = 50
TEAM_REPORT_KEEP_CHARS = 8000
TEAM_HISTORY_KEEP = 20
TEAM_FILES_KEEP_DAYS = 7
TEAM_CLEANUP_SECONDS = 3600
KIND_TEXT = {"giao": "Chỉ huy giao", "nhan": "Chỉ huy nhắn", "lamlai": "Chỉ huy yêu cầu làm lại",
             "tiep": "Làm tiếp", "nhac": "Bot nhắc", "qc": "Bot trả lại (lỗi kỹ thuật)"}
FRESH_KINDS = ("giao", "lamlai", "tiep", "qc")  # tin bat dau 1 luot lam moi (xoa ket qua luot truoc)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
team_inflight = PerTeam(set)  # moi doi 1 bo; viec da xep vao hang doi profile, chua chay xong: "brief", "report", "send:<profile>", "reset"
team_retry_at = PerTeam(dict)  # khoa -> luc duoc thu lai (sau loi)
team_reset_lock = threading.Lock()
team_reset_run = PerTeam(lambda: {"left": set(), "lines": []})  # dot xoa du lieu Muse ca doi dang chay
team_cleaned_at = PerTeam(lambda: [0.0])


def general_send(text, kb=None):
    """Gui tin (HTML) vao muc General cua nhom."""
    group = group_id()
    if not group:
        return None
    try:
        return bot.send_message(group, text[:4000], parse_mode="HTML", reply_markup=kb,
                                link_preview_options=types.LinkPreviewOptions(is_disabled=True))
    except Exception as e:
        logger.warning(f"Khong gui duoc tin vao General: {e}")
        return None


def topic_send(worker, text):
    """Gui tin (HTML) vao topic cua 1 Muse trong doi."""
    topic = topics().get(worker)
    if not topic or not group_id():
        return
    try:
        send_text(tg_target(f"{group_id()}/{topic}"), text)
    except Exception as e:
        logger.warning(f"Khong gui duoc tin vao topic {worker}: {e}")


def team_workers(chief=None):
    """Cac Muse trong doi: profile co topic, tru chi huy va cac Muse bo tick tren dashboard."""
    cfg = muse_team.config()
    chief = chief or cfg["chief"]
    return sorted(p for p in topics() if p != chief and p not in cfg["excluded"])


def _active(state, worker):
    return next((t for t in (state.get("tasks") or {}).values() if t["to"] == worker and t["status"] == "lam"), None)


def _open_task(state, worker):
    """Viec cua Muse dang lam hoac dang cho cham (ket qua chua duoc duyet)."""
    return next((t for t in (state.get("tasks") or {}).values()
                 if t["to"] == worker and t["status"] in ("lam", "bao")), None)


def team_role(key):
    """'chief' (Muse chi huy), 'worker' (Muse dang lam / cho cham 1 viec) hoac None."""
    chief = muse_team.chief()
    if not chief:
        return None
    if key == chief:
        return "chief"
    return "worker" if _open_task(load_state(), key) else None


def team_files_dir(tid):
    return team_dir() / "team" / tid


def team_round_dir(task):
    return team_files_dir(task["id"]) / f"p{task.get('part', 1)}r{task.get('round', 0)}"


def media_kind(path):
    ext = Path(path).suffix.lower()
    return "video" if muse_team.is_video(path) else "image" if ext in IMAGE_EXT else "file"


def team_capture_text(key, text, cmds):
    """Ghi tin Muse lam viet cho viec dang lam (bao cao cho chi huy); [[xong]] / [[vuong]] danh dau xong luot."""
    def change(state):
        t = _active(state, key)
        if not t:
            return
        if text and sum(len(x) for x in t["report"]) < TEAM_REPORT_KEEP_CHARS:
            t["report"].append(text)
        t["last_out"] = t["updated"] = time.time()
        for verb, args in cmds:
            t["done"] = "xong" if verb == "xong" else "vuong: " + (args[1] if len(args) > 1 else "")
    update_state(change)


def team_capture_file(key, data, name):
    """Giu anh / video / file ket qua cua viec dang lam de gui kem bao cao cho chi huy cham.
    Tra ve (ma viec, ly do khong giu): ly do "" = da giu; "late" (viec dang cho cham), "video2" (moi lan chi nop 1
    video), "full" (du file), "big" (qua lon), "none" (khong co viec)."""
    one_video = muse_team.config()["one_video"]

    def add(state):
        t = _active(state, key)
        if not t:
            t = _open_task(state, key)
            return (t["id"], "late") if t else (None, "none")
        if len(data) > muse_team.REPORT_FILE_MAX_BYTES:
            return t["id"], "big"
        if one_video and muse_team.is_video(name) and any(muse_team.is_video(f) for f in t["files"]):
            return t["id"], "video2"
        cap = muse_team.LOOK_MAX_FILES if t.get("stage") == "hinh" else muse_team.REPORT_MAX_FILES
        if len(t["files"]) >= cap:
            return t["id"], "full"
        folder = team_round_dir(t)
        folder.mkdir(parents=True, exist_ok=True)
        stem, ext, n = Path(name).stem or "file", Path(name).suffix, 1
        path = folder / name
        while path.exists():
            n += 1
            path = folder / f"{stem}_{n}{ext}"
        path.write_bytes(data)
        t["files"].append(str(path))
        t["last_out"] = t["updated"] = time.time()
        return t["id"], ""
    try:
        return update_state(add)
    except Exception:
        logger.exception(f"Khong giu duoc file {name} cho bao cao doi Muse")
        return None, "none"


def held_note(tid, kept, dropped):
    """Dong bao trong topic khi bot giu lai anh / video chua duoc duyet."""
    lines = []
    if kept:
        lines.append(f"🔒 Bot giữ {kept} ảnh/video/file để chỉ huy chấm <b>{tid}</b>; đạt mới gửi lên đây. "
                     f"Xem ngay: /ketqua {tid}")
    why = {"late": f"{tid} đang chờ chấm", "video2": "mỗi lần chỉ nộp 1 video", "full": "đã đủ file cho lần nộp này"}
    for reason, n in dropped.items():
        lines.append(f"⏭ Không chuyển {n} ảnh/video ({why.get(reason, reason)}). Xem trên Muse nếu cần.")
    return "\n".join(lines)


def team_send_files(target, files, caption):
    """Gui cac file ket qua (anh / video / file) vao 1 topic Telegram."""
    sent = 0
    for f in files:
        path = Path(f)
        if not path.is_file():
            continue
        try:
            send_media(target, media_kind(path), path.read_bytes(), path.name, caption[:1000] if caption else None)
            sent += 1
            caption = ""  # chu thich chi o file dau
        except Exception as e:
            logger.warning(f"Khong gui duoc {path.name} len Telegram: {e}")
            try:
                send_text(target, f"⚠️ Không gửi được <b>{html.escape(path.name)}</b> lên Telegram: "
                                  f"{html.escape(str(e)[:200])}")
            except Exception:
                pass
    return sent


def team_chief_commands(cmds):
    for verb, args in cmds:
        logger.info(f"Doi Muse: chi huy {verb} {args!r:.300}")
        try:
            {"giao": team_cmd_giao, "nhan": team_cmd_nhan, "lamlai": team_cmd_lamlai,
             "danhgia": team_cmd_danhgia, "kichban": team_cmd_kichban}[verb](args)
        except Exception:
            logger.exception(f"Doi Muse: loi xu ly lenh {verb}")


def team_cmd_giao(args):
    cfg = muse_team.config()
    workers = team_workers()
    if len(args) < 2 or not args[1]:
        general_send(f"⚠️ Chỉ huy viết lệnh giao việc thiếu nội dung: <code>{html.escape(' | '.join(args))}</code>")
        return
    names, bad = muse_team.targets(args[0], workers)
    if bad:
        general_send(f"⚠️ Chỉ huy giao việc cho <b>{html.escape(', '.join(bad))}</b> nhưng đội không có Muse này"
                     + (f" — vẫn giao cho {html.escape(', '.join(names))}" if names else "")
                     + f". Đội: {html.escape(', '.join(workers)) or '—'}")
    if not names:
        return
    text, parts, segment = muse_team.task_parts(args[1])
    if not cfg["video"]:  # doi khong lam video: "| 3 phan" = nop tung phan, khong noi video
        segment = False
    elif not segment and not cfg["one_video"]:  # tat "nop tung video": giu nguyen lenh nhu ban cu
        text, parts = args[1], 1
    # lam video theo video mau da chot kich ban: buoc 1 tao hinh (anh), dat moi lam video
    stage = "hinh" if cfg["video"] and muse_team.wants_look(text, load_state().get("scripts")) else ""

    def create(state):
        tasks = state.setdefault("tasks", {})
        room = cfg["max_new_per_hour"] - sum(time.time() - t["created"] < 3600 for t in tasks.values())
        made = []
        for to in names[:max(0, room)]:
            state["task_seq"] = state.get("task_seq", 0) + 1
            made.append(muse_team.new_task(tasks, state["task_seq"], to, text, parts, segment, stage)["id"])
        return made
    made = update_state(create)
    if len(made) < len(names):
        general_send(f"⚠️ Chỉ huy đã giao {cfg['max_new_per_hour']} việc trong 1 giờ qua, bot tạm không nhận thêm "
                     f"việc cho {html.escape(', '.join(names[len(made):]))}: {html.escape(muse_team.short(text))}")
    if len(made) > 1:
        general_send(f"📋 <b>Chỉ huy giao cùng 1 việc cho {len(made)} Muse</b>: "
                     + ", ".join(f"{tid} → {html.escape(to)}" for tid, to in zip(made, names))
                     + (f" ({parts} {'đoạn' if segment else 'video'})" if parts > 1 else "")
                     + f"\n{html.escape(muse_team.short(text, 1500))}")
    for tid in made:
        team_dispatch(tid, "giao", text, announce=len(made) == 1)


def team_cmd_kichban(args):
    """[[kichban: M1 | ...]]: luu kich ban chot cho video mau (ban v1, v2...); bot tu kem khi giao theo mau do."""
    sid = muse_team.sample_id(args[0]) if args else None
    text = "\n".join((args[1] if len(args) > 1 else "").splitlines()).strip()[:muse_team.SCRIPT_MAX_CHARS]
    samples = load_state().get("samples") or {}
    if not sid or not text:
        general_send("⚠️ Lệnh chốt kịch bản cần dạng <code>[[kichban: M1 | toàn bộ phân kịch]]</code>.")
        return
    if sid not in samples:
        general_send(f"⚠️ Chỉ huy chốt kịch bản cho <b>{sid}</b> nhưng bot không có video mẫu này. Video mẫu đang có: "
                     f"{html.escape(', '.join(sorted(samples))) or '—'}")
        return

    def save(state):
        scripts = state.setdefault("scripts", {})
        old = scripts.get(sid)
        if old and old["text"] == text:
            return old["v"], False
        v = (old or {}).get("v", 0) + 1
        scripts[sid] = {"v": v, "text": text, "at": time.time()}
        return v, True
    v, changed = update_state(save)
    logger.info(f"Doi Muse: kich ban {sid} v{v} ({len(text)} ky tu, {'moi' if changed else 'khong doi'})")
    general_send(f"📝 <b>Kịch bản chốt {sid} — bản v{v}</b>" + ("" if changed else " (giống bản trước)")
                 + f" · {len(text)} ký tự. Giao \"theo video mẫu {sid}\" thì bot tự kèm bản này cho Muse.\n"
                 f"<blockquote expandable>{html.escape(muse_team.short(text, 2500))}</blockquote>")


def _task_from(args, verb):
    tid = muse_team.task_id(args[0]) if args else None
    task = (load_state().get("tasks") or {}).get(tid) if tid else None
    if not task or (verb != "danhgia" and (len(args) < 2 or not args[1])):
        general_send(f"⚠️ Lệnh <b>{verb}</b> của chỉ huy không hợp lệ: không có việc "
                     f"<b>{html.escape(args[0] if args else '?')}</b> hoặc thiếu nội dung.")
        return None
    if task["status"] in muse_team.CLOSED_STATUSES:
        general_send(f"ℹ️ Việc <b>{task['id']}</b> đã {muse_team.STATUS_LABEL[task['status']]}, bot bỏ qua lệnh "
                     f"<b>{verb}</b> của chỉ huy.")
        return None
    if verb != "danhgia" and task["to"] not in team_workers():
        general_send(f"⚠️ {html.escape(task['to'])} không còn trong đội, bot không chuyển lệnh <b>{verb}</b> "
                     f"của chỉ huy cho việc {task['id']}.")
        return None
    return task


def team_cmd_nhan(args):
    task = _task_from(args, "nhan")
    if task:
        team_dispatch(task["id"], "nhan", args[1])


def team_cmd_lamlai(args):
    task = _task_from(args, "lamlai")
    if task:
        team_fail(task, "", args[1])


def team_cmd_danhgia(args):
    task = _task_from(args, "danhgia")
    if not task:
        return
    if task["status"] not in ("bao", "lam", "can_xem"):  # vd chi huy cham 2 lan cho 1 bao cao
        general_send(f"ℹ️ <b>{task['id']}</b> đang {muse_team.STATUS_LABEL.get(task['status'], task['status'])}, "
                     f"chưa có báo cáo mới để chấm. Bot bỏ qua điểm chỉ huy vừa ghi.")
        return
    raw, note = (args[1] if len(args) > 1 else ""), (args[2] if len(args) > 2 else "")
    score = muse_team.parse_score(raw)
    label = muse_team.score_label(score, raw)
    if score is None:
        logger.warning(f"Doi Muse: khong doc duoc diem {raw!r} cua {task['id']}, coi nhu dat")
    if score is not None and score < muse_team.config()["pass_score"]:
        team_fail(task, label, note or "Chưa đạt yêu cầu.")
    else:
        team_pass(task, label, note)


def team_fail(task, label, note):
    """Chua dat (diem duoi muc dat / chi huy yeu cau lam lai): luu ket qua luot nay vao lich su, bao Telegram bang chu
    (khong gui anh / video), gui nhan xet cho Muse lam lai; qua max_rounds lan thi dung, bao chu."""
    cfg = muse_team.config()
    now = time.time()

    def bump(state):
        t = state["tasks"][task["id"]]
        t.setdefault("history", []).append({"part": t.get("part", 1), "round": t.get("round", 0), "score": label,
                                            "note": note, "files": t["files"], "at": now})
        del t["history"][:-TEAM_HISTORY_KEEP]
        t["files"], t["updated"] = [], now
        t["round"] = t.get("round", 0) + 1
        if t["round"] > cfg["max_rounds"]:
            t["status"], t["queue"] = "can_xem", []
            if label:
                t["score"] = label
        else:
            t["status"] = "cho"  # cho gui yeu cau lam lai (duyet tay: cho chu bam Gui)
        return dict(t)
    t = update_state(bump)
    pl = muse_team.part_label(t)
    line = (f"❌ <b>{t['id']}</b> ({html.escape(t['to'])}){' ' + pl if pl else ''}: chưa đạt"
            + (f" <b>{html.escape(label)}</b>" if label else "") + f" — {html.escape(muse_team.short(note, 600))}")
    if t["status"] == "can_xem":
        line += (f"\nĐã chưa đạt {t['round']} lần (tối đa làm lại {cfg['max_rounds']} lần): bot dừng việc này. "
                 f"Bạn xem giúp trong topic {html.escape(t['to'])} · kết quả cuối: /ketqua {t['id']}")
        general_send(line)
        topic_send(t["to"], line)
        return
    line += f"\nChưa đạt lần {t['round']} · Muse làm lại lần {t['round']}/{cfg['max_rounds']}."
    general_send(line)
    topic_send(t["to"], line)
    team_dispatch(t["id"], "lamlai", (f"Điểm {label}. " if label else "") + note, announce=False)


def save_character_lock(task):
    """Bo nhan vat vua dat: chep anh vao CHAR_DIR/<Muse>/<ma viec>/ (giu cac bo khac) de khoa cho cac viec sau."""
    try:
        folder = muse_team.save_lock(char_dir(), task)
    except OSError as e:
        logger.warning(f"Khong luu duoc bo nhan vat {task['id']}: {e}")
        return
    if not folder:
        return
    bound = muse_team.sample_refs(task.get("text"))
    logger.info(f"Doi Muse: luu bo nhan vat {task['id']} cua {task['to']} -> {folder} (mau {bound or 'chung'})")
    general_send(f"🔐 Đã khoá bộ nhân vật <b>{task['id']}</b> của {html.escape(task['to'])}"
                 + (f" cho video mẫu {', '.join(bound)}" if bound else " (bộ chung)")
                 + ": bot tự đính kèm khi giao việc theo video mẫu.")


def team_pass(task, label, note):
    """Dat: viec 1 video thi dong; viec nhieu video thi cho Muse lam video tiep. Anh / video da dat gui vao topic."""
    now = time.time()

    def apply(state):
        t = state["tasks"][task["id"]]
        files = list(t["files"])
        t["passed_files"] = t.get("passed_files", []) + files
        t["passed_report"] = list(t["report"])
        vids = [f for f in files if muse_team.is_video(f)]
        if vids:  # video dat cua video / doan nay (noi doan dung)
            t.setdefault("part_videos", {})[str(t.get("part", 1))] = vids[0]
        t.setdefault("scores", []).append(label)
        t.update(score=label, note=note, files=[], updated=now)
        if t.get("stage") == "hinh":  # buoc tao hinh dat: giu anh, cho lam buoc 2 = video
            t["look_files"] = [f for f in files if Path(f).suffix.lower() in IMAGE_EXT]
            t.update(stage="video", round=0, status="cho", nudged=False, qc_returns=0)
            t["queue"] = [{"kind": "tiep", "text": muse_team.look_done_text(t, label, note)}]
        elif t.get("part", 1) < t.get("parts", 1):
            t.update(part=t.get("part", 1) + 1, round=0, status="cho", nudged=False, qc_returns=0)
            t["queue"] = [{"kind": "tiep", "text": muse_team.next_part_text(t, label, note)}]
        else:
            t.update(status="dat", queue=[])
        return dict(t), files
    t, files = update_state(apply)
    if muse_team.is_character_set(t):
        save_character_lock(t)
    # vua dat buoc tao hinh: con o phan 1 ma chuyen "cho" (dat 1 video / doan thi phan da tang len >= 2)
    look_done = t["status"] == "cho" and t.get("part", 1) == 1
    done = t["part"] - 1 if t["status"] == "cho" else t["part"]
    unit = "đoạn" if t.get("segment") else "video"
    pl = (" bước 1 tạo hình" if look_done else f" {unit} {done}/{t['parts']}" if t.get("parts", 1) > 1 else "")
    line = (f"✅ <b>{t['id']}</b> ({html.escape(t['to'])}){pl} đạt <b>{html.escape(label)}</b>"
            + (f" — {html.escape(muse_team.short(note, 600))}" if note else ""))
    if not look_done and muse_team.is_video_task({**t, "files": files}):
        info = muse_team.video_info({"report": t.get("passed_report")})
        line += "".join(f"\n{name}: {html.escape(info[key])}" for name, key in
                        (("Link tải", "link"), ("Caption", "caption"), ("Hashtag", "hashtag")) if info[key])
    nxt = (f"\nBot giữ {len(t.get('look_files') or [])} ảnh tạo hình, cho {html.escape(t['to'])} làm bước 2 (video) "
           f"từ các ảnh này." if look_done
           else f"\nBot cho {html.escape(t['to'])} làm {unit} {t['part']}/{t['parts']}." if t["status"] == "cho"
           else f"\nĐủ {t['parts']} đoạn: bot đang nối thành 1 video." if t.get("segment") else "\nĐã đóng việc.")
    shown = [f for f in files if Path(f).is_file()]
    general_send(line + nxt + (f" Ảnh/video đã đạt gửi trong topic {html.escape(t['to'])}." if shown else ""))
    videos = [f for f in shown if muse_team.is_video(f)]
    if t.get("segment") and t["status"] == "dat":
        spawn(team_stitch, t)
    if videos and not t.get("segment"):  # dang video dat qua kenh trong Bang dang bai (hoi bang nut / tu dong)
        try:
            team_offer_post(t, done, videos[0], muse_team.video_info({"report": t.get("passed_report")}))
        except Exception:
            logger.exception(f"Loi khi hoi dang video {t['id']}")
    topic = topics().get(t["to"])
    if not topic:
        return
    target = tg_target(f"{group_id()}/{topic}")
    caption = plain(line)

    def publish():
        try:
            send_text(target, line + nxt)
            if shown and not muse_team.config()["show_failed_media"]:  # bat show_failed_media: da gui luc Muse nop
                team_send_files(target, shown, caption)
        except Exception:
            logger.exception(f"Khong gui duoc ket qua dat {t['id']} vao topic {t['to']}")
    spawn(publish)


def team_stitch(t):
    """Viec chia doan vua dat doan cuoi: noi video cac doan (theo thu tu) thanh 1 video, gui topic + hoi dang."""
    parts = [(t.get("part_videos") or {}).get(str(k)) for k in range(1, t.get("parts", 1) + 1)]
    missing = [str(k + 1) for k, f in enumerate(parts) if not f or not Path(f).is_file()]
    if missing:
        general_send(f"⚠️ <b>{t['id']}</b>: thiếu file video đoạn {', '.join(missing)}, bot không nối được. Xem từng "
                     f"đoạn trong topic {html.escape(t['to'])}.")
        return
    out = team_files_dir(t["id"]) / f"{t['id']}_full.mp4"
    try:
        final, err = video_sample.concat(parts, out)
    except Exception as e:
        final, err = None, f"{type(e).__name__}: {e}"
    if not final:
        logger.warning(f"Doi Muse: noi doan {t['id']} loi: {err}")
        general_send(f"⚠️ <b>{t['id']}</b>: nối {len(parts)} đoạn bị lỗi ({html.escape(err[:300])}).")
        return
    _, line, _ = video_sample.check(final)
    update_state(lambda s: s["tasks"][t["id"]].update(final=final, updated=time.time()))
    logger.info(f"Doi Muse: noi {len(parts)} doan {t['id']} -> {final} ({line})")
    general_send(f"🎬 <b>{t['id']}</b> ({html.escape(t['to'])}): đã nối {len(parts)} đoạn thành 1 video — "
                 f"{html.escape(line)}. Video gửi trong topic {html.escape(t['to'])}.")
    topic = topics().get(t["to"])
    if topic:
        team_send_files(tg_target(f"{group_id()}/{topic}"), [final],
                        f"🎬 {t['id']} — video hoàn chỉnh ({len(parts)} đoạn)")
    try:
        team_offer_post(t, 1, final, muse_team.video_info({"report": t.get("passed_report")}))
    except Exception:
        logger.exception(f"Loi khi hoi dang video {t['id']}")


# ---------- kiem tra ky thuat video nop (video_sample.check) ----------

qc_hashes = {}  # (duong dan, kich thuoc, mtime) -> md5


def _video_hash(path):
    st = Path(path).stat()
    key = (str(path), st.st_size, st.st_mtime)
    if key not in qc_hashes:
        qc_hashes[key] = video_sample.file_hash(path)
    return qc_hashes[key]


def old_video_hashes(tasks, own):
    """md5 cac video da nop truoc day (moi viec, ca cac lan chua dat), tru lan nop dang xet cua viec own."""
    out = set()
    for t in tasks.values():
        files = list(t.get("passed_files") or []) + [f for h in t.get("history") or [] for f in h.get("files") or []]
        if t["id"] != own:
            files += t.get("files") or []
        for f in files:
            if muse_team.is_video(f) and Path(f).is_file():
                try:
                    out.add(_video_hash(f))
                except OSError:
                    pass
    return out


def team_qc_return(task, tasks):
    """Do video vua nop (1 lan / lan nop, ghi vao task["qc"] cho bao cao). Loi nang va con luot tra lai: bot gui Muse
    lam lai ngay (khong qua chi huy, khong tinh luot cham), tra ve True."""
    vids = [f for f in task["files"] if muse_team.is_video(f) and Path(f).is_file()]
    if not vids or not muse_team.config()["video"]:  # doi khong dung skill video: khong do ky thuat
        return False
    sig = "v2|" + "|".join(vids)
    if task.get("qc_sig") != sig:
        target = task.get("target")
        if not target:  # viec giao truoc khi bot luu chuan: lay tu video mau nhac trong mo ta viec
            saved = load_state().get("samples") or {}
            sid = next((x for x in video_sample.sample_refs(task.get("text")) if x in saved), None)
            target = video_sample.target_of(saved[sid]) if sid else {}
        target = target or {"sound": False}  # viec khong theo mau: chi bat trung file
        try:
            hard, line, _ = video_sample.check(vids[0], target, task.get("segment"),
                                               old_video_hashes(tasks, task["id"]))
        except Exception as e:
            logger.warning(f"Doi Muse: khong do duoc video {task['id']}: {e}")
            hard, line = [], f"bot không đo được video ({type(e).__name__})"
        logger.info(f"Doi Muse: do video {task['id']}: {line} | loi: {hard or 'khong'}")
        update_state(lambda s: s["tasks"][task["id"]].update(
            qc_sig=sig, qc_hard=hard, qc=[line] + [f"LỖI — {h}" for h in hard]))
        task = load_state()["tasks"][task["id"]]
    hard, used = task.get("qc_hard") or [], task.get("qc_returns", 0)
    if not hard or used >= muse_team.QC_RETURNS:
        return False
    line, now = (task.get("qc") or [""])[0], time.time()
    text = muse_team.qc_text(hard, line, muse_team.QC_RETURNS - used - 1)

    def back(s):
        t = s["tasks"][task["id"]]
        t.setdefault("history", []).append({"part": t.get("part", 1), "round": t.get("round", 0), "score": "bot đo",
                                            "note": "; ".join(hard), "files": t["files"], "at": now})
        del t["history"][:-TEAM_HISTORY_KEEP]
        t.update(qc_returns=used + 1, files=[], updated=now)
        t["queue"].append({"kind": "qc", "text": text})
    update_state(back)
    pl = muse_team.part_label(task)
    note = (f"🔁 <b>{task['id']}</b> ({html.escape(task['to'])}){' ' + pl if pl else ''}: bot trả lại, chưa đưa chỉ huy "
            f"— {html.escape('; '.join(hard))} (lần {used + 1}/{muse_team.QC_RETURNS}, không tính lượt chấm).")
    general_send(note)
    topic_send(task["to"], note)
    return True


# ---------- /dang: xem / dieu khien AutoPost, lay video tu Google Drive vao hang doi ----------
# Trang thai + dieu khien qua file (social_post/post_control.py): AutoPost doc auto_post_control.json moi vong quet (tam
# dung / dang lai ngay), ghi auto_post_events.jsonl moi ket qua -> bot bao ve topic cua profile. Lay video tu Drive
# rieng tu: social_post/drive_fetch.py chay tren trinh duyet cua profile. State chung: "autopost_events_at" (offset da
# bao), "drive_results" {ma: {"profile", "items": [{id, name}]}}, "drive_seq".
DANG_DATA = "dang:"  # + "<r|l|p|c|s>:<profile>" (lam moi / dang lai / tam dung / tiep tuc / bat AutoPost), "g:<ma>:<so>"
DANG_WORDS = {"thulai": "l", "danglai": "l", "lai": "l", "ngay": "l", "retry": "l", "dung": "p", "tamdung": "p",
              "pause": "p", "tiep": "c", "tieptuc": "c", "chay": "c", "resume": "c", "bat": "c"}
DRIVE_KEEP = 20
DRIVE_SHOW = 10
drive_busy = set()


def plain_word(text):
    """'Thử lại' -> 'thulai' (bo dau, viet thuong, bo khoang trang)."""
    flat = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in flat if not unicodedata.combining(c)).lower())


def dang_profiles():
    """Profile tick Tu dong dang (bat ky nen tang) hoac con file trong hang doi."""
    names = [p for p, f in (auto_post_flags_all() or {}).items() if any(f)]
    if SOCIAL_QUEUE_DIR.is_dir():
        names += [d.name for d in SOCIAL_QUEUE_DIR.iterdir()
                  if d.is_dir() and d.name not in names and post_control.queue_files(d.name)]
    return sorted(names)


def dang_text(profile):
    if not profile:
        return (post_control.overview(dang_profiles())
                + "\n\n<i>Chi tiết 1 profile: bấm nút hoặc <code>/dang tên_profile</code>.</i>")
    entry = muse_team.post_channels().get(profile)
    label = muse_team.channel_label(profile, entry) if entry else "Chưa có trong Bảng đăng bài"
    flags = auto_post_flags(profile)
    if flags is not None and not any(flags):
        label += "\n⚠️ Chưa tick Tự động đăng (dashboard FoxProfile)"
    return (post_control.profile_report(profile, label)
            + f"\n\n<i>Lệnh: <code>/dang {html.escape(profile)} thulai</code> · <code>dung</code> · <code>tiep</code> · "
              f"<code>drive từ khoá</code> hoặc <code>drive link</code> (lấy video từ Google Drive của "
              f"{html.escape(profile)} vào hàng đợi)</i>")


def dang_keyboard(profile):
    kb = types.InlineKeyboardMarkup(row_width=2)
    p = profile or ""
    if len(f"{DANG_DATA}x:{p}".encode()) > 64:  # gioi han callback_data cua Telegram
        return None
    paused = post_control.is_paused(profile or None)
    btns = [types.InlineKeyboardButton("🔄 Làm mới", callback_data=f"{DANG_DATA}r:{p}")]
    if profile:
        btns.append(types.InlineKeyboardButton("🔁 Đăng lại ngay", callback_data=f"{DANG_DATA}l:{p}"))
    btns.append(types.InlineKeyboardButton(("▶️ Tiếp tục" if paused else "⏸ Tạm dừng") + ("" if profile else " tất cả"),
                                           callback_data=f"{DANG_DATA}{'c' if paused else 'p'}:{p}"))
    if not post_control.autopost_status()["running"]:
        btns.append(types.InlineKeyboardButton("▶️ Bật AutoPost", callback_data=f"{DANG_DATA}s:{p}"))
    kb.add(*btns)
    if not profile:
        kb.add(*[types.InlineKeyboardButton(f"📤 {n}"[:40], callback_data=f"{DANG_DATA}r:{n}")
                 for n in dang_profiles()[:8] if len(f"{DANG_DATA}r:{n}".encode()) <= 64])
    return kb


def dang_send(chat_id, thread, text, kb=None):
    try:
        return bot.send_message(chat_id, text[:4000], parse_mode="HTML", reply_markup=kb, message_thread_id=thread,
                                link_preview_options=types.LinkPreviewOptions(is_disabled=True))
    except Exception as e:
        logger.warning(f"/dang: khong gui duoc tin: {e}")
        return None


def dang_ensure_running():
    """Bat AutoPost neu chua chay. Tra dong bao them ('' neu dang chay san)."""
    try:
        if post_control.start_autopost():
            logger.info("/dang: da mo AutoPost")
            return "\n▶️ AutoPost chưa chạy, bot đã mở (cửa sổ Muse2tele_AutoPost)."
    except Exception as e:
        logger.exception("/dang: khong mo duoc AutoPost")
        return f"\n⚠️ AutoPost chưa chạy và bot không mở được: {html.escape(str(e))}"
    return ""


def dang_do(action, profile):
    """Thuc hien 1 hanh dong (l / p / c / s). Tra dong bao HTML."""
    who = html.escape(profile) if profile else "tất cả profile"
    if action == "l":
        post_control.request_retry(profile)
        return (f"🔁 Đã yêu cầu AutoPost đăng lại ngay {who}: video lỗi (failed) được đưa về hàng đợi, các đích đang "
                f"chờ thử lại được chạy ngay ở vòng quét tới (≤ 1 phút)." + dang_ensure_running())
    if action == "p":
        post_control.set_paused(profile, True)
        again = f"/dang {html.escape(profile)} tiep" if profile else "/dang tiep"
        return f"⏸ Đã tạm dừng đăng {who}. Bài đang đăng dở (nếu có) vẫn chạy nốt. Tiếp tục: <code>{again}</code>"
    if action == "c":
        post_control.set_paused(profile, False)
        return f"▶️ Tiếp tục đăng {who}." + dang_ensure_running()
    if action == "s":
        return dang_ensure_running() or "🟢 AutoPost đang chạy rồi."
    return ""


def dang_command(m):
    words = m.text.split()[1:]
    thread = topic_of(m)
    profile = None
    if words:
        profile = next((p for p in muse_sync.fox_profiles() if p.casefold() == words[0].casefold()), None)
        if profile:
            words = words[1:]
    if not profile and thread is not None:
        chat = target_for(m)
        profile = chat["profile"] if chat else None
    if words and plain_word(words[0]) == "drive":
        query = " ".join(words[1:]).strip()
        if not profile or not query:
            bot.reply_to(m, "Gõ <code>/dang tên_profile drive từ khoá</code> hoặc <code>/dang tên_profile drive link</code> "
                            "(trong topic của profile thì bỏ tên), vd <code>/dang Muse9 drive LONG TAM Tap 8 phu de "
                            "cung</code>, <code>/dang Muse9 drive https://drive.google.com/file/d/.../view</code>.",
                         parse_mode="HTML")
            return
        file_id = drive_file_id(query)
        if file_id:  # link / id file Drive: tai thang, khong can tim
            spawn(dang_drive_get, m.chat.id, thread, profile, {"id": file_id, "name": ""})
        else:
            spawn(dang_drive_search, m.chat.id, thread, profile, query)
        return
    action = DANG_WORDS.get(plain_word("".join(words))) if words else None
    if words and not action:
        bot.reply_to(m, "Lệnh: <code>/dang [profile]</code> xem hàng đợi · <code>thulai</code> đăng lại ngay · "
                        "<code>dung</code> tạm dừng · <code>tiep</code> tiếp tục · <code>drive từ khoá</code> lấy video "
                        "từ Google Drive.", parse_mode="HTML")
        return
    if action == "l" and not profile:
        bot.reply_to(m, "Đăng lại profile nào? Gõ <code>/dang tên_profile thulai</code>.", parse_mode="HTML")
        return
    if action:
        dang_send(m.chat.id, thread, dang_do(action, profile))
    dang_send(m.chat.id, thread, dang_text(profile), dang_keyboard(profile))


def on_dang_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới điều khiển được việc đăng bài.")
        return
    action, _, rest = c.data[len(DANG_DATA):].partition(":")
    thread = getattr(m, "message_thread_id", None) if getattr(m, "is_topic_message", False) else None
    if action == "g":
        sid, _, idx = rest.partition(":")
        found = (load_state().get("drive_results") or {}).get(sid)
        try:
            bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
        except Exception:
            logger.debug("Khong go duoc nut Drive", exc_info=True)
        if not found or not idx.isdigit() or int(idx) >= len(found["items"]):
            bot.answer_callback_query(c.id, "Đã huỷ." if idx == "x" else "Danh sách này đã cũ, tìm lại nhé.")
            return
        item = found["items"][int(idx)]
        bot.answer_callback_query(c.id, "Đang tải về...")
        spawn(dang_drive_get, m.chat.id, thread, found["profile"], item)
        return
    profile = rest or None
    note = dang_do(action, profile) if action in ("l", "p", "c", "s") else ""
    bot.answer_callback_query(c.id, re.sub(r"<[^>]+>", "", note)[:190] if note else "Đã làm mới.")
    try:
        bot.edit_message_text(dang_text(profile)[:4000], m.chat.id, m.message_id, parse_mode="HTML",
                              reply_markup=dang_keyboard(profile),
                              link_preview_options=types.LinkPreviewOptions(is_disabled=True))
    except ApiTelegramException as e:
        if "not modified" not in str(e):
            logger.warning(f"/dang: khong sua duoc tin: {e}")
    if note and action != "s":
        dang_send(m.chat.id, thread, note)


DRIVE_LINK_RE = re.compile(r"drive\.google\.com/(?:file/d/|open\?(?:.*&)?id=|uc\?(?:.*&)?id=)([\w-]{20,})")


def drive_file_id(text):
    """'https://drive.google.com/file/d/<id>/view?...', '...open?id=<id>' -> '<id>'; tu khoa thuong -> None."""
    m = DRIVE_LINK_RE.search(text)
    return m.group(1) if m else None


def dang_drive_search(chat_id, thread, profile, query):
    if profile in drive_busy:
        dang_send(chat_id, thread, f"⏳ Bot đang làm việc với Google Drive của {html.escape(profile)}, đợi xong nhé.")
        return
    drive_busy.add(profile)
    try:
        dang_send(chat_id, thread, f"🔎 Đang tìm “{html.escape(query)}” trên Google Drive của {html.escape(profile)}"
                                   f" (AutoPost đang đăng trên profile này thì đợi đăng xong)...")
        code, out = social_run(["drive_fetch.py", "--profile", profile, "--search", query], 15 * 60)
    finally:
        drive_busy.discard(profile)
    found = []
    for line in out.splitlines():
        if line.startswith("RESULT "):
            try:
                found.append(json.loads(line[7:]))
            except ValueError:
                pass
    if not found:
        why = ("AutoPost vẫn đang dùng trình duyệt của profile này, thử lại sau" if code == 7 else
               "Drive chưa đăng nhập trên profile này" if code == 3 else
               "không có video nào khớp" if code == 2 else last_log_line(out) or f"mã thoát {code}")
        dang_send(chat_id, thread, f"☁️ Không lấy được danh sách từ Drive của {html.escape(profile)}: "
                                   f"{html.escape(why)}.")
        return
    items = found[:DRIVE_SHOW]

    def add(state):
        state["drive_seq"] = state.get("drive_seq", 0) + 1
        sid = str(state["drive_seq"])
        res = state.setdefault("drive_results", {})
        res[sid] = {"profile": profile, "items": items}
        for old in list(res)[:-DRIVE_KEEP]:
            res.pop(old)
        return sid
    sid = update_state(add)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(*[types.InlineKeyboardButton(f"📥 {it['name']}"[:64], callback_data=f"{DANG_DATA}g:{sid}:{i}")
             for i, it in enumerate(items)])
    kb.add(types.InlineKeyboardButton("✖️ Huỷ", callback_data=f"{DANG_DATA}g:{sid}:x"))
    more = f" (hiện {DRIVE_SHOW} file đầu, gõ từ khoá cụ thể hơn để lọc)" if len(found) > DRIVE_SHOW else ""
    dang_send(chat_id, thread, f"☁️ <b>{len(found)} video</b> trên Drive của {html.escape(profile)} khớp "
                               f"“{html.escape(query)}”{more}. Chọn file để đưa vào hàng đợi đăng "
                               f"(mỗi lần 1 file):", kb)


def dang_drive_get(chat_id, thread, profile, item):
    label = item["name"] or f"file Drive {item['id']}"  # gui bang link: chua biet ten, dung ten file tai ve
    if profile in drive_busy:
        dang_send(chat_id, thread, f"⏳ Bot đang làm việc với Google Drive của {html.escape(profile)}, đợi xong rồi "
                                   f"chọn lại nhé.")
        return
    drive_busy.add(profile)
    try:
        dang_send(chat_id, thread, f"📥 Đang tải <b>{html.escape(label)}</b> từ Drive của {html.escape(profile)} "
                                   f"(file lớn mất vài phút)...")
        code, out = social_run(["drive_fetch.py", "--profile", profile, "--get", item["id"], "--name", item["name"]],
                               40 * 60)
    finally:
        drive_busy.discard(profile)
    saved = [ln[6:].strip() for ln in out.splitlines() if ln.startswith("SAVED ")]
    if code != 0 or not saved:
        why = ("AutoPost vẫn đang dùng trình duyệt của profile này, thử lại sau" if code == 7 else
               "quá 40 phút chưa xong" if code == -1 else last_log_line(out) or f"mã thoát {code}")
        dang_send(chat_id, thread, f"❌ Chưa lấy được {html.escape(label)}: {html.escape(why)}")
        return
    dest = Path(saved[-1])
    entry = muse_team.post_channels().get(profile) or {}
    flags = auto_post_flags(profile) or (False, False, False)
    targets = [t for (t, k), f in zip(POST_TARGET_KEYS, flags) if f and entry.get(k)]
    if targets:
        post_kit.write_request(dest, profile, targets)
    line = (f"✅ Đã đưa <b>{html.escape(dest.name)}</b> vào hàng đợi đăng của {html.escape(profile)}. "
            f"{html.escape(profile)} sẽ làm bộ đăng bài (tiêu đề, mô tả, 3 cover), xong thì AutoPost đăng"
            f"{' lên ' + ', '.join(post_control.TARGET_LABEL[t] for t in targets) if targets else ''}.")
    if not targets:
        line += f"\n⚠️ {html.escape(profile)} chưa tick Tự động đăng / chưa có trong Bảng đăng bài: AutoPost chưa đăng."
    if not post_control.autopost_status()["running"]:
        line += "\n🔴 AutoPost không chạy: bấm ▶️ Bật AutoPost trong <code>/dang</code>."
    dang_send(chat_id, thread, line)


def relay_autopost_events():
    """Goi tu vong doi soat: ket qua dang moi cua AutoPost -> topic cua profile (khong co topic: chat rieng chu bot)."""
    offset = load_state().get("autopost_events_at")
    events, new_offset = post_control.read_events(offset)
    if new_offset != offset:
        update_state(lambda s: s.__setitem__("autopost_events_at", new_offset))
    for ev in events:
        text = post_control.event_text(ev)
        if not text:
            continue
        profile = ev.get("profile") or ""
        with muse_team.in_team(team_of_profile(profile)):
            if topics().get(profile) and group_id():
                topic_send(profile, text)
            else:
                notify(text, parse_mode="HTML")


# ---------- dang video dat: Bang dang bai (social_post/data/post_map.json) -> hang doi auto_post.py ----------

def auto_post_flags_all():
    """{profile: (tick fanpage, tick tiktok, tick youtube)} tren FoxProfile; None neu khong hoi duoc."""
    try:
        data = muse_sync.FoxProfileBrowser("", log=logger.debug)._call("GET", "/profiles", timeout=15).json()
    except Exception as e:
        logger.debug(f"Khong doc duoc danh sach profile FoxProfile: {e}")
        return None
    keys = ("auto_post_fanpage", "auto_post_tiktok", "auto_post_youtube")
    return {x["name"]: tuple(bool(x.get(k)) for k in keys) for x in data.get("profiles") or [] if x.get("name")}


def auto_post_flags(profile):
    """(tick fanpage, tick tiktok, tick youtube) cua profile tren FoxProfile; None neu khong hoi duoc."""
    flags = auto_post_flags_all()
    return None if flags is None else flags.get(profile, (False, False, False))


def team_queue_post(profile, file, info, tid, part, muse=""):
    """Chep video dat + caption (.txt) vao hang doi dang cua profile. Tra (ok, dong bao cao HTML).
    muse: Muse da lam video -- nho chinh Muse do lam bo dang bai (tieu de, mo ta, 3 cover; post_kit.py)."""
    entry = muse_team.post_channels().get(profile)
    src = Path(file)
    if not entry:
        return False, f"{html.escape(profile)} không còn trong Bảng đăng bài."
    if not src.is_file():
        return False, f"File video {html.escape(src.name)} không còn (quá {TEAM_FILES_KEEP_DAYS} ngày đã xoá)."
    folder = SOCIAL_QUEUE_DIR / profile
    folder.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-]+", "_", f"{tid}_v{part}_{src.stem}")[:80]
    dest = folder / f"{stem}{src.suffix.lower()}"
    if dest.exists() or (folder / "done").is_dir() and any((folder / "done").glob(f"*_{dest.name}")):
        return False, f"{html.escape(dest.name)} đã có trong hàng đợi / đã đăng của {html.escape(profile)}."
    dest.with_suffix(".txt").write_text(muse_team.post_caption(info, entry.get("caption_lang", "")) or tid,
                                        encoding="utf-8")
    tmp = dest.with_name(dest.name + ".part")  # chep xong moi doi ten: auto_post khong lay file dang chep do
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)
    want_targets = [t for t, k in (("fanpage", "fanpages"), ("tiktok", "tiktok"), ("youtube", "youtube")) if entry.get(k)]
    post_kit.write_request(dest, profile, want_targets, muse or "")
    logger.info(f"Doi Muse: {tid} video {part} -> hang doi dang {dest} (bo dang bai: {muse or profile})")
    line = f"📤 Đã đưa {html.escape(tid)} video {part} vào hàng đợi đăng: {html.escape(muse_team.channel_label(profile, entry))}"
    flags = auto_post_flags(profile)
    want = (bool(entry.get("fanpages")), bool(entry.get("tiktok")), bool(entry.get("youtube")))
    if flags is not None and not any(f and w for f, w in zip(flags, want)):
        line += (f"\n⚠️ Profile {html.escape(profile)} chưa tick \"Tự động đăng\" (Fanpage / TikTok / YouTube) trên dashboard: "
                 f"AutoPost sẽ chưa đăng.")
    elif flags is not None:
        off = [n for n, f, w in zip(("Fanpage", "TikTok", "YouTube"), flags, want) if w and not f]
        if off:
            line += f"\nℹ️ {html.escape(profile)} chưa tick tự đăng {', '.join(off)}: chỉ đăng phần đã tick."
    return True, line


def team_offer_post(t, part, file, info):
    """Video vua dat: auto -> dua thang vao kenh mac dinh; ask -> nut 📤 cho tung kenh trong Bang dang bai."""
    cfg = muse_team.config()
    if cfg["post_mode"] == "off":
        return
    channels = muse_team.post_channels()
    if not channels:
        general_send(f"ℹ️ Video {html.escape(t['id'])} đạt nhưng Bảng đăng bài chưa có kênh nào "
                     f"(dashboard FoxProfile → Bảng đăng bài), bot không đăng.")
        return
    if cfg["post_mode"] == "auto" and cfg["post_profile"] in channels:
        try:
            ok, line = team_queue_post(cfg["post_profile"], file, info, t["id"], part, t.get("to", ""))
        except OSError as e:
            ok, line = False, f"lỗi {html.escape(str(e))}"
        general_send(line if ok else f"⚠️ Không đưa được {html.escape(t['id'])} vào hàng đợi đăng: {line}")
        return
    names = ([cfg["post_profile"]] if cfg["post_profile"] in channels else []) + sorted(
        n for n in channels if n != cfg["post_profile"])
    names = names[:8]

    def add(state):
        state["team_post_seq"] = state.get("team_post_seq", 0) + 1
        pid = str(state["team_post_seq"])
        pending = state.setdefault("team_posts", {})
        pending[pid] = {"tid": t["id"], "part": part, "file": str(file), "info": info, "choices": names}
        for old in list(pending)[:-POST_PENDING_KEEP]:
            pending.pop(old)
        return pid
    pid = update_state(add)
    kb = types.InlineKeyboardMarkup()
    for i, n in enumerate(names):
        kb.add(types.InlineKeyboardButton(f"📤 Đăng qua {n}"[:60], callback_data=f"{POST_DATA}{pid}:{i}"))
    kb.add(types.InlineKeyboardButton("✖️ Không đăng", callback_data=f"{POST_DATA}{pid}:x"))
    lines = "\n".join(f"• {html.escape(muse_team.channel_label(n, channels[n]))}" for n in names)
    general_send(f"📤 <b>Đăng {html.escape(t['id'])} video {part}?</b> Chọn kênh (Trang Facebook / TikTok / YouTube theo "
                 f"Bảng đăng bài):\n{lines}", kb)


def on_post_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới chọn được kênh đăng.")
        return
    pid, _, choice = c.data[len(POST_DATA):].partition(":")
    item = update_state(lambda s: (s.get("team_posts") or {}).pop(pid, None))
    try:
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
    except Exception:
        logger.debug("Khong go duoc nut dang", exc_info=True)
    if not item:
        bot.answer_callback_query(c.id, "Video này đã xử lý rồi.")
        return
    if choice == "x" or not choice.isdigit() or int(choice) >= len(item["choices"]):
        bot.answer_callback_query(c.id, "Không đăng.")
        bot.reply_to(m, f"✖️ Không đăng {item['tid']} video {item['part']}.")
        return
    profile = item["choices"][int(choice)]
    try:
        task = (load_state().get("tasks") or {}).get(item["tid"]) or {}
        ok, line = team_queue_post(profile, item["file"], item["info"], item["tid"], item["part"], task.get("to", ""))
    except OSError as e:
        ok, line = False, f"lỗi {html.escape(str(e))}"
    bot.answer_callback_query(c.id, "Đã đưa vào hàng đợi đăng." if ok else "Không đưa được.")
    bot.reply_to(m, line if ok else f"⚠️ {line}", parse_mode="HTML")


def team_queue(tid, kind, text):
    """Xep tin cho Muse lam (team_loop gui khi Muse ranh)."""
    def add(state):
        t = state["tasks"][tid]
        t["queue"].append({"kind": kind, "text": text})
        t["updated"] = time.time()
        if t["status"] != "lam":
            t["status"] = "cho"
    update_state(add)


def team_dispatch(tid, kind, text, announce=True):
    """Tin chi huy gui cho Muse lam: tu dong thi xep hang luon, duyet tay thi hien nut Gui / Bo trong General."""
    task = load_state()["tasks"][tid]
    pl = muse_team.part_label(task)
    head = (f"📋 <b>{KIND_TEXT[kind]} {tid} → {html.escape(task['to'])}</b>{' (' + pl + ')' if pl else ''}\n"
            f"{html.escape(muse_team.short(text, 1500))}")
    if muse_team.config()["approval"] == "auto":
        team_queue(tid, kind, text)
        if announce:
            general_send(head)
        return

    def add(state):
        state["team_pseq"] = state.get("team_pseq", 0) + 1
        pid = str(state["team_pseq"])
        pending = state.setdefault("team_pending", {})
        pending[pid] = {"tid": tid, "kind": kind, "text": text}
        for old in list(pending)[:-TEAM_PENDING_KEEP]:
            pending.pop(old)
        return pid
    pid = update_state(add)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Gửi", callback_data=f"{TEAM_DATA}ok:{pid}"),
           types.InlineKeyboardButton("❌ Bỏ", callback_data=f"{TEAM_DATA}no:{pid}"))
    general_send(head + "\n\n<i>Bấm Gửi để chuyển cho Muse (chế độ duyệt tay).</i>", kb)


def on_team_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới duyệt được việc.")
        return
    action, _, pid = c.data[len(TEAM_DATA):].partition(":")
    item = update_state(lambda s: (s.get("team_pending") or {}).pop(pid, None))
    try:
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
    except Exception:
        logger.debug("Khong go duoc nut duyet viec", exc_info=True)
    if not item or item["tid"] not in (load_state().get("tasks") or {}):
        bot.answer_callback_query(c.id, "Việc này đã xử lý rồi.")
        return
    if action == "ok":
        team_queue(item["tid"], item["kind"], item["text"])
        bot.answer_callback_query(c.id, f"Đã duyệt {item['tid']}")
        bot.reply_to(m, f"✅ Đã duyệt {item['tid']}, bot sẽ gửi cho Muse khi Muse rảnh.")
        return
    if item["kind"] in ("giao", "lamlai"):  # bo yeu cau lam lai: viec dung lai, chu tu xu ly
        status = "bo" if item["kind"] == "giao" else "can_xem"
        update_state(lambda s: s["tasks"][item["tid"]].update(status=status, updated=time.time()))
    bot.answer_callback_query(c.id, "Đã bỏ.")
    bot.reply_to(m, f"❌ Đã bỏ {'việc' if item['kind'] == 'giao' else 'tin nhắn của chỉ huy cho việc'} {item['tid']}.")


def team_detach(cfg, state, workers):
    """Muse vua TACH khoi doi (dashboard nut Tach / lenh /tach; muse_team.json "detached"), 1 lan / ma tach:
    bo MOI viec dang mo cua Muse do, ca viec dang lam / cho cham (bo tick tren dashboard thi viec dang lam van cho xong),
    bao o General + topic. Tach ma khong xoa du lieu: khi Muse ranh, nhan Muse bo boi canh doi khoi bo nho dai han
    (gui nhu thiet lap, chu ky "leave:<ma>"; Muse vao doi lai thi thiet lap moi gui de len). Tach co xoa du lieu thi
    team_start_reset (reset_targets) chay truoc va da bo viec. Tra ve True khi da doi state."""
    done, now, changed = state.get("team_detached") or {}, time.time(), False
    todo = {p: d["id"] for p, d in cfg["detached"].items()
            if done.get(p) != d["id"] and p not in workers and p != cfg["chief"]
            and f"send:{p}" not in team_inflight}  # dang gui viec cho Muse: doi gui xong roi moi huy
    if todo:
        def apply(s):
            dropped = []
            for t in (s.get("tasks") or {}).values():
                if t["to"] in todo and t["status"] in muse_team.OPEN_STATUSES:
                    t.update(status="bo", queue=[], updated=now)
                    dropped.append(t["id"])
            s["team_pending"] = {k: v for k, v in (s.get("team_pending") or {}).items()
                                 if v.get("tid") not in dropped}
            s.setdefault("team_detached", {}).update(todo)
            return dropped
        dropped = update_state(apply)
        changed = True
        logger.warning(f"Doi Muse: tach {sorted(todo)} khoi doi, bo viec {dropped}")
        general_send(f"✂️ <b>Đã tách {html.escape(', '.join(sorted(todo)))} khỏi đội Muse</b>"
                     + (f"; huỷ các việc đang mở: {', '.join(dropped)}" if dropped else "")
                     + ". Bot giới thiệu lại đội cho chỉ huy. Muốn cho vào đội lại: dashboard FoxProfile → Đội Muse → "
                       "tick lại Muse đó.")
        for p in todo:
            topic_send(p, "✂️ <b>Muse này đã tách khỏi đội Muse</b>: chỉ huy không giao việc cho Muse này nữa. Bạn nhắn "
                          "trực tiếp ở topic này như Muse độc lập.")
        state = load_state()
    mapped, sent = topics(), state.get("team_setup") or {}
    for p, d in cfg["detached"].items():
        sig = f"leave:{d['id']}"
        if (d["wipe"] or p in workers or p == cfg["chief"] or p not in mapped or sent.get(p) == sig
                or (state.get("team_detached") or {}).get(p) != d["id"]
                or {f"setup:{p}", f"send:{p}"} & team_inflight or not _idle(p)
                or now < team_retry_at.get(f"setup:{p}", 0)):
            continue
        team_inflight.add(f"setup:{p}")
        put_job({"kind": "team_setup", "chat": chat_of(p, mapped[p]), "profile": p, "sig": sig,
                  "text": muse_team.leave_text(),
                  "done": f"✂️ Đã nhắn {html.escape(p)} bỏ bối cảnh đội khỏi bộ nhớ dài hạn (đã tách khỏi đội)."})
    return changed


def team_start_reset(cfg):
    """Xoa du lieu Muse theo dashboard (1 lan / ma reset_id), xong thi gui lai ngu canh + gioi thieu lai doi.
    - reset_targets: chi xoa cac Muse do (vd Muse vua doi ngu canh; chi Muse co topic); trong = chi huy + ca doi.
      Bo viec dang mo cua cac Muse bi xoa (xoa chi huy thi bo moi viec dang mo, chi huy mat het boi canh).
    - reset_full ("Reset doi" hoac doi mau ngu canh): bo HET viec, video mau, kich ban chot; chuyen bo nhan vat khoa +
      video mau vao UPLOAD_DIR/da_reset/<luc>/ (kem ban sao state) de doi lam lai tu dau ma khong mat han. Ma viec /
      ma mau van danh so tiep (khong dung lai T1, M1)."""
    rid, full, now, mapped = cfg["reset_id"], cfg["reset_full"], time.time(), topics()
    chief = cfg["chief"] if cfg["mode"] == "chief" else ""
    if cfg["reset_targets"]:
        targets = [p for p in cfg["reset_targets"] if p in mapped or (p == chief and chief)]
        skipped = [p for p in cfg["reset_targets"] if p not in targets]
    else:
        targets, skipped = ([chief] if chief else []) + team_workers(chief), []
    whole = full or not chief or chief in targets  # bo moi viec dang mo + file ket qua + nut duyet / dang
    archive = team_dir() / "da_reset" / time.strftime("%Y%m%d_%H%M%S") if full else None
    if archive:
        archive.mkdir(parents=True, exist_ok=True)
        try:
            with state_lock:
                shutil.copy2(STATE_FILE, archive / STATE_FILE.name)
        except OSError as e:
            logger.warning(f"Doi Muse: khong sao luu duoc state truoc khi reset doi: {e}")

    def clear(state):
        dropped = []
        for t in (state.get("tasks") or {}).values():
            if t["status"] in muse_team.OPEN_STATUSES and (whole or t["to"] in targets):
                t.update(status="bo", queue=[], updated=now)
                dropped.append(t["id"])
        if full:  # reset doi: bo ca lich su viec, video mau, kich ban (ban sao trong archive)
            for key in ("tasks", "samples", "scripts"):
                state[key] = {}
        if whole:
            state["team_pending"] = {}
            state["team_posts"] = {}  # nut Dang cu: file ket qua bi xoa cung
        else:
            state["team_pending"] = {k: v for k, v in (state.get("team_pending") or {}).items()
                                     if v.get("tid") not in dropped}
        if whole or chief in targets:
            state.pop("team_brief", None)
        sent = state.get("team_setup") or {}
        for p in targets:  # Muse moi reset: gui lai ngon ngu + ngu canh
            sent.pop(p, None)
            (state.get("last_sent") or {}).pop(p, None)
        state["team_reset"] = rid  # ghi ngay: bot tat giua chung cung khong reset lan nua
        return dropped
    dropped = update_state(clear)
    if whole:
        shutil.rmtree(team_dir() / "team", ignore_errors=True)
    else:
        for tid in dropped:
            shutil.rmtree(team_dir() / "team" / tid, ignore_errors=True)
    moved = []
    for folder in ((char_dir(), team_dir() / "mau") if archive else ()):
        if folder.is_dir():
            try:
                shutil.move(str(folder), str(archive / folder.name))
                moved.append(folder.name)
            except OSError as e:
                logger.warning(f"Doi Muse: khong chuyen duoc {folder} vao {archive}: {e}")
    logger.warning(f"Doi Muse: {'reset doi' if full else 'xoa du lieu Muse'} {targets} (reset_id {rid}"
                   + (f", luu tru {archive}: {moved}, bo qua {skipped}" if full else "") + ")")
    if full:
        general_send("♻️ <b>Làm mới đội Muse</b> theo dashboard (reset đội / đổi mẫu ngữ cảnh): đã bỏ mọi việc, video "
                     "mẫu, kịch bản chốt" + (f"; bộ nhân vật khoá + video mẫu cũ chuyển vào <code>"
                                              f"{html.escape(str(archive))}</code>" if moved else "") + ".\n"
                     + (f"Đang xoá dữ liệu Muse của {html.escape(', '.join(targets))}..." if targets
                        else "Không có Muse nào cần xoá dữ liệu.")
                     + (f"\nBỏ qua (không phải Muse bot đang chạy): {html.escape(', '.join(skipped))}" if skipped
                        else ""))
    else:
        leaving = [p for p in targets if p in cfg["detached"] and p != chief and p in cfg["excluded"]]
        general_send(f"♻️ <b>Đang xoá dữ liệu Muse</b> của {html.escape(', '.join(targets)) or '—'} theo cài đặt trên "
                     f"dashboard" + (f" (chỉ huy {html.escape(chief)})" if chief in targets else "")
                     + (f" ({html.escape(', '.join(leaving))} tách khỏi đội)" if leaving else "") + ". "
                     + (f"Đã bỏ việc đang mở: {', '.join(dropped)}. " if dropped else "")
                     + ("" if len(leaving) == len(targets) else
                        "Xong bot gửi lại ngữ cảnh" + (" và giới thiệu lại đội cho chỉ huy." if chief in targets
                                                       else " cho các Muse này.")))
    if not targets:
        return
    with team_reset_lock:
        team_reset_run.update(left=set(targets), lines=[])
    team_inflight.add("reset")
    for p in targets:
        put_job({"kind": "team_reset", "chat": {"key": p, "profile": p}, "profile": p, "chief": p == chief})


def run_team_reset(job):
    profile, line = job["profile"], ""
    try:
        try:
            ok, result = muse_sync.reset_muse(profile)
        except Exception as e:
            ok, result = False, f"lỗi {type(e).__name__}: {e}"
        logger.warning(f"Doi Muse: reset Muse {profile}: ok={ok} {result}")
        line = f"{'✅' if ok else '❌'} {html.escape(profile)}: {html.escape(result)}"
        if ok:
            with stalled_lock:
                stalled.pop(profile, None)
            new, _ = reset_topic(profile)
            name_agent(profile, None if job.get("chief") else new, only_default=False)
    except Exception as e:
        logger.exception(f"Doi Muse: loi reset {profile}")
        line = line or f"❌ {html.escape(profile)}: lỗi {html.escape(type(e).__name__)}"
    finally:
        with team_reset_lock:
            team_reset_run["lines"].append(line)
            team_reset_run["left"].discard(profile)
            finished = not team_reset_run["left"]
            lines = list(team_reset_run["lines"])
        if finished:
            team_inflight.discard("reset")
            general_send("♻️ <b>Xoá dữ liệu Muse của đội xong</b>\n" + "\n".join(lines))


def team_cleanup(tasks):
    """Xoa file ket qua: viec khong con / dong qua TEAM_FILES_KEEP_DAYS ngay; viec da dong thi bo cac vong chua dat
    (giu file da dat lam tham chieu)."""
    root = team_dir() / "team"
    if not root.is_dir():
        return
    now = time.time()
    for d in root.iterdir():
        t = tasks.get(d.name)
        if not d.is_dir():
            continue
        if not t or (t["status"] in muse_team.CLOSED_STATUSES and now - t["updated"] > TEAM_FILES_KEEP_DAYS * 86400):
            shutil.rmtree(d, ignore_errors=True)
            continue
        if t["status"] in muse_team.CLOSED_STATUSES:
            keep = {Path(f).parent.name for f in t.get("passed_files") or []}
            for sub in d.iterdir():
                if sub.is_dir() and sub.name not in keep:
                    shutil.rmtree(sub, ignore_errors=True)


def team_tick():
    cfg = muse_team.config()
    if not group_id() or "reset" in team_inflight:  # dang xoa du lieu Muse ca doi: cho xong moi dieu phoi
        return
    state = load_state()
    # Reset doi (reset_full) chay ca khi thiet lap da ve "solo"; xoa du lieu khi luu chi ap dung o che do chi huy
    if (cfg["reset_id"] and state.get("team_reset") != cfg["reset_id"]
            and (cfg["reset_full"] or cfg["mode"] == "chief")):
        team_start_reset(cfg)
        return
    if cfg["mode"] != "chief":
        return
    chief, now = cfg["chief"], time.time()
    workers = team_workers(chief)
    if team_detach(cfg, state, workers):
        state = load_state()
    if now - team_cleaned_at[0] >= TEAM_CLEANUP_SECONDS:
        team_cleaned_at[0] = now
        team_cleanup(state.get("tasks") or {})
    chief_free = not team_inflight & {"brief", "report"} and _idle(chief)
    # Gioi thieu doi cho chi huy (lan dau / khi doi chi huy, thanh vien, vai tro, luat cham)
    tasks = state.get("tasks") or {}
    # bo nhan vat da khoa (CHAR_DIR): doi bo (vd vua cham dat / luu bo moi) thi gioi thieu lai
    locks = muse_team.locked_sets(char_dir(), tasks)
    brief_sig = json.dumps(["v7", chief, workers, [cfg["roles"].get(w, "") for w in workers],
                            [muse_team.lang_name(cfg, w) for w in workers], cfg["task_lang"], cfg["pass_score"],
                            cfg["max_rounds"], cfg["one_video"],
                            {k: [[x["source"], x["samples"], len(x["files"])] for x in v]
                             for k, v in sorted(locks.items())}], ensure_ascii=False)
    if state.get("team_brief") != brief_sig and chief_free and now >= team_retry_at.get("brief", 0):
        team_inflight.add("brief")
        chief_free = False
        put_job({"kind": "team_brief", "chat": chat_of(chief, None), "sig": brief_sig,
                  "text": muse_team.briefing(cfg, workers, locks, state.get("samples"), state.get("scripts"))})
    mapped = topics()
    # Ngon ngu + ngu canh (bo nho dai han) tung Muse: gui 1 lan / khi chu sua, luc Muse ranh va khong dang lam viec
    sent_setup = state.get("team_setup") or {}
    setup_wait = set()  # Muse chua nhan thiet lap moi: chua gui viec moi
    for p in [chief] + workers:
        sig = muse_team.setup_sig(cfg, p)
        if sent_setup.get(p, "") == sig:
            continue
        if not sig:  # chu xoa thiet lap: chi ghi nho, khong nhan gi cho Muse
            update_state(lambda s, p=p: (s.setdefault("team_setup", {}) or {}).pop(p, None))
            continue
        setup_wait.add(p)
        if p == chief:
            if not chief_free or state.get("team_brief") != brief_sig:
                continue
        elif (p not in mapped or f"send:{p}" in team_inflight or not _idle(p)
              or any(t["to"] == p and t["status"] in ("lam", "bao") for t in tasks.values())):
            # dang lam / cho cham: tin tra loi cua Muse se lan vao bao cao viec -> doi viec xong
            continue
        if f"setup:{p}" in team_inflight or now < team_retry_at.get(f"setup:{p}", 0):
            continue
        team_inflight.add(f"setup:{p}")
        if p == chief:
            chief_free = False
        put_job({"kind": "team_setup", "chat": chat_of(p, None if p == chief else mapped[p]), "profile": p,
                  "sig": sig, "text": muse_team.setup_text(cfg, p, p == chief)})
    # Muse vua bi bo khoi doi: bo cac viec chua bat dau (viec dang lam van cho bao cao xong)
    dropped = [t for t in tasks.values() if t["status"] in ("duyet", "cho") and t["to"] not in workers]
    if dropped:
        def drop(s):
            for t in dropped:
                s["tasks"][t["id"]].update(status="bo", queue=[], updated=time.time())
        update_state(drop)
        general_send("ℹ️ Đã bỏ các việc chưa bắt đầu của Muse không còn trong đội: "
                     + html.escape(", ".join(f"{t['id']} ({t['to']})" for t in dropped)))
        tasks = load_state().get("tasks") or {}
    # Chi huy doc bao cao nhung khong ghi [[danhgia]] (2026-11-08: Muse1 ghi T32, T33 "9/10 dat" tren trang tong hop,
    # bot van treo "cho cham"): sau CHIEF_GRADE_WAIT_SECONDS gui lai bao cao 1 lan, nhac chi lenh moi duoc tinh diem.
    if chief_free and now >= team_retry_at.get("grade_nudge", 0):
        stale = [t for t in tasks.values() if t["status"] == "bao" and not t.get("grade_nudged")
                 and now - (t.get("reported_at") or t.get("updated", 0)) >= CHIEF_GRADE_WAIT_SECONDS]
        if stale:
            t = min(stale, key=lambda x: x.get("reported_at") or x.get("updated", 0))
            update_state(lambda s, tid=t["id"]: s["tasks"][tid].update(grade_nudged=True))
            team_retry_at["grade_nudge"] = now + 120  # moi lan nhac 1 viec, cach nhau it nhat 2 phut
            team_inflight.add("report")
            chief_free = False
            logger.info(f"Doi Muse: {t['id']} cho cham qua {CHIEF_GRADE_WAIT_SECONDS // 60} phut -> gui lai bao cao")
            put_job({"kind": "team_report", "chat": chat_of(chief, None), "tid": t["id"], "nudge": True,
                      "why": "BOT NHẮC — bot chưa nhận lệnh chấm cho báo cáo này. Bot CHỈ tính điểm khi có dòng "
                             f"[[danhgia: {t['id']} | điểm/10 | nhận xét]]; điểm ghi trên trang tổng hợp hay trong lời "
                             "văn KHÔNG được tính, việc vẫn treo \"chờ chấm\". Xem lại kết quả (kèm ảnh ghép khung "
                             "hình nếu là video) rồi chấm bằng lệnh."})
    overdue_s, quiet_s = cfg["overdue_minutes"] * 60, cfg["quiet_minutes"] * 60
    for worker in sorted({t["to"] for t in tasks.values()}):
        mine = sorted((t for t in tasks.values() if t["to"] == worker), key=lambda t: t["created"])
        active = next((t for t in mine if t["status"] == "lam"), None)
        if active and not active["overdue"] and active["sent_at"] and now - active["sent_at"] >= overdue_s:
            update_state(lambda s, tid=active["id"]: s["tasks"][tid].update(overdue=True))
            general_send(f"⏰ <b>{active['id']}</b> ({html.escape(worker)}) đã làm quá {cfg['overdue_minutes']} phút "
                         f"chưa xong: {html.escape(muse_team.short(active['text']))}")
        if f"send:{worker}" in team_inflight or not _idle(worker):
            continue
        if active and not active["queue"]:
            # Xong luot: Muse ghi [[xong]] / [[vuong]], hoac da ranh va im lang quiet_minutes -> bao cao chi huy.
            # Im lang ma chua ghi xong: nhac Muse 1 lan truoc (tranh bao cao rong / bao cao khi Muse con dang lam).
            quiet = now - max(active["sent_at"], active["last_out"])
            if not (active["done"] or quiet >= quiet_s):
                continue
            has_output = bool(active["report"] or active["files"])
            if not active["done"] and not active.get("nudged"):
                def nudge(s, tid=active["id"]):
                    t = s["tasks"][tid]
                    t["nudged"] = True
                    t["queue"].append({"kind": "nhac", "text": muse_team.nudge_text(t, has_output)})
                update_state(nudge)
                logger.info(f"Doi Muse: {active['id']} ({worker}) im lang {quiet:.0f}s chua ghi xong -> nhac")
                continue
            if team_qc_return(active, tasks):  # video loi ky thuat: tra Muse lam lai, khong ton luot chi huy
                continue
            if not chief_free or now < team_retry_at.get(f"report:{active['id']}", 0):
                continue
            done = active["done"]
            why = ("Muse báo đã xong." if done == "xong" else f"Muse báo vướng: {done[6:].strip()}" if done
                   else f"Muse không ghi dòng xong; bot đã nhắc 1 lần, Muse vẫn ngừng trả lời {cfg['quiet_minutes']} "
                        f"phút" + ("." if has_output else " và KHÔNG gửi kết quả nào."))
            update_state(lambda s, tid=active["id"]: s["tasks"][tid].update(status="bao", updated=time.time()))
            team_inflight.add("report")
            chief_free = False
            put_job({"kind": "team_report", "chat": chat_of(chief, None), "tid": active["id"], "why": why})
            continue
        if not active and (worker in setup_wait or f"setup:{worker}" in team_inflight):
            continue  # viec moi cho Muse nhan xong ngon ngu + ngu canh
        nxt = active or next((t for t in mine if t["queue"] and t["status"] == "cho"), None)
        if not nxt or not nxt["queue"] or now < team_retry_at.get(f"send:{worker}", 0):
            continue
        if worker not in mapped:
            update_state(lambda s, tid=nxt["id"]: s["tasks"][tid].update(status="loi", queue=[], updated=time.time()))
            general_send(f"⚠️ <b>{nxt['id']}</b>: {html.escape(worker)} không còn topic trong nhóm, bot bỏ việc này.")
            continue
        item = update_state(lambda s, tid=nxt["id"]: s["tasks"][tid]["queue"].pop(0))
        team_inflight.add(f"send:{worker}")
        put_job({"kind": "team_send", "chat": chat_of(worker, mapped[worker]), "tid": nxt["id"], "item": item})


def run_team_brief(job):
    team_retry_at["brief"] = time.time() + TEAM_RETRY_SECONDS  # loi giua chung: khong thu lai ngay
    try:
        chat, seen = job["chat"], set()
        ok, result = muse_sync.send(chat, job["text"], seen=seen)
        logger.info(f"Doi Muse: gioi thieu doi cho chi huy {chat['key']}: {result}")
        if ok:
            team_retry_at.pop("brief", None)
            update_state(lambda s: s.__setitem__("team_brief", job["sig"]))
            general_send(f"👥 <b>Đã giới thiệu đội cho chỉ huy {html.escape(chat['key'])}.</b> Nhắn yêu cầu vào đây, "
                         f"chỉ huy sẽ chia việc cho các Muse. Gõ /tiendo để xem bảng việc.")
            relay(chat, tg_target(chat["tg"]), seen)
    finally:
        team_inflight.discard("brief")


def run_team_setup(job):
    """Gui ngon ngu + ngu canh (bo nho dai han) cho 1 Muse, chuyen cau xac nhan cua Muse vao topic / General."""
    profile = job["profile"]
    team_retry_at[f"setup:{profile}"] = time.time() + TEAM_RETRY_SECONDS  # loi giua chung: khong thu lai ngay
    try:
        chat, seen = job["chat"], set()
        ok, result = muse_sync.send(chat, job["text"], seen=seen)
        logger.info(f"Doi Muse: gui ngon ngu + ngu canh cho {profile}: {result}")
        if ok:
            team_retry_at.pop(f"setup:{profile}", None)
            update_state(lambda s: s.setdefault("team_setup", {}).__setitem__(profile, job["sig"]))
            general_send(job.get("done") or f"🧠 <b>Đã gửi ngôn ngữ + ngữ cảnh cho {html.escape(profile)}</b> "
                                             f"(cập nhật bộ nhớ dài hạn).")
            relay(chat, tg_target(chat["tg"]), seen)
        else:
            general_send(f"⚠️ Chưa gửi được ngôn ngữ + ngữ cảnh cho {html.escape(profile)}: {html.escape(str(result))}. "
                         f"Bot thử lại sau {TEAM_RETRY_SECONDS // 60} phút.")
    finally:
        team_inflight.discard(f"setup:{profile}")


def team_refs(text, task=None, worker=""):
    """Tham chieu kem cho Muse lam: kich ban chot + video mau (vd "theo video mau M1"), viec da dat nhac trong text (vd
    "bo nhan vat T5"), bo nhan vat da khoa hop voi mau (lenh chua nhac bo nao), khung cuoi doan truoc (viec chia
    doan). Tra ve dict {text, files, ids, scripts {M1: v}, target}."""
    state = load_state()
    tasks, saved, scripts = state.get("tasks") or {}, state.get("samples") or {}, state.get("scripts") or {}
    own = task["id"] if task else ""
    sids = [sid for sid in video_sample.sample_refs(text) if sid in saved]
    samples = [saved[sid] for sid in sids]
    locks = muse_team.locked_sets(char_dir(), tasks)
    picked = [tasks[i] for i in muse_team.task_refs(text) if i in tasks and i != own]
    picked = [r for r in picked if r.get("scores") or muse_team.is_character_set(r)]
    look = [f for f in (task or {}).get("look_files") or [] if Path(f).is_file()]
    if look and (task or {}).get("stage") != "hinh":  # buoc video: anh tao hinh da dat thay cho bo nhan vat khoa
        picked.insert(0, {"id": f"{own} tạo hình", "to": task["to"], "score": (task.get("scores") or ["—"])[0],
                          "passed_files": look,
                          "passed_report": ["Ảnh tạo hình ĐÃ DUYỆT của chính việc này (mặt + tóc + trang phục từng giai "
                                            "đoạn, bối cảnh): MỌI cảnh trong video phải tạo từ các ảnh này, giữ nguyên "
                                            "mặt, tóc, quần áo."]})
    elif samples and not any(muse_team.is_character_set(r) for r in picked):
        lock = muse_team.pick_lock(locks, worker, sids)
        if lock:  # chi anh nhan vat co trong kich ban chot (M1 chi Me + Bo): con cho cho anh ghep video mau
            script = "\n".join(scripts[s]["text"] for s in sids if s in scripts)
            lock = {**lock, "files": muse_team.lock_refs(lock["files"], script, len(lock["files"]))
                    if script else lock["files"]}
            base = tasks.get(lock["source"]) or {"id": lock["source"], "to": lock["owner"], "score": "",
                                                 "status": "dat", "text": "Bộ nhân vật đã duyệt"}
            picked.insert(0, {**base, "passed_files": lock["files"],
                              "passed_report": [f"Bộ nhân vật đã duyệt ({muse_team.lock_label(lock)}). "
                                                + (base.get("text") or "")]})
        elif muse_team.character_sets(tasks).get(worker) in tasks:  # bot chua luu anh: Muse con giu trong chat
            picked.insert(0, tasks[muse_team.character_sets(tasks)[worker]])
    extra_files, extra_lines = [], []
    part = (task or {}).get("part", 1)
    if task and task.get("segment") and part > 1:
        prev = (task.get("part_videos") or {}).get(str(part - 1))
        frame = video_sample.last_frame(prev, team_files_dir(own) / f"doan{part - 1}_khung_cuoi.jpg") if prev else None
        if frame:
            extra_files.append(frame)
            extra_lines.append(f"Ảnh \"doan{part - 1}_khung_cuoi\" bot đính kèm = khung hình CUỐI của đoạn {part - 1} "
                               f"đã đạt: khung đầu của đoạn {part} phải nối liền ảnh này.")
    sample_files = [video_sample.files(s, muse_team.REF_MAX_FILES) for s in samples]
    # chua cho video mau (video + toi da 2 anh ghep moi mau) truoc khi lay anh bo nhan vat
    reserve = min(muse_team.REF_MAX_FILES - 4, sum(min(3, len(f)) for f in sample_files)) + len(extra_files)
    refs, files = [], list(extra_files)
    for r in picked:
        room = muse_team.REF_MAX_FILES - reserve - len(files) + len(extra_files)
        mine = [f for f in r.get("passed_files") or [] if Path(f).is_file()]
        if not mine and muse_team.is_character_set(r):  # file viec da bi don: lay bo da khoa
            sets = locks.get(r["to"]) or []
            hit = next((x for x in sets if x["source"] == r["id"]), None)
            mine = hit["files"] if hit else []
        take = mine[:max(0, room)]
        files += take
        refs.append((r, len(take)))
    used = []
    for smp, sf in zip(samples, sample_files):
        take = sf[:max(0, muse_team.REF_MAX_FILES - len(files))]
        files += take
        used.append((smp, len(take)))
    chosen = [(sid, scripts[sid]) for sid in sids if sid in scripts]
    return {"text": muse_team.ref_block(refs, used, chosen, extra_lines), "files": files,
            "ids": [r["id"] for r, _ in refs] + [smp["id"] for smp, _ in used],
            "scripts": {sid: sc["v"] for sid, sc in chosen},
            "target": video_sample.target_of(samples[0]) if samples else {}}


def run_team_send(job):
    tid, item, chat = job["tid"], job["item"], job["chat"]
    worker = chat["key"]
    team_retry_at[f"send:{worker}"] = time.time() + TEAM_RETRY_SECONDS
    requeue = True
    try:
        state = load_state()
        tasks = state.get("tasks") or {}
        task = tasks.get(tid)
        if not task or task["status"] in ("bo", "dat", "can_xem", "loi"):  # bi huy / da cham trong luc cho
            requeue = False
            return
        cfg = muse_team.config()
        kind, fresh = item["kind"], item["kind"] in FRESH_KINDS
        # Ket qua cac viec truoc cua Muse nay (Muse lam khong thay chi huy cham): bao kem khi giao viec moi
        told = [t for t in tasks.values() if t["to"] == worker and t["id"] != tid and not t.get("told", True)
                and t["status"] in ("dat", "can_xem")] if kind == "giao" else []
        prefix = ("Kết quả việc trước của bạn (bot ghi, bản chuẩn):\n" + "\n".join(
            f"- {t['id']}: {muse_team.STATUS_LABEL[t['status']]} {t.get('score') or ''}"
            + (f" — {muse_team.short(t.get('note'), 200)}" if t.get("note") else "") for t in told) + "\n\n"
                  if told else "")
        ref = (team_refs(item["text"] + ("\n" + task["text"] if kind == "tiep" else ""), task, worker)
               if kind not in ("nhac", "qc") else {"text": "", "files": [], "ids": [], "scripts": {}, "target": {}})
        refs, ref_files, ref_ids = ref["text"], ref["files"], ref["ids"]
        target = ref["target"] or task.get("target") or {}
        tg = tg_target(chat["tg"])
        label = KIND_TEXT[kind] + (f" (lần {task['round']}/{cfg['max_rounds']})" if kind == "lamlai" else "")
        pl = muse_team.part_label(task)
        send_text(tg, f"📋 <b>{label} {tid}</b>{' — ' + pl if pl else ''}\n{html.escape(item['text'])}"
                  + (f"\n<i>Kèm tham chiếu đã duyệt: {html.escape(', '.join(ref_ids))}"
                     f" ({len(ref_files)} file)</i>" if refs else ""))
        seen = set()
        text = muse_team.worker_text(task, kind, item["text"], cfg, prefix, refs, target)
        ok, result = muse_sync.send(chat, text, ref_files, seen=seen)
        if ok is None and ref_files:  # khong dua duoc file tham chieu vao Muse: gui chu thoi
            ok, result = muse_sync.send(chat, text + "\n(Bot không đính kèm được file tham chiếu.)", seen=seen)
        logger.info(f"Doi Muse: {kind} {tid} -> {worker} ({len(ref_files)} file tham chieu): {result}")
        if not ok:
            safe_reply(tg, f"⚠️ Chưa gửi được {tid} cho Muse: {result}. Bot sẽ thử lại.")
            return
        requeue = False
        now = time.time()

        def sent(s):
            t = s["tasks"][tid]
            t.update(status="lam", sent_at=now, overdue=False, fails=0, updated=now)
            if fresh:  # luot lam moi: bo ket qua luot truoc (da luu trong history / passed_files)
                t.update(last_out=0, done="", report=[], files=[], nudged=False, qc=[], qc_hard=[], qc_sig="")
            if ref["scripts"]:
                t.setdefault("script", {}).update(ref["scripts"])
            if ref["target"]:
                t["target"] = ref["target"]
            for x in told:
                s["tasks"][x["id"]]["told"] = True
        update_state(sent)
        team_retry_at.pop(f"send:{worker}", None)
        relay(chat, tg, seen)
    finally:
        if requeue:
            def back(state):
                t = state["tasks"].get(tid)
                if not t:
                    return None
                t["queue"].insert(0, item)
                t["fails"] = t.get("fails", 0) + 1
                if t["fails"] >= TEAM_FAILS:
                    t["status"], t["queue"] = "loi", []
                return t["status"]
            if update_state(back) == "loi":
                general_send(f"⚠️ Bot không gửi được <b>{tid}</b> cho {html.escape(worker)} sau {TEAM_FAILS} lần thử "
                             f"(profile tắt hoặc Muse lỗi). Mở lại profile rồi nhờ chỉ huy giao lại.")
        team_inflight.discard(f"send:{worker}")


REPORT_SEND_MAX_FILES = 8  # bao cao cho chi huy: file Muse nop + anh bot kem them (anh ghep, tao hinh, bo khoa)
CHIEF_GRADE_WAIT_SECONDS = 15 * 60  # bao cao da gui ma chi huy chua [[danhgia]] sau 15 phut: gui lai 1 lan


def report_extras(task, state, files):
    """Anh bot kem them vao bao cao de chi huy so bang mat (khong tin loi Muse tu khai "da QA, dong nhat"):
    - buoc tao hinh: anh bo nhan vat khoa (nhan vat co trong kich ban) de so mat;
    - video: anh ghep khung hinh ket qua (moi o 1 giay) + anh tao hinh da dat (hoac bo khoa).
    Tra ve (file, dong chu cho bao cao)."""
    room = REPORT_SEND_MAX_FILES - len(files)
    if room <= 0 or not muse_team.config()["video"]:
        return [], ""
    tasks, scripts = state.get("tasks") or {}, state.get("scripts") or {}
    sids = video_sample.sample_refs(task.get("text"))
    script = "\n".join(scripts[s]["text"] for s in sids if s in scripts)
    lock = muse_team.pick_lock(muse_team.locked_sets(char_dir(), tasks), task["to"], sids)
    lock_files = muse_team.lock_refs(lock["files"], script) if lock else []
    if task.get("stage") == "hinh":
        take = lock_files[:room]
        return take, (f"Bot kèm thêm {len(take)} ảnh bộ nhân vật KHOÁ ({lock['source']} của {lock['owner']}) sau ảnh "
                      f"của Muse: so mặt từng ảnh tạo hình với các ảnh này." if take else "")
    vids = [f for f in files if muse_team.is_video(f)]
    if not vids:
        return [], ""
    try:
        sheets = video_sample.qa_sheets(vids[0], team_round_dir(task) / "kiem_tra")
    except Exception as e:
        logger.warning(f"Doi Muse: khong cat duoc khung hinh {task['id']}: {e}")
        sheets = []
    sheets = sheets[:room]
    look = [f for f in task.get("look_files") or [] if Path(f).is_file()]
    refs = (look or lock_files)[:room - len(sheets)]
    lines = []
    if sheets:
        lines.append(f"Bot kèm {len(sheets)} ẢNH GHÉP KHUNG HÌNH KẾT QUẢ (bot tự cắt từ video Muse nộp, mỗi ô 1 giây, "
                     f"góc trái ghi giây).")
    if refs:
        lines.append(f"Bot kèm {len(refs)} " + ("ảnh TẠO HÌNH đã duyệt của việc này" if look else
                                               f"ảnh bộ nhân vật KHOÁ {lock['source']}") + " (file cuối).")
    if sheets and refs:
        lines.append("So TỪNG Ô ảnh ghép với ảnh " + ("tạo hình" if look else "bộ khoá") + ": mặt, kiểu tóc, quần áo, vóc "
                     "người. Ô nào khác (dù 1 cảnh) → ghi giây đó, tối đa 7/10.")
    return sheets + refs, "\n".join(lines)


def run_team_report(job):
    tid, chat = job["tid"], job["chat"]
    team_retry_at[f"report:{tid}"] = time.time() + TEAM_RETRY_SECONDS
    ok = False
    try:
        state = load_state()
        tasks = state.get("tasks") or {}
        task = tasks.get(tid)
        if not task:
            ok = True
            return
        cfg = muse_team.config()
        files = [f for f in task["files"] if Path(f).is_file()]
        extra, note = report_extras(task, state, files)
        text = muse_team.report_text(task, tasks, job["why"], cfg, note=note, scripts=state.get("scripts"))
        files += extra
        seen = set()
        ok, result = muse_sync.send(chat, text, files, seen=seen)
        if ok is None and files:  # Muse khong nhan file: gui chu thoi
            ok, result = muse_sync.send(chat, text + "\n(Bot không đính kèm được file kết quả.)", seen=seen)
        logger.info(f"Doi Muse: bao cao {tid} -> chi huy {chat['key']} ({len(files)} file): {result}")
        if ok:
            team_retry_at.pop(f"report:{tid}", None)
            update_state(lambda s: s["tasks"][tid].update(reported_at=time.time(),
                                                          grade_nudged=bool(job.get("nudge"))))
            pl = muse_team.part_label(task)
            general_send(f"📨 <b>{tid}</b> ({html.escape(task['to'])}){' ' + pl if pl else ''}: "
                         + ("chỉ huy chưa ghi lệnh chấm, bot gửi lại báo cáo để chấm" if job.get("nudge")
                            else f"{html.escape(job['why'])} Đã gửi kết quả cho chỉ huy chấm")
                         + (f" (kèm {len(files)} file)." if files else "."))
            relay(chat, tg_target(chat["tg"]), seen)
    finally:
        if not ok:  # ve "lam": team_loop bao cao lai sau TEAM_RETRY_SECONDS
            def back(state):
                t = state["tasks"].get(tid)
                if not t:
                    return None
                t["fails"] = t.get("fails", 0) + 1
                t["status"] = "can_xem" if t["fails"] >= TEAM_FAILS else "lam"
                return t["status"]
            if update_state(back) == "can_xem":
                general_send(f"⚠️ Bot không gửi được báo cáo <b>{tid}</b> cho chỉ huy sau {TEAM_FAILS} lần thử. Xem kết "
                             f"quả trong topic của Muse làm việc này (/ketqua {tid}).")
        team_inflight.discard("report")


def team_loop():
    while True:
        time.sleep(TEAM_LOOP_SECONDS)
        for tid in muse_team.team_ids():
            try:
                run_in_team(tid, team_tick)
            except Exception:
                logger.exception(f"Doi Muse: loi vong dieu phoi (doi {tid})")


def team_result_files(task):
    """File ket qua moi nhat cua 1 viec (cho /ketqua): luot dang lam / cho cham, khong co thi luot chua dat gan nhat,
    khong co nua thi cac video / anh da dat. Tra ve (mo ta, file)."""
    alive = lambda fs: [f for f in fs or [] if Path(f).is_file()]  # noqa: E731
    if alive(task.get("files")):
        return "kết quả đang chờ chấm", alive(task["files"])
    for h in reversed(task.get("history") or []):
        if alive(h.get("files")):
            return f"lần chưa đạt gần nhất ({h.get('score') or 'làm lại'})", alive(h["files"])
    return "kết quả đã đạt", alive(task.get("passed_files"))


def team_summary():
    """Dong tom tat che do doi Muse (HTML)."""
    cfg = muse_team.config()
    if cfg["mode"] != "chief":
        return ("👥 Đội Muse: <b>Độc lập</b> (mỗi Muse tự làm trong topic). Muốn có 1 Muse chỉ huy cả đội ở mục "
                "General: dashboard FoxProfile → <b>Đội Muse</b>.")
    return (f"👥 Đội Muse: chỉ huy <b>{html.escape(cfg['chief'])}</b> ở mục General, gửi việc "
            f"<b>{'tự động' if cfg['approval'] == 'auto' else 'duyệt tay'}</b>, đạt từ <b>{cfg['pass_score']}/10</b>, "
            f"làm lại tối đa {cfg['max_rounds']} lần"
            + (", video nộp từng cái một" if cfg["one_video"] else "")
            + (", ảnh/video chưa đạt vẫn gửi lên Telegram" if cfg["show_failed_media"] else "")
            + f". Đội: {html.escape(', '.join(team_workers(cfg['chief']))) or '—'}.")


# ---------- kiem tra cau hinh + huong dan ----------

def setup_steps():
    """Danh sach (xong?, mo ta, huong dan neu chua xong) cho tung buoc cau hinh."""
    me = bot.get_me()
    steps = []
    try:
        profiles = muse_sync.fox_profiles()
        steps.append((True, f"FoxProfile đang chạy ({len(profiles)} profile)", ""))
    except Exception:
        profiles = None
        steps.append((False, "FoxProfile chưa chạy",
                      "Chạy file <b>start_all.bat</b> (hoặc start_foxprofile.bat) trong thư mục Muse2tele."))
    if profiles is not None:
        error = muse_sync.check_upload(UPLOAD_DIR, profiles)
        steps.append((not error, "FoxProfile nhận được ảnh/video bot tải từ Telegram",
                      "Bot không đưa được file vào Muse: " + html.escape(error or "") + "\nTrong .env, "
                      "<code>MUSE_UPLOAD_DIR</code> phải nằm trong <code>FOXPROFILE_UPLOAD_DIRS</code> (sửa ở "
                      "dashboard FoxProfile → Thư mục upload), rồi khởi động lại FoxProfile và bot."))
    teams = muse_team.raw_teams()
    for t in teams:
        with muse_team.in_team(t["id"]):
            name = html.escape(str(t.get("name") or t["id"]))
            label = f"Đội <b>{name}</b>: " if len(teams) > 1 else ""
            pick = f" Gõ /setup trong nhóm rồi chọn đội {name}." if label else ""
            group = group_id()
            if not group:
                steps.append((False, f"{label}chưa gắn nhóm Telegram", GROUP_HELP.format(bot=me.username) + pick))
            else:
                try:
                    chat = bot.get_chat(group)
                    member = bot.get_chat_member(group, me.id)
                    forum = bool(getattr(chat, "is_forum", False))
                    can_topics = member.status == "creator" or (member.status == "administrator"
                                                                and getattr(member, "can_manage_topics", False))
                    steps.append((forum, f"{label}nhóm <b>{html.escape(chat.title or str(group))}</b> đã bật Chủ đề "
                                         f"(Topics)",
                                  "Mở nhóm → bấm tên nhóm → ✏️ Sửa → bật <b>Chủ đề (Topics)</b>."))
                    steps.append((can_topics, f"{label}bot là quản trị viên nhóm, có quyền Quản lý chủ đề",
                                  f"Mở nhóm → bấm tên nhóm → Quản trị viên → Thêm quản trị viên → chọn @{me.username} "
                                  f"→ bật quyền <b>Quản lý chủ đề (Manage topics)</b> → Lưu."))
                except Exception as e:
                    steps.append((False, f"{label}bot không vào được nhóm đã gắn",
                                  f"Thêm lại @{me.username} vào nhóm rồi gõ /setup trong nhóm. "
                                  f"({html.escape(str(e))})"))
            if profiles is not None and group:
                mapped = topics()
                steps.append((bool(mapped), f"{label}đã có {len(mapped)} topic profile: "
                                            f"{html.escape(', '.join(mapped)) or '—'}",
                              "Trong FoxProfile: tạo profile (gắn proxy nước ngoài), bấm mở profile, đăng nhập "
                              "<b>muse.ai</b>, chọn đội cho profile trên dashboard → Đội Muse. Khoảng 1 phút sau bot tự "
                              "tạo topic cùng tên profile trong nhóm của đội."))
    return steps


GROUP_HELP = ("1. Trên Telegram tạo <b>Nhóm mới</b> (New Group), thêm @{bot} vào nhóm.\n"
              "2. Bấm tên nhóm → ✏️ Sửa → bật <b>Chủ đề (Topics)</b>.\n"
              "3. Quản trị viên → Thêm quản trị viên → chọn @{bot} → bật <b>Quản lý chủ đề</b> → Lưu.\n"
              "4. Trong nhóm, gõ <code>/setup</code> và gửi.")


def status_text():
    lines = ["🛠 <b>Trạng thái cấu hình Muse2tele</b>", ""]
    todo = None
    for done, title, how in setup_steps():
        lines.append(f"{'✅' if done else '❌'} {title}")
        if not done and todo is None:
            todo = how
    if todo:
        lines += ["", "👉 <b>Việc cần làm tiếp:</b>", todo]
    else:
        lines += ["", "🎉 Đã cấu hình xong. Mỗi profile mới đăng nhập Muse sẽ tự có topic riêng trong nhóm."]
    for tid in muse_team.team_ids():
        with muse_team.in_team(tid):
            name = muse_team.config()["name"]
            lines += ["", (f"🏷 <b>{html.escape(name)}</b> · " if len(muse_team.team_ids()) > 1 else "") + team_summary()]
    vn = [p for p, r in ip_results.items() if r[2]]
    if vn:
        lines += ["", "🚫 <b>Profile đang dùng IP Việt Nam:</b> " + html.escape(", ".join(vn)),
                  "Gắn proxy nước ngoài cho các profile này trong FoxProfile để tránh bị Muse chặn."]
    lines += ["", "<b>Lệnh:</b> " + commands_help()]
    return "\n".join(lines)


def startup_report():
    """Luc khoi dong: kiem tra IP moi profile, bao trang thai cho chu bot."""
    try:
        for profile in muse_sync.fox_profiles():
            with muse_team.in_team(team_of_profile(profile)):
                check_ip(profile, topics().get(profile))
    except Exception as e:
        logger.warning(f"Khong doc duoc danh sach profile: {e}")
    try:
        text = status_text()
        logger.info("\n" + plain(text))
        notify("🤖 Bot đã khởi động.\n\n" + text, parse_mode="HTML")
    except Exception:
        logger.exception("Khong tao duoc bao cao khoi dong")


# ---------- bot ----------

# Moi lenh cua bot: (lenh, mo ta trong menu "/" cua Telegram, noi dung: "private" / "group" / "both").
# Bot tu khai bao voi Telegram luc khoi dong (set_commands) -> khong can /setcommands o BotFather.
COMMANDS = [
    ("start", "Xem trạng thái cấu hình và việc cần làm tiếp", "private"),
    ("help", "Hướng dẫn sử dụng (giống /start)", "private"),
    ("setup", "Gắn nhóm này với bot (gõ trong nhóm đã bật Chủ đề)", "group"),
    ("gan", "Gõ trong topic: gán topic với profile (trùng tên thì gán luôn, không thì chọn)", "group"),
    ("kiemtra", "Kiểm tra IP từng profile, cảnh báo IP Việt Nam", "both"),
    ("reset", "Xoá dữ liệu Muse của 1 profile (trong topic); ở General: reset cả đội + chọn ngữ cảnh", "both"),
    ("tach", "Tách 1 Muse thành viên khỏi đội (gõ trong topic của Muse, /tach tên, hoặc chọn ở General)", "both"),
    ("dang", "Đăng bài: hàng đợi, lỗi, đăng lại ngay, tạm dừng, lấy video từ Drive (vd /dang Muse9)", "both"),
    ("rebrand", "Đổi nhận diện kênh: Muse làm bộ nhận diện, tạo Trang FB + kênh YT mới, xoá video TikTok cũ", "both"),
    ("kenhmoi", "Lịch tạo Trang FB + kênh YT mới cho mọi profile, mỗi đợt cách 24h30ph (bat/tat/ngay/chon)", "both"),
    ("tiendo", "Bảng việc của đội Muse (chế độ có chỉ huy)", "both"),
    ("ketqua", "Xem ảnh/video kết quả 1 việc của đội Muse, vd /ketqua T8", "both"),
    ("allow_on", "Bật tự bấm Allow khi Muse xin quyền", "both"),
    ("allow_off", "Tắt tự bấm Allow khi Muse xin quyền", "both"),
]
# Khung "What can this bot do?" (chat rieng trong, toi da 512 ky tu) va mo ta ngan o trang thong tin bot (toi da 120).
BOT_DESCRIPTION = ("Muse2tele nối các tài khoản Muse (muse.ai) với một nhóm Telegram: mỗi profile FoxProfile có một "
                   "topic riêng. Nhắn tin, gửi ảnh / video / file vào topic, bot gõ vào Muse và gửi câu trả lời của "
                   "Muse về đúng topic đó.\n\nBấm Start để nhận quyền chủ bot và xem hướng dẫn cấu hình.")
BOT_SHORT_DESCRIPTION = "Dùng Muse (muse.ai) ngay trong nhóm Telegram: mỗi tài khoản Muse một topic."


def commands_help():
    """Dong liet ke lenh cho /start."""
    return " · ".join(f"/{name} {html.escape(desc[0].lower() + desc[1:])}" for name, desc, _ in COMMANDS
                      if name != "help")


def set_commands():
    """Khai bao menu lenh (rieng cho chat rieng / nhom) va phan gioi thieu bot. Chi goi API khi noi dung khac
    cai Telegram dang luu (cac lenh set nay bi gioi han tan suat)."""
    menus = [(types.BotCommandScopeDefault(), ("private", "group", "both")),
             (types.BotCommandScopeAllPrivateChats(), ("private", "both")),
             (types.BotCommandScopeAllGroupChats(), ("group", "both"))]
    for scope, where in menus:
        want = [(name, desc) for name, desc, w in COMMANDS if w in where]
        try:
            have = [(c.command, c.description) for c in bot.get_my_commands(scope=scope) or []]
            if have != want:
                bot.set_my_commands([types.BotCommand(n, d) for n, d in want], scope=scope)
                logger.info(f"Da cap nhat menu lenh ({scope.type}): {len(want)} lenh")
        except Exception:
            logger.exception(f"Khong dat duoc menu lenh ({scope.type})")
    for get, put, attr, text in ((bot.get_my_description, bot.set_my_description, "description", BOT_DESCRIPTION),
                                 (bot.get_my_short_description, bot.set_my_short_description, "short_description",
                                  BOT_SHORT_DESCRIPTION)):
        try:
            if getattr(get(), attr, None) != text:
                put(**{attr: text})
                logger.info(f"Da cap nhat {attr} cua bot")
        except Exception:
            logger.exception(f"Khong dat duoc {attr} cua bot")


# ---------- /setup: gan nhom Telegram voi 1 doi Muse (moi doi 1 nhom) ----------
SETUP_DATA = "tsetup:"  # + "<ma doi>" / "+" (tao doi moi mang ten nhom) / "" (huy)


def bind_group(chat_id, title):
    """Gan nhom chat_id cho doi dang xu ly. Doi dang o nhom khac: bo topic cu (tao lai o nhom moi). Doi khac dang giu\n    nhom nay: bo gan."""
    here = muse_team.current_team()
    for tid, st in team_states().items():
        if tid != here and st.get("group") == chat_id:
            gone = list(st.get("topics") or {})
            update_state(lambda s, gone=gone: s.update(group=None, group_title="", topics={}, watched=[
                k for k in s.get("watched", []) if k not in gone]), tid)
            logger.info(f"Bo gan nhom {chat_id} khoi doi {tid}")

    def change(state):
        if state.get("group") and state.get("group") != chat_id:
            gone = list(state.get("topics") or {})
            state["topics"] = {}
            state["watched"] = [k for k in state.get("watched", []) if k not in gone]
        state.update(group=chat_id, group_title=title or "")
    update_state(change)
    logger.info(f"Gan nhom {chat_id} ({title}) cho doi {here}")


def finish_setup(chat_id, title, reply=None):
    """Kiem tra nhom (bat Chu de, bot co quyen Quan ly chu de) roi dong bo topic cho doi dang xu ly."""
    cfg = muse_team.config()
    update_state(lambda s: s.update(group_title=title or s.get("group_title") or ""))
    me = bot.get_me()
    member = bot.get_chat_member(chat_id, me.id)
    can_topics = member.status == "creator" or (member.status == "administrator"
                                                and getattr(member, "can_manage_topics", False))
    bad = [(t, how) for done, t, how in [
        (bool(getattr(bot.get_chat(chat_id), "is_forum", False)), "Nhóm chưa bật Chủ đề (Topics)",
         "Bấm tên nhóm → ✏️ Sửa → bật <b>Chủ đề (Topics)</b>."),
        (can_topics, "Bot chưa có quyền Quản lý chủ đề",
         f"Bấm tên nhóm → Quản trị viên → Thêm quản trị viên → chọn @{me.username} → bật "
         f"<b>Quản lý chủ đề</b> → Lưu.")] if not done]
    team = f"đội <b>{html.escape(cfg['name'])}</b>"
    if bad:
        text = (f"⚠️ Đã gắn nhóm này với {team} nhưng còn thiếu:\n"
                + "\n".join(f"❌ {t}\n👉 {how}" for t, how in bad) + "\n\nSửa xong gõ lại /setup.")
    else:
        text = (f"✅ <b>Đã gắn nhóm này với bot</b> — {team}.\nProfile của đội (dashboard FoxProfile → Đội Muse) đang mở "
                f"và đã đăng nhập muse.ai: khoảng 1 phút sau bot tự tạo topic cho từng profile.")
    if reply is not None:
        bot.reply_to(reply, text, parse_mode="HTML")
    else:
        bot.send_message(chat_id, text, parse_mode="HTML")
    if not bad:
        spawn(sync_topics)


def ask_setup_team(m):
    """Nhom moi, da co doi khac gan nhom: chon doi cho nhom nay (doi dang o nhom khac thi chuyen sang) hoac tao doi moi."""
    states = team_states()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for t in muse_team.raw_teams():
        st = states.get(t["id"]) or {}
        where = (f" (đang ở nhóm {st.get('group_title') or st.get('group')} → chuyển sang đây)" if st.get("group")
                 else " (chưa có nhóm)")
        kb.add(types.InlineKeyboardButton((str(t.get("name") or t["id"]) + where)[:64],
                                          callback_data=f"{SETUP_DATA}{t['id']}"))
    kb.add(types.InlineKeyboardButton(f"➕ Tạo đội mới: {m.chat.title or 'nhóm này'}"[:64],
                                      callback_data=f"{SETUP_DATA}+"),
           types.InlineKeyboardButton("Huỷ", callback_data=SETUP_DATA))
    bot.reply_to(m, "👥 <b>Nhóm này dùng cho đội Muse nào?</b>\nMỗi đội làm việc trong 1 nhóm riêng (chỉ huy ở General, "
                    "mỗi profile 1 topic). Chọn đội có sẵn hoặc tạo đội mới; profile của đội chọn trên dashboard "
                    "FoxProfile → Đội Muse.", parse_mode="HTML", reply_markup=kb)


def on_setup_button(c):
    m = c.message
    if not is_admin(c.from_user):
        bot.answer_callback_query(c.id, "Chỉ chủ bot mới gắn được nhóm.")
        return
    try:
        bot.edit_message_reply_markup(m.chat.id, m.message_id, reply_markup=None)
    except Exception:
        logger.debug("Khong go duoc nut chon doi", exc_info=True)
    choice = c.data[len(SETUP_DATA):]
    if not choice:
        bot.answer_callback_query(c.id, "Đã huỷ.")
        return
    if choice == "+":
        try:
            tid = fox_api("POST", "/settings/muse-team/teams", json={"name": (m.chat.title or "Đội mới")[:60]})["id"]
        except Exception as e:
            logger.exception("Khong tao duoc doi moi tu Telegram")
            bot.answer_callback_query(c.id, "Lỗi, chưa tạo đội.")
            bot.send_message(m.chat.id, f"❌ Chưa tạo được đội mới: {html.escape(str(e))}", parse_mode="HTML")
            return
    elif choice in muse_team.team_ids():
        tid = choice
    else:
        bot.answer_callback_query(c.id, "Đội này không còn.")
        return
    bot.answer_callback_query(c.id, "Đã chọn đội.")
    with muse_team.in_team(tid):
        bind_group(m.chat.id, m.chat.title)
        finish_setup(m.chat.id, m.chat.title)


def teamed(fn):
    """Lenh / nut bam chay trong doi cua nhom gui tin (chat rieng / nhom chua gan: doi mac dinh)."""
    @functools.wraps(fn)
    def run(x):
        m = getattr(x, "message", None) or x
        chat = getattr(m, "chat", None)
        with muse_team.in_team(team_of_group(chat.id) if chat else None):
            return fn(x)
    return run


def register_handlers():
    @bot.message_handler(commands=["start", "help"])
    @teamed
    def _start(m):
        if m.chat.type != "private":
            bot.reply_to(m, "Mở chat riêng với bot và gõ /start để xem hướng dẫn. Gõ /setup ở đây để gắn nhóm này.")
            return
        if not admin_id():
            update_state(lambda state: state.__setitem__("admin", m.from_user.id))
            logger.info(f"Chu bot: {m.from_user.id}")
            bot.send_message(m.chat.id, "👋 <b>Chào bạn! Bạn đã là chủ của bot này.</b>\nTừ giờ chỉ bạn mới cấu hình "
                                        "được bot.", parse_mode="HTML")
        if not is_admin(m.from_user):
            bot.reply_to(m, "Bot này là bot riêng, bạn không có quyền dùng.")
            return
        bot.send_message(m.chat.id, "⏳ Đang kiểm tra...")
        bot.send_message(m.chat.id, status_text(), parse_mode="HTML")

    @bot.message_handler(commands=["setup"])
    @teamed
    def _setup(m):
        if m.chat.type not in ("group", "supergroup"):
            bot.reply_to(m, "Gõ /setup <b>trong nhóm</b> Telegram bạn muốn dùng (nhóm đã bật Chủ đề).",
                         parse_mode="HTML")
            return
        if not admin_id() and m.from_user:
            update_state(lambda state: state.__setitem__("admin", m.from_user.id))
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới gắn được nhóm.")
            return
        tid = team_of_group(m.chat.id)
        if tid:  # nhom da gan 1 doi: kiem tra lai quyen, dong bo topic
            with muse_team.in_team(tid):
                finish_setup(m.chat.id, m.chat.title, reply=m)
            return
        if not any(st.get("group") for t, st in team_states().items() if t in muse_team.team_ids()):
            with muse_team.in_team(muse_team.default_team()):  # nhom dau tien: gan doi mac dinh
                bind_group(m.chat.id, m.chat.title)
                finish_setup(m.chat.id, m.chat.title, reply=m)
            return
        ask_setup_team(m)

    @bot.message_handler(commands=["kiemtra"])
    @teamed
    def _kiemtra(m):
        if not is_admin(m.from_user):
            return
        bot.reply_to(m, "⏳ Đang kiểm tra IP các profile (mỗi profile ~10 giây)...")
        lines = []
        for profile in muse_sync.fox_profiles():
            with muse_team.in_team(team_of_profile(profile)):
                r = check_ip(profile, topics().get(profile))
            lines.append(f"{'🚫' if r and r[2] else '✅' if r else '❔'} {html.escape(profile)}: "
                         + (f"{html.escape(r[0])} ({html.escape(r[1])})" if r else "không kiểm tra được"))
        bot.send_message(m.chat.id, "🌐 <b>IP các profile</b>\n" + ("\n".join(lines) or "Chưa có profile nào."),
                         parse_mode="HTML", message_thread_id=topic_of(m))

    @bot.message_handler(commands=["allow_on", "allow_off"])
    @teamed
    def _allow(m):
        if not is_admin(m.from_user):
            return
        muse_auto.set_enabled(m.text.split()[0].split("@")[0] == "/allow_on")
        bot.reply_to(m, f"Tự bấm Allow trên Muse: {'BẬT' if muse_auto.enabled() else 'TẮT'}")

    @bot.message_handler(commands=["reset"])
    @teamed
    def _reset(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới reset được Muse.")
            return
        chat = target_for(m)
        arg = m.text.partition(" ")[2].strip()
        profile = chat["profile"] if chat else next((p for p in muse_sync.fox_profiles()
                                                     if p.casefold() == arg.casefold()), None) if arg else None
        if profile:
            with muse_team.in_team(team_of_profile(profile) if not chat else None):
                chief, _ = team_reset_people()
                if profile == chief:  # reset tu chi huy: ca doi, chon ngu canh thiet lap lai
                    if not chat and muse_team.current_team() != team_of_group(m.chat.id):
                        bot.reply_to(m, f"{html.escape(profile)} là chỉ huy đội "
                                        f"<b>{html.escape(muse_team.config()['name'])}</b>: gõ /reset ở mục General "
                                        f"của nhóm đội đó để reset cả đội.", parse_mode="HTML")
                        return
                    ask_team_reset(m)
                    return
            ask_reset(m, profile)
            return
        names = ", ".join(muse_sync.fox_profiles()) or "—"
        bot.reply_to(m, ("Không có profile tên " + html.escape(arg) + ". " if arg else "")
                     + "Gõ /reset trong <b>topic của profile</b> cần reset, hoặc <code>/reset tên_profile</code>.\n"
                       f"Các profile: {html.escape(names)}", parse_mode="HTML")

    @bot.message_handler(commands=["tach"])
    @teamed
    def _tach(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới tách được Muse khỏi đội.")
            return
        arg, chat = m.text.partition(" ")[2].strip(), target_for(m)
        if arg and not chat and m.chat.type == "private":  # chat rieng: doi cua Muse ghi ten
            match = next((p for p in muse_sync.fox_profiles() if p.casefold() == arg.casefold()), arg)
            muse_team.TEAM.set(team_of_profile(match))  # chi trong lenh nay (teamed dat lai sau)
        chief, workers = team_reset_people()
        if not chief:
            bot.reply_to(m, "Đội Muse đang ở chế độ Độc lập, không có đội để tách Muse ra.")
            return
        if arg:
            profile = next((p for p in workers + sorted(topics()) + [chief] if p.casefold() == arg.casefold()), arg)
        else:
            profile = chat["profile"] if chat and chat["profile"] != chief else None
        if profile:
            err = detach_check(profile)
            if err:
                bot.reply_to(m, err, parse_mode="HTML")
                return
            ask_detach(m, profile)
            return
        # o General / chat rieng khong ghi ten: chon Muse tu danh sach thanh vien
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(*[types.InlineKeyboardButton(w, callback_data=f"{DETACH_DATA}ask:{w}") for w in workers
                 if len(f"{DETACH_DATA}ask:{w}".encode()) <= 64])
        kb.add(types.InlineKeyboardButton("Huỷ", callback_data=f"{DETACH_DATA}no"))
        bot.send_message(m.chat.id, f"✂️ <b>Tách Muse nào khỏi đội?</b> (chỉ huy {html.escape(chief)})",
                         parse_mode="HTML", reply_markup=kb, message_thread_id=topic_of(m))

    @bot.message_handler(commands=["rebrand"])
    @teamed
    def _rebrand(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới rebrand được kênh.")
            return
        chat, arg = target_for(m), m.text.partition(" ")[2].strip()
        first, _, rest = arg.partition(" ")
        named = next((p for p in muse_sync.fox_profiles() if first and p.casefold() == first.casefold()), None)
        profile = named or (chat["profile"] if chat else None)
        note = rest.strip() if named else arg
        if not profile:
            names = ", ".join(muse_sync.fox_profiles()) or "—"
            bot.reply_to(m, "Gõ /rebrand trong <b>topic của profile</b>, hoặc <code>/rebrand tên_profile [định hướng "
                            "kênh mới]</code>.\nVd: <code>/rebrand Muse9 kênh hoạt hình rồng cho thiếu nhi</code>\n"
                            f"Các profile: {html.escape(names)}", parse_mode="HTML")
            return
        ask_rebrand(m, profile, note)

    @bot.message_handler(commands=["kenhmoi"])
    @teamed
    def _kenhmoi(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới đặt được lịch tạo kênh.")
            return
        kenhmoi_command(m)

    @bot.message_handler(commands=["dang"])
    @teamed
    def _dang(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới điều khiển được việc đăng bài.")
            return
        dang_command(m)

    @bot.message_handler(commands=["tiendo"])
    @teamed
    def _tiendo(m):
        if not (is_admin(m.from_user) or m.chat.id == group_id()):
            return
        here = team_of_group(m.chat.id)
        parts = []
        for tid in [here] if here else muse_team.team_ids():  # chat rieng: moi doi
            with muse_team.in_team(tid):
                tasks = load_state().get("tasks") or {}
                head = f"🏷 <b>{html.escape(muse_team.config()['name'])}</b>\n" if not here else ""
                parts.append(head + team_summary() + "\n\n📋 <b>Bảng việc</b>\n"
                             + html.escape(muse_team.board(tasks, 30 if here else 10)))
        bot.send_message(m.chat.id, "\n\n".join(parts)[:4000], parse_mode="HTML", message_thread_id=topic_of(m))

    @bot.message_handler(commands=["ketqua"])
    @teamed
    def _ketqua(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới xem được kết quả việc.")
            return
        tid = muse_team.task_id(m.text.partition(" ")[2])
        task = (load_state().get("tasks") or {}).get(tid) if tid else None
        if not task:
            bot.reply_to(m, "Gõ <code>/ketqua T8</code> (mã việc trong /tiendo).", parse_mode="HTML")
            return
        what, files = team_result_files(task)
        if not files:
            bot.reply_to(m, f"{tid} chưa có ảnh/video/file kết quả nào (hoặc file đã được dọn).")
            return
        pl = muse_team.part_label(task)
        caption = (f"{tid} ({task['to']}{', ' + pl if pl else ''}) — {what} · "
                   f"{muse_team.STATUS_LABEL.get(task['status'], task['status'])}")
        bot.reply_to(m, f"⏳ Đang gửi {len(files)} file của {tid}...")
        spawn(team_send_files, m, files, caption)

    @bot.message_handler(commands=["gan"])
    @teamed
    def _gan(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới gán được topic.")
            return
        if m.chat.type not in ("group", "supergroup"):
            bot.reply_to(m, "Gõ /gan <b>trong topic</b> của nhóm mà bạn muốn gán với một profile.", parse_mode="HTML")
            return
        if m.chat.id != group_id():
            bot.reply_to(m, "Nhóm này chưa gắn với bot. Gõ /setup trước.")
            return
        topic = topic_of(m)
        if topic is None:
            bot.reply_to(m, "Hãy gõ /gan trong một <b>topic</b> (không phải mục General).", parse_mode="HTML")
            return
        profiles = muse_team.group_profiles(muse_sync.fox_profiles())  # chi profile cua doi nhom nay
        if not profiles:
            bot.reply_to(m, "Đội của nhóm này chưa có profile nào (dashboard FoxProfile → Đội Muse).")
            return
        arg = m.text.partition(" ")[2].strip()
        name = arg or topic_name(m)
        match = next((p for p in profiles if name and p.casefold() == name.casefold()), None)
        if match:
            do_link(m.chat.id, topic, match)
            return
        why = (f"Không có profile tên <b>{html.escape(arg)}</b>." if arg
               else f"Không có profile trùng tên topic <b>{html.escape(name)}</b>." if name
               else "Bot không đọc được tên topic này.")
        choose_profile(m, topic, profiles, why)

    @bot.message_handler(content_types=CONTENT_TYPES)
    @teamed
    def _forward(m):
        if m.from_user and m.from_user.is_bot:
            return
        if (m.text or "").startswith("/"):
            return
        chat = target_for(m)
        if chat is None:
            if m.chat.type == "private":
                bot.reply_to(m, "Hãy nhắn tin trong <b>topic của profile</b> trong nhóm. Gõ /start để xem trạng thái.",
                             parse_mode="HTML")
            elif m.chat.id == group_id() and topic_of(m) is None:
                bot.reply_to(m, "ℹ️ Mục General chưa gắn Muse nào. Hãy nhắn trong topic mang tên profile, hoặc chọn 1 "
                                "Muse làm chỉ huy cả đội ở đây: dashboard FoxProfile → Đội Muse → Có chỉ huy.")
            elif m.chat.id == group_id():
                bot.reply_to(m, "ℹ️ Topic này không gắn với profile nào. Hãy nhắn trong topic mang tên profile.")
            return
        enqueue(m, chat, (m.text or m.caption or "").strip())

    @bot.callback_query_handler(func=lambda c: True)
    @teamed
    def _callback(c):
        if c.data == CHOSEN_DATA:
            bot.answer_callback_query(c.id, "Đã chọn rồi.")
        elif c.data.startswith(RESET_DATA):
            on_reset_button(c)
        elif c.data.startswith(TEAM_RESET_DATA):
            on_team_reset_button(c)
        elif c.data.startswith(DETACH_DATA):
            on_detach_button(c)
        elif c.data.startswith(LINK_DATA):
            on_link_button(c)
        elif c.data.startswith(APPROVE_DATA):
            on_approve_button(c)
        elif c.data.startswith(SETUP_DATA):
            on_setup_button(c)
        elif c.data.startswith(TEAM_DATA):
            on_team_button(c)
        elif c.data.startswith(POST_DATA):
            on_post_button(c)
        elif c.data.startswith(REBRAND_DATA):
            on_rebrand_button(c)
        elif c.data.startswith(DANG_DATA):
            on_dang_button(c)
        else:
            choose(c)


def console_guide(problem):
    """Huong dan tren cua so console khi chua co / sai token."""
    if not ENV_FILE.exists() and (ROOT / ".env.example").exists():
        shutil.copy(ROOT / ".env.example", ENV_FILE)
    print(f"""
==================================================================
  {problem}
==================================================================
  1. Mo Telegram, tim @BotFather, gui /newbot, dat ten cho bot.
  2. BotFather gui lai 1 dong token dang 123456789:ABC-xyz...
  3. File .env vua duoc mo bang Notepad. Dan token vao sau dau =
       TELEGRAM_BOT_TOKEN=123456789:ABC-xyz...
     roi bam Ctrl+S de luu.
  4. Dong cua so nay va chay lai start_all.bat.
  (File .env nam o: {ENV_FILE})
==================================================================
""")
    try:
        subprocess.Popen(["notepad.exe", str(ENV_FILE)])
    except Exception:
        pass
    input("Bam Enter de thoat...")
    sys.exit(1)


def main():
    ctypes.windll.kernel32.SetConsoleTitleW(TITLE)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    main.mutex = kernel32.CreateMutexW(None, False, "Local\\" + TITLE)
    if ctypes.get_last_error() == 183:
        raise SystemExit("Bot dang chay o cua so khac -- thoat")
    if not TOKEN:
        console_guide("CHUA CO TOKEN BOT TELEGRAM")
    try:
        me = bot.get_me()
    except ApiTelegramException:
        console_guide("TOKEN BOT TELEGRAM SAI (kiem tra lai dong TELEGRAM_BOT_TOKEN trong .env)")
    except requests.RequestException as e:
        raise SystemExit(f"Khong ket noi duoc Telegram: {e}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for p in UPLOAD_DIR.iterdir():  # file tam con sot khi bot tat giua chung
        if p.is_dir() and re.fullmatch(r"-?\d+_\d+", p.name):
            shutil.rmtree(p, ignore_errors=True)
    register_handlers()
    set_commands()
    clear_stale_activity()
    for target in (worker, watch_loop, topics_loop, reconcile_loop, team_loop, startup_report):
        threading.Thread(target=target, daemon=True).start()
    threading.Thread(target=muse_auto.loop,
                     args=(lambda: [c["profile"] for c in mapped_chats()], lambda p, ctx: logger.info(f"Auto Allow ({p}): {ctx[:300]}")),
                     daemon=True).start()
    if not admin_id():
        print(f"\n>>> Mo Telegram, tim @{me.username} va gui /start de bat dau cau hinh. <<<\n")
    logger.info(f"Bot @{me.username} da chay.")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()
