# -*- coding: utf-8 -*-
"""
Video mau: chu gui link video (Facebook / TikTok / YouTube / Instagram...) hoac file video -> bot tai ve, cat khung
hinh moi giay thanh anh ghep (goc trai ghi giay), dat ma M1, M2... va gui kem cho Muse. Muse khong tu mo duoc link
Facebook / TikTok (bi chan dang nhap), nen bot phai tai ho.

Doi Muse (muse_team.py): chi huy ghi "theo video mau M1" trong lenh giao -> bot dinh kem video + anh ghep cua M1 cho
Muse lam (giong cach nhac ma viec T5 de dinh kem bo nhan vat).

State: "samples": {"M1": {"id", "url", "video", "sheets", "meta", "created"}}, "sample_seq": N.
File: <UPLOAD_DIR>/mau/<ma>/ (video.mp4, sheet_1.jpg...). Giu SAMPLES_KEEP mau moi nhat / SAMPLES_KEEP_DAYS ngay.
"""

import hashlib
import re
import shutil
import subprocess
import time
from pathlib import Path

SAMPLE_REF_RE = re.compile(r"(?<![\w/])M(\d{1,4})\b")
# Link video tren mang xa hoi (chi link trong giong video: tranh tai nham link fanpage / trang ca nhan)
LINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)*(?:"
    r"(?:facebook|fb)\.com/(?:share/[rv]/|reel/|watch|[^\s/]+/videos/|video\.php|story\.php)"
    r"|fb\.watch/"
    r"|tiktok\.com/(?:@[^\s/]+/video/|t/|v/)|(?:vt|vm)\.tiktok\.com/"
    r"|douyin\.com/(?:video/)|v\.douyin\.com/"
    r"|youtube\.com/(?:shorts/|watch)|youtu\.be/"
    r"|instagram\.com/(?:reels?|p|tv)/"
    r"|(?:x|twitter)\.com/[^\s/]+/status/"
    r"|threads\.(?:net|com)/@[^\s/]+/post/"
    r")[^\s<>\"')\]]*", re.IGNORECASE)
MAX_LINKS = 2               # moi tin toi da 2 link video
MAX_SECONDS = 300           # video mau dai qua 5 phut / nang qua MAX_BYTES: khong tai ca video, chi lay khung hinh
MAX_BYTES = 60 * 1024 * 1024  # thang tu link (remote_sheets) de Muse tu xem va quyet dinh
GRAB_WORKERS = 6            # so ffmpeg lay khung hinh tu link chay cung luc
MAX_FRAMES = 48             # tong so khung hinh tren cac anh ghep
TILE_COLS, TILE_ROWS, TILE_WIDTH = 4, 2, 360
SAMPLES_KEEP = 50
SAMPLES_KEEP_DAYS = 14
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


class SampleError(Exception):
    pass


class _QuietLog:
    """yt-dlp van in 'ERROR: ...' ra console du quiet: loi da tra ve qua SampleError, bo dong in."""
    def debug(self, msg):
        pass

    warning = info = error = debug


def find_links(text):
    out = []
    for m in LINK_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;!?")
        if url not in out:
            out.append(url)
    return out[:MAX_LINKS]


def sample_refs(text):
    """Ma video mau nhac trong text: 'theo video mau M1' -> ['M1']."""
    out = []
    for m in SAMPLE_REF_RE.finditer(text or ""):
        sid = f"M{int(m.group(1))}"
        if sid not in out:
            out.append(sid)
    return out


def ffmpeg_exe():
    """ffmpeg trong PATH, khong co thi ban di kem imageio-ffmpeg (requirements). Khong co ca hai -> None."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _estimated_bytes(info):
    """Dung luong uoc tinh cua ban yt-dlp chon (hinh + tieng). Thieu so lieu -> 0 (cu tai thu)."""
    sizes = [f.get("filesize") or f.get("filesize_approx") or 0 for f in info.get("requested_formats") or [info]]
    return sum(sizes) if all(sizes) else 0


def download(url, folder):
    """Tai video tu link ve folder/video.<ext>. Tra ve (duong dan | None, meta, info yt-dlp). Video dai qua MAX_SECONDS
    / nang qua MAX_BYTES: khong tai ca video (None) - build() lay khung hinh thang tu link. Loi -> SampleError."""
    try:
        import yt_dlp
    except ImportError as e:
        raise SampleError("máy chưa cài yt-dlp (chạy setup.bat hoặc pip install yt-dlp)") from e
    ffmpeg = ffmpeg_exe()
    folder.mkdir(parents=True, exist_ok=True)
    opts = {"outtmpl": str(folder / "video.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True,
            "noprogress": True, "logger": _QuietLog(), "socket_timeout": 30, "retries": 2, "max_filesize": MAX_BYTES,
            # co ffmpeg: ghep hinh + tieng ban tot nhat (<= 1920 doc); khong co: ban lien san co tieng
            "format": ("bv*[height<=1920]+ba/b[height<=1920]/bv*+ba/b" if ffmpeg else "b[height<=1920]/b"),
            "merge_output_format": "mp4"}
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                entries = [e for e in info.get("entries") or [] if e]
                if not entries:
                    raise SampleError("link không có video")
                info = entries[0]
            if (info.get("duration") or 0) <= MAX_SECONDS and _estimated_bytes(info) <= MAX_BYTES:
                # file lon hon max_filesize (biet truoc dung luong): yt-dlp bo qua khong bao loi -> khong thay file
                info = ydl.process_ie_result(info, download=True) or info
    except SampleError:
        raise
    except Exception as e:
        msg = " ".join(str(e).replace("ERROR:", "").split())
        raise SampleError(msg[:300] or type(e).__name__) from e
    paths = [Path(d["filepath"]) for d in info.get("requested_downloads") or [] if d.get("filepath")]
    paths = [p for p in paths if p.is_file()] or sorted(p for p in folder.glob("video.*") if p.suffix in VIDEO_EXT)
    meta = {"title": info.get("title") or "", "uploader": info.get("uploader") or info.get("channel") or "",
            "description": info.get("description") or "", "duration": info.get("duration") or 0,
            "width": info.get("width") or 0, "height": info.get("height") or 0,
            "audio": (info.get("acodec") or "") not in ("", "none") or bool(info.get("requested_formats"))}
    return (paths[0] if paths else None), meta, info


def probe_duration(video, ffmpeg):
    """Thoi luong (giay) doc tu ffmpeg -i (khong can ffprobe). Khong doc duoc -> 0."""
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60).stderr
    except Exception:
        return 0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0


def make_sheets(video, folder, duration=0, cols=TILE_COLS, rows=TILE_ROWS, width=TILE_WIDTH, max_frames=MAX_FRAMES,
                prefix="sheet"):
    """Cat khung hinh deu theo thoi gian (toi da max_frames, moi giay 1 khung voi video ngan), ghep cols x rows moi anh,
    goc trai ghi giay. Tra ve [duong dan anh ghep]; khong co ffmpeg / Pillow -> []."""
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        return []
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []
    duration = duration or probe_duration(video, ffmpeg)
    if duration <= 0:
        return []
    fps = min(1.0, max_frames / duration)
    frames_dir = folder / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)
    try:
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                        "-vf", f"fps={fps:.6f},scale={width}:-2", "-q:v", "4", str(frames_dir / "f_%03d.jpg")],
                       capture_output=True, timeout=180, check=True)
        frames = sorted(frames_dir.glob("f_*.jpg"))[:max_frames]
        # khung thu n (tu 0) cua bo loc fps nam quanh giay n / fps
        labels = [f"{n / fps:.0f}s" if fps >= 0.999 else f"{n / fps:.1f}s" for n in range(len(frames))]
        return _tile(frames, labels, folder, cols, rows, width, prefix)
    except Exception:
        return []
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


def _tile(frames, labels, folder, cols, rows, width, prefix):
    """Ghep frames thanh anh cols x rows, goc trai moi o ghi labels[i]. Tra ve [duong dan anh ghep]."""
    from PIL import Image, ImageDraw, ImageFont
    if not frames:
        return []
    try:
        font = ImageFont.load_default(size=max(16, width * 28 // 360))
    except TypeError:  # Pillow cu
        font = ImageFont.load_default()
    per = cols * rows
    sheets = []
    for start in range(0, len(frames), per):
        tiles = [Image.open(f).convert("RGB") for f in frames[start:start + per]]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * cols, h * rows), "black")
        draw = ImageDraw.Draw(sheet)
        for i, tile in enumerate(tiles):
            x, y = (i % cols) * w, (i // cols) * h
            sheet.paste(tile.resize((w, h)), (x, y))
            label = labels[start + i]
            box = draw.textbbox((x + 8, y + 8), label, font=font)
            draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill="black")
            draw.text((x + 8, y + 8), label, fill="yellow", font=font)
        path = folder / f"{prefix}_{start // per + 1}.jpg"
        sheet.save(path, quality=85)
        sheets.append(str(path))
    return sheets


def clock(seconds):
    """4925 -> '1:22:05', 75 -> '1:15'."""
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def remote_sheets(info, folder, duration, max_frames=MAX_FRAMES):
    """Video qua dai / qua nang de tai: ffmpeg doc thang luong hinh tu link (chi tai doan quanh moi moc), lay max_frames
    khung rai deu ca video, ghep anh (goc trai ghi phut:giay). Tra ve [duong dan anh ghep]; loi / khong co ffmpeg -> []."""
    from concurrent.futures import ThreadPoolExecutor
    ffmpeg = ffmpeg_exe()
    stream = next((f for f in info.get("requested_formats") or [info]
                   if f.get("url") and f.get("vcodec") != "none"), None)
    if not (ffmpeg and stream and duration > 0):
        return []
    try:
        import PIL  # noqa: F401
    except ImportError:
        return []
    headers = "".join(f"{k}: {v}\r\n" for k, v in (stream.get("http_headers") or info.get("http_headers") or {}).items())
    times = [duration * (k + 0.5) / max_frames for k in range(max_frames)]
    frames_dir = folder / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)

    def grab(k):
        out = frames_dir / f"f_{k:03d}.jpg"
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{times[k]:.2f}"]
        cmd += ["-headers", headers] if headers else []
        cmd += ["-i", stream["url"], "-frames:v", "1", "-vf", f"scale={TILE_WIDTH}:-2", "-q:v", "4", str(out)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60)
        except Exception:
            pass
        return (out, times[k]) if out.is_file() else None

    try:
        with ThreadPoolExecutor(GRAB_WORKERS) as pool:
            got = [g for g in pool.map(grab, range(max_frames)) if g]
        return _tile([f for f, _ in got], [clock(t) for _, t in got], folder, TILE_COLS, TILE_ROWS, TILE_WIDTH,
                     "sheet")
    except Exception:
        return []
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


QA_COLS, QA_ROWS, QA_WIDTH, QA_MAX_FRAMES = 8, 4, 240, 64  # anh ghep kiem tra ket qua: 32 o / anh, mac dinh 1 giay 1 o


def qa_sheets(video, folder):
    """Anh ghep khung hinh video Muse nop (moi o 1 giay, 32 o / anh, toi da 2 anh) de chi huy so mat / toc / trang phuc
    tung giay voi anh tao hinh. Loi -> []."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return make_sheets(video, folder, 0, QA_COLS, QA_ROWS, QA_WIDTH, QA_MAX_FRAMES, "khung_hinh_ket_qua")


def build(sid, folder, url="", video_file=None):
    """Tao video mau sid trong folder: tai tu url (hoac chep video_file), lam anh ghep. Tra ve dict mau. Video qua
    dai / qua nang: khong co file video (video = ""), chi co anh ghep lay thang tu link + meta (meta["no_video"])."""
    if url:
        video, meta, info = download(url, folder)
        if video is None:
            meta["no_video"] = True
            sheets = remote_sheets(info, folder, meta.get("duration") or 0)
            if not sheets and not (meta["title"] or meta["description"]):
                raise SampleError("không tải được video (file quá nặng hoặc trang chặn tải) và không lấy được "
                                  "khung hình nào")
            return {"id": sid, "url": url, "video": "", "folder": str(folder), "sheets": sheets, "meta": meta,
                    "created": time.time()}
    else:
        folder.mkdir(parents=True, exist_ok=True)
        video = folder / ("video" + (Path(video_file).suffix.lower() or ".mp4"))
        shutil.copyfile(video_file, video)
        meta = {}
    sheets = make_sheets(video, folder, meta.get("duration") or 0)
    if not meta.get("duration"):
        ffmpeg = ffmpeg_exe()
        meta["duration"] = probe_duration(video, ffmpeg) if ffmpeg else 0
    return {"id": sid, "url": url, "video": str(video), "folder": str(folder), "sheets": sheets, "meta": meta,
            "created": time.time()}


def files(sample, limit):
    """File dinh kem cua 1 mau (video truoc, roi anh ghep), toi da limit file con tren may."""
    out = [f for f in [sample.get("video")] + list(sample.get("sheets") or []) if f and Path(f).is_file()]
    return out[:max(0, limit)]


def describe(sample, for_chief):
    """Doan chu bot noi them vao tin gui Muse: video mau la gi, dinh kem nhung gi."""
    meta, sid = sample.get("meta") or {}, sample["id"]
    src = f"từ link {sample['url']}" if sample.get("url") else "từ file chủ gửi"
    no_video = bool(meta.get("no_video"))
    lines = [f"[Bot: video mẫu {sid} {src}" + (" — video dài / nặng nên bot KHÔNG tải cả video]" if no_video
                                               else ", đã tải]")]
    who = meta.get("uploader")
    title = " ".join((meta.get("description") or meta.get("title") or "").split())
    if who or title:
        lines.append(f"- Nguồn: {who or '?'}" + (f' — "{title[:300]}"' if title else ""))
    shape = ""
    if meta.get("width") and meta.get("height"):
        w, h = meta["width"], meta["height"]
        shape = f", khung {w}x{h} ({'dọc' if h > w else 'ngang' if w > h else 'vuông'})"
    if meta.get("duration"):
        lines.append(f"- Thời lượng {meta['duration']:.0f} giây"
                     + (f" ({clock(meta['duration'])})" if meta["duration"] >= 60 else "") + shape
                     + (", có tiếng" if meta.get("audio") else "") + ".")
    n = len(sample.get("sheets") or [])
    if no_video:
        lines.append("- Đính kèm: KHÔNG có video gốc. "
                     + (f"Chỉ có {n} ảnh ghép khung hình lấy rải đều cả video (góc trái ghi phút:giây), không có "
                        f"tiếng / chuyển động." if n else "Bot cũng không lấy được khung hình nào: chưa ai xem được "
                        "nội dung, đừng đoán.")
                     + " Tự quyết định video này dùng được không, dùng đoạn nào; cần xem kỹ 1 đoạn thì nhờ chủ cắt "
                       "đoạn đó và gửi thẳng file.")
    else:
        lines.append("- Đính kèm: video gốc" + (f" + {n} ảnh ghép khung hình (mỗi ô 1 khung, góc trái ghi giây)"
                                                if n else "") + ".")
    if for_chief:
        lines.append(f"Làm theo mục \"LÀM VIDEO THEO VIDEO MẪU\" trong luật đội: phân tích + đánh giá mức A/B/C, gửi chủ "
                     f"duyệt phân kịch, rồi [[kichban: {sid} | ...]] và [[giao: cả đội | Làm video theo video mẫu "
                     f"{sid}]] — bot tự kèm kịch bản chốt, video, ảnh ghép, bộ nhân vật cho từng Muse.")
    else:
        lines.append("Xem kỹ " + ("ảnh ghép" if no_video else "video và ảnh ghép") + " trước khi phân tích hoặc làm.")
    return "\n".join(lines)


def register(state, sample):
    """Luu mau vao state, bo mau cu (qua SAMPLES_KEEP_DAYS ngay / ngoai SAMPLES_KEEP mau moi nhat) + thu muc cua no."""
    samples = state.setdefault("samples", {})
    samples[sample["id"]] = sample
    now = time.time()
    keep = sorted(samples.values(), key=lambda s: s.get("created", 0), reverse=True)[:SAMPLES_KEEP]
    keep_ids = {s["id"] for s in keep if now - s.get("created", 0) < SAMPLES_KEEP_DAYS * 86400}
    keep_ids.add(sample["id"])
    keep_ids |= set(state.get("scripts") or {})  # mau da co kich ban chot: giu (con giao viec theo mau nay)
    for sid in [k for k in samples if k not in keep_ids]:
        old = samples.pop(sid)
        folder = old.get("folder") or (Path(old["video"]).parent if old.get("video") else None)
        if folder:
            shutil.rmtree(folder, ignore_errors=True)


# ---------- kiem tra ky thuat video Muse nop (bot tu do, khong dua vao loi Muse / chi huy) ----------

SILENT_DB = -60.0           # mean_volume duoi muc nay coi nhu khong co tieng
DURATION_MIN_RATIO = 0.75   # video remake ngan hon 75% / dai hon 140% video mau: sai thoi luong
DURATION_MAX_RATIO = 1.4
SEGMENT_MIN_SECONDS = 3     # 1 doan (viec nhieu doan) ngan hon 3 giay: loi


def probe(video):
    """Thong so video doc tu 1 lan ffmpeg -i ... volumedetect: {duration, width, height, fps, audio, mean_db}.
    Khong co ffmpeg / loi -> {}."""
    ffmpeg = ffmpeg_exe()
    if not ffmpeg or not video or not Path(video).is_file():
        return {}
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(video), "-map", "0:a:0?",
                              "-af", "volumedetect", "-vn", "-f", "null", "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180).stderr
    except Exception:
        return {}
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "audio": False, "mean_db": None}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Stream #\S+.*?Video:.*?(\d{2,5})x(\d{2,5})", out)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?) fps", out)
    if m:
        info["fps"] = float(m.group(1))
    info["audio"] = bool(re.search(r"Stream #\S+.*?Audio:", out))
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", out)
    if m:
        info["mean_db"] = float(m.group(1))
    return info


def has_sound(info):
    return bool(info.get("audio")) and (info.get("mean_db") is None or info["mean_db"] > SILENT_DB)


def shape(info):
    w, h = info.get("width") or 0, info.get("height") or 0
    return "" if not (w and h) else "dọc" if h > w * 1.05 else "ngang" if w > h * 1.05 else "vuông"


def file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def target_of(sample):
    """Chuan ky thuat lay tu video mau: {id, duration, shape, sound}. Do lai file mau (meta link co the thieu)."""
    info = probe(sample.get("video") or "") if sample else {}
    meta = (sample or {}).get("meta") or {}
    return {"id": (sample or {}).get("id", ""), "duration": info.get("duration") or meta.get("duration") or 0,
            "shape": shape(info) or shape(meta), "sound": has_sound(info) if info else bool(meta.get("audio"))}


def check(video, target=None, segment=False, old_hashes=()):
    """Kiem tra 1 video nop. Tra ve (loi nang [chu], dong thong so [chu], md5). Loi nang = bot tra lai Muse lam lai
    ngay, khong can chi huy cham: trung file da nop, khong co tieng (mau co tieng / mac dinh), sai khung doc/ngang,
    sai thoi luong (viec 1 video theo mau)."""
    info = probe(video)
    digest = file_hash(video) if Path(video).is_file() else ""
    if not info:
        return [], "bot không đo được video (thiếu ffmpeg)", digest
    target = target or {}
    hard = []
    if digest and digest in old_hashes:
        hard.append("đây là file video ĐÃ NỘP trước đó (trùng từng byte) — phải làm video mới")
    if not info["width"]:
        hard.append("file không có hình (không phải video hợp lệ)")
    sound = has_sound(info)
    if target.get("sound", True) and not sound:
        hard.append("video KHÔNG có tiếng" + (" (có track nhưng im lặng)" if info["audio"] else
                                              " (không có track âm thanh)") + " — cần thoại / nhạc / tiếng động")
    if target.get("shape") and shape(info) and shape(info) != target["shape"]:
        hard.append(f"khung {shape(info)} {info['width']}x{info['height']}, mẫu là khung {target['shape']}")
    dur, want = info["duration"], target.get("duration") or 0
    if segment:
        if dur and dur < SEGMENT_MIN_SECONDS:
            hard.append(f"đoạn chỉ dài {dur:.1f} giây")
    elif want and dur and not (want * DURATION_MIN_RATIO <= dur <= want * DURATION_MAX_RATIO):
        hard.append(f"dài {dur:.0f} giây, mẫu {want:.0f} giây (cho phép {want * DURATION_MIN_RATIO:.0f}–"
                    f"{want * DURATION_MAX_RATIO:.0f} giây)")
    line = (f"{dur:.1f} giây, {info['width']}x{info['height']} ({shape(info) or '?'}), {info['fps']:g} fps, "
            + ("có tiếng" if sound else "KHÔNG có tiếng")
            + (f" (âm lượng TB {info['mean_db']:.0f} dB)" if info.get("mean_db") is not None else ""))
    return hard, line, digest


def last_frame(video, out):
    """Khung hinh cuoi cua video -> out (jpg). Dung lam diem noi cho doan sau. Loi -> None."""
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        return None
    try:
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-sseof", "-0.3", "-i", str(video),
                        "-frames:v", "1", "-q:v", "2", "-update", "1", str(out)], capture_output=True, timeout=60)
    except Exception:
        return None
    return str(out) if Path(out).is_file() and Path(out).stat().st_size else None


def concat(videos, out):
    """Noi cac doan video (co the khac do phan giai / fps / co-khong tieng) thanh 1 file mp4, khung theo doan dau.
    Tra ve (duong dan | None, loi)."""
    ffmpeg = ffmpeg_exe()
    if not ffmpeg:
        return None, "máy chưa có ffmpeg"
    infos = [probe(v) for v in videos]
    if not infos or not all(i.get("width") for i in infos):
        return None, "có đoạn không đọc được hình"
    w, h = infos[0]["width"] // 2 * 2, infos[0]["height"] // 2 * 2
    cmd, chains = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"], []
    for v in videos:
        cmd += ["-i", str(v)]
    for k, info in enumerate(infos):
        chains.append(f"[{k}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                      f"setsar=1,fps=30,format=yuv420p[v{k}]")
        if info.get("audio"):
            chains.append(f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo[a{k}]")
        else:  # doan khong co tieng: chen im lang dung bang thoi luong
            chains.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{info['duration'] or 0.1:.3f}[a{k}]")
    chains.append("".join(f"[v{k}][a{k}]" for k in range(len(videos))) + f"concat=n={len(videos)}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset",
            "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    if r.returncode or not Path(out).is_file():
        return None, (r.stderr or "ffmpeg lỗi").strip()[-300:]
    return str(out), ""
