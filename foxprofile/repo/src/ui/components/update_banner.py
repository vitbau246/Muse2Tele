"""Muse2Tele update notice above the profile sheet: new version, update running, or last result."""

import time
from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE


def short_date(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        t = time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return time.strftime("%d/%m/%Y", t)
    except ValueError:
        return iso[:10]


def _recent(iso: str | None, seconds: int) -> bool:
    try:
        return time.time() - time.mktime(time.strptime((iso or "")[:19], "%Y-%m-%dT%H:%M:%S")) < seconds
    except ValueError:
        return False


def build_update_banner(
    info: dict | None,
    on_open: Callable[[], None],
    on_dismiss: Callable[[], None],
    dismissed: bool = False,
) -> ft.Control | None:
    """None when there is nothing to say."""
    if not info or not info.get("supported"):
        return None
    last = info.get("last_update") or {}
    if info.get("busy"):
        return _bar(
            get_string("update_busy", message=last.get("message", "")),
            None,
            COLORS["paper_sunk"],
            COLORS["text_sub"],
            ft.ProgressRing(width=16, height=16, stroke_width=2, color=COLORS["text_sub"]),
        )
    if info.get("available"):
        remote = info.get("remote") or {}
        return _bar(
            get_string("update_available"),
            get_string(
                "update_available_sub",
                date=short_date(remote.get("date")),
                message=remote.get("message", ""),
            ),
            COLORS["accent_soft"],
            COLORS["text_main"],
            ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT, size=18, color=COLORS["accent"]),
            ft.Button(
                get_string("update_open"),
                icon=ft.Icons.DOWNLOAD,
                height=34,
                style=ACCENT_STYLE,
                on_click=lambda _: on_open(),
            ),
        )
    if dismissed or not _recent(last.get("at"), 3600):
        return None
    if last.get("state") == "done":
        text, bg, icon = get_string("update_done", message=last.get("message", "")), COLORS["card_selected_bg"], ft.Icons.CHECK_CIRCLE_OUTLINE
        color = COLORS["success"]
    elif last.get("state") == "error":
        text, bg, icon = get_string("update_failed", message=last.get("message", "")), COLORS["warn_tint"], ft.Icons.WARNING_AMBER_ROUNDED
        color = COLORS["warning"]
    else:
        return None
    return _bar(
        text,
        None,
        bg,
        COLORS["text_main"],
        ft.Icon(icon, size=18, color=color),
        ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_size=16,
            icon_color=COLORS["text_sub"],
            tooltip=get_string("dismiss"),
            on_click=lambda _: on_dismiss(),
        ),
    )


def _bar(
    title: str,
    sub: str | None,
    bg: str,
    color: str,
    lead: ft.Control,
    action: ft.Control | None = None,
) -> ft.Container:
    return ft.Container(
        margin=ft.Margin.only(bottom=14),
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        border_radius=10,
        bgcolor=bg,
        border=ft.Border.all(1, COLORS["card_border"]),
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                lead,
                ft.Column(
                    spacing=1,
                    expand=True,
                    controls=[
                        ft.Text(title, size=13.5, font_family=FONT_SEMIBOLD, color=color),
                        *(
                            [
                                ft.Text(
                                    sub,
                                    size=12,
                                    color=COLORS["text_sub"],
                                    no_wrap=True,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                )
                            ]
                            if sub
                            else []
                        ),
                    ],
                ),
                *([action] if action else []),
            ],
        ),
    )
