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
# Nut Allow cua yeu cau duyet (Allow/Deny) tren muse.ai; chi bam nut dang hien thi, moi lan 1 nut.
CLICK_ALLOW_JS = """() => {
  const b = [...document.querySelectorAll('button[data-hatch-approval-primary-action="true"]')]
    .find(e => ['Allow', 'Cho phép'].includes(e.innerText.trim()) && e.offsetParent !== null && !e.disabled);
  if (!b) return null;
  let p = b;
  for (let i = 0; i < 8 && p.parentElement; i++) { p = p.parentElement; if (p.innerText.length > 120) break; }
  const ctx = p.innerText.split('\\n').filter(Boolean).slice(0, 2).join(' | ');
  b.click();
  return ctx;
}"""

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


def approve_once(profile):
    """Bam Allow neu 1 tab muse.ai cua profile dang hien yeu cau duyet. Tra ve mo ta yeu cau, hoac None neu khong co."""
    fox = FoxProfileBrowser(profile, log=logger.info)
    if not fox.profile_exists() or not fox.is_running():  # khong tu mo profile chi de do nut
        return None
    tabs = [t for t in fox.tabs() if urlparse(t["url"]).netloc == "muse.ai"]
    if not tabs:
        return None
    if not fox.supports_tab():  # FoxProfile cu: chi lam duoc tren tab hien hanh
        if not tabs[0]["active"]:
            fox.tab_select(tabs[0]["index"])
        return fox.evaluate(CLICK_ALLOW_JS)
    for t in tabs:
        fox.tab = t["url"]
        if fox.evaluate(APPROVALS_TAB_JS) == "switched":
            logger.info(f"{profile}: chuyen sang tab Phe duyet")
            time.sleep(1)
        clicked = fox.evaluate(CLICK_ALLOW_JS)
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
