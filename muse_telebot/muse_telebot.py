# -*- coding: utf-8 -*-
"""
Bot Telegram <-> muse.ai qua FoxProfile.

  - 1 nhom Telegram bat Chu de (Topics) = noi quan ly cac profile FoxProfile. Moi profile 1 topic (ten = ten profile).
  - Profile dang mo va da dang nhap muse.ai ma chua co topic: bot tu tao topic (topics_loop).
  - Telegram -> Muse: tin / anh / video / gif / file / audio trong topic duoc go vao main chat muse.ai cua profile
    (muse_sync.py), nguyen van. Album gom thanh 1 tin. Reply 1 tin thi trich tin goc o dau.
  - Muse -> Telegram: bot doc tra loi cua Muse tren trang (chu + anh/video/file) va gui ve topic (relay ngay sau khi
    gui tin; watch moi WATCH_INTERVAL giay cho tin Muse tu viet / go tren web). Dong "[[nút: A | B]]" cuoi tin thanh
    nut bam; bam nut thi lua chon duoc gui lai vao Muse.
  - /reset (chu bot): bam nut xac nhan -> xoa toan bo du lieu Muse cua profile (Settings -> Data controls -> Reset
    <ten agent>, bot tu doc ten agent), xoa topic cu, tao topic moi cung ten, dat ten agent = ten profile.
  - Ten agent: agent con ten mac dinh "Muse" thi khi tao topic / /gan bot gui "Change your name to <profile>".
  - Khoi dong / /start: bot kiem tra tung buoc cau hinh va huong dan nguoi dung; canh bao profile dung IP Viet Nam.

Trang thai (muse_telebot_state.json, bot tu tao):
    {"admin": <user id chu bot>, "group": <chat id nhom>, "topics": {"<profile>": <topic id>},
     "delivered": {"<profile>": [id tin Muse da chuyen]}, "watched": ["<profile>"]}

.env (thu muc goc Muse2tele): TELEGRAM_BOT_TOKEN, MUSE_UPLOAD_DIR (phai nam trong FOXPROFILE_UPLOAD_DIRS).
"""

import ctypes
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
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from types import SimpleNamespace

import requests
import telebot
from dotenv import load_dotenv
from telebot import types
from telebot.apihelper import ApiTelegramException

import muse_auto
import muse_sync
from muse_sync import HERE

TITLE = "Muse2tele_Bot"
ROOT = HERE.parent
ENV_FILE = ROOT / ".env"
load_dotenv(HERE / ".env")
load_dotenv(ENV_FILE)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
UPLOAD_DIR = Path(os.environ.get("MUSE_UPLOAD_DIR", str(ROOT / "Videos" / "downloads" / "muse_telebot")))
STATE_FILE = HERE / "muse_telebot_state.json"
TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024  # getFile cua Bot API
TG_UPLOAD_LIMIT = 50 * 1024 * 1024  # gui file qua Bot API
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
WATCH_INTERVAL = 5
WATCH_WORKERS = 4
WATCH_RETRY_SECONDS = 60
DELIVERED_KEEP = 200
MEDIA_RELOAD_SECONDS = 20
MEDIA_RELOAD_GAP = 90
MEDIA_MISSING_WAIT = 240
TOPICS_CHECK_SECONDS = 30  # quet profile moi dang nhap Muse
IP_CHECK_SECONDS = 6 * 3600  # kiem tra lai IP cac profile
UPDATE_CHECK_SECONDS = 6 * 3600  # hoi FoxProfile co ban Muse2Tele moi tren GitHub khong
STALL_RETRY_SECONDS = 60
STALL_GIVE_UP_SECONDS = 30 * 60
WATCH_HANG_SECONDS = 180
MUSE_DOWN_TEXT = "⏳ Muse đang gặp lỗi, bot sẽ tự gửi lại tin này khi Muse hoạt động trở lại."
CHOSEN_DATA = "muse_bridge_chosen"
RESET_DATA = "muse_reset:"  # + "go:<profile>" / "no"
LINK_DATA = "muse_link:"  # + "<profile>" / "" (huy): nut chon profile cua /gan
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
state_lock = threading.Lock()
stalled = {}
stalled_lock = threading.Lock()
ip_results = {}  # profile -> (ip, quoc gia, la VN)
ip_warned = {}  # profile -> luc canh bao IP VN gan nhat


# ---------- trang thai ----------

def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def update_state(change):
    with state_lock:
        state = load_state()
        result = change(state)
        save_state(state)
        return result


def admin_id():
    return load_state().get("admin")


def group_id():
    return load_state().get("group")


def topics():
    """profile -> topic id."""
    return {p: int(t) for p, t in (load_state().get("topics") or {}).items()}


def chat_of(profile, topic):
    """Chat muse (main chat cua profile) map voi 1 topic."""
    return {"profile": profile, "url": muse_sync.MUSE_URL, "tg": f"{group_id()}/{topic}", "key": profile}


def mapped_chats():
    return [chat_of(p, t) for p, t in topics().items()]


def topic_of(m):
    return m.message_thread_id if getattr(m, "is_topic_message", False) else None


def target_for(m):
    """Chat muse nhan tin m: topic cua 1 profile trong nhom da cai dat."""
    if m.chat.id != group_id():
        return None
    topic = topic_of(m)
    profile = next((p for p, t in topics().items() if t == topic), None)
    return chat_of(profile, topic) if profile else None


def is_admin(user):
    return bool(user) and user.id == admin_id()


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
    path.write_bytes(bot.download_file(info.file_path))
    return str(path)


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
        if files or text.strip():
            base = batch[0].setdefault("base", set())
            ok, result = muse_sync.send(chat, text, files, seen=seen, base=base)
            muse_down = not ok and not errors
        else:
            ok, result = False, "không có gì để gửi"
        if errors:
            ok, result = False, f"{result}\nKhông tải được: " + "; ".join(errors)
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
        remember_sent(chat, first, text)
        relay(chat, first, seen)
        return True
    safe_reply(first, f"⚠️ Chưa gửi được cho Muse: {result}")
    return True


def remember_sent(chat, m, text):
    """Ghi tin cuoi da gui vao Muse de doi soat (reconcile_loop kiem tra no con tren Muse khong)."""
    entry = {"mid": m.message_id, "chat_id": m.chat.id, "topic": topic_of(m), "text": text,
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
        try:
            if job["kind"] == "stalled":
                run_stalled(job["key"])
            elif job["kind"] == "reset":
                run_reset(job)
            elif job["kind"] == "name":
                name_agent(job["profile"], job["topic"])
            elif job["kind"] == "ask":
                seen = set()
                ok, result = muse_sync.send(job["chat"], job["text"], seen=seen)
                logger.info(f"Hoi link video {job['chat']['key']}: {result}")
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


def enqueue(m, chat, text, kind="msg"):
    logger.info(f"Nhan TG {m.message_id} ({kind}/{getattr(m, 'content_type', '?')}) -> {chat['key']}: {text[:150]!r}")
    jobs.put({"kind": kind, "m": m, "chat": chat, "text": text})
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
    threading.Thread(target=relay_loop, args=(chat, r), daemon=True).start()


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


class TooLarge(Exception):
    pass


ASK_LINK = ('Video "{title}" không gửi được qua Telegram ({why}). Hãy gửi lại link tải công khai cho video này '
            '(dạng https://muse.ai/files/...).')


def ask_link(chat, target, title, why):
    """Video Muse khong gui duoc ve Telegram: nho worker nhan Muse gui link tai (worker giu thu tu, khong chan relay)."""
    jobs.put({"kind": "ask", "chat": chat, "target": target, "text": ASK_LINK.format(title=title, why=why)})


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
    if kind == "image":
        try:
            return upload(bot.send_photo)
        except ApiTelegramException as e:
            logger.info(f"send_photo {name}: {e}; gui dang file")
    return upload(bot.send_document)


def send_reply(fox, msg, target, key, chat=None):
    """Gui 1 tin cua Muse (chu + nut bam + anh/video/file) ve topic."""
    logger.info(f"Gui ve TG {key}: tin Muse {msg['id'][:30]} ({len(msg.get('text') or '')} ky tu, "
                f"{len(msg.get('media') or [])} anh/video/file): {(msg.get('text') or '')[:100]!r}")
    text, kb = msg.get("html") or html.escape(msg["text"]), None
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
    if text:
        send_text(target, text, kb)
    for a in msg["media"]:
        kind = a["kind"] if a["kind"] in KIND_LABEL else "file"
        title = re.sub(r"^Open (?:generated|animated) (?:image|video)\s*", "", a["title"]).strip()
        base = re.sub(r'[\\/:*?"<>|\s]+', "_", title)[:60] or f"muse_{kind}"
        if not a["src"] and a["kind"] != "file":
            logger.info(f"{key}: khong tai duoc {a['kind']} {title!r} (lost={a.get('lost')})")
            if a["kind"] == "missing":
                why = ("Muse không còn file này" if a.get("lost")
                       else f"Muse không nạp được file sau {MEDIA_MISSING_WAIT // 60} phút")
                send_text(target, f"📎 <b>{html.escape(title or base)}</b>: {why}. Nhắn Muse gửi lại nhé.")
                continue
            send_text(target, f"{'🎵' if a['kind'] == 'audio' else '📎'} <b>{html.escape(title or base)}</b> "
                              f"({html.escape(a['kind'])}): bot không tải được file này, mở Muse để nghe / xem.")
            continue
        try:
            if a["kind"] == "file":
                content = muse_sync.fetch_file(fox, msg["id"], a.get("name") or "")
                if content is None:
                    raise ValueError("khung xem file cua Muse khong co noi dung chu")
                data, mime = content.encode("utf-8"), a.get("mime") or "text/plain"
            else:
                data, mime = muse_sync.fetch_media(fox, a["src"])
            if kind == "video" and not mime.startswith("video/"):
                raise ValueError(f"tai ve {mime or 'rong'} ({len(data)} byte), khong phai video")
            name = re.sub(r'[\\/:*?"<>|\s]+', "_", a.get("name") or "") or base + (mimetypes.guess_extension(mime) or "")
            send_media(target, kind, data, name, title[:1000] or None)
            logger.info(f"{key}: da gui {kind} {name} ({len(data) // 1024} KB) ve TG")
            del data
        except Exception as e:
            if kind == "video" and isinstance(e, (TooLarge, requests.RequestException, ApiTelegramException)):
                why = str(e) if isinstance(e, TooLarge) else "lỗi mạng khi tải lên Telegram"
                logger.warning(f"{key}: video {title or base} khong gui duoc ({e})")
                linked = a["src"].startswith("http")  # video lay tu link tai: gui link, khong hoi lai (tranh lap)
                try:
                    send_text(target, f"⚠️ Video <b>{html.escape(title or base)}</b>: {html.escape(why)}. "
                              + (f'Tải tại: <a href="{html.escape(a["src"])}">link</a>' if linked
                                 else "Bot đã nhờ Muse gửi link tải."))
                except Exception:
                    logger.exception("Khong bao duoc loi gui video")
                if not linked and chat:
                    ask_link(chat, target, title or base, why)
                continue
            logger.exception(f"Khong chuyen duoc {kind} {title or a['src']} ve Telegram")
            try:
                send_text(target, f"⚠️ Không gửi được {KIND_LABEL.get(kind, 'file')} "
                                  f"<b>{html.escape(title or base)}</b>: {html.escape(type(e).__name__)}")
            except Exception:
                logger.exception("Khong bao duoc loi gui file")


def deliver_new(fox, chat, r, target, busy):
    """Gui ve Telegram cac tin moi cua Muse da viet xong. Tra ve True neu con tin dang viet / dang tai."""
    # Tin da chuyen (ghi trong state) bo qua ngay: sau khi bot khoi dong lai r["seen"] rong, tin cu khong chu luc Muse
    # dang ban se lam vong nay dung cho mai, khong toi duoc tin moi phia sau.
    delivered = set((load_state().get("delivered") or {}).get(chat["key"], []))
    for msg in muse_sync.messages(fox):
        if msg["role"] != "assistant" or msg["id"] in r["seen"]:
            continue
        if msg["id"] in delivered:
            r["seen"].add(msg["id"])
            continue
        if msg["streaming"]:
            return True
        loading = any(not a["src"] and a["kind"] in KIND_LABEL for a in msg["media"])
        unfound = any(a["kind"] == "missing" and not a.get("lost") for a in msg["media"])
        waited = time.time() - r["waiting"].setdefault(msg["id"], time.time()) if loading or unfound else 0
        if loading or unfound and waited < MEDIA_MISSING_WAIT:
            if waited > MEDIA_RELOAD_SECONDS and time.time() - r["reloaded"] > MEDIA_RELOAD_GAP:
                logger.info(f"{chat['key']}: anh/video chua nap sau {waited:.0f}s, tai lai trang")
                r["reloaded"] = time.time()
                muse_sync.reload_chat(fox, chat["url"])
            return True
        if not msg["text"] and not msg["media"] and not msg.get("choices"):
            if busy:
                return True
            r["seen"].add(msg["id"])
            continue
        r["seen"].add(msg["id"])
        if not claim(chat["key"], msg["id"]):
            continue
        try:
            send_reply(fox, msg, target, chat["key"], chat)
        except Exception as e:
            if "thread not found" in str(e).lower():  # nguoi dung da xoa topic: bo map, bot se tao topic moi
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
            busy = muse_sync.is_busy(fox)
            pending = deliver_new(fox, chat, r, target, busy)
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
        try:
            bot.send_chat_action(target.chat.id, "typing", message_thread_id=topic_of(target))
        except Exception as e:
            logger.debug(f"send_chat_action: {e}")
    minutes = int((time.time() - start) // 60)
    logger.info(f"{chat['key']}: Muse {'xong' if done else 'chua xong'} sau {time.time() - start:.0f}s")
    for m in targets:
        if done:
            react(m, "👌")
        else:
            why = f"không đọc được trả lời của Muse ({error})" if errors else "Muse vẫn đang làm"
            safe_reply(m, f"⏳ {why} sau {minutes} phút, bot ngừng chờ. Câu trả lời đến sau vẫn sẽ được gửi về đây.")


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
    deliver_new(fox, chat, r, tg_target(chat["tg"]), muse_sync.is_busy(fox))


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

            if not group_id():
                continue
            chats = mapped_chats()
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
                active[key] = (chat, pool.submit(watch_chat, chat, r, {}))


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
    threading.Thread(target=check_ip, args=(profile, topic), daemon=True).start()
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
    jobs.put({"kind": "reset", "m": m, "chat": {"key": profile, "profile": profile}, "profile": profile})


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
    jobs.put({"kind": "name", "chat": {"key": profile, "profile": profile}, "profile": profile, "topic": topic})


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
    """Profile dang mo + da dang nhap Muse ma chua co topic: tao topic ten = ten profile."""
    group = group_id()
    if not group:
        return
    existing = muse_sync.fox_profiles()
    mapped = topics()
    for profile in [p for p in mapped if p not in existing]:  # profile da xoa khoi FoxProfile
        forget_topic(profile)
        notify(f"ℹ️ Profile {profile} không còn trong FoxProfile, bot ngừng đồng bộ topic của nó.")
    for profile in existing:
        if profile in mapped:
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


def _on_muse(msgs, text):
    want = muse_sync._flat(text)[:60]
    return any(m["role"] == "user" and not m.get("failed") and want in muse_sync._flat(m.get("text")) for m in msgs)


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
    if not ls or not ls.get("text") or ls.get("verified"):
        return muse_tg, "ok" if ls else "-"
    if time.time() - ls["at"] < RECONCILE_GRACE:
        return muse_tg, "cho"
    found = _on_muse(msgs, ls["text"])
    if not found:  # trang co the dang o tab khac / tin tam: tai lai trang (du lieu that tren server) roi xem lai
        muse_sync.reload_chat(fox, chat["url"])
        found = _on_muse(muse_sync.messages(fox), ls["text"])
    if found:
        update_state(lambda s: s["last_sent"][key].update(verified=True))
        logger.info(f"Doi soat {key}: tin TG {ls['mid']} da co tren Muse")
        return muse_tg, "ok"
    target = SimpleNamespace(chat=SimpleNamespace(id=ls["chat_id"]), message_thread_id=ls["topic"],
                             is_topic_message=bool(ls["topic"]))
    if ls.get("resends", 0) >= RECONCILE_RESEND_MAX:
        update_state(lambda s: s["last_sent"][key].update(verified=True))
        logger.error(f"Doi soat {key}: tin TG {ls['mid']} van khong co tren Muse sau {RECONCILE_RESEND_MAX} lan gui lai")
        safe_reply(target, f"⚠️ Muse vẫn chưa nhận tin này sau {RECONCILE_RESEND_MAX} lần gửi lại, bạn gửi lại giúp: "
                           f"{ls['text'][:300]}")
        return muse_tg, "BO"
    logger.warning(f"Doi soat {key}: tin TG {ls['mid']} KHONG co tren Muse -> gui lai (lan {ls.get('resends', 0) + 1})")
    seen = set()
    ok, result = muse_sync.send(chat, ls["text"], seen=seen)
    logger.info(f"Gui lai TG {ls['mid']} -> {key}: {result}")
    update_state(lambda s: s["last_sent"][key].update(resends=ls.get("resends", 0) + 1, at=time.time()))
    if ok:
        safe_reply(target, "🔁 Muse chưa nhận tin trước của bạn (lỗi Delivery not confirmed), bot đã gửi lại.")
        relay(chat, target, seen)
    return muse_tg, "GUI LAI" if ok else "LOI"


def reconcile_loop():
    runs = {}
    while True:
        time.sleep(RECONCILE_SECONDS)
        if not group_id():
            continue
        summary = []
        for chat in mapped_chats():
            key = chat["key"]
            if not _idle(key):
                summary.append(f"{key}=ban")
                continue
            try:
                a, b = reconcile_chat(chat, runs)
                summary.append(f"{key}={a}/{b}")
            except Exception as e:
                summary.append(f"{key}=loi")
                logger.warning(f"Doi soat {key} loi: {type(e).__name__}: {e}")
        logger.info("Doi soat (Muse->TG / TG->Muse): " + ", ".join(summary))


def topics_loop():
    last_ip = 0
    last_update = time.time() - UPDATE_CHECK_SECONDS + 120  # lan dau: 2 phut sau khi bot chay
    while True:
        try:
            sync_topics()
        except Exception as e:
            logger.warning(f"Tu tao topic loi: {type(e).__name__}: {e}")
        if time.time() - last_ip >= IP_CHECK_SECONDS:
            last_ip = time.time()
            for profile, topic in topics().items():
                check_ip(profile, topic)
        if time.time() - last_update >= UPDATE_CHECK_SECONDS:
            last_update = time.time()
            check_update()
        time.sleep(TOPICS_CHECK_SECONDS)


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
    group = group_id()
    if not group:
        steps.append((False, "Chưa gắn nhóm Telegram", GROUP_HELP.format(bot=me.username)))
    else:
        try:
            chat = bot.get_chat(group)
            member = bot.get_chat_member(group, me.id)
            forum = bool(getattr(chat, "is_forum", False))
            can_topics = member.status == "creator" or (member.status == "administrator"
                                                        and getattr(member, "can_manage_topics", False))
            steps.append((forum, f"Nhóm <b>{html.escape(chat.title or str(group))}</b> đã bật Chủ đề (Topics)",
                          "Mở nhóm → bấm tên nhóm → ✏️ Sửa → bật <b>Chủ đề (Topics)</b>."))
            steps.append((can_topics, "Bot là quản trị viên nhóm, có quyền Quản lý chủ đề",
                          f"Mở nhóm → bấm tên nhóm → Quản trị viên → Thêm quản trị viên → chọn @{me.username} → "
                          f"bật quyền <b>Quản lý chủ đề (Manage topics)</b> → Lưu."))
        except Exception as e:
            steps.append((False, "Bot không vào được nhóm đã gắn",
                          f"Thêm lại @{me.username} vào nhóm rồi gõ /setup trong nhóm. ({html.escape(str(e))})"))
    if profiles is not None:
        mapped = topics()
        steps.append((bool(mapped), f"Đã có {len(mapped)} topic profile: {html.escape(', '.join(mapped)) or '—'}",
                      "Trong FoxProfile: tạo profile (gắn proxy nước ngoài), bấm mở profile, đăng nhập "
                      "<b>muse.ai</b>. Khoảng 1 phút sau bot tự tạo topic cùng tên profile trong nhóm."))
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
    ("reset", "Xoá toàn bộ dữ liệu Muse của 1 profile và topic của nó (có nút xác nhận)", "both"),
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


def register_handlers():
    @bot.message_handler(commands=["start", "help"])
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
        old = group_id()
        update_state(lambda state: state.update({"group": m.chat.id, **({"topics": {}, "watched": []}
                                                                          if old and old != m.chat.id else {})}))
        logger.info(f"Gan nhom {m.chat.id} ({m.chat.title})")
        me = bot.get_me()
        member = bot.get_chat_member(m.chat.id, me.id)
        can_topics = member.status == "creator" or (member.status == "administrator"
                                                    and getattr(member, "can_manage_topics", False))
        bad = [(t, how) for done, t, how in [
            (bool(getattr(bot.get_chat(m.chat.id), "is_forum", False)), "Nhóm chưa bật Chủ đề (Topics)",
             "Bấm tên nhóm → ✏️ Sửa → bật <b>Chủ đề (Topics)</b>."),
            (can_topics, "Bot chưa có quyền Quản lý chủ đề",
             f"Bấm tên nhóm → Quản trị viên → Thêm quản trị viên → chọn @{me.username} → bật "
             f"<b>Quản lý chủ đề</b> → Lưu.")] if not done]
        if bad:
            bot.reply_to(m, "⚠️ Đã gắn nhóm nhưng còn thiếu:\n" + "\n".join(f"❌ {t}\n👉 {how}" for t, how in bad)
                         + "\n\nSửa xong gõ lại /setup.", parse_mode="HTML")
            return
        bot.reply_to(m, "✅ <b>Đã gắn nhóm này với bot.</b>\nMở profile trong FoxProfile và đăng nhập muse.ai, "
                        "khoảng 1 phút sau bot tự tạo topic cho profile.", parse_mode="HTML")
        threading.Thread(target=sync_topics, daemon=True).start()

    @bot.message_handler(commands=["kiemtra"])
    def _kiemtra(m):
        if not is_admin(m.from_user):
            return
        bot.reply_to(m, "⏳ Đang kiểm tra IP các profile (mỗi profile ~10 giây)...")
        lines = []
        for profile in muse_sync.fox_profiles():
            r = check_ip(profile, topics().get(profile))
            lines.append(f"{'🚫' if r and r[2] else '✅' if r else '❔'} {html.escape(profile)}: "
                         + (f"{html.escape(r[0])} ({html.escape(r[1])})" if r else "không kiểm tra được"))
        bot.send_message(m.chat.id, "🌐 <b>IP các profile</b>\n" + ("\n".join(lines) or "Chưa có profile nào."),
                         parse_mode="HTML", message_thread_id=topic_of(m))

    @bot.message_handler(commands=["allow_on", "allow_off"])
    def _allow(m):
        if not is_admin(m.from_user):
            return
        muse_auto.set_enabled(m.text.split()[0].split("@")[0] == "/allow_on")
        bot.reply_to(m, f"Tự bấm Allow trên Muse: {'BẬT' if muse_auto.enabled() else 'TẮT'}")

    @bot.message_handler(commands=["reset"])
    def _reset(m):
        if not is_admin(m.from_user):
            bot.reply_to(m, "Chỉ chủ bot mới reset được Muse.")
            return
        chat = target_for(m)
        arg = m.text.partition(" ")[2].strip()
        profile = chat["profile"] if chat else next((p for p in muse_sync.fox_profiles()
                                                     if p.casefold() == arg.casefold()), None) if arg else None
        if profile:
            ask_reset(m, profile)
            return
        names = ", ".join(muse_sync.fox_profiles()) or "—"
        bot.reply_to(m, ("Không có profile tên " + html.escape(arg) + ". " if arg else "")
                     + "Gõ /reset trong <b>topic của profile</b> cần reset, hoặc <code>/reset tên_profile</code>.\n"
                       f"Các profile: {html.escape(names)}", parse_mode="HTML")

    @bot.message_handler(commands=["gan"])
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
        profiles = muse_sync.fox_profiles()
        if not profiles:
            bot.reply_to(m, "FoxProfile chưa có profile nào.")
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
            elif m.chat.id == group_id():
                bot.reply_to(m, "ℹ️ Topic này không gắn với profile nào. Hãy nhắn trong topic mang tên profile.")
            return
        enqueue(m, chat, (m.text or m.caption or "").strip())

    @bot.callback_query_handler(func=lambda c: True)
    def _callback(c):
        if c.data == CHOSEN_DATA:
            bot.answer_callback_query(c.id, "Đã chọn rồi.")
        elif c.data.startswith(RESET_DATA):
            on_reset_button(c)
        elif c.data.startswith(LINK_DATA):
            on_link_button(c)
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
    for target in (worker, watch_loop, topics_loop, reconcile_loop, startup_report):
        threading.Thread(target=target, daemon=True).start()
    threading.Thread(target=muse_auto.loop,
                     args=(lambda: list(topics()), lambda p, ctx: logger.info(f"Auto Allow ({p}): {ctx[:300]}")),
                     daemon=True).start()
    if not admin_id():
        print(f"\n>>> Mo Telegram, tim @{me.username} va gui /start de bat dau cau hinh. <<<\n")
    logger.info(f"Bot @{me.username} da chay.")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()
