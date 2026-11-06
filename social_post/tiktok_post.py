# -*- coding: utf-8 -*-
"""
Tu dong dang 1 video len TikTok (TikTok Studio) bang tai khoan TikTok da dang nhap o profile FoxProfile.
Lay tu foxprofile\\00.tiktok_upload.py (helper dung chung: fox_common.py).

Chay:
    python tiktok_post.py --folder "..\\Videos\\downloads\\<id>" --file "tap1.mp4" --profile P1

File video phai nam trong FOXPROFILE_UPLOAD_DIRS (mac dinh Muse2Tele\\Videos\\downloads).

--expect-account <username>: chi dang khi tai khoan TikTok dang nhap dung la tai khoan nay (auto_post.py truyen tu
Bang dang bai).
Ma thoat: 0 OK, 1 loi, 2 khong thay file, 3 chua dang nhap TikTok, 5 FoxProfile chua san sang,
          6 tai khoan dang nhap khac --expect-account (khong dang).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from fox_common import (
    EXIT_ERROR, EXIT_FOX_UNAVAILABLE, EXIT_NO_FILE, EXIT_NOT_LOGGED_IN, EXIT_OK,
    FoxSession, FoxUnavailable, NotLoggedIn, click_robust, close_work_tab, eval_retry, js_click_css, log,
    open_work_tab, save_shot, wait_any, wait_for,
)
from fox_common import FoxError

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
CONTENT_URL_PART = "/tiktokstudio/content"  # dang xong TikTok chuyen ve day

# Selector theo data-e2e cua TikTok Studio -> khong phu thuoc ngon ngu giao dien.
SELECT_VIDEO_BTN = "[data-e2e='select_video_button']"
CAPTION_EDITOR = "[data-e2e='caption_container'] [contenteditable='true']"
POST_BTN = "[data-e2e='post_video_button']"
FILE_INPUT = "input[type='file']"

LOGIN_MARK = "text=/Log in to TikTok|Đăng nhập vào TikTok/i"
POST_NOW_BTN = "role=button[name=/^\\s*(Post now|Đăng ngay)\\s*$/i] >> nth=0"
HASHTAGS = ["#phimhay ", "#drama ", "#tổngtài ", "#xuhuong2026 ", "#trending "]

# Dong popup 'Bat kiem tra noi dung tu dong?' (Huy/Bat) va tooltip 'Da hieu'.
# Chi bam 'Huy' NAM TRONG hop chua nut 'Bat': trang con 1 nut 'Huy' khac (the tien trinh upload)
# ma bam nham se huy luon video dang tai len.
DISMISS_JS = """() => {
    const txt = e => (e.innerText || '').trim();
    const btns = [...document.querySelectorAll('button,[role=button]')];
    const done = [];
    const turnOn = btns.find(b => /^(Turn on|Bật)$/i.test(txt(b)));
    if (turnOn) {
        for (let box = turnOn.parentElement; box; box = box.parentElement) {
            const c = [...box.querySelectorAll('button,[role=button]')].find(b => /^(Cancel|Hủy)$/i.test(txt(b)));
            if (c) { c.click(); done.push('cancel'); break; }
        }
    }
    const g = btns.find(b => /^(Got it|Đã hiểu)$/i.test(txt(b)) && b.getBoundingClientRect().width > 0);
    if (g) { g.click(); done.push('gotit'); }
    return done;
}"""


def build_caption(file: str, text: str | None = None) -> str:
    """Caption tu --caption; khong co thi dung ten file + bo hashtag mac dinh (nhu ban cu)."""
    if text and text.strip():
        return text.strip() + "\n"
    # Dung stem de ten co dau cham (vd "tap.1.mp4") khong bi cat mat.
    return Path(file).stem + "\n" + "\n".join(HASHTAGS) + "\n"


def ensure_caption(fb, caption: str, tries: int = 4) -> None:
    """Dien caption va kiem tra hashtag con trong o. TikTok tu dien san ten file vao o mo ta ngay sau khi tai len
    va co the ghi de len caption vua dien (hashtag mat) -> dien lai toi khi giu duoc."""
    # Tu cuoi cua caption: TikTok ghi de ten file vao dau o mo ta, mat thi tu cuoi cung mat theo
    marker = caption.split()[-1][:30] if caption.split() else HASHTAGS[0].strip()
    for i in range(1, tries + 1):
        fb.type_into(CAPTION_EDITOR, caption)
        time.sleep(2)
        if marker in fb.text_of(CAPTION_EDITOR):
            return
        log(f"Caption chua giu duoc hashtag (lan {i}/{tries}), dien lai")
    raise RuntimeError("Khong dien duoc caption kem hashtag")


def dismiss_popups(fb, wait_s: float = 0) -> None:
    deadline = time.time() + wait_s
    while True:
        done = eval_retry(fb, DISMISS_JS)
        if "cancel" in done:
            log("Da dong popup kiem tra noi dung (Huy)")
        if "gotit" in done:
            log("Da dong tooltip 'Da hieu'")
        if done or time.time() >= deadline:
            return
        time.sleep(1)


def wait_upload_done(fb, timeout_s: float) -> None:
    """Nut Dang bi khoa (aria-disabled) cho toi khi video tai len xong."""
    ready = (f"() => {{ const b = document.querySelector({json.dumps(POST_BTN)});"
             " return !!b && !b.disabled && b.getAttribute('aria-disabled') !== 'true'; }")
    if not wait_for(lambda: eval_retry(fb, ready), timeout_s, interval=3):
        raise TimeoutError(f"Nut 'Dang' van khoa sau {timeout_s:g}s")
    # Nut Dang mo khoa tu ~99%: cho them toi khi the tien trinh het hien "NN%"
    gone = ("() => { const c = document.querySelector(\"[data-e2e='upload_status_container']\");"
            " return !c || !/\\d+(\\.\\d+)?%/.test(c.innerText); }")
    if not wait_for(lambda: eval_retry(fb, gone), 120, interval=3):
        log("The tien trinh van hien %, van tiep tuc dang")


def post_video(fb, post_wait: float, max_attempts: int) -> None:
    """Click 'Dang' toi khi trang chuyen ve danh sach bai dang. Chi nut Dang bien mat la chua du:
    da gap truong hop nut mat nhung video khong duoc dang (cung khong thanh nhap)."""
    for attempt in range(1, max_attempts + 1):
        log(f"Click 'Dang' (lan {attempt})")
        try:
            click_robust(fb, POST_BTN, lambda: js_click_css(fb, POST_BTN))
        except FoxError:
            pass  # nut co the da bien mat ngay sau lan click truoc
        if fb.visible(POST_NOW_BTN, 3000):  # hop xac nhan 'Dang ngay' (khi kiem tra noi dung chua xong)
            try:
                fb.click(POST_NOW_BTN, timeout=3000)
                log("Da xac nhan 'Dang ngay'")
            except FoxError:
                pass
        if wait_for(lambda: CONTENT_URL_PART in fb.url(), post_wait, interval=1):
            return
        if not fb.visible(POST_BTN, 300):
            raise RuntimeError(f"Nut 'Dang' da mat nhung trang khong chuyen sang danh sach bai dang (url={fb.url()})")
        dismiss_popups(fb)
    raise RuntimeError(f"Nut 'Dang' van con sau {max_attempts} lan click")


# @username cua tai khoan dang dang nhap: API passport, khong duoc thi doc du lieu trang chu (webapp.app-context).
ACCOUNT_JS = """async () => {
    try {
        const r = await fetch('/passport/web/account/info/?aid=1988', {credentials: 'include'});
        const j = await r.json();
        const u = j && j.data && (j.data.username || j.data.unique_id);
        if (u) return String(u);
    } catch (e) {}
    try {
        const html = await (await fetch('/', {credentials: 'include'})).text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const el = doc.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
        const data = el && JSON.parse(el.textContent);
        const user = data && data.__DEFAULT_SCOPE__ && data.__DEFAULT_SCOPE__['webapp.app-context']
            && data.__DEFAULT_SCOPE__['webapp.app-context'].user;
        if (user && user.uniqueId) return String(user.uniqueId);
    } catch (e) {}
    return '';
}"""
EXIT_WRONG_ACCOUNT = 6


class WrongAccount(Exception):
    pass


def check_account(fb, expected: str, always: bool = False) -> None:
    """Dung neu tai khoan TikTok dang nhap khac tai khoan ghi trong Bang dang bai (tranh dang nham kenh).
    always: doc tai khoan ca khi khong co expected (in TIKTOK_ACCOUNT=... cho check_accounts.py)."""
    expected = expected.strip().lstrip("@").lower()
    if not expected and not always:
        return
    current = str(eval_retry(fb, ACCOUNT_JS) or "").strip().lstrip("@").lower()
    print(f"TIKTOK_ACCOUNT={current}", flush=True)
    if not expected:
        if not current:
            raise RuntimeError("Khong doc duoc tai khoan TikTok dang dang nhap")
        return
    if not current:
        raise RuntimeError("Khong doc duoc tai khoan TikTok dang dang nhap -> chua dang (se thu lai)")
    if current != expected:
        raise WrongAccount(f"Profile dang dang nhap TikTok @{current}, Bang dang bai ghi @{expected}")
    log(f"Tai khoan TikTok khop: @{current}")


def run(folder: str, file: str, profile: str, post_wait: float = 30, upload_wait: float = 600,
        max_post_attempts: int = 5, no_post: bool = False, keep_open: bool = False,
        caption_text: str | None = None, expect_account: str = "", check_only: bool = False) -> int:
    video_path = Path(folder) / file
    if not check_only and not video_path.is_file():
        log(f"Khong tim thay file: {video_path}")
        return EXIT_NO_FILE

    try:
        session = FoxSession(profile, keep_open)
        fb = session.__enter__()
    except FoxUnavailable as e:
        log(f"LOI FoxProfile: {e}")
        return EXIT_FOX_UNAVAILABLE
    try:
        open_work_tab(fb)
        log("Mo TikTok Studio (trang upload)")
        fb.navigate(UPLOAD_URL, wait_until="load")
        # Chua dang nhap thi TikTok hien trang 'Log in to TikTok' (khong doi URL)
        which = wait_any(fb, [SELECT_VIDEO_BTN, LOGIN_MARK], 30)
        if which < 0:
            raise RuntimeError("Khong thay nut chon video lan trang dang nhap")
        if which == 1 or "/login" in fb.url():
            raise NotLoggedIn(f"Profile '{profile}' chua dang nhap TikTok")
        check_account(fb, expect_account, always=check_only)
        if check_only:
            log("--check-account: chi kiem tra tai khoan, khong dang")
            return EXIT_OK

        log(f"Chon file: {video_path}")
        fb.upload([video_path], input_selector=FILE_INPUT, timeout=30000)

        # Popup 'Huy / Bat' kiem tra noi dung xuat hien vai giay sau khi chon file
        dismiss_popups(fb, wait_s=10)

        log("Dien caption")
        if not fb.wait_visible(CAPTION_EDITOR, 30):
            raise TimeoutError("Khong thay o caption")
        caption = build_caption(file, caption_text)
        ensure_caption(fb, caption)

        log(f"Cho video tai len xong (toi da {upload_wait:g}s)")
        wait_upload_done(fb, upload_wait)
        dismiss_popups(fb)  # popup co the hien ra muon, che nut Dang
        ensure_caption(fb, caption)  # kiem tra lai ngay truoc khi dang

        if no_post:
            save_shot(fb, Path(folder) / f"nopost_tiktok_{video_path.stem}.png")
            log("--no-post: dung truoc khi bam Dang")
            return EXIT_OK

        post_video(fb, post_wait, max_post_attempts)
        log(f"Da dang video: {video_path}")
        return EXIT_OK
    except NotLoggedIn as e:
        log(f"LOI: {e}")
        return EXIT_NOT_LOGGED_IN
    except WrongAccount as e:
        log(f"DUNG, KHONG DANG: {e}")
        return EXIT_WRONG_ACCOUNT
    except Exception as e:
        log(f"LOI: {e}")
        save_shot(fb, Path(folder) / f"error_tiktok_{video_path.stem}.png")
        return EXIT_ERROR
    finally:
        close_work_tab(fb)
        session.__exit__()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tu dong dang video len TikTok da dang nhap o profile FoxProfile")
    ap.add_argument("--folder", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--check-account", action="store_true",
                    help="Chi mo TikTok Studio, in TIKTOK_ACCOUNT=<username> roi thoat (khong can --folder/--file)")
    ap.add_argument("--profile", required=True, help="Ten profile FoxProfile, vd Full1")
    ap.add_argument("--post-wait-timeout", type=float, default=30,
                    help="So giay cho trang chuyen ve danh sach sau moi lan click Dang")
    ap.add_argument("--upload-wait", type=float, default=600,
                    help="So giay toi da cho video tai len xong (nut Dang mo khoa)")
    ap.add_argument("--max-post-attempts", type=int, default=5)
    ap.add_argument("--caption", default=None, help="Noi dung bai dang (mac dinh: ten file + hashtag co san)")
    ap.add_argument("--caption-file", default=None, help="Doc caption tu file .txt (UTF-8)")
    ap.add_argument("--expect-account", default="",
                    help="@username TikTok phai dang nhap o profile (Bang dang bai); khac thi khong dang, ma thoat 6")
    ap.add_argument("--no-post", action="store_true", help="Chay thu: KHONG bam Dang")
    ap.add_argument("--keep-open", action="store_true", help="Khong dong profile du chinh script mo no")
    a = ap.parse_args()
    if not a.check_account and not (a.folder and a.file):
        ap.error("can --folder va --file (hoac --check-account)")
    caption = a.caption
    if a.caption_file:
        caption = Path(a.caption_file).read_text(encoding="utf-8")
    sys.exit(run(a.folder, a.file, a.profile, a.post_wait_timeout, a.upload_wait,
                 a.max_post_attempts, a.no_post, a.keep_open, caption, a.expect_account, a.check_account))


if __name__ == "__main__":
    main()
