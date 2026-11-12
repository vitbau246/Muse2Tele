# -*- coding: utf-8 -*-
"""
Quan ly tai khoan TikTok dang nhap o 1 profile FoxProfile (dung cho lenh /rebrand cua bot):

  python tiktok_manage.py --profile Muse9 --list                                  # in TIKTOK_POSTS=[id, ...]
  python tiktok_manage.py --profile Muse9 --delete-all --expect-account mywayf    # XOA moi video (khong hoan tac)
  python tiktok_manage.py --profile Muse9 --delete-all --expect-account mywayf --dry-run   # chi liet ke
  python tiktok_manage.py --profile Muse9 --edit-profile --expect-account mywayf \\
         [--name "Ten"] [--bio "Tieu su"] [--avatar anh.png] [--username moi1,moi2] [--dry-run]

--delete-all BAT BUOC --expect-account: chi xoa khi tai khoan dang nhap dung la tai khoan nay (tranh xoa nham kenh).
Xoa tung video: TikTok Studio > Bai dang (nut ... cua dong > Xoa > xac nhan); khong duoc thi mo trang video
(/@user/video/<id>, nut ... > Xoa). Xoa xong 1 video thi liet ke lai de chac video do da mat.
Sua ho so: trang /@user > "Sua ho so" (data-e2e edit-profile-*): anh dai dien, Ten (TikTok chi cho doi 7 ngay/lan),
Tieu su (<= 80 ky tu), Username (30 ngay/lan, doi ca link kenh). In TIKTOK_ACCOUNT=<username sau khi sua>.

Kiem chung 2026-11-11 tren Muse9 (@mywayf): liet ke, sua ho so that (anh, Ten, Tieu su; username
@longtamhorong da co nguoi dung -> giu @mywayf). Tai khoan luc do KHONG con video nao nen
buoc xoa chua chay tren video that: lan dau dung nen chay --dry-run / xem anh chup trong logs\\.
Ma thoat: 0 OK, 1 loi (co anh chup), 2 thieu file, 3 chua dang nhap TikTok, 5 FoxProfile chua san sang,
          6 tai khoan dang nhap khac --expect-account (khong lam gi).
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from fox_common import (EXIT_ERROR, EXIT_FOX_UNAVAILABLE, EXIT_NO_FILE, EXIT_NOT_LOGGED_IN, EXIT_OK, FoxError,
                        FoxSession, FoxUnavailable, close_work_tab, eval_retry, log, open_work_tab, save_shot,
                        wait_for)
from tiktok_post import ACCOUNT_JS, dismiss_popups

EXIT_WRONG_ACCOUNT = 6
LOG_DIR = Path(__file__).resolve().parent / "logs"
STUDIO_CONTENT = "https://www.tiktok.com/tiktokstudio/content"
DELETE_WORDS = ["Delete", "Xóa", "Xoá", "Delete post", "Xóa bài đăng", "Xoá bài đăng", "Delete video", "Xóa video"]
VIDEO_ID_RE = r"/(?:video|analytics|content|post)/(\d{15,22})"


class WrongAccount(Exception):
    pass


def shot(fb, name):
    LOG_DIR.mkdir(exist_ok=True)
    save_shot(fb, LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_tiktok_{name}.png")


def current_account(fb) -> str:
    return str(eval_retry(fb, ACCOUNT_JS) or "").strip().lstrip("@").lower()


def require_account(fb, expected: str) -> str:
    current = current_account(fb)
    print(f"TIKTOK_ACCOUNT={current}", flush=True)
    if not current:
        raise RuntimeError("Khong doc duoc tai khoan TikTok dang dang nhap")
    expected = expected.strip().lstrip("@").lower()
    if expected and current != expected:
        raise WrongAccount(f"Profile dang dang nhap TikTok @{current}, can @{expected}: khong lam gi")
    return current


def logged_in(fb) -> bool:
    return bool(current_account(fb))


# ---------- liet ke ----------

IDS_JS = """(re) => { const r = new RegExp(re); const out = [];
  for (const a of document.querySelectorAll('a[href]')) { const m = a.getAttribute('href').match(r);
    if (m && !out.includes(m[1])) out.push(m[1]); }
  return out; }"""


def studio_ids(fb) -> list[str] | None:
    """Video trong TikTok Studio > Bai dang; None neu trang chua tai xong."""
    fb.navigate(STUDIO_CONTENT, wait_until="load")
    state = {}

    def ready():
        text = fb.text_of("body", 6000)
        state["empty"] = bool(re.search(r"No posts yet|Chưa có bài đăng|Chưa có bài viết", text))
        state["ids"] = eval_retry(fb, f"() => ({IDS_JS})({json.dumps(VIDEO_ID_RE)})")
        return state["empty"] or state["ids"]
    if not wait_for(ready, 40, 2):
        return None
    dismiss_popups(fb)
    if state["empty"]:
        return []
    # cuon het bang de tai them dong
    last = -1
    for _ in range(30):
        ids = eval_retry(fb, f"() => ({IDS_JS})({json.dumps(VIDEO_ID_RE)})")
        if len(ids) == last:
            break
        last = len(ids)
        eval_retry(fb, "() => { for (const e of document.querySelectorAll('*')) if (e.scrollHeight > e.clientHeight + 50"
                       " && /auto|scroll/.test(getComputedStyle(e).overflowY)) e.scrollTop = e.scrollHeight;"
                       " window.scrollTo(0, document.body.scrollHeight); }")
        time.sleep(2)
    return ids


def profile_ids(fb, user: str) -> list[str]:
    fb.navigate(f"https://www.tiktok.com/@{user}", wait_until="load")
    wait_for(lambda: eval_retry(fb, "() => document.readyState") == "complete", 20)
    time.sleep(5)
    ids, last = [], -1
    pattern = json.dumps("/@" + re.escape(user) + r"/video/(\d{15,22})")
    for _ in range(40):
        ids = eval_retry(fb, f"() => ({IDS_JS})({pattern})")
        if len(ids) == last:
            break
        last = len(ids)
        eval_retry(fb, "() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2.5)
    return ids


def list_posts(fb, user: str) -> list[str]:
    """Moi video cua tai khoan: TikTok Studio (ca video rieng tu / dang duyet) + trang ho so."""
    ids = studio_ids(fb)
    if ids is None:
        log("TikTok Studio chua tai xong danh sach bai dang -> chi dung trang ho so")
        ids = []
    for i in profile_ids(fb, user):
        if i not in ids:
            ids.append(i)
    return ids


# ---------- xoa ----------

MENU_ITEM_JS = """(words) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const els = [...document.querySelectorAll('[role=menuitem], [role=option], li, button, [role=button], div, span')]
    .filter(e => vis(e) && words.includes((e.innerText || '').trim()) && [...e.children].every(c => !words.includes((c.innerText || '').trim())));
  const e = els[els.length - 1]; if (!e) return null; const r = e.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2]; }"""

# Nut "..." (them tuy chon) trong dong co video id, hoac tren trang video
MORE_BTNS_JS = """(id) => { const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let scope = document;
  if (id) { const a = [...document.querySelectorAll('a[href]')].find(a => a.getAttribute('href').includes(id));
    if (!a) return [];
    let row = a; for (let i = 0; i < 12 && row.parentElement; i++) { row = row.parentElement;
      if (row.querySelectorAll('button,[role=button]').length >= 2 && row.getBoundingClientRect().width > 600) break; }
    row.scrollIntoView({block: 'center'}); scope = row; }
  const re = /more|thêm|tùy chọn|tuỳ chọn|options|setting|ellipsis/i;
  const btns = [...scope.querySelectorAll('button,[role=button],[data-e2e]')].filter(vis).filter(b =>
    re.test((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('data-e2e') || '') + ' ' + (b.getAttribute('data-tt') || ''))
    || /^(\\.\\.\\.|…|⋯)$/.test((b.innerText || '').trim()));
  const cand = btns.length ? btns : (id ? [...scope.querySelectorAll('button,[role=button]')].filter(vis).slice(-1) : []);
  return cand.slice(0, 4).map(b => { const r = b.getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; }); }"""


def click_delete_menu(fb, points) -> bool:
    """Bam lan luot cac nut '...' toi khi menu co muc Xoa; bam Xoa roi nut Xoa trong hop xac nhan."""
    for pt in points:
        fb.click_at(*pt)
        time.sleep(1.5)
        item = eval_retry(fb, f"() => ({MENU_ITEM_JS})({json.dumps(DELETE_WORDS)})")
        if not item:
            fb.press("Escape")
            time.sleep(0.5)
            continue
        fb.click_at(*item)
        time.sleep(2)
        confirm = eval_retry(fb, f"() => ({MENU_ITEM_JS})({json.dumps(DELETE_WORDS)})")
        if confirm:
            fb.click_at(*confirm)
            time.sleep(3)
        return True
    return False


def delete_one(fb, user: str, vid: str) -> None:
    fb.navigate(STUDIO_CONTENT, wait_until="load")
    wait_for(lambda: vid in (eval_retry(fb, f"() => ({IDS_JS})({json.dumps(VIDEO_ID_RE)})") or []), 30, 2)
    dismiss_popups(fb)
    done = click_delete_menu(fb, eval_retry(fb, f"() => ({MORE_BTNS_JS})({json.dumps(vid)})") or [])
    if not done:
        log(f"  {vid}: Studio khong co muc Xoa -> thu tren trang video")
        fb.navigate(f"https://www.tiktok.com/@{user}/video/{vid}", wait_until="load")
        time.sleep(6)
        done = click_delete_menu(fb, eval_retry(fb, f"() => ({MORE_BTNS_JS})('')") or [])
    if not done:
        shot(fb, f"delete_{vid}")
        raise RuntimeError(f"khong tim thay nut Xoa cho video {vid}")


def delete_all(fb, user: str, dry_run: bool, limit: int) -> int:
    ids = list_posts(fb, user)
    print(f"TIKTOK_POSTS={json.dumps(ids)}", flush=True)
    log(f"@{user}: {len(ids)} video")
    if dry_run or not ids:
        return 0
    if len(ids) > limit:
        raise RuntimeError(f"{len(ids)} video > gioi han --max {limit}: khong xoa (tang --max neu dung)")
    deleted, failed = 0, []
    for vid in ids:
        try:
            delete_one(fb, user, vid)
        except (RuntimeError, FoxError) as e:
            log(f"  {vid}: LOI {e}")
            failed.append(vid)
            if len(failed) >= 3 and not deleted:
                break  # giao dien khac du kien: dung, khong bam lung tung
            continue
        deleted += 1
        log(f"  da xoa {vid} ({deleted}/{len(ids)})")
    left = [i for i in list_posts(fb, user) if i in ids]
    print(f"TIKTOK_DELETED={deleted} TIKTOK_LEFT={json.dumps(left)}", flush=True)
    if left:
        raise RuntimeError(f"con {len(left)} video chua xoa duoc: {left[:10]}")
    return deleted


# ---------- sua ho so ----------

E2E = "[data-e2e='{}']"
SAVE_DISABLED_JS = ("() => { const b = document.querySelector(\"[data-e2e='edit-profile-save']\");"
                    " return !b || b.disabled || b.getAttribute('aria-disabled') === 'true'; }")


def set_field(fb, selector: str, text: str) -> None:
    pt = eval_retry(fb, "() => { const e = document.querySelector(%s); if (!e) return null; e.scrollIntoView({block:"
                        "'center'}); const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2]; }"
                    % json.dumps(selector))
    if not pt:
        raise RuntimeError(f"khong thay o {selector}")
    fb.click_at(*pt)
    fb.press("Control+A")
    fb.press("Backspace")
    if text:
        fb.keyboard_type(text)
    time.sleep(1)


def edit_profile(fb, user: str, name: str, bio: str, avatar: Path | None, usernames: list[str],
                 dry_run: bool) -> str:
    """Sua ho so; usernames: username moi theo thu tu uu tien (cai dau tien con trong duoc dung, het thi giu cu)."""
    fb.navigate(f"https://www.tiktok.com/@{user}", wait_until="load")
    if not wait_for(lambda: eval_retry(fb, "() => !!document.querySelector(\"[data-e2e='edit-profile-entrance']\")"), 30):
        raise RuntimeError("khong thay nut Sua ho so (dang mo trang ho so nguoi khac?)")
    time.sleep(2)
    eval_retry(fb, "() => document.querySelector(\"[data-e2e='edit-profile-entrance']\").click()")  # bam toa do khong an
    if not wait_for(lambda: eval_retry(fb, "() => !!document.querySelector(\"[data-e2e='edit-profile-save']\")"), 20):
        raise RuntimeError("khong mo duoc hop Sua ho so")
    time.sleep(2)
    if avatar:
        fb.upload([str(avatar)], input_selector=f"{E2E.format('edit-profile-popup')} input[type=file]")
        log("TikTok: da chon anh dai dien")
        time.sleep(4)
        apply = eval_retry(fb, f"() => ({MENU_ITEM_JS})({json.dumps(['Apply', 'Áp dụng'])})")
        if not apply:
            shot(fb, "avatar")
            raise RuntimeError("khong thay nut Ap dung sau khi chon anh dai dien")
        fb.click_at(*apply)
        time.sleep(3)
    wanted = [u for u in usernames if u and u.lower() != user.lower()]
    for i, username in enumerate(wanted):
        set_field(fb, E2E.format("edit-profile-username-input") + " input, " + E2E.format("edit-profile-username")
                  + " input", username)
        time.sleep(4)  # TikTok kiem tra username con trong
        popup = eval_retry(fb, "() => { const p = document.querySelector(\"[data-e2e='edit-profile-popup']\");"
                               " return p ? p.innerText : ''; }") or ""
        bad = re.search(r"isn.t available|not available|enter a new one|đã được sử dụng|không khả dụng|không có sẵn"
                        r"|can.t change|chỉ có thể thay đổi", popup, re.I)
        if not bad and not eval_retry(fb, SAVE_DISABLED_JS):
            log(f"TikTok: username @{username} dung duoc")
            break
        log(f"TikTok: username @{username} khong dung duoc ({bad.group(0) if bad else 'nut Luu khoa'})")
        print(f"TIKTOK_USERNAME_REJECTED={username}", flush=True)
        if i == len(wanted) - 1:
            # O username da bao loi thi go lai username cu van bao loi -> dong hop, mo lai, khong doi username
            log(f"TikTok: khong username nao dung duoc -> giu @{user}")
            shot(fb, "username_rejected")
            eval_retry(fb, "() => { const b = document.querySelector(\"[data-e2e='edit-profile-cancel']\");"
                           " if (b) b.click(); }")
            time.sleep(2)
            return edit_profile(fb, user, name, bio, avatar, [], dry_run)
    name_sel = E2E.format("edit-profile-name-input") + " input, " + E2E.format("edit-profile-name") + " input"
    if name and not eval_retry(fb, "() => !!document.querySelector(%s)" % json.dumps(name_sel)):
        # Vua doi Ten trong 7 ngay: o Ten thanh chu thuong "You can change it again after <ngay>"
        popup = eval_retry(fb, "() => { const p = document.querySelector(\"[data-e2e='edit-profile-popup']\");"
                               " return p ? p.innerText : ''; }") or ""
        when = re.search(r"(?:again after|sau ngày)\s+([^.\n]+)", popup, re.I)
        log(f"TikTok: Ten dang khoa (doi 7 ngay/lan{', mo lai sau ' + when.group(1).strip() if when else ''}) -> giu ten cu")
        print(f"TIKTOK_NAME_LOCKED={when.group(1).strip() if when else ''}", flush=True)
        name = ""
    if name:
        set_field(fb, name_sel, name[:30])
    if bio:
        set_field(fb, E2E.format("edit-profile-bio-input"), bio[:80])
    shot(fb, "edit_profile_form")
    if dry_run:
        log("TikTok: --dry-run, khong bam Luu")
        fb.press("Escape")
        return user
    if eval_retry(fb, SAVE_DISABLED_JS):
        shot(fb, "edit_profile_disabled")
        raise RuntimeError("nut Luu dang khoa (ten / username khong hop le, hoac chua doi duoc: Ten 7 ngay/lan)")
    eval_retry(fb, "() => document.querySelector(\"[data-e2e='edit-profile-save']\").click()")
    time.sleep(3)
    # Doi username: TikTok hoi xac nhan "Dat username?" -> bam xac nhan
    confirm = eval_retry(fb, f"() => ({MENU_ITEM_JS})({json.dumps(['Confirm', 'Xác nhận', 'Set username', 'Đặt'])})")
    if confirm:
        fb.click_at(*confirm)
        time.sleep(3)
    if not wait_for(lambda: not eval_retry(fb, "() => !!document.querySelector(\"[data-e2e='edit-profile-save']\")"), 30):
        shot(fb, "edit_profile_not_saved")
        raise RuntimeError("bam Luu nhung hop Sua ho so chua dong (TikTok tu choi thay doi?)")
    now = current_account(fb) or user
    print(f"TIKTOK_ACCOUNT={now}", flush=True)
    log(f"TikTok: da luu ho so @{now}")
    return now


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Liet ke / xoa video, sua ho so TikTok o profile FoxProfile")
    ap.add_argument("--profile", required=True)
    act = ap.add_mutually_exclusive_group(required=True)
    act.add_argument("--list", action="store_true")
    act.add_argument("--delete-all", action="store_true")
    act.add_argument("--edit-profile", action="store_true")
    ap.add_argument("--expect-account", default="", help="@username phai dang nhap (bat buoc voi --delete-all)")
    ap.add_argument("--max", type=int, default=500, help="--delete-all: nhieu hon so nay thi khong xoa")
    ap.add_argument("--name", default="")
    ap.add_argument("--bio", default="")
    ap.add_argument("--avatar", default="")
    ap.add_argument("--username", default="", help="username moi, nhieu lua chon cach nhau dau phay")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-open", action="store_true")
    a = ap.parse_args()
    if a.delete_all and not a.expect_account:
        ap.error("--delete-all can --expect-account (tranh xoa nham tai khoan)")
    avatar = Path(a.avatar).resolve() if a.avatar else None
    if avatar and not avatar.is_file():
        log(f"Khong thay anh {avatar}")
        return EXIT_NO_FILE
    try:
        with FoxSession(a.profile, keep_open=a.keep_open, need_upload=bool(avatar)) as fb:
            open_work_tab(fb)
            try:
                fb.navigate("https://www.tiktok.com/tiktokstudio", wait_until="load")
                if not wait_for(lambda: logged_in(fb), 30, 2):
                    log(f"Profile '{a.profile}' chua dang nhap TikTok")
                    return EXIT_NOT_LOGGED_IN
                user = require_account(fb, a.expect_account)
                if a.list:
                    ids = list_posts(fb, user)
                    print(f"TIKTOK_POSTS={json.dumps(ids)}", flush=True)
                    log(f"@{user}: {len(ids)} video")
                elif a.delete_all:
                    delete_all(fb, user, a.dry_run, a.max)
                else:
                    edit_profile(fb, user, a.name, a.bio, avatar,
                                 [u.strip().lstrip("@") for u in a.username.split(",") if u.strip()], a.dry_run)
                return EXIT_OK
            except WrongAccount as e:
                log(f"DUNG: {e}")
                return EXIT_WRONG_ACCOUNT
            except (RuntimeError, FoxError) as e:
                log(f"LOI: {e}")
                shot(fb, "error")
                return EXIT_ERROR
            finally:
                close_work_tab(fb)
    except FoxUnavailable as e:
        log(f"FoxProfile chua san sang: {e}")
        return EXIT_FOX_UNAVAILABLE


if __name__ == "__main__":
    sys.exit(main())
