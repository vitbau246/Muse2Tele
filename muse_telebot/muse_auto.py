# -*- coding: utf-8 -*-
"""
Tu dong bam Allow tren cac yeu cau duyet (Allow/Deny) cua muse.ai, o moi tab muse.ai (main chat / side chat) cua
cac profile da co topic. Chay nhu 1 thread trong muse_telebot.py; bat/tat bang /allow_on, /allow_off (mac dinh BAT).
Trang thai bat/tat luu trong muse_autoapprove.json ({"on": true/false}) nen giu nguyen qua lan restart bot.

Tab duoc doc ngam qua tham so "tab" cua FoxProfile (khong chuyen tab); profile chua mo thi bo qua, khong tu mo.
"""

import json
import logging
import time
from urllib.parse import urlparse

import muse_sync
from muse_sync import HERE, FoxProfileBrowser

STATE_FILE = HERE / "muse_autoapprove.json"
INTERVAL_SECONDS = 5
# Nut Allow cua yeu cau duyet (Allow/Deny) tren muse.ai; chi bam nut dang hien thi, moi lan 1 nut. Tra ve mo ta yeu
# cau (2 dong dau cua khung chua nut). READ_ALLOW_JS: chi doc mo ta, khong bam.
# Nut chinh khong phai luc nao cung ghi "Allow": nhieu yeu cau dung nhan theo viec (vd "Edit bio" / "Don't change" khi
# sua bio Instagram, 2026-11-12). Khi do nhan dien the duyet qua nut menu "More allow options" canh nut chinh
# (data-pel-click ...approval_allow_options..., khong phu thuoc ngon ngu).
_ALLOW_JS = """() => {
  const isCard = e => {
    for (let p = e.parentElement, i = 0; p && i < 6; p = p.parentElement, i++)
      if (p.querySelector('[data-pel-click*="approval_allow_options"]')) return true;
    return false;
  };
  const b = [...document.querySelectorAll('button[data-hatch-approval-primary-action="true"]')]
    .find(e => e.offsetParent !== null && !e.disabled
      && (['Allow', 'Cho phép'].includes(e.innerText.trim()) || isCard(e)));
  if (!b) return null;
  let p = b;
  for (let i = 0; i < 8 && p.parentElement; i++) { p = p.parentElement; if (p.innerText.length > 120) break; }
  const ctx = p.innerText.split('\\n').filter(Boolean).slice(0, 2).join(' | ');
  %s
  return ctx;
}"""
CLICK_ALLOW_JS = _ALLOW_JS % "b.click();"
READ_ALLOW_JS = _ALLOW_JS % ""

# Bang ben phai cua Muse co 3 tab (Hoat dong / Phe duyet / Danh tinh, nut aria-pressed): yeu cau duyet chi hien o tab
# Phe duyet. Chua o tab do thi bam sang. Nhan theo ngon ngu, du phong nut thu 2 cua nhom 3 nut. Kiem tra 2026-11-04.
APPROVALS_TAB_JS = """() => {
  const all = [...document.querySelectorAll('button[aria-pressed]')];
  const b = all.find(e => ['Phê duyệt', 'Approvals', 'Approval'].includes(e.getAttribute('aria-label')))
    || (() => { const g = all.filter(e => e.parentElement === (all[0] || {}).parentElement); return g.length === 3 ? g[1] : null; })();
  if (!b) return 'missing';
  if (b.getAttribute('aria-pressed') === 'true') return 'ok';
  b.click(); return 'switched';
}"""

logger = logging.getLogger("muse.auto")


def enabled():
    try:
        return bool(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("on"))
    except FileNotFoundError:
        return True  # mac dinh bat: Muse khong bi ket cho nguoi bam Allow tren web
    except (OSError, ValueError, AttributeError):
        return False


def set_enabled(on):
    STATE_FILE.write_text(json.dumps({"on": on}), encoding="utf-8")


def approve_once(profile, click=True):
    """Bam Allow neu 1 tab muse.ai cua profile dang hien yeu cau duyet. Tra ve mo ta yeu cau, hoac None neu khong co.
    click=False: chi doc mo ta yeu cau dang cho (de bao len Telegram), khong bam."""
    js = CLICK_ALLOW_JS if click else READ_ALLOW_JS
    fox = FoxProfileBrowser(profile, log=logger.info)
    if not fox.profile_exists() or not fox.is_running():  # khong tu mo profile chi de do nut
        return None
    tabs = [t for t in fox.tabs() if urlparse(t["url"]).netloc == "muse.ai"]
    if not tabs:
        return None
    if not fox.supports_tab():  # FoxProfile cu: chi lam duoc tren tab hien hanh
        if not tabs[0]["active"]:
            fox.tab_select(tabs[0]["index"])
        return fox.evaluate(js)
    for t in tabs:
        fox.tab = t["url"]
        if fox.evaluate(APPROVALS_TAB_JS) == "switched":
            logger.info(f"{profile}: chuyen sang tab Phe duyet")
            time.sleep(1)
        clicked = fox.evaluate(js)
        if clicked:
            return clicked
    return None


def loop(profiles, notify):
    """Chay mai: moi INTERVAL_SECONDS quet cac profile (profiles() tra ve danh sach); bam duoc thi goi
    notify(profile, mo_ta)."""
    while True:
        time.sleep(INTERVAL_SECONDS)
        if not enabled():
            continue
        for profile in profiles():
            lock = muse_sync.lock_for(profile)
            if not lock.acquire(blocking=False):
                continue
            try:
                clicked = approve_once(profile)
            except Exception as e:
                logger.warning(f"auto approve {profile}: {type(e).__name__}: {e}")
                continue
            finally:
                lock.release()
            if clicked:
                logger.info(f"Auto Allow {profile}: {clicked}")
                notify(profile, clicked)
