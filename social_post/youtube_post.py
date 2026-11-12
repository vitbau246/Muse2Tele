# -*- coding: utf-8 -*-
"""
Dang 1 video len kenh YouTube (YouTube Studio) bang tai khoan Google da dang nhap o profile FoxProfile.

  python youtube_post.py --profile Muse9 --folder "..\\Videos\\downloads\\social_queue\\Muse9" --file tap1.mp4 \\
         --expect-channel LongTamHoRong [--title "..."] [--caption-file tap1.txt] \\
         [--thumbs a.jpg b.jpg c.jpg] [--visibility public|unlisted|private] [--no-post]

- Kenh: --expect-channel = handle trong Bang dang bai (khong @). Script mo trang @handle lay channel id roi vao
  Studio cua dung kenh do (tai khoan quan ly nhieu kenh: Tai khoan thuong hieu). Tai khoan khong quan ly kenh do
  -> ma 6, khong dang.
- Tieu de: --title, khong co thi dong dau caption (<= 100 ky tu); mo ta: phan con lai cua caption (<= 5000).
- Anh thu nho: 1 anh -> dat lam thumbnail; 2-3 anh -> "Thu nghiem va so sanh" (A/B test, YouTube tu chon anh
  thang). Kenh chua mo tinh nang hinh thu nho tuy chinh (xac minh SDT) thi bo qua thumbnail, van dang video.
- Danh dau "noi dung tong hop / da chinh sua" (video AI): mac dinh Co (--no-altered de tat).
- Khong danh cho tre em.
File video / anh phai nam trong FOXPROFILE_UPLOAD_DIRS (mac dinh Muse2Tele\\Videos\\downloads).

Ma thoat: 0 OK, 1 loi (co anh chup logs\\), 2 khong thay file, 3 chua dang nhap Google / YouTube,
          5 FoxProfile chua san sang, 6 tai khoan khong quan ly kenh --expect-channel (khong dang).
In dong "YOUTUBE_URL: https://youtu.be/..." khi dang xong.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from fox_common import (EXIT_ERROR, EXIT_FOX_UNAVAILABLE, EXIT_NO_FILE, EXIT_NOT_LOGGED_IN, EXIT_OK, FoxError,
                        FoxSession, FoxUnavailable, close_work_tab, log, open_work_tab, save_shot, wait_for)
from fanpage_jobs import LOG_DIR

EXIT_WRONG_ACCOUNT = 6
STUDIO = "https://studio.youtube.com"
UPLOAD_URL = STUDIO + "/channel/{cid}/videos/upload?d=ud"
TITLE_BOX = "#title-textarea #textbox"
DESC_BOX = "#description-textarea #textbox"
DIALOG = "ytcp-uploads-dialog"
TITLE_MAX = 100
DESC_MAX = 5000


def shot(fb, name):
    from datetime import datetime
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    save_shot(fb, LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{name}.png")


class StepError(Exception):
    pass


class WrongAccount(Exception):
    pass


class NotLoggedIn(Exception):
    pass


def js(fb, fn, *args):
    return fb.evaluate(f"() => ({fn})({', '.join(json.dumps(a) for a in args)})")


CENTER_JS = """(sel, texts) => {
  const ok = e => e.offsetParent && (!texts || texts.includes((e.innerText || '').trim()))
      && !e.hasAttribute('disabled') && e.getAttribute('aria-disabled') !== 'true';
  const e = [...document.querySelectorAll(sel)].filter(ok).pop();
  if (!e) return false;
  e.scrollIntoView({block: 'center'});
  e.click();
  return true;
}"""


def click(fb, sel, texts=None):
    """Bam phan tu dang hien bang element.click(). Studio: bam theo selector hay het gio (lop phu), con bam chuot
    theo toa do (click-at) treo giua chung -- nut chuot nhan xuong khong nha, boi den chu (2026-11-11)."""
    return bool(js(fb, CENTER_JS, sel, list(texts) if texts else None))


def click_wait(fb, sel, texts=None, timeout_s=20, what=""):
    if not wait_for(lambda: click(fb, sel, texts), timeout_s):
        raise StepError(f"khong thay {what or (texts[0] if texts else sel)}")


def set_rich_text(fb, sel, text):
    """O nhap cua Studio (contenteditable): Enter lam con tro nhay ve dau -> chen ca doan bang insertText."""
    if not js(fb, """(s, t) => { const e = document.querySelector(s); if (!e) return false;
            e.scrollIntoView({block: 'center'}); e.focus(); document.execCommand('selectAll', false, null);
            document.execCommand('insertText', false, t); return true; }""", sel, text):
        raise StepError(f"khong thay o {sel}")
    time.sleep(1)
    got = js(fb, "(s) => (document.querySelector(s) || {}).innerText || ''", sel)
    if got.strip() != text.strip():
        raise StepError(f"dien {sel} khong khop ({len(got)}/{len(text)} ky tu)")


# ---------------- kenh ----------------

def channel_id_of(fb, handle):
    fb.navigate(f"https://www.youtube.com/@{handle}")
    found = {}

    def read():
        found["cid"] = js(fb, """() => { const l = document.querySelector('link[rel=canonical]');
            const m = l && l.href.match(/channel\\/(UC[\\w-]+)/); return m ? m[1] : null; }""")
        return found["cid"]
    if not wait_for(read, 30):
        raise StepError(f"khong tim thay kenh @{handle}")
    return found["cid"]


CHANNELS_JS = r"""() => [...document.querySelectorAll('ytd-account-item-renderer')].filter(e => e.offsetParent)
  .map(e => { const t = (e.innerText || '').trim(); const m = t.normalize('NFC').match(/@[\p{L}\p{N}\p{M}_.\-]+/u);
    const n = e.querySelector('#channel-title');
    return {name: (n ? n.innerText : t.split(String.fromCharCode(10))[0]).trim(), handle: m ? m[0].slice(1) : ''}; })
  .filter(c => c.handle)"""


def list_channels(fb):
    """Cac kenh YouTube tai khoan Google dang nhap quan ly (trang chuyen kenh): [{name, handle}]."""
    fb.navigate("https://www.youtube.com/channel_switcher")
    if not fb.wait_visible("ytd-account-item-renderer", 30):
        if "accounts.google.com" in fb.url() or "ServiceLogin" in fb.url():
            raise NotLoggedIn("chua dang nhap Google")
        raise StepError("khong mo duoc trang chuyen kenh YouTube (chua co kenh / chua dang nhap?)")
    time.sleep(2)
    return js(fb, CHANNELS_JS)


def save_channels(profile, channels):
    """Bo nho dem cho dashboard (Bang dang bai goi y kenh): data/yt_channels_<profile>.json."""
    from fanpage_jobs import DATA_DIR
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"yt_channels_{safe}.json").write_text(json.dumps(
        {"at": time.strftime("%Y-%m-%d %H:%M"), "channels": channels}, ensure_ascii=False, indent=1), encoding="utf-8")


def switch_channel(fb, handle):
    """Tai khoan Google quan ly nhieu kenh (Tai khoan thuong hieu): Studio luon mo kenh DANG DUNG, nen chuyen sang
    kenh can dang o youtube.com/channel_switcher. Tra False neu tai khoan khong co kenh nay."""
    fb.navigate("https://www.youtube.com/channel_switcher")
    if not fb.wait_visible("ytd-account-item-renderer", 30):
        if "accounts.google.com" in fb.url():
            raise NotLoggedIn("chua dang nhap Google")
        raise StepError("khong mo duoc trang chuyen kenh YouTube")
    pt = js(fb, """(h) => { const e = [...document.querySelectorAll('ytd-account-item-renderer')].find(e =>
        e.offsetParent && (e.innerText || '').normalize('NFC').toLowerCase().includes('@' + h.normalize('NFC').toLowerCase()));
        if (!e) return null; e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect();
        return [r.x + r.width / 2, r.y + r.height / 2]; }""", handle)
    if not pt:
        return False
    fb.click_at(*pt)
    time.sleep(6)
    return True


def open_upload(fb, cid, handle):
    for attempt in range(2):
        fb.navigate(UPLOAD_URL.format(cid=cid))
        time.sleep(5)
        url = fb.url()
        if "accounts.google.com" in url:
            raise NotLoggedIn("chua dang nhap Google")
        if f"/channel/{cid}" in url:
            break
        if attempt or not switch_channel(fb, handle):
            raise WrongAccount(f"tai khoan khong quan ly kenh @{handle} ({cid}); Studio mo {url}")
        log(f"Da chuyen sang kenh @{handle}")
    if not fb.wait_visible(f"{DIALOG} #select-files-button, {DIALOG} ytcp-uploads-file-picker", 40):  # o file luon an
        raise StepError("khong mo duoc hop thoai tai video len")


# ---------------- tai len + chi tiet ----------------

PROGRESS_JS = """() => { const e = document.querySelector(
    'ytcp-uploads-dialog .progress-label, ytcp-uploads-dialog ytcp-video-upload-progress');
    return e ? e.innerText.trim() : ''; }"""


def upload_video(fb, video, timeout_s=1800):
    """Chon video roi CHO TAI LEN XONG: trong luc trinh duyet day file len, moi lenh dieu khien (go chu, bam) deu
    treo toi FoxProfile tra 504 (2026-11-11, video 76 MB), nen chua dien gi cho toi khi het 'Da tai duoc NN%'."""
    fb.upload([video], input_selector=f"{DIALOG} input[type=file], input[name=Filedata]", timeout=30000)
    deadline, last, label = time.time() + timeout_s, 0, ""
    while time.time() < deadline:
        time.sleep(5)
        try:
            label = fb.evaluate(PROGRESS_JS)
        except FoxError as e:  # 504: trinh duyet dang ban day file len
            if e.status not in (504, 0) and not e.is_timeout:
                raise
            continue
        if label and not re.search(r"\d+\s*%", label):
            break  # "Da tai xong", "Dang xu ly...", "Dang kiem tra..."
        if time.time() - last > 60:
            log(f"Tai len: {label or '...'}")
            last = time.time()
    else:
        raise StepError(f"qua {timeout_s}s video chua tai len xong ({label})")
    log(f"Tai len xong: {label}")
    if not fb.wait_visible(TITLE_BOX, 60):
        raise StepError("tai video xong nhung khong hien form chi tiet (gioi han tai len / video loi?)")
    time.sleep(2)


def set_thumbnails(fb, thumbs):
    """1 anh: thumbnail. 2-3 anh: Thu nghiem va so sanh. Tra ve mo ta ket qua."""
    if not thumbs:
        return "khong co anh"
    if len(thumbs) == 1:
        try:
            fb.upload([thumbs[0]], input_selector="#file-loader", timeout=15000)
        except FoxError as e:
            return f"khong dat duoc thumbnail ({e})"
        time.sleep(5)
        if feature_locked(fb):
            return "KHONG dat duoc: kenh chua bat hinh thu nho tuy chinh (" + LOCKED_HINT + ")"
        return "1 thumbnail"
    # O "Thu nghiem A/B": nut that la #select-button ben trong (bam the ngoai khong mo gi)
    if not js(fb, """() => { const b = document.querySelector('ytcp-thumbnails-experiment-editor #select-button');
            if (!b || !b.offsetParent) return false; b.scrollIntoView({block: 'center'}); b.click(); return true; }"""):
        log("Khong thay o Thu nghiem A/B -> dat anh dau lam thumbnail")
        return set_thumbnails(fb, thumbs[:1]) + " (khong co Thu nghiem A/B)"
    # Hop thoai xac minh SDT (kenh chua mo tinh nang) co the hien cham hon hop thoai A/B: cho toi da 12s xem cai nao
    for _ in range(6):
        time.sleep(2)
        if feature_locked(fb):
            return "KHONG chay duoc Thu nghiem A/B: " + LOCKED_HINT
        if fb.visible("ytcp-thumbnails-ab-test-dialog, ytcp-thumbnail-ab-test-dialog", 300):
            break
    else:  # 12s khong thay hop thoai nao (hop thoai tai len: goi y hashtag giu focus, bam A/B khong mo gi)
        if not js(fb, "() => [...document.querySelectorAll('ytcp-dialog input[type=file], tp-yt-paper-dialog "
                      "input[type=file]')].some(i => i.closest('ytcp-dialog, tp-yt-paper-dialog')"
                      ".getBoundingClientRect().width > 0 && i.id !== 'file-loader')"):
            raise StepError("khong mo duoc hop thoai Thu nghiem A/B (kenh chua xac minh SDT?)")
    sel = "ytcp-thumbnails-ab-test-dialog input[type=file], tp-yt-paper-dialog input[type=file][multiple], " \
          "ytcp-dialog input[type=file]"
    if not fb.wait_visible("ytcp-thumbnails-ab-test-dialog, ytcp-thumbnail-ab-test-dialog", 15):
        log("Hop thoai Thu nghiem va so sanh: khong nhan ra ten the, thu o file dau tien trong hop thoai")
    fb.upload(thumbs[:3], input_selector=sel, timeout=20000)
    time.sleep(8)
    shot(fb, "yt_abtest")
    if not click(fb, "ytcp-button, button", ["Xong", "Done", "Lưu", "Save"]):
        raise StepError("khong bam duoc Xong o hop thoai Thu nghiem va so sanh")
    time.sleep(3)
    return f"thu nghiem {len(thumbs[:3])} thumbnail"


LOCKED_HINT = ("kenh chua xac minh so dien thoai -- Studio > Cai dat > Kenh > Dieu kien su dung tinh nang > "
               "2. Cac tinh nang bac trung > Xac minh so dien thoai, roi chay lai voi --thumbs-only <video id>")
LOCKED_RE = (r"đã có quyền sử dụng tính năng này|already have access to this feature|xác minh số điện thoại"
             r"|verify your phone|Khai thác nhiều tính năng|hình thu nhỏ tu[ỳy] chỉnh|custom thumbnails")


def feature_locked(fb):
    """Kenh chua bat tinh nang bac trung (hinh thu nho tuy chinh, Thu nghiem A/B): Studio hien hop thoai 'Ban da
    hoan tat / Ban da co quyen... hay lam moi trang' hoac xin xac minh SDT, va KHONG dat anh (2026-11-11 kenh
    LongTamHoRong). Dong hop thoai, tra True."""
    # Hop thoai co dinh (position: fixed) co offsetParent = null -> do bang kich thuoc. 11/2026: hop thoai moi
    # yt-trust-tiers-wizard-dialog "Khai thac nhieu tinh nang khac ... hay xac minh so dien thoai" (nut Xac minh / Huy).
    text = js(fb, """() => [...document.querySelectorAll('yt-trust-tiers-wizard-dialog, ytcp-dialog, tp-yt-paper-dialog')]
        .filter(d => d.getBoundingClientRect().width > 0).map(d => d.innerText).join('\\n')""")
    if not re.search(LOCKED_RE, text or "", re.I):
        return False
    # Hop thoai xac minh: chi bam the ytcp-button#cancel-button moi dong (bam <button> ben trong khong an, click-at treo)
    if not js(fb, """() => { const b = document.querySelector('yt-trust-tiers-wizard-dialog #cancel-button');
            if (!b || !b.getBoundingClientRect().width) return false; b.click(); return true; }"""):
        click(fb, "ytcp-dialog ytcp-button, ytcp-dialog button", ["Hủy", "Huỷ", "Cancel", "Đã hiểu", "Got it", "Đóng",
                                                                  "Close"])
    time.sleep(1)
    log("Kenh chua bat hinh thu nho tuy chinh / Thu nghiem A/B: " + LOCKED_HINT)
    return True


def set_audience(fb, altered):
    # Khong danh cho tre em
    if not click(fb, "tp-yt-paper-radio-button[name=VIDEO_MADE_FOR_KIDS_NOT_MFK]"):
        raise StepError("khong thay lua chon 'Khong danh cho tre em'")
    time.sleep(1)
    # Noi dung tong hop / da chinh sua (AI): nam trong "Hien them"
    want = "VIDEO_HAS_ALTERED_CONTENT_YES" if altered else "VIDEO_HAS_ALTERED_CONTENT_NO"
    if not click(fb, f"tp-yt-paper-radio-button[name={want}]"):
        click(fb, f"{DIALOG} ytcp-button#toggle-button, {DIALOG} #toggle-button")
        time.sleep(2)
        if not click(fb, f"tp-yt-paper-radio-button[name={want}]"):
            log("Khong thay muc 'Noi dung da chinh sua' -> bo qua")


def next_steps(fb):
    for _ in range(3):
        click_wait(fb, f"{DIALOG} #next-button", what="nut Tiep")
        time.sleep(3)


def wait_checks(fb, timeout_s=900):
    """Cho tai len xong (dong trang thai 'Da tai xong' / 'Upload complete' / dang xu ly) truoc khi xuat ban."""
    def done():
        t = js(fb, "(s) => (document.querySelector(s) || {}).innerText || ''", f"{DIALOG} .progress-label, "
               f"{DIALOG} ytcp-video-upload-progress")
        if re.search(r"\d+\s*%", t) and not re.search(r"xử lý|process|kiểm tra|check", t, re.I):
            return None
        return t or "?"
    return wait_for(done, timeout_s, interval=5)


def publish(fb, visibility):
    name = {"public": "PUBLIC", "unlisted": "UNLISTED", "private": "PRIVATE"}[visibility]
    click_wait(fb, f"tp-yt-paper-radio-button[name={name}]", what=f"lua chon {visibility}")
    time.sleep(1)
    url = js(fb, "() => { const a = document.querySelector('ytcp-uploads-dialog .video-url-fadeable a, "
                 "ytcp-uploads-dialog a[href*=\"youtu.be\"]'); return a ? a.href : ''; }")
    click_wait(fb, f"{DIALOG} #done-button", what="nut Xuat ban / Luu")
    ok = wait_for(lambda: js(fb, """() => !!document.querySelector('ytcp-video-share-dialog, ytcp-prechecks-warning-dialog')
        || !document.querySelector('ytcp-uploads-dialog tp-yt-paper-dialog[opened], ytcp-uploads-dialog #dialog')"""), 120)
    if js(fb, "() => !!document.querySelector('ytcp-prechecks-warning-dialog')"):
        click(fb, "ytcp-prechecks-warning-dialog ytcp-button, ytcp-prechecks-warning-dialog button",
              ["Vẫn xuất bản", "Publish anyway", "Xuất bản", "Publish"])
        time.sleep(5)
    if not ok:
        raise StepError("bam Xuat ban nhung hop thoai khong dong")
    return url


def thumbs_only(fb, video_id, thumbs):
    fb.navigate(f"{STUDIO}/video/{video_id}/edit")
    if not fb.wait_visible("ytcp-video-thumbnail-editor, #file-loader", 40):
        raise StepError(f"khong mo duoc trang chinh sua video {video_id}")
    time.sleep(3)
    result = set_thumbnails(fb, thumbs)
    log(f"Thumbnail: {result}")
    if result.startswith("KHONG"):
        return EXIT_ERROR
    click(fb, "ytcp-button#save, #save", None)
    time.sleep(5)
    return EXIT_OK


# ---------------- main ----------------

def run_list_channels(a):
    try:
        with FoxSession(a.profile, keep_open=a.keep_open, need_upload=False) as fb:
            open_work_tab(fb)
            try:
                channels = list_channels(fb)
            except NotLoggedIn as e:
                log(f"Chua dang nhap: {e}")
                return EXIT_NOT_LOGGED_IN
            except (StepError, FoxError) as e:
                log(f"LOI: {e}")
                return EXIT_ERROR
            finally:
                close_work_tab(fb)
    except FoxUnavailable as e:
        log(f"FoxProfile chua san sang: {e}")
        return EXIT_FOX_UNAVAILABLE
    save_channels(a.profile, channels)
    log("Kenh YouTube: " + (", ".join(f"{c['name']} @{c['handle']}" for c in channels) or "(khong co)"))
    print("YOUTUBE_CHANNELS=" + json.dumps(channels, ensure_ascii=False), flush=True)
    return EXIT_OK


def run(a):
    video = (Path(a.folder) / a.file).resolve() if a.folder else Path(a.file).resolve()
    thumbs = [Path(t) if Path(t).is_absolute() else (Path(a.folder) / t) for t in a.thumbs or []]
    if a.list_channels:
        return run_list_channels(a)
    if not a.file and not a.thumbs_only:
        log("Thieu --file")
        return EXIT_NO_FILE
    if not a.expect_channel and not a.thumbs_only:
        log("Thieu --expect-channel (handle kenh trong Bang dang bai)")
        return EXIT_NO_FILE
    missing = [p for p in ([] if a.thumbs_only else [video]) + thumbs if not p.is_file()]
    if missing:
        log(f"Khong thay file: {missing}")
        return EXIT_NO_FILE
    caption = a.caption or ""
    if a.caption_file:
        caption = Path(a.caption_file).read_text(encoding="utf-8-sig")
    lines = caption.strip().splitlines()
    title = (a.title or (lines[0] if lines else "") or video.stem).strip()[:TITLE_MAX]
    desc = "\n".join(lines[1:] if not a.title else lines).strip()[:DESC_MAX]
    title = title.replace("<", "").replace(">", "")  # YouTube khong nhan < >
    desc = desc.replace("<", "").replace(">", "")

    try:
        with FoxSession(a.profile, keep_open=a.keep_open) as fb:
            open_work_tab(fb)
            if fb.tab is not None:
                # Camoufox: moi tab 1 cua so; cua so nen bi giam nhip ve -> Studio khong phan hoi bam / tai anh
                # (2026-11-11). Dua tab lam viec len truoc.
                fb.tab_select(fb.tab)
            try:
                if a.thumbs_only:
                    return thumbs_only(fb, a.thumbs_only, [str(t.resolve()) for t in thumbs])
                cid = channel_id_of(fb, a.expect_channel.lstrip("@"))
                log(f"Kenh @{a.expect_channel} = {cid}")
                open_upload(fb, cid, a.expect_channel.lstrip("@"))
                upload_video(fb, str(video))
                log(f"Da chon video {video.name}")
                set_rich_text(fb, TITLE_BOX, title)
                if desc:
                    set_rich_text(fb, DESC_BOX, desc)
                # Mo ta co hashtag -> YouTube mo danh sach goi y hashtag de len o Thu nghiem A/B: bam truot, hop thoai
                # khong mo, set_input_files het gio (2026-11-11 tap 2). Dong goi y truoc.
                fb.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
                time.sleep(1.5)
                thumb_paths = [str(t.resolve()) for t in thumbs]
                try:
                    log(f"Thumbnail: {set_thumbnails(fb, thumb_paths)}")
                except (StepError, FoxError) as e:
                    # Anh loi khong dang bo ca video (video da tai len, thu lai se tao them ban nhap): dong hop thoai,
                    # dang tiep; dat anh sau bang --thumbs-only <video id>.
                    shot(fb, "yt_thumbs_error")
                    log(f"Thumbnail LOI ({str(e)[:120]}) -> van dang video, dat anh sau: --thumbs-only <video id> "
                        f"--thumbs {' '.join(thumb_paths)}")
                    print("YOUTUBE_THUMBS_PENDING=1", flush=True)
                    if not feature_locked(fb):  # dong hop thoai xac minh neu dang mo, khong thi hop thoai khac
                        click(fb, "ytcp-dialog ytcp-button, ytcp-dialog button, tp-yt-paper-dialog ytcp-button",
                              ["Hủy", "Huỷ", "Cancel", "Đóng", "Close"])
                        time.sleep(1)
                set_audience(fb, not a.no_altered)
                shot(fb, "yt_details")
                next_steps(fb)
                if a.no_post:
                    shot(fb, "yt_visibility")
                    log("--no-post: dung o buoc Che do hien thi (video da tai len o dang ban nhap rieng tu)")
                    return EXIT_OK
                log(f"Trang thai tai len: {wait_checks(fb)}")
                url = publish(fb, a.visibility)
                log(f"Da xuat ban ({a.visibility})")
                print(f"YOUTUBE_URL: {url}", flush=True)
                return EXIT_OK
            except NotLoggedIn as e:
                log(f"Chua dang nhap: {e}")
                return EXIT_NOT_LOGGED_IN
            except WrongAccount as e:
                log(f"Sai kenh: {e}")
                return EXIT_WRONG_ACCOUNT
            except (StepError, FoxError) as e:
                log(f"LOI: {e}")
                shot(fb, "yt_error")
                return EXIT_ERROR
            finally:
                close_work_tab(fb)
    except FoxUnavailable as e:
        log(f"FoxProfile chua san sang: {e}")
        return EXIT_FOX_UNAVAILABLE


def main():
    ap = argparse.ArgumentParser(description="Dang video len kenh YouTube qua YouTube Studio")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--folder", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--expect-channel", default="", help="handle kenh (khong @), lay tu Bang dang bai")
    ap.add_argument("--title", default="")
    ap.add_argument("--caption", default="")
    ap.add_argument("--caption-file", default="")
    ap.add_argument("--thumbs", nargs="*", default=[], help="1 anh: thumbnail; 2-3 anh: thu nghiem va so sanh")
    ap.add_argument("--list-channels", action="store_true",
                    help="chi liet ke kenh tai khoan quan ly (in YOUTUBE_CHANNELS=json, luu data/yt_channels_<profile>.json)")
    ap.add_argument("--thumbs-only", default="", metavar="VIDEO_ID",
                    help="video da dang: chi dat lai thumbnail / Thu nghiem A/B (vd sau khi xac minh SDT)")
    ap.add_argument("--visibility", choices=["public", "unlisted", "private"], default="public")
    ap.add_argument("--no-altered", action="store_true", help="khong danh dau noi dung tong hop / AI")
    ap.add_argument("--no-post", action="store_true", help="chay thu: dung truoc khi xuat ban")
    ap.add_argument("--keep-open", action="store_true")
    sys.exit(run(ap.parse_args()))


if __name__ == "__main__":
    main()
