"""Confirm a Muse2Tele update: versions, what's new, what is kept and what restarts."""

from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..components.update_banner import short_date
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE


def open_update_dialog(page: ft.Page, info: dict, on_confirm: Callable[[], str | None]) -> None:
    remote = info.get("remote") or {}
    local = (info.get("local_sha") or "")[:7] or get_string("update_unknown_local")
    changes = info.get("changes") or ([remote["message"]] if remote.get("message") else [])
    error = ft.Text("", size=12, color=COLORS["error"], visible=False)

    def note(icon: str, text: str, color: str) -> ft.Row:
        return ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(icon, size=16, color=color),
                ft.Text(text, size=12.5, color=COLORS["text_sub"], expand=True),
            ],
        )

    def confirm(_: ft.ControlEvent) -> None:
        problem = on_confirm()
        if problem:
            error.value = problem
            error.visible = True
            page.update()
            return
        page.pop_dialog()

    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=8, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(get_string("update_title"), size=19, font_family=FONT_BOLD, color=COLORS["text_main"]),
                ft.Text(
                    get_string(
                        "update_versions",
                        local=local,
                        remote=(remote.get("sha") or "")[:7],
                        date=short_date(remote.get("date")),
                    ),
                    size=12.5,
                    font_family=FONT_DATA,
                    color=COLORS["text_sub"],
                ),
            ],
        ),
        content=ft.Container(
            width=520,
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text(get_string("update_changes"), size=13, font_family=FONT_SEMIBOLD, color=COLORS["text_main"]),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                        border_radius=8,
                        bgcolor=COLORS["bg"],
                        border=ft.Border.all(1, COLORS["card_border"]),
                        content=ft.Column(
                            spacing=4,
                            controls=[ft.Text(f"• {c}", size=12.5, color=COLORS["text_main"], selectable=True) for c in changes]
                            or [ft.Text(get_string("update_no_changes"), size=12.5, color=COLORS["text_dim"])],
                        ),
                    ),
                    *([ft.Text(info["note"], size=12, color=COLORS["text_dim"])] if info.get("note") else []),
                    ft.Container(height=4),
                    note(ft.Icons.LOCK_OUTLINE, get_string("update_keep_data"), COLORS["success"]),
                    note(ft.Icons.RESTART_ALT, get_string("update_restart_note"), COLORS["warning"]),
                    note(ft.Icons.INVENTORY_2_OUTLINED, get_string("update_backup_note"), COLORS["text_sub"]),
                    error,
                ],
            ),
        ),
        actions=[
            ft.TextButton(
                get_string("cancel"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=lambda _: page.pop_dialog(),
            ),
            ft.Button(get_string("update_now"), icon=ft.Icons.DOWNLOAD, style=ACCENT_STYLE, on_click=confirm),
        ],
    )
    page.show_dialog(dlg)
