# -*- coding: utf-8 -*-
"""
Client REST cho FoxProfile (http://127.0.0.1:8090/api/v1): mo/dong profile va dieu khien tab hien hanh.

Dung boi 00.facebook_business_upload.py. Moi lan goi REST phai xong trong < 60s (FoxProfile cat o 60s),
nen cac thao tac cho lau (cho nut, cho upload...) duoc viet thanh vong lap thăm do o phia script.
Selector la selector cua Playwright: CSS, text=..., role=button[name="..."s], xpath=..., "a >> b", ">> nth=-1".
"""

import base64
import os
import time
from urllib.parse import urlparse

import requests


def same_url(a, b):
    """Cung tab theo cach FoxProfile so tham so 'tab': scheme + host + path, bo query/#/dau / cuoi."""
    def key(u):
        p = urlparse(u.strip())
        return p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/")
    return key(a) == key(b)


class FoxError(Exception):
    """Loi tu FoxProfile API (status 0 = khong ket noi duoc)."""

    def __init__(self, status, detail):
        super().__init__(f"[{status}] {detail}")
        self.status = status
        self.detail = detail

    @property
    def is_timeout(self):
        return "timeout" in self.detail.lower()


class FoxProfileBrowser:
    def __init__(self, profile, base_url=None, token=None, log=print):
        base_url = (base_url or os.environ.get("FOXPROFILE_URL", "http://127.0.0.1:8090")).rstrip("/")
        token = os.environ.get("FOXPROFILE_API_TOKEN", "") if token is None else token
        self.profile = profile
        self.log = log
        # Tab dich (so thu tu hoac URL): thao tac tren tab do ma khong doi tab hien hanh / khong keo cua so len truoc.
        # None = tab hien hanh nhu cu. Can FoxProfile ho tro tham so "tab" (xem supports_tab()).
        self.tab = None
        self._root = f"{base_url}/api/v1"
        self._resolved = False
        self._http = requests.Session()
        if token:
            self._http.headers["Authorization"] = f"Bearer {token}"

    # -- REST --

    def _call(self, method, path, timeout=90, **kwargs):
        try:
            r = self._http.request(method, f"{self._root}{path}", timeout=timeout, **kwargs)
        except requests.RequestException as e:
            raise FoxError(0, f"Khong ket noi duoc FoxProfile ({self._root}): {e}") from e
        if r.status_code == 401:
            raise FoxError(401, "FOXPROFILE_API_TOKEN sai hoac thieu")
        if not r.ok:
            try:
                detail = r.json().get("detail") or r.text
            except ValueError:
                detail = r.text
            raise FoxError(r.status_code, str(detail)[:400])
        return r

    def _page(self, method, action, timeout=90, **kwargs):
        if self.tab is not None and not action.startswith("tabs"):
            key = "params" if method == "GET" else "json"
            kwargs[key] = {**(kwargs.get(key) or {}), "tab": self.tab}
        return self._call(method, f"/browser/{self.profile}/page/{action}", timeout=timeout, **kwargs).json()

    # -- vong doi profile --

    def profile_exists(self):
        """Tim profile khong phan biet hoa/thuong va dung ten that (cac route khac so khop dung chinh ta)."""
        for p in self._call("GET", "/profiles", timeout=15).json()["profiles"]:
            if p["name"].casefold() == self.profile.casefold():
                self.profile = p["name"]
                return True
        return False

    def is_running(self):
        if not self._resolved:
            if not self.profile_exists():
                raise SystemExit(f"Profile '{self.profile}' chua co trong FoxProfile -- tao/dang nhap profile truoc")
            self._resolved = True
        return bool(self._call("GET", f"/browser/{self.profile}/status", timeout=15).json()["is_running"])

    def _status_running(self):
        return bool(self._call("GET", f"/browser/{self.profile}/status", timeout=15).json()["is_running"])

    def launch(self, timeout=90):
        self.log(f"Mo profile FoxProfile '{self.profile}'")
        self._call("POST", f"/browser/{self.profile}/launch", timeout=timeout + 30)
        deadline = time.time() + timeout
        while True:  # cho kenh dieu khien san sang
            try:
                self.tabs()
                return
            except FoxError as e:
                if e.status not in (409, 503) or time.time() > deadline:
                    raise
                if e.status == 409 and not self._status_running():  # khoi dong that bai (LAUNCH_FAILED)
                    raise
            time.sleep(1)

    def ensure(self):
        """Mo profile neu chua chay. Tra ve True neu chinh lan nay mo no."""
        if self.is_running():
            return False
        self.launch()
        return True

    def stop(self):
        try:
            self._call("POST", f"/browser/{self.profile}/stop", timeout=60)
            self.log(f"Da dong profile '{self.profile}'")
        except FoxError as e:
            if e.status != 409:  # 409 = da dung roi
                self.log(f"Khong dong duoc profile: {e}")

    # -- thao tac tren tab hien hanh --

    def navigate(self, url, wait_until="load"):
        return self._page("POST", "navigate", json={"url": url, "wait_until": wait_until})

    def evaluate(self, script):
        return self._page("POST", "evaluate", json={"script": script})["result"]

    def url(self):
        return self.evaluate("() => location.href")

    def click(self, selector, timeout=10000):
        return self._page("POST", "click", json={"selector": selector, "timeout": timeout})

    def click_at(self, x, y):
        return self._page("POST", "click-at", json={"x": x, "y": y})

    def type_into(self, selector, text, timeout=10000):
        return self._page("POST", "type", json={"selector": selector, "text": text, "clear": True, "timeout": timeout})

    def press(self, key, selector=None):
        return self._page("POST", "press", json={"key": key, "selector": selector})

    def keyboard_type(self, text):
        return self._page("POST", "keyboard", json={"text": text})

    def text_of(self, selector="body", max_chars=40000):
        return self._page("GET", "text", params={"selector": selector, "max_chars": max_chars})["text"]

    def visible(self, selector, timeout_ms=300):
        """Phan tu dau tien khop selector dang hien thi? (cho toi da timeout_ms)"""
        try:
            self._page("POST", "wait", json={"selector": selector, "timeout": max(100, timeout_ms)})
            return True
        except FoxError as e:
            if e.status in (400, 422):
                return False
            raise

    def wait_visible(self, selector, timeout_s):
        """Cho phan tu hien thi (chia nho < 60s moi lan goi). True neu thay, False neu het gio."""
        deadline = time.time() + timeout_s
        while True:
            left = deadline - time.time()
            if left <= 0:
                return False
            if self.visible(selector, int(min(left, 20) * 1000)):
                return True

    def screenshot_png(self, full_page=False):
        res = self._page("GET", "screenshot", params={"full_page": str(full_page).lower(), "format": "json"})
        return base64.b64decode(res["png_base64"])

    # -- tab --

    def tabs(self):
        return self._page("GET", "tabs", timeout=30)["tabs"]

    def active_tab_index(self):
        return next((t["index"] for t in self.tabs() if t["active"]), 0)

    def tab_new(self, url=None):
        return self._page("POST", "tabs", json={"url": url})["tabs"]

    def tab_select(self, index):
        return self._page("POST", f"tabs/{index}/select")["tabs"]

    def tab_close(self, index):
        return self._page("DELETE", f"tabs/{index}")["tabs"]

    def supports_tab(self):
        """FoxProfile (ca server lan trinh duyet cua profile) co hieu tham so 'tab' chua. Ban cu bo qua tham so la
        -> thao tac nham vao tab hien hanh, nen phai kiem tra truoc khi dung self.tab."""
        try:
            self._call("POST", f"/browser/{self.profile}/page/evaluate", timeout=30,
                       json={"script": "() => 1", "tab": "about:__probe__"})
        except FoxError as e:
            return "No tab with URL" in e.detail
        return False

    def open_tab(self, url):
        """Dat self.tab = url; chua co tab nao o url do thi mo moi (FoxProfile/Camoufox mo thanh 1 cua so rieng)."""
        if not any(same_url(t["url"], url) for t in self.tabs()):
            new = next(t for t in self.tab_new(url) if t["active"])
            if not same_url(new["url"], url):  # trang tu chuyen di noi khac (vd side chat da xoa): dong, khong mo lai mai
                self.tab_close(new["index"])
                raise FoxError(404, f"Mo {url} nhung trang chuyen sang {new['url']}")
        self.tab = url

    # -- upload (action 'upload' do ban va FoxProfile them vao) --

    def upload(self, files, trigger=None, input_selector=None, timeout=15000):
        body = {"files": [str(f) for f in files], "timeout": timeout}
        if trigger:
            body["trigger"] = trigger
        if input_selector:
            body["input_selector"] = input_selector
        return self._page("POST", "upload", json=body)

    def check_upload_support(self):
        """None neu FoxProfile da ho tro + bat upload; nguoc lai tra ve cau huong dan sua."""
        try:
            # File khong ton tai: FoxProfile tu choi truoc khi bam/chon gi tren trang
            self.upload([os.path.join(os.path.dirname(os.path.abspath(__file__)), "__probe__.none")],
                        trigger="body", timeout=100)
        except FoxError as e:
            if e.status == 404 or "unknown action" in e.detail.lower():
                return "FoxProfile chua co action 'upload' -- khoi dong lai FoxProfile bang ban da va"
            if "disabled" in e.detail.lower():
                return ("FoxProfile chua bat upload -- dat FOXPROFILE_UPLOAD_DIRS=<thu muc chua anh/video> "
                        "(vd E:\\Python\\Videos\\downloads) trong moi truong/.env cua FoxProfile roi khoi dong lai")
            # "Not a file" = action da bat va da kiem tra file
        return None
