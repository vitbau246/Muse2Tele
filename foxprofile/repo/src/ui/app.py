import asyncio
import os
import threading
import time

import flet as ft

from ..core import app_update, muse_team, post_map
from ..core.config import DATA_DIR
from ..core.container import Container
from ..core.logging import get_logger
from ..core.strings import current_language, get_string, set_language
from ..interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from ..services.browser import fingerprint
from .components import (
    build_content_area,
    build_empty_state,
    build_profile_card,
    build_sidebar,
    build_ui_refs,
    rebuild_bulk_bar,
)
from .components.profile_card import build_header_row
from .components.sidebar import build_filter_buttons
from .components.update_banner import build_update_banner
from .dialogs.mcp_guide import open_mcp_guide
from .dialogs.muse_team import open_muse_team_dialog
from .dialogs.post_map import open_post_map_dialog
from .dialogs.update import open_update_dialog
from .dialogs.upload_dirs import open_upload_dirs_dialog
from .handlers import AppHandlers
from .refs import UIRefs
from .state import ITEMS_PER_PAGE, AppState
from .theme import COLORS, configure_page
from .theme.colors import FONT_SEMIBOLD
from .theme.page import ASSETS_DIR

logger = get_logger("app")


class App:
    def __init__(self, container: Container | None = None) -> None:
        c = container or Container()
        self.pm: IProfileManager = c.profile_manager
        self.bl: IBrowserLauncher = c.browser_launcher
        self.ps: IProxyService = c.proxy_service
        self.state = AppState()
        self.page: ft.Page | None = None
        self._reconcile_started = False
        self.refs: UIRefs | None = None
        self.filter = "all"
        self._live_since: dict[str, str] = {}
        self._filter_column = ft.Column(spacing=2)
        self._header_slot = ft.Container()
        self._notice_slot = ft.Container()
        self._update_info: dict | None = None
        self._update_dismissed = False
        self._update_started = False
        c.event_bus.subscribe(self.state.schedule_refresh)
        self.h = AppHandlers(
            pm=self.pm,
            bl=self.bl,
            ps=self.ps,
            state=self.state,
            get_page=lambda: self.page,
            get_refs=lambda: self.refs,
            log_fn=self._log,
            refresh_fn=self._refresh_profiles,
            get_page_profiles=self._get_page_profiles,
        )

    def run(self) -> None:
        ft.run(self._main, assets_dir=ASSETS_DIR)

    def _main(self, page: ft.Page) -> None:
        self.page = page
        configure_page(page)
        fp = ft.FilePicker()
        page.services.append(fp)
        self.clipboard = ft.Clipboard()
        page.services.append(self.clipboard)
        self._file_picker = fp
        self._build_ui()
        self.state._last_running_snapshot = self.bl.running_profile_names()
        if not self._reconcile_started:
            self._reconcile_started = True
            page.run_task(self._ui_reconcile_loop)
        if not self._update_started and app_update.root() is not None:
            self._update_started = True
            threading.Thread(target=self._update_loop, daemon=True).start()

    def _build_ui(self) -> None:
        """(Re)build every control; strings are read at build time."""
        assert self.page is not None
        self.refs = build_ui_refs(
            pm=self.pm,
            on_change_page=self._change_page,
            file_picker=self._file_picker,
            on_search=self._on_search,
        )
        self._filter_column = ft.Column(spacing=2)
        self._header_slot = ft.Container()
        self._notice_slot = ft.Container()
        self.page.title = get_string("window_title")
        self.page.controls.clear()
        self.page.add(self._build_root_layout(self.refs))
        self._restore_log()
        self._refresh_profiles()

    def _restore_log(self) -> None:
        """Refill a freshly built log pane (flush_log only returns new lines)."""
        r = self.refs
        assert r is not None
        lines = self.state.get_all_log_lines()[-6:]
        r.log_text.value = "\n".join(lines)
        r.log_column.height = max(72, len(lines) * 18 + 20)
        r.log_column.visible = bool(lines) and not self.state.log_collapsed
        r.log_toggle_btn.icon = (
            ft.Icons.KEYBOARD_ARROW_RIGHT
            if self.state.log_collapsed
            else ft.Icons.KEYBOARD_ARROW_DOWN
        )

    def _set_language(self, code: str) -> None:
        if code == current_language():
            return
        set_language(code)
        self.state.search_query = ""
        self._build_ui()

    def _build_root_layout(self, r: UIRefs) -> ft.Row:
        sidebar = build_sidebar(
            r.stats_text,
            r.running_text,
            r.log_text,
            r.log_column,
            r.log_toggle_btn,
            on_new_profile=lambda _: self.h.open_add_dialog(),
            on_import=self.h.on_import,
            on_export=lambda _: self.h.on_export_open(),
            on_mcp=lambda _: open_mcp_guide(self.page, self.clipboard),
            on_toggle_log=lambda _: self.h.toggle_log(),
            on_fullscreen_log=lambda _: self.h.open_log_fullscreen(),
            filter_column=self._filter_column,
            language=current_language(),
            on_language=self._set_language,
            on_upload_dirs=lambda _: open_upload_dirs_dialog(
                self.page, self._file_picker, self._log
            ),
            on_check_update=(lambda _: self._check_update_now())
            if app_update.root() is not None
            else None,
            on_team=(
                lambda _: open_muse_team_dialog(
                    self.page, [p.name for p in self.pm.list_profiles()], self._log
                )
            )
            if muse_team.current().bot_installed
            else None,
            on_post_map=(
                lambda _: open_post_map_dialog(self.page, self.pm.list_profiles(), self._log)
            )
            if post_map.current().installed
            else None,
        )
        content = build_content_area(
            r.content_subtitle,
            r.profile_list_area,
            r.prev_btn,
            r.next_btn,
            r.page_label,
            r.bulk_bar,
            r.search_field,
            header_slot=self._header_slot,
            notice_slot=self._notice_slot,
        )
        return ft.Row(
            expand=True,
            spacing=0,
            controls=[
                sidebar,
                content,
            ],
        )

    def _on_search(self, query: str) -> None:
        self.state.search_query = query.strip().lower()
        self.state.current_page = 1
        self._refresh_profiles()

    def _on_filter(self, fid: str) -> None:
        self.filter = fid
        self.state.current_page = 1
        self._refresh_profiles()

    def _filter_tests(self) -> dict:
        return {
            "all": lambda p: True,
            "running": lambda p: self.bl.is_running(p.name),
            "proxy": lambda p: bool(p.proxy),
            "direct": lambda p: not p.proxy,
            "chrome": lambda p: p.engine == "chrome",
        }

    def _get_page_profiles(self) -> tuple[list, list, int]:
        all_profiles = self.pm.list_profiles()
        test = self._filter_tests().get(self.filter, lambda p: True)
        all_profiles = [p for p in all_profiles if test(p)]
        if q := self.state.search_query:
            all_profiles = [
                p for p in all_profiles if q in p.name.lower() or q in (p.proxy or "").lower()
            ]
        total = max(1, (len(all_profiles) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        self.state.current_page = min(self.state.current_page, total)
        start = (self.state.current_page - 1) * ITEMS_PER_PAGE
        return all_profiles, all_profiles[start : start + ITEMS_PER_PAGE], total

    def _refresh_profiles(self) -> None:
        r = self.refs
        assert r is not None
        self._update_stats()
        self._flush_log()
        all_profiles, page_profiles, total_pages = self._get_page_profiles()

        all_names = set(self.pm.profiles)
        for stale in self.state.selected_names() - all_names:
            self.state.toggle_selection(stale)

        running = self.bl.running_profile_names()
        # A failure mark lasts until the profile runs again or is gone.
        self.state.failed.intersection_update(all_names - running)
        for name in running - set(self._live_since):
            self._live_since[name] = time.strftime("%H:%M")
        for name in set(self._live_since) - running:
            del self._live_since[name]

        everything = self.pm.list_profiles()
        tests = self._filter_tests()
        self._filter_column.controls = build_filter_buttons(
            self.filter,
            {fid: sum(1 for p in everything if test(p)) for fid, test in tests.items()},
            self._on_filter,
        )
        names = [p.name for p in page_profiles]
        all_sel = bool(names) and all(self.state.is_selected(n) for n in names)
        any_sel = any(self.state.is_selected(n) for n in names)
        self._header_slot.content = (
            build_header_row(
                all_sel,
                any_sel,
                lambda select: self.h.on_select_all_page() if select else self.h.on_deselect_page(),
            )
            if page_profiles
            else None
        )

        r.profile_list_area.controls = (
            [
                build_profile_card(
                    p,
                    self.state.is_loading(p.name),
                    self.bl.is_running(p.name),
                    self.h.on_launch,
                    self.h.on_edit,
                    self.h.on_delete,
                    is_selected=self.state.is_selected(p.name),
                    on_select=self.h.on_toggle_select,
                    on_cookies=self.h.on_cookies,
                    on_clone=self.h.on_clone,
                    device=self._device_label(p.name),
                    since=self._live_since.get(p.name, ""),
                    failed=p.name in self.state.failed,
                )
                for p in page_profiles
            ]
            if page_profiles
            else [self._build_empty_or_no_results()]
        )
        self._notice_slot.content = build_update_banner(
            self._update_info,
            self._open_update_dialog,
            self._dismiss_update,
            self._update_dismissed,
        )
        rebuild_bulk_bar(
            r.bulk_bar,
            self.state,
            page_profiles,
            {
                "launch": self.h.on_bulk_launch,
                "stop": self.h.on_bulk_stop,
                "delete": self.h.on_bulk_delete,
                "select_page": self.h.on_select_all_page,
                "deselect_page": self.h.on_deselect_page,
                "clear": self.h.on_clear_selection,
            },
        )
        self._set_subtitle(r.content_subtitle)
        r.page_label.value = get_string(
            "page_of",
            current=self.state.current_page,
            total=total_pages,
        )
        r.prev_btn.disabled = self.state.current_page <= 1
        r.next_btn.disabled = self.state.current_page >= total_pages
        self._safe_update()

    # -- Muse2Tele self-update --

    def _update_loop(self) -> None:
        """Check GitHub soon after start, then every 6 h; poll quickly while an update runs."""
        time.sleep(4)
        last_check = 0.0
        while self.page:
            busy = bool(self._update_info and self._update_info.get("busy"))
            if busy or time.time() - last_check >= 6 * 3600:
                try:
                    self._update_info = app_update.status(force=not busy and last_check > 0)
                except Exception as e:
                    logger.warning("Update check failed: %s", e)
                last_check = time.time() if not busy else last_check
                self.state.schedule_refresh()
            time.sleep(3 if busy else 60)

    def _check_update_now(self) -> None:
        self._snack(get_string("update_checking"))

        def work() -> None:
            info = app_update.status(force=True)
            self._update_info = info
            self.state.schedule_refresh()
            if info.get("available"):
                self._open_update_dialog()
            elif info.get("error"):
                self._snack(get_string("update_check_error", error=info["error"]))
            else:
                self._snack(get_string("update_latest"))

        threading.Thread(target=work, daemon=True).start()

    def _open_update_dialog(self) -> None:
        if not self.page or not self._update_info:
            return

        def confirm() -> str | None:
            try:
                app_update.apply()
            except RuntimeError as e:
                return str(e)
            self._log(get_string("update_started"))
            self._update_info = {**(self._update_info or {}), "busy": True, "available": False,
                                 "last_update": app_update.last_update()}
            self.state.schedule_refresh()
            self._snack(get_string("update_started"))
            return None

        open_update_dialog(self.page, self._update_info, confirm)

    def _dismiss_update(self) -> None:
        self._update_dismissed = True
        self._refresh_profiles()

    def _snack(self, text: str) -> None:
        if self.page:
            try:
                self.page.show_dialog(ft.SnackBar(ft.Text(text)))
            except Exception as e:
                logger.warning("Snack failed: %s", e)

    @staticmethod
    def _device_label(name: str) -> str:
        info = fingerprint.summary(os.path.join(DATA_DIR, name))
        if not info:
            return ""
        cpu = f"{info['hardware_concurrency']} CPU"
        return f"{info['screen']} · {cpu}" if info.get("screen") else cpu

    def _build_empty_or_no_results(self) -> ft.Control:
        if self.pm.profiles:
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=56, horizontal=24),
                alignment=ft.Alignment(0, 0),
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    controls=[
                        ft.Text(
                            get_string("no_search_results", query=self.state.search_query)
                            if self.state.search_query
                            else get_string("no_filter_results"),
                            size=14,
                            color=COLORS["text_sub"],
                        ),
                        ft.OutlinedButton(
                            get_string("clear_filters"),
                            on_click=lambda _: self._clear_filters(),
                        ),
                    ],
                ),
            )
        return build_empty_state(lambda _: self.h.open_add_dialog())

    def _clear_filters(self) -> None:
        self.filter = "all"
        self.state.search_query = ""
        if self.refs and self.refs.search_field is not None:
            self.refs.search_field.value = ""
        self._refresh_profiles()

    def _change_page(self, delta: int) -> None:
        self.state.current_page += delta
        self._refresh_profiles()

    def _set_subtitle(self, text: ft.Text) -> None:
        """ "10 profile · 2 đang chạy", the running count in stamp violet."""
        c, r = len(self.pm.profiles), self.bl.running_count()
        head = get_string("profiles_configured", count=c) + " · "
        text.value = None
        text.spans = (
            [
                ft.TextSpan(head),
                ft.TextSpan(str(r), ft.TextStyle(color=COLORS["live"], font_family=FONT_SEMIBOLD)),
                ft.TextSpan(" " + get_string("profiles_running_suffix")),
            ]
            if r
            else [ft.TextSpan(head + get_string("profiles_none_running"))]
        )

    def _update_stats(self) -> None:
        r = self.refs
        if r:
            cnt = self.bl.running_count()
            r.stats_text.value = get_string(
                "total_profiles",
                count=len(self.pm.profiles),
            )
            r.running_text.value = (
                get_string("browsers_running", count=cnt)
                if cnt
                else get_string("no_active_sessions")
            )

    def _log(self, message: str) -> None:
        logger.info(message)
        if self.state.add_log(message):
            self.state.schedule_refresh()

    def _flush_log(self) -> None:
        text = self.state.flush_log()
        if text is not None and self.refs:
            lines = text.split("\n")
            sidebar_lines = lines[-6:]
            self.refs.log_text.value = "\n".join(sidebar_lines)
            self.refs.log_column.height = max(72, len(sidebar_lines) * 18 + 20)
            self.refs.log_column.visible = bool(sidebar_lines) and not self.state.log_collapsed

    def _safe_update(self) -> None:
        if not self.page:
            return
        try:
            with self.state._ui_update_lock:
                self.page.update()
        except Exception as e:
            logger.error("Error updating UI: %s", e)

    async def _ui_reconcile_loop(self) -> None:
        while self.page:
            try:
                running_now = self.bl.running_profile_names()
                changed = running_now != self.state._last_running_snapshot
                if changed:
                    self.state._last_running_snapshot = running_now
                if changed or self.state.consume_refresh():
                    self._refresh_profiles()
            except Exception as e:
                logger.error("Error in UI reconcile loop: %s", e)
            await asyncio.sleep(0.12)
