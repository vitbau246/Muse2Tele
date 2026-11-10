"""Muse2Tele team mode: each Muse alone, or one chief Muse leading the others (muse_team.json)."""

from collections.abc import Callable

import flet as ft

from ...core import muse_team, post_map
from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, ERROR_STYLE, OUTLINE_STYLE


def open_muse_team_dialog(
    page: ft.Page, profile_names: list[str], log: Callable[[str], None]
) -> None:
    cfg = muse_team.current()
    names = list(profile_names)
    if cfg.chief and cfg.chief not in names:
        names.insert(0, cfg.chief)
    error = ft.Text("", size=12, color=COLORS["error"], visible=False)

    def choice(value: str, label: str, explain: str) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.only(bottom=4),
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Radio(value=value, active_color=COLORS["sidebar"]),
                    ft.Column(
                        spacing=1,
                        tight=True,
                        expand=True,
                        controls=[
                            ft.Container(
                                padding=ft.Padding.only(top=9),
                                content=ft.Text(
                                    label,
                                    size=13.5,
                                    font_family=FONT_SEMIBOLD,
                                    color=COLORS["text_main"],
                                ),
                            ),
                            ft.Text(explain, size=12.5, color=COLORS["text_sub"]),
                        ],
                    ),
                ],
            ),
        )

    mode_group = ft.RadioGroup(
        value=cfg.mode,
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                choice("solo", get_string("team_mode_solo"), get_string("team_mode_solo_explain")),
                choice(
                    "chief", get_string("team_mode_chief"), get_string("team_mode_chief_explain")
                ),
            ],
        ),
    )
    approval_group = ft.RadioGroup(
        value=cfg.approval,
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                choice(
                    "manual",
                    get_string("team_approval_manual"),
                    get_string("team_approval_manual_explain"),
                ),
                choice(
                    "auto",
                    get_string("team_approval_auto"),
                    get_string("team_approval_auto_explain"),
                ),
            ],
        ),
    )
    chief_dropdown = ft.Dropdown(
        value=cfg.chief or None,
        options=[ft.DropdownOption(key=n, text=n) for n in names],
        hint_text=get_string("team_chief_hint"),
        expand=True,
        **{k: v for k, v in DLG_FIELD_KWARGS.items() if k != "cursor_color"},
    )
    task_lang = ft.Dropdown(
        value=cfg.task_lang or "-",  # "-": khong quy dinh (Dropdown khong nhan khoa rong)
        options=[ft.DropdownOption(key=k or "-", text=v) for k, v in muse_team.LANGS.items()],
        width=280,
        dense=True,
        **{k: v for k, v in DLG_FIELD_KWARGS.items() if k != "cursor_color"},
    )
    mapped = post_map.current().profiles
    post_group = ft.RadioGroup(
        value=cfg.post_mode,
        content=ft.Column(
            spacing=0,
            tight=True,
            controls=[
                choice("off", get_string("team_post_off"), get_string("team_post_off_explain")),
                choice("ask", get_string("team_post_ask"), get_string("team_post_ask_explain")),
                choice("auto", get_string("team_post_auto"), get_string("team_post_auto_explain")),
            ],
        ),
    )
    channels = list(profile_names)
    if cfg.post_profile and cfg.post_profile not in channels:
        channels.insert(0, cfg.post_profile)
    post_profile = ft.Dropdown(
        value=cfg.post_profile or "-",
        label=get_string("team_post_profile"),
        options=[ft.DropdownOption(key="-", text=get_string("team_post_profile_none"))]
        + [ft.DropdownOption(key=n, text=n) for n in channels],
        width=320,
        dense=True,
        **{k: v for k, v in DLG_FIELD_KWARGS.items() if k != "cursor_color"},
    )
    post_note = ft.Text(get_string("team_post_unmapped"), size=12, color=COLORS["error"], visible=False)
    role_fields = {
        n: ft.TextField(
            label=n,
            value=cfg.roles.get(n, ""),
            max_length=muse_team.MAX_ROLE,
            expand=True,
            disabled=n in cfg.excluded,
            **DLG_FIELD_KWARGS,
        )
        for n in profile_names
    }
    member_boxes = {
        n: ft.Checkbox(
            value=n not in cfg.excluded,
            active_color=COLORS["sidebar"],
            tooltip=get_string("team_member_hint"),
        )
        for n in profile_names
    }
    # Tach 1 thanh vien khoi doi (ap dung ngay, khong can Luu): chi Muse dang trong doi theo cai dat da luu
    detach_panels: dict[str, ft.Container] = {}

    def detach_panel(name: str) -> ft.Container:
        wipe = ft.Checkbox(
            value=False,
            active_color=COLORS["error"],
            label=get_string("team_detach_wipe"),
            label_style=ft.TextStyle(size=12.5, color=COLORS["text_sub"]),
        )

        def go(_: ft.ControlEvent) -> None:
            try:
                muse_team.detach(name, bool(wipe.value), profile_names)
            except muse_team.MuseTeamError as e:
                error.value = str(e)
                error.visible = True
                page.update()
                return
            done = get_string("team_detach_done_wipe" if wipe.value else "team_detach_done", name=name)
            log(done)
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text(done)))

        def cancel(_: ft.ControlEvent) -> None:
            panel.visible = False
            page.update()

        panel = ft.Container(
            visible=False,
            padding=ft.Padding.all(10),
            margin=ft.Margin.only(left=34),
            border=ft.Border.all(1, COLORS["error"]),
            border_radius=8,
            content=ft.Column(
                spacing=6,
                tight=True,
                controls=[
                    ft.Text(get_string("team_detach_explain", name=name), size=12.5, color=COLORS["text_main"]),
                    wipe,
                    ft.Row(
                        controls=[
                            ft.Button(
                                get_string("team_detach_go", name=name),
                                icon=ft.Icons.CONTENT_CUT,
                                style=ERROR_STYLE,
                                on_click=go,
                            ),
                            ft.TextButton(
                                get_string("cancel"),
                                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                                on_click=cancel,
                            ),
                        ],
                    ),
                ],
            ),
        )
        return panel

    def detach_button(name: str) -> ft.Control:
        if cfg.mode != "chief" or name == cfg.chief or name in cfg.excluded:
            return ft.Container(width=40)
        detach_panels[name] = detach_panel(name)

        def toggle(_: ft.ControlEvent) -> None:
            detach_panels[name].visible = not detach_panels[name].visible
            page.update()

        return ft.IconButton(
            ft.Icons.CONTENT_CUT,
            icon_size=18,
            icon_color=COLORS["text_sub"],
            tooltip=get_string("team_detach_hint"),
            on_click=toggle,
        )

    member_rows = {}
    for n, field in role_fields.items():
        row = ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Container(padding=ft.Padding.only(top=6), content=member_boxes[n]),
                field,
                ft.Container(padding=ft.Padding.only(top=4), content=detach_button(n)),
            ],
        )
        member_rows[n] = (
            ft.Column(spacing=6, tight=True, controls=[row, detach_panels[n]]) if n in detach_panels else row
        )
    roles_column = ft.Column(spacing=8, tight=True)

    # Ngon ngu + ngu canh (bo nho dai han) tung Muse, ca chi huy: bot gui cho Muse 1 lan, sua thi gui lai
    def setup_panel(name: str) -> dict:
        item = cfg.setup.get(name, {})
        head = ft.Text(name, size=13, font_family=FONT_SEMIBOLD, color=COLORS["text_main"])
        lang = ft.Dropdown(
            value=item.get("lang") or "-",  # "-": mac dinh (Dropdown khong nhan khoa rong)
            label=get_string("team_setup_lang"),
            options=[ft.DropdownOption(key=k or "-", text=v) for k, v in muse_team.LANGS.items()],
            width=230,
            dense=True,
            **{k: v for k, v in DLG_FIELD_KWARGS.items() if k != "cursor_color"},
        )
        context = ft.TextField(
            label=get_string("team_setup_context"),
            value=item.get("context", ""),
            multiline=True,
            min_lines=4,
            max_lines=14,
            max_length=muse_team.MAX_CONTEXT,
            visible=False,
            **DLG_FIELD_KWARGS,
        )

        def label() -> str:
            n = len((context.value or "").strip())
            return get_string("team_setup_open") + (f" ({n})" if n else "")

        def toggle(_: object) -> None:
            context.visible = not context.visible
            open_button.icon = (
                ft.Icons.KEYBOARD_ARROW_UP if context.visible else ft.Icons.KEYBOARD_ARROW_DOWN
            )
            page.update()

        def fill(text: str) -> None:
            context.value = text
            if lang.value in (None, "-"):
                lang.value = "vi"
            open_button.content = label()

        def typed(_: object) -> None:
            disarm_template()
            open_button.content = label()
            auto_reset()
            page.update()

        context.on_change = typed
        lang.on_select = typed
        open_button = ft.TextButton(
            label(),
            icon=ft.Icons.KEYBOARD_ARROW_DOWN,
            style=ft.ButtonStyle(color=COLORS["sidebar"]),
            on_click=toggle,
        )
        box = ft.Column(
            spacing=4,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                head,
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[lang, open_button],
                ),
                context,
            ],
        )
        return {"head": head, "lang": lang, "context": context, "box": box, "fill": fill}

    setups = {n: setup_panel(n) for n in names}
    setup_column = ft.Column(spacing=12, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # Mau ca doi: 1 lan bam dien ngu canh chi huy cho chi huy, ngu canh thanh vien cho moi Muse dang tick (va vai tro
    # con trong). Co Muse dang co ngu canh khac mau: bam lan 1 hien canh bao, bam lan 2 moi thay.
    template_armed = {"id": ""}
    template_used = {"id": ""}  # mau da dien trong lan mo nay: luu thi bot lam moi ca du lieu doi
    template_note = ft.Text("", size=12.5, color=COLORS["error"], visible=False)

    def team_now() -> tuple[str, list[str]]:
        lead = chief_dropdown.value or ""
        return lead, [n for n in profile_names if n != lead and member_boxes[n].value]

    def disarm_template() -> None:
        template_armed["id"] = ""
        template_note.visible = False

    def use_template(tpl: dict[str, str]) -> None:
        lead, members = team_now()
        want = ({lead: tpl["chief"]} if lead in setups else {}) | {
            n: tpl["member"] for n in members if n in setups
        }
        busy = [
            n for n, text in want.items()
            if (setups[n]["context"].value or "").strip() not in ("", text.strip())
        ]
        if busy and template_armed["id"] != tpl["id"]:
            template_armed["id"] = tpl["id"]
            template_note.value = get_string("team_setup_replace", names=", ".join(busy))
            template_note.visible = True
            page.update()
            return
        disarm_template()
        for n, text in want.items():
            setups[n]["fill"](text)
        for n in members:
            if tpl.get("member_role") and not (role_fields[n].value or "").strip():
                role_fields[n].value = tpl["member_role"]
        template_used["id"] = tpl["id"]
        auto_reset()
        page.update()

    template_row = ft.Column(
        spacing=2,
        tight=True,
        controls=[
            ft.Text(get_string("team_setup_template_pick"), size=12.5, color=COLORS["text_sub"]),
            ft.Row(
                wrap=True,
                spacing=4,
                controls=[
                    ft.Button(
                        tpl["label"],
                        icon=ft.Icons.AUTO_AWESOME,
                        style=OUTLINE_STYLE,
                        on_click=lambda _, tpl=tpl: use_template(tpl),
                    )
                    for tpl in muse_team.TEMPLATES
                ],
            ),
            template_note,
        ],
    )
    roles_none = ft.Text(get_string("team_roles_none"), size=12.5, color=COLORS["text_dim"])
    # Review settings: key -> (label key, hint key or "")
    number_specs = {
        "pass_score": ("team_pass_score", "team_pass_score_hint"),
        "max_rounds": ("team_max_rounds", "team_max_rounds_hint"),
        "quiet_minutes": ("team_quiet", "team_quiet_hint"),
        "overdue_minutes": ("team_overdue", ""),
        "max_new_per_hour": ("team_max_new", ""),
    }
    number_fields = {
        key: ft.TextField(
            label=get_string(label),
            value=str(getattr(cfg, key)),
            helper=get_string(hint) if hint else None,
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
            **DLG_FIELD_KWARGS,
        )
        for key, (label, hint) in number_specs.items()
    }

    def tick(value: bool, label: str, explain: str) -> tuple[ft.Checkbox, ft.Row]:
        box = ft.Checkbox(value=value, active_color=COLORS["sidebar"])
        row = ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                box,
                ft.Column(
                    spacing=1,
                    tight=True,
                    expand=True,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.only(top=9),
                            content=ft.Text(
                                label,
                                size=13.5,
                                font_family=FONT_SEMIBOLD,
                                color=COLORS["text_main"],
                            ),
                        ),
                        ft.Text(explain, size=12.5, color=COLORS["text_sub"]),
                    ],
                ),
            ],
        )
        return box, row

    one_video_box, one_video_row = tick(
        cfg.one_video, get_string("team_one_video"), get_string("team_one_video_explain")
    )
    show_failed_box, show_failed_row = tick(
        cfg.show_failed_media, get_string("team_show_failed"), get_string("team_show_failed_explain")
    )
    # Xoa du lieu Muse khi luu: tu tick khi doi ngu canh (chi xoa cac Muse doi ngu canh, roi bot gui ngu canh moi);
    # chu tu bam o nay thi thoi tu dong. Doi mau: bot bo ca viec, video mau, kich ban, cat bo nhan vat cu.
    reset_box, reset_row = tick(False, get_string("team_reset"), get_string("team_reset_explain"))
    reset_note = ft.Text("", size=12.5, color=COLORS["text_sub"], visible=False)
    reset_manual = {"on": False}
    reset_warning = ft.Text("", size=12.5, color=COLORS["error"], visible=False)

    def changed_setup() -> list[str]:
        """Muse trong doi (chi huy + thanh vien dang tick) co ngon ngu / ngu canh khac ban da luu."""
        lead, members = team_now()
        out = []
        for n in ([lead] if lead else []) + members:
            if n not in setups:
                continue
            old = cfg.setup.get(n, {})
            now = ((setups[n]["lang"].value or "").strip("-"), (setups[n]["context"].value or "").strip())
            if now != (old.get("lang", ""), old.get("context", "").strip()):
                out.append(n)
        return out

    def reset_plan() -> tuple[list[str], bool]:
        """(Muse se xoa -- [] = chi huy + ca doi, co lam moi du lieu doi khong)."""
        return changed_setup(), bool(template_used["id"])

    def auto_reset() -> None:
        targets, full = reset_plan()
        if not reset_manual["on"]:
            reset_box.value = bool(targets or full)
        lead, members = team_now()
        names = ", ".join(targets or ([lead] if lead else []) + members)
        reset_note.value = get_string("team_reset_who", names=names or "-") + (
            " " + get_string("team_reset_template") if full else ""
        )
        reset_note.visible = bool(reset_box.value)
    confirmed = {"names": ""}  # reset da xac nhan cho dung danh sach nay (bam Luu lan 2)

    def section(label: str, *body: ft.Control) -> ft.Column:
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
                *body,
            ],
        )

    chief_part = ft.Column(
        spacing=4,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            section(
                get_string("team_chief_label"),
                ft.Row(controls=[chief_dropdown]),
                ft.Text(get_string("team_chief_note"), size=12, color=COLORS["text_dim"]),
            ),
            section(get_string("team_approval_label"), approval_group),
            section(
                get_string("team_task_lang_label"),
                ft.Text(get_string("team_task_lang_explain"), size=12.5, color=COLORS["text_sub"]),
                ft.Row(controls=[task_lang]),
            ),
            section(
                get_string("team_roles_label"),
                ft.Text(get_string("team_roles_explain"), size=12.5, color=COLORS["text_sub"]),
                roles_column,
                roles_none,
            ),
            section(
                get_string("team_setup_label"),
                ft.Text(get_string("team_setup_explain"), size=12.5, color=COLORS["text_sub"]),
                template_row,
                setup_column,
            ),
            section(
                get_string("team_post_label"),
                post_group,
                ft.Row(controls=[post_profile]),
                post_note,
            ),
            section(
                get_string("team_review_label"),
                ft.Row(controls=[number_fields["pass_score"], number_fields["max_rounds"]]),
                ft.Row(controls=[number_fields["quiet_minutes"], number_fields["overdue_minutes"]]),
                ft.Row(controls=[number_fields["max_new_per_hour"], ft.Container(expand=True)]),
                one_video_row,
                show_failed_row,
            ),
            ft.Container(padding=ft.Padding.only(top=10), content=reset_row),
            reset_note,
            reset_warning,
        ],
    )

    def sync(_: object = None) -> None:
        chief_part.visible = mode_group.value == "chief"
        chosen = "" if (post_profile.value or "-") == "-" else post_profile.value
        entry = mapped.get(chosen) or {}
        post_note.visible = bool(chosen) and not (entry.get("fanpages") or entry.get("tiktok"))
        roles_column.controls = [r for n, r in member_rows.items() if n != chief_dropdown.value]
        roles_none.visible = not roles_column.controls
        for n, box in member_boxes.items():
            role_fields[n].disabled = not box.value
        lead = chief_dropdown.value
        shown = ([lead] if lead in setups else []) + [
            n for n in profile_names if n != lead and member_boxes[n].value
        ]
        for n in shown:
            setups[n]["head"].value = get_string("team_setup_chief", name=n) if n == lead else n
        setup_column.controls = [setups[n]["box"] for n in shown]
        # doi lua chon thi phai xac nhan xoa du lieu / reset doi lai tu dau
        confirmed["names"] = ""
        reset_warning.visible = False
        save_button.content = get_string("save_changes")
        disarm_full_reset()
        disarm_template()
        auto_reset()
        page.update()

    def reset_ticked(e: object) -> None:
        reset_manual["on"] = True  # chu da tu chon: khong tu tick / bo tick nua
        sync(e)

    mode_group.on_change = sync
    post_profile.on_select = sync
    chief_dropdown.on_select = sync
    reset_box.on_change = reset_ticked
    for box in member_boxes.values():
        box.on_change = sync

    # Reset doi: moi thiet lap ve mac dinh + bot xoa du lieu Muse cua chi huy va ca doi. Bam lan 1 hien canh
    # bao (nut doi thanh mau do), bam lan 2 moi reset; doi bat ky lua chon nao thi phai bam lai tu dau.
    full_armed = {"names": None}
    full_warning = ft.Text("", size=12.5, color=COLORS["error"], visible=False)

    def reset_names() -> list[str]:
        lead = chief_dropdown.value or ""
        team = ([lead] if lead else []) + [
            n for n in profile_names if n != lead and member_boxes[n].value
        ]
        # chi Muse bot dang chay (co topic); bot chua chay lan nao thi lay ca doi
        return [n for n in team if n in cfg.muse_profiles] if cfg.muse_profiles else team

    def disarm_full_reset() -> None:
        full_armed["names"] = None
        full_warning.visible = False
        full_reset_button.content = get_string("team_full_reset")
        full_reset_button.style = OUTLINE_STYLE

    def on_full_reset(_: ft.ControlEvent) -> None:
        targets = reset_names()
        names = ", ".join(targets) or get_string("team_full_reset_none")
        if full_armed["names"] != names:
            full_armed["names"] = names
            full_warning.value = get_string("team_full_reset_confirm", names=names)
            full_warning.visible = True
            full_reset_button.content = get_string("team_full_reset_go")
            full_reset_button.style = ERROR_STYLE
            page.update()
            return
        try:
            muse_team.reset(targets)
        except muse_team.MuseTeamError as e:
            error.value = str(e)
            error.visible = True
            disarm_full_reset()
            page.update()
            return
        done = get_string("team_full_reset_done", names=names)
        log(done)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(done)))

    full_reset_button = ft.Button(
        get_string("team_full_reset"),
        icon=ft.Icons.RESTART_ALT,
        style=OUTLINE_STYLE,
        tooltip=get_string("team_full_reset_hint"),
        on_click=on_full_reset,
    )

    def on_save(_: ft.ControlEvent) -> None:
        error.visible = False
        mode = mode_group.value or "solo"
        if mode == "chief" and not chief_dropdown.value:
            error.value = get_string("team_chief_missing")
            error.visible = True
            page.update()
            return
        roles = {n: f.value or "" for n, f in role_fields.items()}
        excluded = [n for n, box in member_boxes.items() if not box.value]
        others = [n for n in profile_names if n != chief_dropdown.value]
        if mode == "chief" and others and all(n in excluded for n in others):
            error.value = get_string("team_no_members")
            error.visible = True
            page.update()
            return
        params: dict[str, object] = {}
        for key, (label, _) in number_specs.items():
            raw = (number_fields[key].value or "").strip()
            lo, hi = muse_team.LIMITS[key]
            try:
                value = int(raw)
            except ValueError:
                value = None
            if value is None or not lo <= value <= hi:
                if mode != "chief":
                    continue
                error.value = get_string(
                    "team_number_error", label=get_string(label), lo=lo, hi=hi
                )
                error.visible = True
                page.update()
                return
            params[key] = value
        setup = {
            n: {"lang": (p["lang"].value or "").strip("-"), "context": (p["context"].value or "").strip()}
            for n, p in setups.items()
        }
        for n, item in setup.items():
            if len(item["context"]) > muse_team.MAX_CONTEXT:
                error.value = get_string("team_setup_too_long", name=n, max=muse_team.MAX_CONTEXT)
                error.visible = True
                page.update()
                return
        params["one_video"] = bool(one_video_box.value)
        params["show_failed_media"] = bool(show_failed_box.value)
        wipe = mode == "chief" and bool(reset_box.value)
        targets, full = reset_plan()
        if wipe:
            team = targets or [chief_dropdown.value or ""] + [
                n for n in others if member_boxes[n].value
            ]
            names = ", ".join(team)
            if confirmed["names"] != names:  # bam Luu lan 1: hien canh bao, lan 2 moi xoa
                confirmed["names"] = names
                reset_warning.value = get_string("team_reset_confirm", names=names) + (
                    " " + get_string("team_reset_template") if full else ""
                )
                reset_warning.visible = True
                save_button.content = get_string("team_reset_go")
                page.update()
                return
        try:
            muse_team.save(
                mode,
                chief_dropdown.value,
                approval_group.value or "manual",
                roles,
                excluded,
                params,
                wipe,
                setup,
                (task_lang.value or "").strip("-"),
                post_group.value or "ask",
                "" if (post_profile.value or "-") == "-" else post_profile.value,
                targets if wipe else None,
                wipe and full,
            )
        except muse_team.MuseTeamError as e:
            error.value = str(e)
            error.visible = True
            page.update()
            return
        done = get_string("team_saved_reset" if wipe else "team_saved")
        log(done)
        page.pop_dialog()
        page.show_dialog(ft.SnackBar(ft.Text(done)))

    save_button = ft.Button(
        get_string("save_changes"), icon=ft.Icons.SAVE, style=ACCENT_STYLE, on_click=on_save
    )
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
                    get_string("team_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    get_string("team_sub", path=cfg.file),
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
                controls=[
                    section(get_string("team_mode_label"), mode_group),
                    chief_part,
                    error,
                ],
            ),
        ),
        actions=[
            ft.Column(
                spacing=8,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    full_warning,
                    ft.Row(
                        controls=[
                            full_reset_button,
                            ft.Container(expand=True),
                            ft.TextButton(
                                get_string("cancel"),
                                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                                on_click=lambda _: page.pop_dialog(),
                            ),
                            save_button,
                        ],
                    ),
                ],
            ),
        ],
    )
    page.show_dialog(dlg)
    sync()
