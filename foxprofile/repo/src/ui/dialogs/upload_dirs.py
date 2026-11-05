"""Choose FOXPROFILE_UPLOAD_DIRS and MUSE_UPLOAD_DIR (saved to Muse2Tele's .env)."""

import pathlib
from collections.abc import Callable

import flet as ft

from ...core import upload_dirs
from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, OUTLINE_STYLE

_DATA = ft.TextStyle(font_family=FONT_DATA, size=12.5)


def open_upload_dirs_dialog(
    page: ft.Page, file_picker: ft.FilePicker, log: Callable[[str], None]
) -> None:
    cfg = upload_dirs.current()
    muse_default = str(upload_dirs.muse_default())

    rows = ft.Column(spacing=6, tight=True)
    empty_note = ft.Text(get_string("upload_dirs_none"), size=12, color=COLORS["warning"])
    error = ft.Text("", size=12, color=COLORS["error"], visible=False)

    muse_field = ft.TextField(
        value=cfg.muse_upload_dir if cfg.muse_custom else "",
        hint_text=muse_default,
        text_style=_DATA,
        expand=True,
        **DLG_FIELD_KWARGS,
    )
    muse_warn = ft.Text(get_string("muse_dir_outside"), size=12, color=COLORS["warning"])

    def dir_values() -> list[str]:
        return [
            (r.controls[0].value or "").strip()
            for r in rows.controls
            if (r.controls[0].value or "").strip()
        ]

    def sync(_: object = None) -> None:
        """Live hints: no folder at all, or a Muse folder outside every upload folder."""
        values = dir_values()
        empty_note.visible = not values
        muse = (muse_field.value or "").strip() or muse_default
        roots = [pathlib.Path(v) for v in values]
        try:
            m = pathlib.Path(muse).resolve()
            inside = any(m == r.resolve() or m.is_relative_to(r.resolve()) for r in roots)
        except (OSError, ValueError):
            inside = False
        muse_warn.visible = cfg.bot_installed and bool(values) and not inside
        page.update()

    async def pick_into(field: ft.TextField) -> None:
        path = await file_picker.get_directory_path(
            dialog_title=get_string("choose_folder"),
            initial_directory=(field.value or "").strip() or None,
        )
        if path:
            field.value = path
            sync()

    def add_row(value: str = "") -> ft.TextField:
        field = ft.TextField(
            value=value, text_style=_DATA, expand=True, on_change=sync, **DLG_FIELD_KWARGS
        )
        row = ft.Row(spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        async def choose(_: ft.ControlEvent) -> None:
            await pick_into(field)

        def remove(_: ft.ControlEvent) -> None:
            rows.controls.remove(row)
            sync()

        row.controls = [
            field,
            ft.OutlinedButton(
                get_string("choose_folder"),
                icon=ft.Icons.FOLDER_OPEN,
                height=38,
                style=OUTLINE_STYLE,
                on_click=choose,
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE,
                icon_size=18,
                icon_color=COLORS["text_sub"],
                tooltip=get_string("upload_dirs_remove"),
                on_click=remove,
            ),
        ]
        rows.controls.append(row)
        return field

    for d in cfg.upload_dirs:
        add_row(d)

    async def on_add(_: ft.ControlEvent) -> None:
        field = add_row()
        page.update()
        await pick_into(field)

    async def on_choose_muse(_: ft.ControlEvent) -> None:
        await pick_into(muse_field)

    def on_muse_default(_: ft.ControlEvent) -> None:
        muse_field.value = ""
        sync()

    muse_field.on_change = sync

    def on_save(_: ft.ControlEvent) -> None:
        error.visible = False
        try:
            upload_dirs.save(dir_values(), muse_field.value)
        except upload_dirs.UploadDirsError as e:
            error.value = str(e)
            error.visible = True
            page.update()
            return
        log(get_string("upload_dirs_saved"))
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(get_string("upload_dirs_saved"))))

    def section(label: str, explain: str, *body: ft.Control) -> ft.Column:
        return ft.Column(
            spacing=6,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Container(
                    padding=ft.Padding.only(top=12),
                    content=ft.Text(
                        label, size=13, font_family=FONT_SEMIBOLD, color=COLORS["text_main"]
                    ),
                ),
                ft.Text(explain, size=12.5, color=COLORS["text_sub"]),
                *body,
            ],
        )

    upload_section = section(
        get_string("upload_dirs_label"),
        get_string("upload_dirs_explain"),
        rows,
        empty_note,
        ft.Row(
            controls=[
                ft.TextButton(get_string("upload_dirs_add"), icon=ft.Icons.ADD, on_click=on_add)
            ]
        ),
    )
    muse_section = section(
        get_string("muse_dir_label"),
        get_string("muse_dir_explain"),
        ft.Row(
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                muse_field,
                ft.OutlinedButton(
                    get_string("choose_folder"),
                    icon=ft.Icons.FOLDER_OPEN,
                    height=38,
                    style=OUTLINE_STYLE,
                    on_click=on_choose_muse,
                ),
                ft.TextButton(get_string("use_default"), on_click=on_muse_default),
            ],
        ),
        ft.Text(
            get_string("muse_dir_default", path=muse_default), size=12, color=COLORS["text_dim"]
        ),
        muse_warn,
    )
    muse_section.visible = cfg.bot_installed

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
                ft.Text(
                    get_string("upload_dirs_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    get_string("upload_dirs_sub", path=cfg.env_file),
                    size=13,
                    color=COLORS["text_sub"],
                    selectable=True,
                ),
            ],
        ),
        content=ft.Container(
            width=600,
            content=ft.Column(
                tight=True,
                spacing=4,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[upload_section, muse_section, error],
            ),
        ),
        actions=[
            ft.TextButton(
                get_string("cancel"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=lambda _: page.pop_dialog(),
            ),
            ft.Button(
                get_string("save_changes"), icon=ft.Icons.SAVE, style=ACCENT_STYLE, on_click=on_save
            ),
        ],
    )
    page.show_dialog(dlg)
    sync()
