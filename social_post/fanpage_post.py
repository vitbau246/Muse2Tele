# -*- coding: utf-8 -*-
"""
Tu dong dang bai len cac Trang Facebook (fanpage) ma profile FoxProfile da dang nhap, qua Meta Business Suite
(https://business.facebook.com/latest/): dang anh -> (cho) dang video -> comment vao video.
Lay tu foxprofile\\00.facebook_business_upload.py. Trong Muse2Tele moi profile FoxProfile (cong 8090) la 1 tai khoan,
nen --profile la BAT BUOC va danh sach Trang duoc cache rieng theo profile (social_post\\data\\fb_pages_<profile>.json).
Dinh dang file ke hoach: xem fanpage_jobs.py.

Khac ban cu:
  - Chon file bang action 'upload' cua FoxProfile (ban da them), chi nhan file trong FOXPROFILE_UPLOAD_DIRS.
  - REST chi co 1 tab "hien hanh" nen cac Trang chay TUAN TU trong 1 tien trinh (khong chay song song nhieu tab).
  - Moi cho cu dung wait_for_function/locator duoc thay bang vong lap tham do qua evaluate / selector.
  - Profile do script mo thi script dong khi xong; profile dang mo san thi giu nguyen.

  python fanpage_post.py --profile P1 --login                 # mo profile, dang nhap Facebook bang tay
  python fanpage_post.py --profile P1 --list-pages            # quet Trang, luu data\\fb_pages_P1.json
  python fanpage_post.py --profile P1 --plan jobs.json [--due-only] [--no-post] [--only "Phim 365"]
  python fanpage_post.py --profile P1 --plan jobs.json --comment [--no-post]   # comment vao video da len song

File anh/video phai nam trong FOXPROFILE_UPLOAD_DIRS (mac dinh Muse2Tele\\Videos\\downloads).

Job co "page_id" (auto_post.py ghi tu Bang dang bai): chon Trang theo Page ID; Trang khong thuoc tai khoan dang
nhap thi khong dang.
Ma thoat: 0 = tat ca OK, 1 = co loi, 2 = khong thay file, 3 = chua dang nhap, 4 = FoxProfile chua san sang,
          6 = Trang khong thuoc tai khoan dang nhap (khong dang).
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fanpage_jobs
from fanpage_jobs import LOG_DIR

fanpage_jobs.load_env()
sys.path.insert(0, str(fanpage_jobs.ROOT_DIR / "foxprofile"))
from foxprofile_client import FoxError, FoxProfileBrowser  # noqa: E402
from fox_common import close_work_tab, open_work_tab  # noqa: E402

START_URL = "https://business.facebook.com/latest/?"

# Nhan ca tieng Viet lan tieng Anh
# Selector theo chu (khong dung role=button: .first khop nham phan tu khac -> click timeout 15s, khong mo duoc o chon file)
ADD_MEDIA_SEL = r"text=/Thêm ảnh\/video|Add photo\/video/i >> visible=true"
POSTED_RE = r"Đã đăng bài viết|Bạn đã đăng được|you.?ve posted|has been (posted|published)"
SCHEDULED_RE = r"đã được lên lịch|đã lên lịch|lên lịch thành công|has been scheduled|scheduled"
# Giao dien moi (10/2026): "Dang tai file phuong tien len" + thanh tien trinh, khong co %
UPLOADING_RE = r"(Đang tải lên|Uploading)\s*\d+\s*%|Đang tải (file )?phương tiện lên|Uploading media"
MIN_LEAD_MINUTES = 25  # Facebook: hen gio phai cach luc tao tu 20 phut den 29 ngay
CONTENTEDITABLE = "[contenteditable='true'] >> visible=true"
COMMENT_BOX_SEL = r"role=textbox[name=/Bình luận|Viết bình luận|Comment|Write a comment/i] >> visible=true >> nth=-1"
UPLOAD_FAIL_RE = r"Tải lên không thành công|Không thể tải lên|Tải lên thất bại|Upload failed|couldn.?t upload|failed to upload"
INNER_TRIES = 3        # so lan tu lam lai TOAN BO buoc soan bai (load lai composer) truoc khi tinh la 1 lan loi
SLOW_CLICK_MS = 45000  # click/go o composer (< 60s: FoxProfile cat moi lan goi REST o 60s)
DATE_INPUT = "input:not([type]):not([aria-label]) >> visible=true"

fb: FoxProfileBrowser = None  # gan trong run()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class NotLoggedIn(Exception):
    pass


def asset_id_of(url: str) -> str:
    return (parse_qs(urlparse(url).query).get("asset_id") or [""])[0]


def xpath_literal(s: str) -> str:
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'
    return "concat(" + ", \"'\", ".join(f"'{p}'" for p in s.split("'")) + ")"


def role_btn(name: str, which: str = "first") -> str:
    """Selector nut theo ten CHINH XAC; which = 'first' | 'last'."""
    return f'role=button[name="{name}"s] >> nth={"-1" if which == "last" else "0"}'


def eval_retry(script: str, tries: int = 3):
    """evaluate nhung chiu duoc luc trang dang chuyen huong (FoxProfile tra 400)."""
    for i in range(tries):
        try:
            return fb.evaluate(script)
        except FoxError as e:
            if e.status not in (400, 422) or i == tries - 1:
                raise
            time.sleep(1)


def body_text() -> str:
    return eval_retry("() => document.body ? document.body.innerText : ''")


# ---------- Liet ke Trang ----------

HEADING = "h1,h2,h3,h4,h5,h6,[role=heading]"
ROWS_FB = 'xpath=//*[@role="row"][contains(., "Facebook")]'
ROW_COUNT_JS = '() => [...document.querySelectorAll("[role=row]")].filter(r => r.innerText.includes("Facebook")).length'
ROW_NAMES_JS = """() => [...document.querySelectorAll("[role=row]")].filter(r => r.innerText.includes("Facebook"))
    .map(r => { const h = r.querySelector("%s"); return h ? h.innerText.trim() : ""; })""" % HEADING


def open_switcher() -> None:
    """Mo bo chon tai san (combobox goc tren trai thanh ben)."""
    for attempt in range(3):
        if not eval_retry(ROW_COUNT_JS):  # lan bam truoc co the da mo san -> bam nua se dong lai
            fb.click("role=combobox >> nth=0")
        if fb.wait_visible(ROWS_FB, 5):
            break
        if attempt == 2:
            raise RuntimeError("Khong mo duoc bo chon Trang")
    time.sleep(1)


def switch_page(name: str) -> None:
    open_switcher()
    row = (f'xpath=//*[@role="row"][.//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 '
           f'or self::h6 or @role="heading"][normalize-space(.)={xpath_literal(name)}]]')
    checked = eval_retry("""() => {
        const name = %s;
        const row = [...document.querySelectorAll("[role=row]")].find(r => {
            const h = r.querySelector("%s"); return h && h.innerText.trim() === name; });
        const input = row && row.querySelector("input");
        return !!(input && input.checked);
    }""" % (json.dumps(name), HEADING))
    if checked:
        fb.press("Escape")  # dang dung san o Trang nay
        return
    before = asset_id_of(fb.url())
    fb.click(row)
    for _ in range(30):
        if asset_id_of(fb.url()) != before:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("asset_id trong URL khong doi sau khi chon")
    for _ in range(40):  # cho trang load xong
        try:
            if fb.evaluate("() => document.readyState") == "complete":
                break
        except FoxError:
            pass
        time.sleep(0.5)
    time.sleep(1.5)


def list_pages() -> list[dict]:
    """[{name, asset_id}]: mo bo chon Trang, bam lan luot tung muc, doc asset_id tu URL."""
    open_switcher()
    names = []
    for t in eval_retry(ROW_NAMES_JS):
        if t and t not in names:
            names.append(t)
    fb.press("Escape")
    log(f"Thay {len(names)} Trang: {names}")
    result = []
    for name in names:
        try:
            switch_page(name)
            result.append({"name": name, "asset_id": asset_id_of(fb.url())})
            log(f"  {name} -> asset_id={result[-1]['asset_id']}")
        except Exception as e:
            log(f"  Bo qua '{name}': {e}")
    return result


# ---------- Dang bai (Meta Business Suite composer) ----------

def wait_upload_done(timeout_s: float) -> None:
    log(f"Cho tai len xong (toi da {timeout_s:g}s)")
    script = f"() => !new RegExp({json.dumps(UPLOADING_RE)}, 'i').test(document.body.innerText)"
    fail_script = f"() => new RegExp({json.dumps(UPLOAD_FAIL_RE)}, 'i').test(document.body.innerText)"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if fb.evaluate(fail_script):
                raise RuntimeError("Facebook bao tai len khong thanh cong")
            if fb.evaluate(script):
                return
        except FoxError as e:
            if e.status not in (400, 422):
                raise
        time.sleep(3)
    raise TimeoutError(f"Tai len chua xong sau {timeout_s:g}s")


def open_composer(asset_id: str, files: list[Path]) -> None:
    fb.navigate(f"https://business.facebook.com/latest/composer/?asset_id={asset_id}", wait_until="load")
    if not fb.wait_visible(ADD_MEDIA_SEL, 60):
        raise TimeoutError("Khong thay nut 'Them anh/video'")
    # Business Suite tu chuyen sang Trang khac neu tai khoan khong quan ly Trang nay -> khong dang nham
    landed = asset_id_of(fb.url())
    if landed and landed != str(asset_id):
        raise RuntimeError(f"Business Suite mo Trang {landed} thay vi {asset_id}: dung, khong dang nham Trang")
    # Trang Business Suite hay nghen (doc file video vai GB) -> Playwright cho phan tu "dung yen" lau hon 10-15s
    fb.upload(files, trigger=ADD_MEDIA_SEL, timeout=SLOW_CLICK_MS)
    time.sleep(3)


def caption_ok(text: str) -> bool:
    """Noi dung bai dang con nguyen trong o soan (Facebook doi khi xoa/khong nhan chu luc tai file)."""
    probe = " ".join(text.split())[:15]
    try:
        # Gop chu cua MOI o contenteditable dang hien (selector chi lay o dau tien co the la o khac, vd mo ta tung anh)
        shown = eval_retry("""() => [...document.querySelectorAll("[contenteditable='true']")]
            .filter(x => x.getBoundingClientRect().width > 0).map(x => x.innerText).join(" ")""")
        return probe in " ".join((shown or "").split())
    except FoxError:
        return False


def fill_text(text: str) -> None:
    """Dien o Van ban/Mo ta (o contenteditable dang hien thi), kiem tra lai va thu cach khac neu khong nhan chu."""
    if not fb.wait_visible(CONTENTEDITABLE, 60):
        raise TimeoutError("Khong thay o noi dung")
    for attempt in range(1, 4):
        fb.click(CONTENTEDITABLE, timeout=SLOW_CLICK_MS)
        fb.press("Control+A")
        fb.press("Delete")
        if attempt < 3:
            fb.type_into(CONTENTEDITABLE, text, timeout=SLOW_CLICK_MS)
        else:  # cach du phong: chen thang vao o contenteditable
            eval_retry("""() => { const e = [...document.querySelectorAll("[contenteditable='true']")]
                .filter(x => x.getBoundingClientRect().width > 0).pop();
                if (!e) return false; e.focus(); document.execCommand('selectAll');
                return document.execCommand('insertText', false, %s); }""" % json.dumps(text))
        time.sleep(1.5)
        fb.click_at(1500, 600)  # bam ra ngoai de dong goi y hashtag (che cac nut ben duoi)
        time.sleep(0.5)
        if caption_ok(text):
            return
        log(f"O noi dung chua nhan chu (lan {attempt}/3) -> thu lai")
    raise RuntimeError("O noi dung van trong sau khi dien")


def ensure_caption(text: str) -> None:
    if not caption_ok(text):
        log("Noi dung bi mat sau khi tai file -> dien lai")
        fill_text(text)


def assert_caption_before_post(text: str) -> None:
    """Kiem tra lai noi dung NGAY TRUOC khi bam Dang (Facebook co the xoa chu trong luc cho tai/xu ly); khong co thi
    dien lai, van khong co thi bao loi de KHONG dang bai trong chu."""
    if caption_ok(text):
        return
    log("Noi dung bi mat truoc khi bam Dang -> dien lai")
    fill_text(text)
    if not caption_ok(text):
        raise RuntimeError("Noi dung trong -> khong bam Dang")


def retry_step(what: str, fn, tries: int = INNER_TRIES):
    """Lam lai tu dau (fn tu load lai composer) khi buoc soan bai loi. CHI dung cho phan TRUOC khi bam Dang."""
    for i in range(1, tries + 1):
        try:
            return fn()
        except NotLoggedIn:
            raise
        except Exception as e:
            if i == tries:
                raise
            log(f"{what}: loi lan {i}/{tries} ({str(e)[:150]}) -> lam lai tu dau")
            time.sleep(5 * i)


def button_state(name: str, which: str = "last"):
    """{'visible', 'disabled'} cua nut theo ten chinh xac (nut cuoi/dau), hoac None neu chua co."""
    pick = "els[els.length - 1]" if which == "last" else "els[0]"
    return eval_retry("""() => {
        const els = [...document.querySelectorAll('button,[role="button"]')].filter(e =>
            [e.getAttribute("aria-label"), e.innerText].some(t => (t || "").trim() === %s));
        const e = %s;
        if (!e) return null;
        const r = e.getBoundingClientRect();
        return {visible: r.width > 0 && r.height > 0,
                disabled: e.getAttribute("aria-disabled") === "true" || e.disabled === true};
    }""" % (json.dumps(name), pick))


def wait_enabled(name: str, timeout_s: float, which: str = "last") -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = button_state(name, which)
        if st and st["visible"] and not st["disabled"]:
            return
        time.sleep(2)
    raise TimeoutError(f"Nut '{name}' khong san sang sau {timeout_s:g}s")


def confirm_done(pattern: str, what: str, timeout_s: float = 180) -> None:
    """Cho Facebook bao thanh cong (hop thoai 'Da dang bai viet...' / da len lich) roi dong hop thoai.

    Thanh cong khi: thay cau thong bao, hoac trinh soan bai da dong (URL roi /composer). Trong luc Facebook con
    xu ly ('Len lich dang bai... Ban cho chut nhe') thi cho tiep -- dong trinh duyet luc nay se huy video."""
    deadline = time.time() + timeout_s
    last_log = 0.0
    check = f"() => new RegExp({json.dumps(pattern)}, 'i').test(document.body.innerText)"
    while time.time() < deadline:
        try:
            found = fb.evaluate(check)
            url = fb.url()
        except FoxError as e:
            if e.status not in (400, 422):
                raise
            found, url = False, "/composer"
        if found or "/composer" not in url:
            log(f"Facebook bao: {what} thanh cong")
            done = 'role=button[name=/^(Xong|Done|Để sau|Later)$/i] >> visible=true'
            if fb.visible(done, 300):
                try:
                    fb.click(done, timeout=3000)
                except FoxError:
                    pass
            time.sleep(2)
            return
        if time.time() - last_log > 120:
            log(f"Dang cho Facebook xu ly ({what})...")
            last_log = time.time()
        time.sleep(3)
    try:
        shot = LOG_DIR / f"fb_confirm_timeout_{int(time.time())}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(fb.screenshot_png())
        dlg = eval_retry("""() => { const d = [...document.querySelectorAll("[role=dialog]")].pop();
                                    return d ? d.innerText.slice(0, 400) : ""; }""").replace("\n", " | ")
        log(f"Chan doan: url={fb.url()} | hop thoai: {dlg} | anh: {shot}")
    except Exception as e:
        log(f"Chan doan loi: {e}")
    raise TimeoutError(f"Khong thay thong bao {what} thanh cong sau {timeout_s:g}s")


def save_shot(path: Path) -> None:
    try:
        path.write_bytes(fb.screenshot_png())
    except Exception as e:
        log(f"Khong chup duoc anh {path.name}: {e}")


def post_photos(asset_id: str, files: list[Path], caption: str, upload_timeout: float,
                no_post: bool, shot: Path) -> None:
    def prepare():
        open_composer(asset_id, files)
        fill_text(caption)
        wait_upload_done(upload_timeout)
        ensure_caption(caption)
        wait_enabled("Đăng", upload_timeout)
    retry_step("dang anh", prepare)
    if no_post:
        save_shot(shot)
        log(f"--no-post: anh form {shot}")
        return
    assert_caption_before_post(caption)
    wait_enabled("Đăng", 60)  # dien lai chu co the lam nut 'Dang' tam thoi bi khoa
    log("Click 'Đăng'")
    fb.click(role_btn("Đăng", "last"))
    confirm_done(POSTED_RE, "dang anh")


def read_schedule() -> tuple[str, str]:
    """Doc lai (ngay hien thi, 'HH:MM') dang dat o buoc Chia se."""
    date_txt = eval_retry("""() => { const i = [...document.querySelectorAll("input:not([type]):not([aria-label])")]
        .find(e => e.getBoundingClientRect().width > 0); return i ? i.value : ""; }""")
    row = eval_retry(r"""() => { const re = /Asia\/|GMT|UTC/;
        const el = [...document.querySelectorAll("body *")].find(e => e.children.length === 0 && re.test(e.textContent));
        return el && el.parentElement ? el.parentElement.innerText : ""; }""")
    m = re.search(r"(\d{1,2})\D+(\d{2})", row)
    return date_txt, (f"{int(m.group(1)):02d}:{m.group(2)}" if m else row.strip())


def set_schedule(when: datetime) -> None:
    """Buoc 'Chia se' cua thuoc phim: tab 'Len lich' -> ngay (d/m/yyyy) + gio + phut."""
    fb.click(role_btn("Lên lịch", "first"))  # tab (nut 'Len lich' thu 2 o cuoi trang)
    time.sleep(1.5)
    fb.click(DATE_INPUT)
    fb.press("Control+A")
    fb.keyboard_type(f"{when.day}/{when.month}/{when.year}")
    fb.press("Enter")
    time.sleep(0.8)
    for label, value in (("giờ", f"{when.hour:02d}"), ("phút", f"{when.minute:02d}")):
        sel = f'role=spinbutton[name="{label}"i]'
        fb.click(sel)
        fb.press("Control+A")
        fb.keyboard_type(value)
    fb.press("Tab")
    time.sleep(0.8)
    date_txt, hhmm = read_schedule()
    log(f"Lich dang video da dat: '{date_txt}' {hhmm} (can {when:%d/%m/%Y %H:%M})")
    if hhmm != f"{when:%H:%M}" or f"{when.day}" not in date_txt.split()[0] or f"Tháng {when.month}" not in date_txt:
        raise RuntimeError(f"Khong dat dung lich hen: '{date_txt}' {hhmm} != {when:%d/%m/%Y %H:%M}")


def scheduled_in_calendar(asset_id: str, when: datetime) -> bool:
    """Mo tab moi xem Lich noi dung (tuan cua `when`) co bai nao o dung gio hen khong."""
    origin = fb.active_tab_index()
    tabs = fb.tab_new(f"https://business.facebook.com/latest/content_calendar?asset_id={asset_id}")
    new_index = next(t["index"] for t in tabs if t["active"])
    try:
        time.sleep(12)
        if when.date() > datetime.now().date() and when.weekday() == 0:  # tuan bat dau Chu nhat: sang tuan sau
            fb.click("role=button[name=/Tiếp|Next|Sau/] >> nth=-1")
            time.sleep(5)
        return fb.visible(f'text="{when:%H:%M}" >> visible=true', 1000)
    except Exception as e:
        log(f"Khong kiem tra duoc lich noi dung: {e}")
        return False
    finally:
        try:
            fb.tab_close(new_index)
            fb.tab_select(origin)
        except FoxError as e:
            log(f"Khong dong duoc tab lich: {e}")


def round_up_5(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    return dt + timedelta(minutes=(5 - dt.minute % 5) % 5)


# 10/2026: hop thoai 'Chinh sua video' khong con muc anh thu nho; mo no ra chi de lai hop thoai che nut 'Dang'
# (hop thoai hien cham, dong khong kip) -> tat buoc dat anh bia. Facebook co lai tinh nang thi doi thanh True.
SET_COVER = False
# Nut but chi canh video (khong co aria-label, ten = "Chinh sua video" + ky tu zero-width)
EDIT_MEDIA_SEL = r"role=button[name=/^(Chỉnh sửa|Edit)( video)?\W*$/i] >> visible=true >> nth=0"
THUMB_TAB_SEL = r"role=dialog >> text=/Ảnh thu nhỏ|Ảnh bìa|Thumbnail|Cover/i >> visible=true >> nth=0"
THUMB_UPLOAD_SEL = r"role=button[name=/Tải ảnh lên|Tải lên|Upload/i] >> visible=true >> nth=0"
THUMB_SAVE_SEL = r"role=button[name=/^(Lưu|Xong|Áp dụng|Save|Done|Apply)$/i] >> visible=true >> nth=-1"
DIALOG_CANCEL_SEL = r"role=dialog >> role=button[name=/^(Hủy|Đóng|Cancel|Close)\W*$/i] >> visible=true >> nth=-1"


def close_dialog() -> None:
    try:
        if fb.visible(DIALOG_CANCEL_SEL, 1000):
            fb.click(DIALOG_CANCEL_SEL, timeout=5000)
        else:
            fb.press("Escape")
        time.sleep(1)
    except FoxError as e:
        log(f"Khong dong duoc hop thoai: {e}")


def set_cover(cover: Path, shot: Path) -> None:
    """Dat anh bia cho video vua tai len: Chinh sua video -> Anh thu nho -> Tai anh len -> Luu.
    Giao dien 10/2026: hop thoai 'Chinh sua video' chi con 'Thu ngan', khong co anh thu nho -> KHONG dat duoc
    thi chup man hinh vao `shot`, dong hop thoai va dang voi anh bia Facebook tu chon (khong tinh la loi)."""
    log(f"Dat anh bia: {cover.name}")
    try:
        if not fb.wait_visible(EDIT_MEDIA_SEL, 120):  # nut chi hien khi video da tai len xong
            raise TimeoutError("Khong thay nut 'Chỉnh sửa video'")
        fb.click(EDIT_MEDIA_SEL, timeout=10000)
        time.sleep(2)
        if not fb.visible(THUMB_TAB_SEL, 3000):
            raise RuntimeError("Hop thoai 'Chỉnh sửa video' khong co muc anh thu nho")
        fb.click(THUMB_TAB_SEL, timeout=5000)
        time.sleep(1)
        fb.upload([cover], trigger=THUMB_UPLOAD_SEL, timeout=15000)
        time.sleep(4)
        fb.click(THUMB_SAVE_SEL, timeout=10000)
        time.sleep(3)
    except Exception as e:
        save_shot(shot)
        log(f"Bo qua anh bia ({str(e)[:150]}); anh man hinh: {shot}")
        close_dialog()


def publish_video(asset_id: str, video: Path, caption: str, upload_timeout: float,
                  no_post: bool, shot: Path, cover: Path | None = None) -> None:
    """Dang video NGAY (khong hen gio): Tao -> Chinh sua -> Chia se -> 'Dang'. Co `cover` thi dat anh bia."""
    def prepare() -> str:
        open_composer(asset_id, [video])
        fill_text(caption)
        wait_upload_done(upload_timeout)
        if cover and SET_COVER:
            set_cover(cover, shot.with_name(f"{shot.stem}_cover_error.png"))
        ensure_caption(caption)
        # Giao dien hien tai: chi co nut 'Dang'. Giao dien cu (thuoc phim) co them 1-2 buoc 'Tiep' truoc 'Chia se' -> bam neu thay.
        final, clicked, deadline = "Đăng", 0, time.time() + min(upload_timeout, 600)
        while time.time() < deadline:
            st = button_state("Đăng")
            if st and st["visible"] and not st["disabled"]:
                break
            nxt = button_state("Tiếp")
            if nxt and nxt["visible"] and not nxt["disabled"]:
                clicked += 1
                log(f"Click 'Tiếp' (buoc {clicked})")
                fb.click(role_btn("Tiếp", "last"))
                time.sleep(3)
                if clicked >= 2:
                    final = next((n for n in ("Đăng", "Chia sẻ", "Đăng ngay") if button_state(n)), "Đăng")
                    break
                continue
            time.sleep(2)
        else:
            raise TimeoutError("Khong thay nut 'Đăng'/'Tiếp' san sang sau 600s")
        wait_enabled(final, min(upload_timeout, 300))
        return final
    final = retry_step("dang video", prepare)
    if no_post:
        save_shot(shot)
        log(f"--no-post: anh form {shot} (nut cuoi: '{final}')")
        return
    assert_caption_before_post(caption)
    wait_enabled(final, 60)
    log(f"Click '{final}' (nut cuoi)")
    try:
        # Facebook co the khoa lai nut ngay sau khi vua mo (video dai dang xu ly) -> click 10s mac dinh het gio.
        # Click het gio = chua bam (Playwright cho nut mo khoa roi moi bam) nen cho tiep, khong so dang 2 lan.
        for i in range(1, 5):
            try:
                fb.click(role_btn(final, "last"), timeout=SLOW_CLICK_MS)
                break
            except FoxError as e:
                if not e.is_timeout or i == 4:
                    raise
                log(f"Nut '{final}' van bi khoa sau 45s (lan {i}/4) -> cho tiep")
    except FoxError as e:
        # Click co the bao loi du Facebook da nhan lenh (trinh soan bai tu dong dong) -> kiem tra truoc khi coi la that bai.
        try:
            still_composer = "/composer" in fb.url()
        except FoxError:
            still_composer = True
        if still_composer:
            raise
        log(f"Click '{final}' bao loi ({e}) nhung trinh soan bai da dong -> coi nhu da dang")
    # Chi can bam 'Dang' thanh cong la du: cho ngan xem Facebook xac nhan, het gio van tinh la da dang
    # (video len muc 'Da dang' rat lau, khong cho no xuat hien).
    try:
        confirm_done(POSTED_RE, "dang video", min(upload_timeout, 90))
    except TimeoutError as e:
        log(f"{e} -> da bam '{final}' nen van tinh la da dang")


# ---------- Comment vao video da len song ----------

def post_comment(asset_id: str, job: dict, no_post: bool, shot: Path) -> None:
    """Mo danh sach bai da dang cua Trang, bam vao bai video (tim theo tieu de) roi comment bang tai khoan Trang."""
    snippet = job["video_caption"].splitlines()[0].strip()[:30]
    text = job["comment_text"]
    row = f"xpath=(//*[not(*)][contains(normalize-space(.), {xpath_literal(snippet)})])[1]"
    box_ready = False
    for attempt in range(1, 4):  # danh sach bai co the cham cap nhat / dialog chua mo -> load lai tu dau
        fb.navigate(f"https://business.facebook.com/latest/posts/published_posts?asset_id={asset_id}", wait_until="load")
        if not fb.wait_visible(row, 45 + 30 * attempt):
            log(f"Chua thay bai video '{snippet}' (lan {attempt}/3)")
            continue
        fb.click(row)
        if fb.wait_visible(COMMENT_BOX_SEL, 30):
            box_ready = True
            break
        log(f"Khong thay o binh luan sau khi mo bai (lan {attempt}/3)")
    if not box_ready:
        save_shot(shot)
        raise RuntimeError(f"Khong mo duoc o binh luan cua bai '{snippet}' (co the chua len song)")
    fb.click(COMMENT_BOX_SEL)
    fb.type_into(COMMENT_BOX_SEL, text)
    time.sleep(1)
    if no_post:
        save_shot(shot)
        log(f"--no-post: anh o binh luan {shot}")
        return
    fb.press("Enter")
    probe = text[:25]
    for i in range(12):
        time.sleep(2)
        if not fb.text_of(COMMENT_BOX_SEL).strip() and probe in body_text():
            return
        if i == 5 and fb.text_of(COMMENT_BOX_SEL).strip():  # Enter chua gui duoc (o van con chu) -> bam lai
            fb.press("Enter")
    save_shot(shot)
    raise RuntimeError("Khong xac nhan duoc binh luan da len")


def run_comment_job(job: dict, asset_id: str, a, save) -> None:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", job["page"])
    shot = job_dir(job) / f"comment_{safe}.png"
    job["comment_try_at"] = datetime.now().isoformat(timespec="minutes")
    save()
    log(f"--- Comment: {job['comment_text']} ---")
    post_comment(asset_id, job, a.no_post, shot)
    if not a.no_post:
        job["comment_status"], job["commented_at"] = "done", time.strftime("%Y-%m-%dT%H:%M:%S")
        job.pop("error", None)
        save()


# ---------- Dieu phoi theo ke hoach ----------

def job_files(job: dict) -> list[str]:
    """Anh + video cua job; job co the chi co video (photo_files rong) hoac chi co anh (khong video_file)."""
    return [*job.get("photo_files", []), *([job["video_file"]] if job.get("video_file") else [])]


def job_dir(job: dict) -> Path:
    files = job_files(job)
    return Path(files[0]).parent if files else LOG_DIR


def run_job(job: dict, asset_id: str, a, save) -> None:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", job["page"])
    shot_dir = job_dir(job)
    delay = timedelta(hours=job.get("video_delay_hours", 2))
    has_video = bool(job.get("video_file"))

    if not job.get("photo_files") and job.get("photo_status") != "done":
        # Bai chi co video: bo buoc anh, dang video ngay
        job["photo_status"], job["video_at"] = "done", datetime.now().isoformat(timespec="minutes")

    if job.get("photo_status") != "done":
        # Gio dang video = (bay gio + so gio cho), lam tron 5 phut; ghi vao bai anh de nhac nguoi xem
        when = round_up_5(datetime.now() + delay)
        job["video_at"] = when.isoformat(timespec="minutes")
        caption = (job["photo_caption"].format(video_time=f"{when:%H:%M}", video_date=f"{when:%d/%m}")
                   if has_video else job.get("photo_caption", ""))
        log(f"--- Anh: {len(job['photo_files'])} anh"
            + (f", video se dang luc {when:%H:%M %d/%m} ---" if has_video else " ---"))
        post_photos(asset_id, [Path(f) for f in job["photo_files"]], caption, a.upload_timeout,
                    a.no_post, shot_dir / f"nopost_photo_{safe}.png")
        if not a.no_post:
            job["photo_status"], job["photo_posted_at"] = "done", time.strftime("%Y-%m-%dT%H:%M:%S")
            job.pop("error", None)
            job.pop("retry_at", None)
            if not has_video:  # bai chi co anh: xong luon
                job["video_status"] = "done"
            save()

    if job.get("video_status") not in ("done", "failed"):
        if not a.now and datetime.fromisoformat(job["video_at"]) > datetime.now():
            log(f"Chua toi gio dang video ({job['video_at']}) -> de lan chay sau")
            return
        log("--- Dang video ngay ---")
        cover = Path(job["video_cover"]) if job.get("video_cover") else None
        publish_video(asset_id, Path(job["video_file"]), job["video_caption"], a.upload_timeout,
                      a.no_post, shot_dir / f"nopost_video_{safe}.png", cover)
        if not a.no_post:
            posted = datetime.now()
            job["video_status"], job["video_posted_at"] = "done", posted.strftime("%Y-%m-%dT%H:%M:%S")
            job["comment_status"] = "pending"
            job["comment_at"] = (posted + timedelta(minutes=job.get("comment_delay_minutes", fanpage_jobs.COMMENT_DELAY_MIN))
                                 ).isoformat(timespec="minutes")
            job.pop("error", None)
            save()


job_complete = fanpage_jobs.job_complete


def load_pages(a) -> list[dict]:
    cache = Path(a.pages_cache or fanpage_jobs.pages_cache(a.profile))
    cache.parent.mkdir(parents=True, exist_ok=True)
    if a.list_pages or a.refresh_pages or not cache.exists():
        pages = list_pages()
        cache.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Da luu {len(pages)} Trang vao {cache}")
        return pages
    return json.loads(cache.read_text(encoding="utf-8"))


def fresh_tab() -> None:
    """Xong 1 Trang -> dong tab lam viec, mo tab rieng moi cho nhe RAM (khong dong tab Muse cua bot)."""
    close_work_tab(fb)
    open_work_tab(fb)


def logged_in() -> bool:
    fb.navigate(START_URL, wait_until="load")
    time.sleep(3)
    return not ("login" in fb.url() or fb.visible("input[name='pass']", 300))


def run(a) -> int:
    global fb
    fb = FoxProfileBrowser(a.profile, log=log)
    plan_path = Path(a.plan) if a.plan else None
    jobs = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path else []
    for j in jobs if not a.comment else []:
        missing = [f for f in job_files(j) if not Path(f).is_file()]
        if missing:
            log(f"Khong tim thay file: {missing}")
            return 2

    only = {n.casefold() for n in a.only}
    now = datetime.now()

    def wanted(j: dict) -> bool:
        if only and j["page"].casefold() not in only:
            return False
        if a.comment:
            return fanpage_jobs.comment_due(j, now) and bool(j.get("comment_text"))
        return not job_complete(j)

    own_pages = {j["page"].casefold() for j in jobs if wanted(j)}

    def save():
        """Ghi lai cac job cua tien trinh nay, GIU NGUYEN job cua tien trinh khac."""
        if not plan_path:
            return
        current = json.loads(plan_path.read_text(encoding="utf-8"))
        mine = {j["page"].casefold(): j for j in jobs}
        merged = [mine[j["page"].casefold()] if j["page"].casefold() in own_pages else j for j in current]
        tmp = plan_path.with_name(f"{plan_path.name}.{os.getpid()}.tmp")  # ghi nguyen tu
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, plan_path)

    started = False
    try:
        try:
            started = fb.ensure()
        except FoxError as e:
            log(f"LOI FoxProfile: {e}")
            return 4
        open_work_tab(fb)

        if a.plan and not a.comment:
            problem = fb.check_upload_support()
            if problem:
                log(f"LOI: {problem}")
                return 4

        if not logged_in():
            raise NotLoggedIn(f"Profile '{fb.profile}' chua dang nhap Facebook/Meta Business")

        pages = load_pages(a)
        if a.list_pages:
            return 0
        by_name = {p["name"].casefold(): p for p in pages if p["asset_id"]}
        by_id = {str(p["asset_id"]): p for p in pages if p["asset_id"]}
        refreshed = a.list_pages or a.refresh_pages
        todo = [j for j in jobs if wanted(j)
                and (a.comment or not a.due_only or a.now or fanpage_jobs.job_due(j, now))]
        log(f"Se chay {len(todo)}/{len(jobs)} job: {[j['page'] for j in todo]}")

        failed = wrong = 0
        for i, j in enumerate(todo, 1):
            page_id = str(j.get("page_id") or "")
            if page_id:  # Bang dang bai: chon Trang theo Page ID, khong theo ten (2 Trang co the trung ten)
                if page_id not in by_id and not refreshed:
                    log(f"Page ID {page_id} chua co trong danh sach Trang da quet -> quet lai")
                    pages = list_pages()
                    Path(a.pages_cache or fanpage_jobs.pages_cache(a.profile)).write_text(
                        json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
                    by_id = {str(p["asset_id"]): p for p in pages if p["asset_id"]}
                    refreshed = True
                p = by_id.get(page_id)
                if not p:
                    log(f"DUNG: Trang {j['page']} ({page_id}) KHONG thuoc tai khoan Facebook dang nhap o profile "
                        f"'{a.profile}' -> khong dang (sua Bang dang bai hoac dang nhap dung tai khoan)")
                    j["error"] = "Trang không thuộc tài khoản đang đăng nhập"
                    if not a.comment:
                        j["photo_status"] = j["video_status"] = "failed"
                    wrong += 1
                    save()
                    continue
            else:
                p = by_name.get(j["page"].casefold())
            if not p:
                log(f"Khong co Trang '{j['page']}' trong danh sach")
                j["error"] = "không có Trang"
                failed += 1
                save()
                continue
            log(f"=== [{i}/{len(todo)}] {p['name']} ({p['asset_id']}) ===")
            try:
                if a.comment:
                    run_comment_job(j, p["asset_id"], a, save)
                else:
                    run_job(j, p["asset_id"], a, save)
                log(f"OK: {p['name']}")
                if not a.comment and job_complete(j):
                    fresh_tab()
            except Exception as e:
                log(f"LOI o '{p['name']}': {e}")
                j["error"] = str(e)[:300]
                if not a.comment:
                    # Dem so lan loi theo tung buoc; chua toi --max-attempts thi nghi mot luc roi tu thu lai
                    # (scheduler goi lai khi het retry_at), qua han moi bo buoc do de khong ket hang doi mai.
                    phase = "photo" if j.get("photo_status") != "done" else "video"
                    j[f"{phase}_attempts"] = j.get(f"{phase}_attempts", 0) + 1
                    n = j[f"{phase}_attempts"]
                    if n >= a.max_attempts:
                        j[f"{phase}_status"] = "failed"
                        if phase == "photo":
                            j["video_status"] = "failed"
                        j.pop("retry_at", None)
                        log(f"'{p['name']}': loi {n} lan -> bo qua buoc {phase}")
                    else:
                        wait = min(fanpage_jobs.RETRY_BACKOFF_MIN * n, fanpage_jobs.RETRY_BACKOFF_MAX)
                        j["retry_at"] = (datetime.now() + timedelta(minutes=wait)).isoformat(timespec="minutes")
                        log(f"'{p['name']}': loi {n}/{a.max_attempts} -> tu thu lai {phase} sau {wait} phut ({j['retry_at']})")
                if a.comment:
                    j["comment_attempts"] = j.get("comment_attempts", 0) + 1
                    if j["comment_attempts"] >= fanpage_jobs.COMMENT_MAX_ATTEMPTS:
                        j["comment_status"] = "failed"
                failed += 1
                save_shot(job_dir(j) / f"error_fb_biz_{p['asset_id']}.png")
                save()
            if i < len(todo):
                time.sleep(a.delay)
        if wrong:
            log(f"{wrong} job co Trang khong thuoc tai khoan dang nhap")
            return 6
        if failed:
            log(f"That bai {failed} job")
            return 1
        return 0
    except NotLoggedIn as e:
        log(f"LOI: {e}")
        return 3
    finally:
        close_work_tab(fb)
        if started and not a.keep_open:
            fb.stop()


def login(a) -> int:
    global fb
    fb = FoxProfileBrowser(a.profile, log=log)
    fb.ensure()
    fb.navigate("https://business.facebook.com/latest/", wait_until="domcontentloaded")
    input("Dang nhap Facebook/Meta Business tren cua so profile, xong nhan Enter (profile van duoc giu mo)...")
    return 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tu dong dang bai len fanpage Facebook da dang nhap o profile FoxProfile")
    ap.add_argument("--plan", default="", help="File jobs JSON")
    ap.add_argument("--due-only", action="store_true", help="Chi chay job da toi gio 'due'")
    ap.add_argument("--profile", required=True, help="Ten profile FoxProfile da dang nhap Facebook")
    ap.add_argument("--only", nargs="+", default=[], help="Chi chay cac Trang co ten nay")
    ap.add_argument("--login", action="store_true", help="Mo profile de dang nhap Facebook bang tay roi thoat")
    ap.add_argument("--list-pages", action="store_true", help="Chi liet ke Trang + luu cache roi thoat")
    ap.add_argument("--refresh-pages", action="store_true", help="Quet lai danh sach Trang")
    ap.add_argument("--pages-cache", default="", help="Mac dinh: social_post/data/fb_pages_<profile>.json")
    ap.add_argument("--upload-timeout", type=float, default=1500)
    ap.add_argument("--max-attempts", type=int, default=6, help="So lan loi toi da moi buoc (anh/video) truoc khi bo")
    ap.add_argument("--now", action="store_true", help="Dang video ngay du chua toi video_at (de thu)")
    ap.add_argument("--delay", type=float, default=10, help="Giay nghi giua cac Trang")
    ap.add_argument("--comment", action="store_true", help="Comment vao video da len song (job toi gio comment)")
    ap.add_argument("--no-post", action="store_true", help="Chay thu, KHONG bam Dang/Len lich/Enter comment")
    ap.add_argument("--keep-open", action="store_true", help="Khong dong profile du chinh script mo no")
    a = ap.parse_args()
    if a.login:
        sys.exit(login(a))
    if not a.list_pages and not a.plan:
        ap.error("can --plan (hoac --list-pages / --login)")
    sys.exit(run(a))


if __name__ == "__main__":
    main()
