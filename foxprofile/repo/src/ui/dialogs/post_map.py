"""Posting map: which Facebook Pages (Page ID), TikTok account and YouTube channel each profile
auto-posts to, how many posts a day, in which hours, the caption language, and an account check."""

import threading
import time
from collections.abc import Callable

import flet as ft

from ...core import muse_team, post_map
from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS

CHECK_POLL_SECONDS = 3


def check_lines(result: dict | None) -> list[tuple[bool, str]]:
    """Last account check as (ok, text) lines for the table."""
    if not result:
        return []
    if result.get("running"):
        return [(True, get_string("post_map_checking"))]
    lines = [(True, get_string("post_map_check_at", at=result.get("at", "")))]
    if result.get("error"):
        lines.append((False, get_string("post_map_check_error", site="Check", message=result["error"])))
    if result.get("filled"):
        lines.append((True, get_string("post_map_check_filled", items=", ".join(result["filled"]))))
    fb, tt =result.get("fanpage") or {}, result.get("tiktok") or {}
    yt = result.get("youtube") or {}
    for site, part in (("Facebook", fb), ("TikTok", tt), ("YouTube", yt)):
        status = part.get("status")
        if status == "not_logged_in":
            lines.append((False, get_string("post_map_check_login", site=site)))
        elif status in ("error", "fox_unavailable"):
            lines.append((False, get_string("post_map_check_error", site=site, message=part.get("message", ""))))
    if fb.get("status") == "ok":
        mapped = len(fb.get("mapped") or [])
        lines.append((True, get_string("post_map_check_fb_ok", count=mapped) if mapped
                      else get_string("post_map_check_fb_found", count=len(fb.get("found") or []))))
    elif fb.get("status") == "mismatch":
        lines.append((False, get_string("post_map_check_fb_missing", ids=", ".join(fb.get("missing") or []))))
    if tt.get("status") == "ok":
        lines.append((True, get_string("post_map_check_tt_ok", account=tt.get("account", ""))))
    elif tt.get("status") == "found":
        lines.append((True, get_string("post_map_check_tt_found", account=tt.get("account", ""))))
    elif tt.get("status") == "mismatch":
        lines.append((False, get_string("post_map_check_tt_bad", account=tt.get("account", ""),
                                        expected=tt.get("expected", ""))))
    if yt.get("status") == "ok":
        lines.append((True, get_string("post_map_check_yt_ok", handle=yt.get("expected", ""))))
    elif yt.get("status") == "found":
        lines.append((True, get_string("post_map_check_yt_found", count=len(yt.get("channels") or []))))
    elif yt.get("status") == "mismatch":
        lines.append((False, yt.get("message") or get_string("post_map_check_yt_bad", handle=yt.get("expected", ""))))
    return lines


def open_post_map_dialog(page: ft.Page, profiles: list, log: Callable[[str], None]) -> None:
    """profiles: FoxProfile Profile objects (name, auto_post_fanpage, auto_post_tiktok,
    auto_post_youtube)."""
    cfg = post_map.current()
    error = ft.Text("", size=12, color=COLORS["error"], visible=False)
    rows: dict[str, dict] = {}
    body: list[ft.Control] = []
    alive = {"open": True}
    kw_dd = {k: v for k, v in DLG_FIELD_KWARGS.items() if k != "cursor_color"}

    def active(p) -> bool:
        e = cfg.profiles.get(p.name, {})
        on = p.auto_post_fanpage or p.auto_post_tiktok or p.auto_post_youtube
        return bool(on or e.get("fanpages") or e.get("tiktok") or e.get("youtube"))

    # Profiles that auto-post or are mapped first, the rest after
    for p in sorted(profiles, key=lambda p: (not active(p), p.name.lower())):
        entry = cfg.profiles.get(p.name, {})
        pages_field = ft.TextField(
            label=get_string("post_map_pages"),
            value=", ".join(x["id"] for x in entry.get("fanpages", [])),
            helper=get_string("post_map_pages_hint"),
            expand=True,
            **DLG_FIELD_KWARGS,
        )
        tiktok_field = ft.TextField(
            label=get_string("post_map_tiktok"),
            value=("@" + entry["tiktok"]) if entry.get("tiktok") else "",
            helper=get_string("post_map_tiktok_hint"),
            width=210,
            **DLG_FIELD_KWARGS,
        )
        youtube_field = ft.TextField(
            label=get_string("post_map_youtube"),
            value=("@" + entry["youtube"]) if entry.get("youtube") else "",
            helper=get_string("post_map_youtube_hint"),
            width=210,
            **DLG_FIELD_KWARGS,
        )
        per_day = ft.TextField(
            label=get_string("post_map_per_day"),
            value=str(entry.get("max_per_day") or 0),
            helper=get_string("post_map_per_day_hint"),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=170,
            **DLG_FIELD_KWARGS,
        )
        hours_field = ft.TextField(
            label=get_string("post_map_hours"),
            value=entry.get("hours", ""),
            helper=get_string("post_map_hours_hint"),
            expand=True,
            **DLG_FIELD_KWARGS,
        )
        caption_lang = ft.Dropdown(
            value=entry.get("caption_lang") or "-",
            label=get_string("post_map_caption_lang"),
            options=[ft.DropdownOption(key=k or "-", text=v) for k, v in muse_team.LANGS.items()],
            width=210,
            dense=True,
            tooltip=get_string("post_map_caption_lang_hint"),
            **kw_dd,
        )
        rows[p.name] = {"pages": pages_field, "tiktok": tiktok_field, "youtube": youtube_field,
                        "per_day": per_day, "hours": hours_field, "lang": caption_lang}
        targets = [t for t, on in (("Fanpage", p.auto_post_fanpage), ("TikTok", p.auto_post_tiktok),
                                   ("YouTube", p.auto_post_youtube)) if on]
        warning = ft.Text("", size=12, color=COLORS["error"], visible=False)
        check_box = ft.Column(spacing=2, tight=True)

        def check(_: object = None, p=p, pages_field=pages_field, tiktok_field=tiktok_field,
                  youtube_field=youtube_field, warning=warning) -> None:
            missing = []
            if p.auto_post_fanpage and not post_map.page_ids(pages_field.value):
                missing.append("Fanpage")
            if p.auto_post_tiktok and not post_map.tiktok_handle(tiktok_field.value):
                missing.append("TikTok")
            if p.auto_post_youtube and not post_map.youtube_handle(youtube_field.value):
                missing.append("YouTube")
            warning.value = get_string("post_map_missing", target=" / ".join(missing))
            warning.visible = bool(missing)
            if _ is not None:
                page.update()

        pages_field.on_change = check
        tiktok_field.on_change = check
        youtube_field.on_change = check
        check()

        def add(page_id: str, pages_field=pages_field, check=check) -> None:
            ids = post_map.page_ids(pages_field.value)
            if page_id not in ids:
                pages_field.value = ", ".join([*ids, page_id])
                check(True)

        def show_check(result: dict | None, check_box=check_box) -> None:
            check_box.controls = [
                ft.Text(("✓ " if ok else "✗ ") + text, size=12,
                        color=COLORS["text_sub"] if ok else COLORS["error"])
                for ok, text in check_lines(result)
            ]

        def watch(name: str, show_check=show_check, pages_field=pages_field, tiktok_field=tiktok_field,
                  youtube_field=youtube_field, check=check) -> None:
            while alive["open"]:
                time.sleep(CHECK_POLL_SECONDS)
                result = post_map.check_result(name)
                show_check(result)
                done = not result or not result.get("running")
                if done:
                    # The check may have written empty slots into the map: show them, so Save keeps them
                    saved = post_map.current().profiles.get(name) or {}
                    if not (pages_field.value or "").strip() and saved.get("fanpages"):
                        pages_field.value = ", ".join(p["id"] for p in saved["fanpages"])
                    if not (tiktok_field.value or "").strip() and saved.get("tiktok"):
                        tiktok_field.value = "@" + saved["tiktok"]
                    if not (youtube_field.value or "").strip() and saved.get("youtube"):
                        youtube_field.value = "@" + saved["youtube"]
                    check()
                try:
                    page.update()
                except Exception:
                    return
                if done:
                    return

        def start(_: object, name=p.name, show_check=show_check, watch=watch) -> None:
            try:
                post_map.start_check(name)
            except post_map.PostMapError as e:
                show_check({"running": False, "at": "", "error": str(e)})
                page.update()
                return
            show_check({"running": True})
            page.update()
            threading.Thread(target=watch, args=(name,), daemon=True).start()

        show_check(post_map.check_result(p.name))
        if (post_map.check_result(p.name) or {}).get("running"):
            threading.Thread(target=watch, args=(p.name,), daemon=True).start()

        known = post_map.known_pages(p.name)
        known_tt, known_yt = post_map.known_tiktok(p.name), post_map.known_youtube(p.name)
        # Empty field + exactly one known account: fill it (kept only when the owner saves)
        filled = []
        if p.auto_post_tiktok and not tiktok_field.value and known_tt:
            tiktok_field.value = "@" + known_tt
            filled.append("TikTok")
        if p.auto_post_youtube and not youtube_field.value and len(known_yt) == 1:
            youtube_field.value = "@" + known_yt[0]["handle"]
            filled.append("YouTube")
        if filled:
            check()

        def put(field: ft.TextField, value: str, check=check) -> None:
            field.value = value
            check(True)

        def suggest(label: str, items: list[tuple[str, Callable]]) -> ft.Row:
            return ft.Row(wrap=True, spacing=2, run_spacing=0, controls=[
                ft.Text(label, size=12, color=COLORS["text_dim"]),
                *[ft.TextButton(text, style=ft.ButtonStyle(color=COLORS["sidebar"]), on_click=fn)
                  for text, fn in items],
            ])

        tt_row = suggest(
            get_string("post_map_known_tt") if known_tt else get_string("post_map_known_tt_none"),
            [("@" + known_tt, lambda _, f=tiktok_field, v="@" + known_tt, put=put: put(f, v))] if known_tt else [],
        )
        yt_row = suggest(
            get_string("post_map_known_yt") if known_yt else get_string("post_map_known_yt_none"),
            [(f"{c['name'] or c['handle']} · @{c['handle']}",
              lambda _, f=youtube_field, v="@" + c["handle"], put=put: put(f, v)) for c in known_yt],
        )
        filled_note = ft.Text(get_string("post_map_autofilled", targets=", ".join(filled)), size=12,
                              color=COLORS["sidebar"], visible=bool(filled))
        known_row = ft.Row(
            wrap=True,
            spacing=2,
            run_spacing=0,
            controls=[
                ft.Text(
                    get_string("post_map_known") if known else get_string("post_map_known_none"),
                    size=12,
                    color=COLORS["text_dim"],
                ),
                *[
                    ft.TextButton(
                        f"+ {k['name'] or k['id']} ({k['id']})",
                        style=ft.ButtonStyle(color=COLORS["sidebar"]),
                        on_click=lambda _, i=k["id"], add=add: add(i),
                    )
                    for k in known
                ],
            ],
        )
        body.append(
            ft.Container(
                padding=ft.Padding.only(top=10, bottom=6),
                border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["rule_strong"])),
                content=ft.Column(
                    spacing=6,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Text(p.name, size=14, font_family=FONT_SEMIBOLD,
                                        color=COLORS["text_main"]),
                                ft.Text(
                                    get_string("post_map_auto", targets=", ".join(targets))
                                    if targets else get_string("post_map_auto_off"),
                                    size=12,
                                    color=COLORS["text_sub"],
                                    expand=True,
                                ),
                                ft.TextButton(
                                    get_string("post_map_check"),
                                    icon=ft.Icons.VERIFIED_USER_OUTLINED,
                                    style=ft.ButtonStyle(color=COLORS["sidebar"]),
                                    on_click=start,
                                ),
                            ],
                        ),
                        ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            controls=[pages_field, tiktok_field, youtube_field],
                        ),
                        ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            controls=[per_day, hours_field, caption_lang],
                        ),
                        known_row,
                        tt_row,
                        yt_row,
                        filled_note,
                        warning,
                        check_box,
                    ],
                ),
            )
        )

    def close(_: object = None) -> None:
        alive["open"] = False
        page.pop_dialog()

    def on_save(_: ft.ControlEvent) -> None:
        error.visible = False
        data = {
            n: {
                "fanpages": r["pages"].value or "",
                "tiktok": r["tiktok"].value or "",
                "youtube": r["youtube"].value or "",
                "max_per_day": (r["per_day"].value or "0").strip() or "0",
                "hours": r["hours"].value or "",
                "caption_lang": "" if (r["lang"].value or "-") == "-" else r["lang"].value,
            }
            for n, r in rows.items()
        }
        try:
            post_map.save(data)
        except post_map.PostMapError as e:
            error.value = str(e)
            error.visible = True
            page.update()
            return
        done = get_string("post_map_saved")
        log(done)
        close()
        page.show_dialog(ft.SnackBar(ft.Text(done)))

    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=4, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(get_string("post_map_title"), size=19, font_family=FONT_BOLD,
                        color=COLORS["text_main"]),
                ft.Text(get_string("post_map_sub", path=cfg.file), size=13,
                        color=COLORS["text_sub"], selectable=True),
            ],
        ),
        content=ft.Container(
            width=720,
            content=ft.Column(
                tight=True,
                spacing=4,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Text(get_string("post_map_explain"), size=12.5, color=COLORS["text_sub"]),
                    *(body or [ft.Text(get_string("post_map_none"), size=12.5,
                                       color=COLORS["text_dim"])]),
                    error,
                ],
            ),
        ),
        actions=[
            ft.TextButton(
                get_string("cancel"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=close,
            ),
            ft.Button(get_string("save_changes"), icon=ft.Icons.SAVE, style=ACCENT_STYLE,
                      on_click=on_save),
        ],
    )
    page.show_dialog(dlg)
