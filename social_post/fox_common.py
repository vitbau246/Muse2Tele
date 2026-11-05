# -*- coding: utf-8 -*-
"""Dung chung cho cac script dang bai qua FoxProfile trong social_post\\ (tiktok_post.py...).
Lay tu foxprofile\\fox_upload_common.py; nap Muse2Tele\\.env va dung foxprofile\\foxprofile_client.py cua Muse2Tele.

Thay Chrome + Playwright CDP (chrome_cdp.py) bang profile FoxProfile qua REST (foxprofile_client.py).
Khac ban cu:
  - Chon file bang action 'upload' cua FoxProfile: chi nhan file trong FOXPROFILE_UPLOAD_DIRS.
  - REST chi co 1 tab "hien hanh"; moi lan goi phai xong < 60s nen moi cho cho deu la vong lap tham do.
  - Profile do script mo thi script dong khi xong; profile dang mo san thi giu nguyen.

Ma thoat dung chung:
  0 = OK, 1 = loi (co anh chup), 2 = khong thay file, 3 = chua dang nhap, 4 = sai trang Facebook,
  5 = FoxProfile chua san sang (khong chay / thieu profile / chua bat upload).
"""

import json
import sys
import time
from pathlib import Path

import fanpage_jobs

fanpage_jobs.load_env()
sys.path.insert(0, str(fanpage_jobs.ROOT_DIR / "foxprofile"))
from foxprofile_client import FoxError, FoxProfileBrowser  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_FILE = 2
EXIT_NOT_LOGGED_IN = 3
EXIT_WRONG_PAGE = 4
EXIT_FOX_UNAVAILABLE = 5


class NotLoggedIn(Exception):
    pass


class WrongPage(Exception):
    pass


class FoxUnavailable(Exception):
    pass


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def launch_with_retry(fb: FoxProfileBrowser, attempts: int = 3, timeout: int = 240) -> None:
    """Mo profile; Camoufox doi khi treo luc khoi dong (~180s roi LAUNCH_FAILED) -> thu mo lai."""
    for i in range(1, attempts + 1):
        try:
            fb.launch(timeout=timeout)
            return
        except FoxError as e:
            if i == attempts or e.status == 0:
                raise
            log(f"Mo profile that bai lan {i}/{attempts} ({e.detail[:80]}), thu lai")
            time.sleep(5)


class FoxSession:
    """Mo (neu chua chay) profile FoxProfile, kiem tra upload da bat; dong lai khi xong neu chinh minh mo."""

    def __init__(self, profile: str, keep_open: bool = False, need_upload: bool = True):
        self.fb = FoxProfileBrowser(profile, log=log)
        self.keep_open = keep_open
        self.need_upload = need_upload
        self.started = False

    def __enter__(self) -> FoxProfileBrowser:
        try:
            self.started = not self.fb.is_running()
            if self.started:
                launch_with_retry(self.fb)
            problem = self.fb.check_upload_support() if self.need_upload else None
        except FoxError as e:
            self.__exit__()
            raise FoxUnavailable(str(e)) from e
        except SystemExit as e:  # profile chua co trong FoxProfile
            raise FoxUnavailable(str(e)) from e
        if problem:
            self.__exit__()
            raise FoxUnavailable(problem)
        return self.fb

    def __exit__(self, *exc) -> None:
        if self.started and not self.keep_open:
            self.fb.stop()


def open_work_tab(fb: FoxProfileBrowser) -> None:
    """Lam viec tren 1 tab rieng (fb.tab = so thu tu) de khong dung vao tab Muse cua bot.

    FoxProfile cu chua hieu tham so 'tab' thi giu nhu cu: lam tren tab hien hanh."""
    try:
        if not fb.supports_tab():
            log("FoxProfile chua ho tro tham so 'tab' -> lam tren tab hien hanh")
            return
        tabs = fb.tab_new("about:blank")
        fb.tab = next((t["index"] for t in tabs if t["active"]), len(tabs) - 1)
    except FoxError as e:
        log(f"Khong mo duoc tab rieng ({e}) -> lam tren tab hien hanh")
        fb.tab = None


def close_work_tab(fb: FoxProfileBrowser) -> None:
    index, fb.tab = fb.tab, None
    if index is None:
        return
    try:
        if len(fb.tabs()) > 1:
            fb.tab_close(index)
    except FoxError as e:
        log(f"Khong dong duoc tab rieng: {e}")


def eval_retry(fb: FoxProfileBrowser, script: str, tries: int = 3):
    """evaluate nhung chiu duoc luc trang dang chuyen huong (FoxProfile tra 400)."""
    for i in range(tries):
        try:
            return fb.evaluate(script)
        except FoxError as e:
            if e.status not in (400, 422) or i == tries - 1:
                raise
            time.sleep(1)


def body_matches(fb: FoxProfileBrowser, pattern: str, flags: str = "i") -> str | None:
    """Doan van ban dau tien trong body khop regex JS `pattern`, hoac None."""
    script = (f"() => {{ const m = (document.body ? document.body.innerText : '')"
              f".match(new RegExp({json.dumps(pattern)}, {json.dumps(flags)})); return m ? m[0].trim() : null; }}")
    return eval_retry(fb, script)


def wait_for(cond, timeout_s: float, interval: float = 1.0) -> bool:
    """Goi cond() toi khi tra ve gia tri that (loi FoxError 400/422 khi trang chuyen huong bi bo qua)."""
    deadline = time.time() + timeout_s
    while True:
        try:
            if cond():
                return True
        except FoxError as e:
            if e.status not in (400, 422):
                raise
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def wait_any(fb: FoxProfileBrowser, selectors: list[str], timeout_s: float) -> int:
    """Cho toi khi 1 trong cac selector hien thi; tra ve chi so cua selector do, -1 neu het gio."""
    deadline = time.time() + timeout_s
    while True:
        for i, sel in enumerate(selectors):
            if fb.visible(sel, 400):
                return i
        if time.time() >= deadline:
            return -1


def role_btn(name: str, which: str = "first", exact: bool = True) -> str:
    """Selector nut theo ten (chinh xac); which = 'first' | 'last'."""
    flag = "s" if exact else "i"
    return f'role=button[name="{name}"{flag}] >> nth={"-1" if which == "last" else "0"}'


def save_shot(fb: FoxProfileBrowser, path: Path) -> None:
    try:
        path.write_bytes(fb.screenshot_png())
        log(f"Da luu anh: {path}")
    except Exception as e:
        log(f"Khong chup duoc anh {path.name}: {e}")


def js_click_text(fb: FoxProfileBrowser, text: str, which: str = "first", scope: str = "body") -> bool:
    """Click bang JS vao phan tu co chu CHINH XAC `text` (nut cha gan nhat neu co). True neu tim thay.

    Du phong khi click that cua Playwright khong kich hoat duoc nut (da gap tren Zalo: click toi timeout / khong
    mo form, con button.click() thi chay)."""
    # scope co the khop nhieu hop thoai (gom ca cai dang an) -> chi tim trong cac vung dang hien thi
    script = ("() => { const t = %s;"
              " const roots = [...document.querySelectorAll(%s)].filter(r => r.getBoundingClientRect().width > 0);"
              " const els = (roots.length ? roots : [document.body]).flatMap(r => [...r.querySelectorAll('*')])"
              ".filter(e => e.children.length === 0 && e.textContent.trim() === t && e.getBoundingClientRect().width > 0);"
              " const el = %s; if (!el) return false;"
              " (el.closest('button,[role=button],a') || el).click(); return true; }"
              ) % (json.dumps(text), json.dumps(scope), "els[els.length - 1]" if which == "last" else "els[0]")
    return bool(eval_retry(fb, script))


def js_click_css(fb: FoxProfileBrowser, css: str) -> bool:
    return bool(eval_retry(fb, f"() => {{ const e = document.querySelector({json.dumps(css)});"
                               " if (!e) return false; e.click(); return true; }"))


def click_robust(fb: FoxProfileBrowser, selector: str, fallback, timeout: int = 5000) -> None:
    """Click that; loi (timeout...) thi chay fallback() (tra True neu da click duoc), khong duoc thi nem lai loi."""
    try:
        fb.click(selector, timeout=timeout)
    except FoxError as e:
        if e.status in (0, 401):
            raise
        if not fallback():
            raise
        log(f"Click that bai ({e.detail[:60]}) -> da click bang JS")
