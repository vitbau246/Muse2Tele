# -*- coding: utf-8 -*-
"""
Tao Trang Facebook va kenh YouTube (kenh them, Tai khoan thuong hieu) tren tai khoan dang dang nhap trong 1 profile
FoxProfile, roi gan ten, tieu su / mo ta, anh dai dien, anh bia / banner. Moi profile 1 file cau hinh:
social_post\\data\\channels\\<profile>.json (xem data\\channels\\Muse9.json):

  {"facebook": {"name", "category", "bio" (<= 255 ky tu), "avatar", "cover",
                "account" (ten trang ca nhan dang nhap: tao xong tu chuyen ve, xem fb_switch_to)},
   "youtube":  {"name", "handle" (khong co @), "description", "avatar", "banner" (>= 2048x1152, <= 6 MB),
                "links": [{"title", "url"}] (tuy chon; "{facebook}" = link Trang vua tao)}}

Duong dan anh tinh tu thu muc goc Muse2Tele va phai nam trong FOXPROFILE_UPLOAD_DIRS (Videos\\downloads).
Tao xong, script ghi ket qua vao chinh file do ("created": page_id / channel_id, url, at); da co "created" thi KHONG
tao lai (tranh 2 Trang / 2 kenh), chi lam lai buoc anh + mo ta khi them --refresh.

  python create_channels.py --profile Muse9                    # Facebook + YouTube
  python create_channels.py --profile Muse9 --only facebook    # hoac youtube
  python create_channels.py --profile Muse9 --dry-run          # dien form, chup anh, KHONG bam tao
  python create_channels.py --profile Muse9 --only youtube --refresh   # cap nhat anh / mo ta kenh da tao

Kiem chung 2026-11-11 tren Muse9 (giao dien tieng Viet). Cac nut cua Facebook / YouTube Studio bam theo toa do
(evaluate tim nut theo chu, click-at): click theo selector hay het gio vi lop phu vo hinh.
Khong lam: dang ky tai khoan moi, xac minh SDT / CAPTCHA (gap thi dung, bao lam tay).
Ma thoat: 0 = OK, 1 = loi (co anh chup trong logs\\), 2 = thieu file / cau hinh, 5 = FoxProfile chua san sang.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import fanpage_jobs
from fox_common import (EXIT_ERROR, EXIT_FOX_UNAVAILABLE, EXIT_NO_FILE, EXIT_OK, FoxError, FoxSession,
                        FoxUnavailable, close_work_tab, log, open_work_tab, wait_for)

ROOT = fanpage_jobs.ROOT_DIR
CONFIG_DIR = Path(__file__).resolve().parent / "data" / "channels"
LOG_DIR = Path(__file__).resolve().parent / "logs"

FB_CREATE_URL = "https://www.facebook.com/pages/creation/"
# Trang chuyen kenh co link "Tao kenh" (/create_channel?...); /account khong con link nay khi dang dung kenh thuong hieu
YT_ACCOUNT_URL = "https://www.youtube.com/channel_switcher"
STUDIO_PROFILE_URL = "https://studio.youtube.com/channel/{id}/editing/profile"

# Chu tren nut (vi + en)
T_CREATE_PAGE = ("Tạo Trang", "Create Page")
T_NEXT = ("Tiếp", "Next")
T_SKIP = ("Bỏ qua", "Skip")
T_DONE = ("Xong", "Done")
T_CREATE_CHANNEL = ("Tạo kênh", "Create channel")
T_PUBLISH = ("Xuất bản", "Publish")
T_ADD_LINK = ("Thêm đường liên kết", "Add link")

# Tam diem cac phan tu dang hien co chu dung bang 1 trong cac chu cho truoc (cuon vao giua man hinh truoc)
FIND_JS = """(texts, sel) => {
  const els = [...document.querySelectorAll(sel)].filter(e => e.offsetParent && texts.includes(e.innerText.trim())
      && e.getAttribute('aria-disabled') !== 'true' && !e.hasAttribute('disabled'));
  const e = els[els.length - 1];
  if (!e) return null;
  const r0 = e.getBoundingClientRect();
  if (r0.top < 0 || r0.bottom > innerHeight) e.scrollIntoView({block: 'center'});
  const r = e.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
}"""
BUTTONS = "[role=button], button, ytcp-button, a, [role=option]"


class StepError(Exception):
    pass


def goto(fb, url, tries=2):
    """Mo trang, chi cho DOM (Facebook / YouTube tai 'load' hay qua 30s); het gio thi thu lai."""
    for i in range(tries):
        try:
            return fb.navigate(url, wait_until="domcontentloaded")
        except FoxError as e:
            if i == tries - 1 or "Timeout" not in str(e):
                raise
            log(f"Mo {url} qua lau, thu lai")


def js(fb, fn, *args):
    return fb.evaluate(f"() => ({fn})({', '.join(json.dumps(a) for a in args)})")


def click_text(fb, texts, sel=BUTTONS):
    pt = js(fb, FIND_JS, list(texts), sel)
    if not pt:
        return False
    fb.click_at(*pt)
    return True


def click_text_wait(fb, texts, timeout_s=20, sel=BUTTONS):
    if not wait_for(lambda: click_text(fb, texts, sel), timeout_s):
        raise StepError(f"khong thay nut {texts[0]!r}")


def body(fb, n=4000):
    return fb.text_of("body", n)


def shot(fb, name):
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{name}.png"
    try:
        path.write_bytes(fb.screenshot_png())
        log(f"Anh chup: {path}")
    except FoxError as e:
        log(f"Khong chup duoc anh: {e}")
    return path


def image(path):
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    if not p.is_file():
        raise FileNotFoundError(f"khong thay anh {p}")
    return p.resolve()


def type_at(fb, point, text, clear=True):
    fb.click_at(*point)
    if clear:
        fb.press("Control+A")
        fb.press("Backspace")
    fb.keyboard_type(text)


def save_created(cfg_path, data, key, created):
    data[key]["created"] = {**created, "at": datetime.now().isoformat(timespec="seconds")}
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Da ghi ket qua {key} vao {cfg_path}")


# ---------------- Facebook ----------------

ACCOUNT_BTN = '[aria-label="Tài khoản, trang cá nhân của bạn"], [aria-label="Your profile"]'
CATEGORY_SEL = 'input[aria-label^="Hạng mục"], input[aria-label^="Category"]'


def center_of(fb, selector):
    return js(fb, """(sel) => { const e = [...document.querySelectorAll(sel)].find(e => e.offsetParent);
        if (!e) return null; const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }""",
              selector)


def fb_switch_to(fb, name):
    """Dung Facebook voi tu cach `name` (trang ca nhan). Tao Trang xong, Facebook tu chuyen phien sang dung voi tu
    cach Trang moi; Trang thi khong tao duoc Trang khac ("Ban hien khong xem duoc noi dung nay")."""
    goto(fb, "https://www.facebook.com/")
    if not wait_for(lambda: center_of(fb, ACCOUNT_BTN), 20):
        raise StepError("khong thay nut tai khoan Facebook")
    fb.click_at(*center_of(fb, ACCOUNT_BTN))
    target = f'[aria-label="Chuyển sang {name}"], [aria-label="Switch to {name}"]'
    if not wait_for(lambda: center_of(fb, target), 8):
        fb.press("Escape")
        log(f"Facebook: khong co nut chuyen sang {name!r} (dang dung voi tu cach {name}?)")
        return
    fb.click_at(*center_of(fb, target))
    log(f"Facebook: chuyen sang {name}")
    time.sleep(10)


def fb_fill_form(fb, c):
    goto(fb, FB_CREATE_URL)
    if not fb.wait_visible(CATEGORY_SEL, 20) and c.get("account"):
        fb_switch_to(fb, c["account"])
        goto(fb, FB_CREATE_URL)
    if not fb.wait_visible(CATEGORY_SEL, 30):
        raise StepError("khong mo duoc form Tao Trang (chua dang nhap Facebook, hoac dang dung voi tu cach Trang: "
                        "dien \"account\" = ten trang ca nhan trong cau hinh)")
    fb.type_into('label:has-text("Tên Trang") input, label:has-text("Page name") input', c["name"])
    fb.type_into(CATEGORY_SEL, c["category"])
    # Danh sach goi y: chon muc trung chu, khong co thi muc dau tien
    if not wait_for(lambda: click_text(fb, [c["category"]], "[role=option]"), 10):
        options = js(fb, "() => [...document.querySelectorAll('[role=option]')].filter(e => e.offsetParent)"
                         ".map(e => e.innerText.trim())")
        if not options or not click_text(fb, options[:1], "[role=option]"):
            raise StepError(f"khong chon duoc hang muc {c['category']!r}")
        log(f"Facebook: khong co hang muc {c['category']!r}, chon {options[0]!r}")
    time.sleep(1)
    if c.get("bio"):
        fb.type_into('label:has-text("Tiểu sử") textarea, label:has-text("Bio") textarea', c["bio"][:255])
    time.sleep(1)


def fb_wizard(fb, c):
    """Cac buoc sau khi tao: 1 lien he (bo trong), 2 anh dai dien + anh bia, 3 WhatsApp (bo qua), 4 moi ban (tiep),
    5 thong bao (xong). Tra ve URL Trang (profile.php?id=...)."""
    uploaded = False
    idle = 0
    for _ in range(25):
        time.sleep(3)
        url = fb.url()
        if "/pages/creation" not in url:
            return url
        text = body(fb, 1500)
        step = re.search(r"(?:Bước|Step) (\d)/5", text)
        if step and step.group(1) == "2" and not uploaded:
            for key, nth in (("avatar", "0"), ("cover", "-1")):
                if c.get(key):
                    fb.upload([image(c[key])], input_selector=f"input[type=file] >> nth={nth}")
                    log(f"Facebook: da chon {key}")
                    time.sleep(5)
            uploaded = True
            time.sleep(4)
        if click_text(fb, T_SKIP) or click_text(fb, T_NEXT) or click_text(fb, T_DONE):
            idle = 0
            continue
        idle += 1
        if idle > 5:
            raise StepError("ket o trinh thiet lap Trang")
    raise StepError("trinh thiet lap Trang chua xong")


def facebook(fb, cfg_path, data, dry_run=False, refresh=False):
    c = data["facebook"]
    if c.get("created") and not refresh:
        log(f"Facebook: da tao truoc do {c['created'].get('url')}, bo qua")
        return
    if c.get("created"):
        log("Facebook: --refresh chua ho tro cho Trang (doi anh trong trang Trang), bo qua")
        return
    fb_fill_form(fb, c)
    shot(fb, "fb_form")
    if dry_run:
        log("Facebook: --dry-run, khong bam Tao Trang")
        return
    click_text_wait(fb, T_CREATE_PAGE)
    if not wait_for(lambda: re.search(r"(?:Bước|Step) \d/5", body(fb, 800)) or "/pages/creation" not in fb.url(), 60):
        raise StepError("bam Tao Trang nhung khong thay Trang duoc tao")
    log("Facebook: da tao Trang, dang thiet lap")
    save_created(cfg_path, data, "facebook", {"page_id": "", "url": ""})
    url = fb_wizard(fb, c)
    m = re.search(r"[?&]id=(\d+)", url) or re.search(r"facebook\.com/(\d+)", url)
    save_created(cfg_path, data, "facebook", {"page_id": m.group(1) if m else "", "url": url})
    log(f"Facebook: xong {url}")
    if c.get("account"):  # tra trinh duyet ve trang ca nhan nhu truoc
        fb_switch_to(fb, c["account"])
    else:
        log("Facebook: trinh duyet dang dung voi tu cach Trang moi (them \"account\" de tu chuyen ve ca nhan)")


# ---------------- YouTube ----------------

INPUTS_JS = """() => [...document.querySelectorAll('input')].filter(e => e.offsetParent && e.type === 'text'
  && !/Tìm kiếm|Search/i.test(e.placeholder)).map(e => { const r = e.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2]; })"""


def yt_create(fb, c):
    goto(fb, YT_ACCOUNT_URL)
    time.sleep(6)
    if not wait_for(lambda: click_text(fb, ["Tạo kênh mới", "Create a new channel", "Tạo kênh", "Create channel"],
                                       "a[href*='create_channel']"), 20):
        raise StepError("khong thay link Tao kenh moi (chua dang nhap YouTube?)")
    if not wait_for(lambda: len(js(fb, INPUTS_JS)) >= 2, 20):
        raise StepError("khong mo duoc hop thoai tao kenh")
    name_pt, handle_pt = js(fb, INPUTS_JS)[:2]
    type_at(fb, name_pt, c["name"])
    time.sleep(2)
    type_at(fb, handle_pt, c["handle"].lstrip("@"))
    time.sleep(5)  # YouTube kiem tra handle con trong


def youtube(fb, cfg_path, data, dry_run=False, refresh=False):
    c = data["youtube"]
    created = c.get("created")
    if created and not refresh:
        log(f"YouTube: da tao truoc do {created.get('url')}, bo qua")
        return
    if not created:
        yt_create(fb, c)
        shot(fb, "yt_form")
        if dry_run:
            log("YouTube: --dry-run, khong bam Tao kenh")
            return
        click_text_wait(fb, T_CREATE_CHANNEL)
        if not wait_for(lambda: "/channel/UC" in fb.url(), 60):
            raise StepError("bam Tao kenh nhung khong chuyen sang kenh moi (handle trung / can xac minh?)")
        cid = re.search(r"/channel/(UC[\w-]+)", fb.url()).group(1)
        created = {"channel_id": cid, "url": f"https://www.youtube.com/@{c['handle'].lstrip('@')}"}
        save_created(cfg_path, data, "youtube", created)
        log(f"YouTube: da tao kenh {cid}")
    yt_customize(fb, c, created["channel_id"], data)


def yt_customize(fb, c, cid, data):
    """YouTube Studio > Tuy chinh > Ho so: banner (o file 0), anh (o 1), mo ta, duong lien ket, Xuat ban."""
    goto(fb, STUDIO_PROFILE_URL.format(id=cid))
    if not fb.wait_visible("#textbox[contenteditable=true]", 40):
        raise StepError("khong mo duoc YouTube Studio > Tuy chinh kenh")
    time.sleep(3)
    for key, nth in (("banner", 0), ("avatar", 1)):
        if c.get(key):
            fb.upload([image(c[key])], input_selector=f"input[type=file] >> nth={nth}")
            time.sleep(5)
            click_text_wait(fb, T_DONE, 30)  # hop thoai cat anh
            log(f"YouTube: da gan {key}")
            time.sleep(3)
    if c.get("description"):
        # Go phim Enter trong o mo ta lam con tro nhay ve dau: chen ca doan bang insertText
        fb.evaluate("() => document.querySelector('#textbox[contenteditable=true]').scrollIntoView({block:'center'})")
        pt = fb.evaluate("() => { const r = document.querySelector('#textbox[contenteditable=true]')"
                         ".getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }")
        fb.click_at(*pt)
        fb.press("Control+A")
        fb.press("Backspace")
        fb.evaluate(f"() => document.execCommand('insertText', false, {json.dumps(c['description'])})")
    page_url = ((data.get("facebook") or {}).get("created") or {}).get("url", "")
    existing = js(fb, "() => [...document.querySelectorAll('input')].map(e => e.value)")
    for link in c.get("links") or []:
        url = link["url"].replace("{facebook}", page_url)
        if not url or url in existing:
            continue
        before = len([v for v in existing if not v])
        click_text_wait(fb, T_ADD_LINK)
        time.sleep(2)
        empty = js(fb, """() => [...document.querySelectorAll('input')].filter(e => e.offsetParent && !e.value
            && e.id !== 'query-input' && e.type !== 'email' && !/mail/i.test(e.placeholder)).map(e => {
            const r = e.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; })""")
        if len(empty) < 2:
            raise StepError(f"khong thay o tieu de / URL duong lien ket (con {before} o trong)")
        type_at(fb, empty[0], link["title"])
        type_at(fb, empty[1], url)
    time.sleep(2)
    click_text_wait(fb, T_PUBLISH)
    if not wait_for(lambda: not click_text_present(fb, T_PUBLISH), 30):
        raise StepError("bam Xuat ban nhung thay doi chua luu")
    log("YouTube: da xuat ban anh + mo ta (anh co the mat vai phut moi hien tren kenh)")


def click_text_present(fb, texts):
    """Con nut texts dang bam duoc?"""
    return bool(js(fb, """(texts) => [...document.querySelectorAll('ytcp-button, button')].some(e => e.offsetParent
        && texts.includes(e.innerText.trim()) && !e.hasAttribute('disabled')
        && e.getAttribute('aria-disabled') !== 'true')""", list(texts)))


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser(description="Tao Trang Facebook + kenh YouTube theo cau hinh tung profile")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--config", help="mac dinh data/channels/<profile>.json")
    ap.add_argument("--only", choices=["facebook", "youtube"])
    ap.add_argument("--dry-run", action="store_true", help="dien form + chup anh, khong bam tao")
    ap.add_argument("--refresh", action="store_true", help="kenh YouTube da tao: gan lai anh, mo ta, lien ket")
    ap.add_argument("--keep-open", action="store_true", help="profile do script mo: de mo khi xong")
    a = ap.parse_args()

    cfg_path = Path(a.config) if a.config else CONFIG_DIR / f"{a.profile}.json"
    if not cfg_path.is_file():
        log(f"Khong thay cau hinh {cfg_path}")
        return EXIT_NO_FILE
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    targets = [t for t in ("facebook", "youtube") if t in data and a.only in (None, t)]
    try:
        for t in targets:
            for key in ("avatar", "cover", "banner"):
                if data[t].get(key):
                    image(data[t][key])
    except FileNotFoundError as e:
        log(str(e))
        return EXIT_NO_FILE

    try:
        with FoxSession(a.profile, keep_open=a.keep_open) as fb:
            open_work_tab(fb)
            try:
                for t in targets:
                    try:
                        (facebook if t == "facebook" else youtube)(fb, cfg_path, data, a.dry_run, a.refresh)
                    except (StepError, FoxError) as e:
                        log(f"{t}: LOI {e}")
                        shot(fb, f"{t}_error")
                        return EXIT_ERROR
            finally:
                close_work_tab(fb)
    except FoxUnavailable as e:
        log(f"FoxProfile chua san sang: {e}")
        return EXIT_FOX_UNAVAILABLE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
