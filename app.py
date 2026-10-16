#!/usr/bin/env python3
"""Standalone GTK application for browsing and managing Omarchy plugins."""

from __future__ import annotations

import shutil
import subprocess
import threading
import urllib.error
import urllib.request

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

from store_model import (
    CATALOG_URL,
    MAX_CATALOG_BYTES,
    CatalogError,
    Plugin,
    enable_args,
    github_repository,
    install_args,
    installed_map,
    parse_catalog,
    remove_args,
    search_plugins,
)


SECURITY_NOTICE = (
    "Third-party plugins run unsandboxed with your user permissions. "
    "Marketplace verification is not a security audit. Omarchy installs the "
    "repository's current GitHub HEAD, not a verified commit. Review source "
    "and dependencies before installing."
)


class PluginItem(GObject.Object):
    def __init__(self, plugin: Plugin):
        super().__init__()
        self.plugin = plugin


def fetch_catalog() -> tuple[list[Plugin], str]:
    request = urllib.request.Request(
        CATALOG_URL,
        headers={"Accept": "application/json", "User-Agent": "OmarchyStore/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            if response.geturl() != CATALOG_URL:
                raise CatalogError("Marketplace redirected away from its catalog URL")
            raw = response.read(MAX_CATALOG_BYTES + 1)
    except urllib.error.URLError as error:
        raise CatalogError(f"Could not reach plugins.omarchy.org: {error}") from error
    if len(raw) > MAX_CATALOG_BYTES:
        raise CatalogError("Marketplace catalog exceeded the 24 MiB size limit")
    return parse_catalog(raw)


class StoreWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application):
        super().__init__(application=application, title="Omarchy Store")
        self.set_default_size(1120, 780)
        self.set_size_request(760, 560)

        self.plugins: list[Plugin] = []
        self.installed: dict[str, dict[str, bool]] = {}
        self.catalog_ready = False
        self.installed_ready = False
        self.catalog_loading = False
        self.installed_loading = False
        self.busy = False
        self.filter_mode = "all"

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(root)

        header = Adw.HeaderBar()
        title = Gtk.Label(label="Omarchy Store")
        title.add_css_class("title")
        header.set_title_widget(title)
        refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh marketplace and installed plugins")
        refresh_button.connect("clicked", self._refresh)
        self.refresh_button = refresh_button
        header.pack_end(refresh_button)
        root.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(16)
        content.set_margin_end(16)
        root.append(content)

        warning = Gtk.Label(label=SECURITY_NOTICE)
        warning.set_xalign(0)
        warning.set_wrap(True)
        warning.set_selectable(True)
        warning.add_css_class("warning")
        warning.add_css_class("card")
        content.append(warning)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.append(controls)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search name, author, category, tag, or plugin ID")
        self.search.connect("search-changed", self._filter_changed)
        controls.append(self.search)

        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.append(filter_row)
        self.filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for index, (mode, label) in enumerate((
            ("all", "All"), ("installable", "Installable"), ("installed", "Installed")
        )):
            button = Gtk.ToggleButton(label=label)
            if index:
                button.set_group(self.filter_buttons["all"])
            button.connect("toggled", self._filter_mode_changed, mode)
            filter_row.append(button)
            self.filter_buttons[mode] = button
        self.status = Gtk.Label(label="Loading marketplace and installed plugins…")
        self.status.set_xalign(0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.add_css_class("dim-label")
        content.append(self.status)

        self.store = Gio.ListStore.new(PluginItem)
        self.custom_filter = Gtk.CustomFilter.new(self._matches_filter)
        self.filtered_store = Gtk.FilterListModel.new(self.store, self.custom_filter)
        self.selection = Gtk.SingleSelection.new(self.filtered_store)
        self.selection.set_autoselect(True)
        self.selection.connect("notify::selected-item", self._selection_changed)
        self.filter_buttons["all"].set_active(True)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_list_row)
        factory.connect("bind", self._bind_list_row)
        self.list_view = Gtk.ListView.new(self.selection, factory)
        self.list_view.add_css_class("navigation-sidebar")
        self.list_view.set_single_click_activate(False)

        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroll.set_min_content_width(335)
        list_scroll.set_child(self.list_view)

        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.details.set_margin_top(18)
        self.details.set_margin_bottom(18)
        self.details.set_margin_start(20)
        self.details.set_margin_end(20)
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        detail_scroll.set_child(self.details)

        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        panes.set_wide_handle(True)
        panes.set_start_child(list_scroll)
        panes.set_end_child(detail_scroll)
        panes.set_position(370)
        panes.set_resize_start_child(False)
        panes.set_shrink_start_child(False)
        panes.set_shrink_end_child(False)
        content.append(panes)

        self._refresh(None)

    def _refresh(self, _button) -> None:
        if self.catalog_loading or self.installed_loading or self.busy:
            return
        self.catalog_loading = True
        self.refresh_button.set_sensitive(False)
        self.status.set_text("Refreshing marketplace and installed plugins…")
        threading.Thread(target=self._catalog_worker, daemon=True).start()
        self._refresh_installed()

    def _refresh_installed(self) -> None:
        if self.installed_loading:
            return
        self.installed_loading = True
        self._update_refresh_button()
        threading.Thread(target=self._installed_worker, daemon=True).start()

    def _catalog_worker(self) -> None:
        try:
            result = fetch_catalog()
            GLib.idle_add(self._catalog_loaded, result, None)
        except Exception as error:  # deliver worker exceptions to the GTK thread
            GLib.idle_add(self._catalog_loaded, None, str(error))

    def _catalog_loaded(self, result, error) -> bool:
        self.catalog_loading = False
        self._update_refresh_button()
        if error:
            self.status.set_text(f"Catalog unavailable: {error}")
            return GLib.SOURCE_REMOVE
        self.plugins, generated_at = result
        self.catalog_ready = True
        items = [PluginItem(plugin) for plugin in self.plugins]
        self.store.splice(0, self.store.get_n_items(), items)
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
        suffix = f" · catalog updated {generated_at[:10]}" if generated_at else ""
        self.status.set_text(f"{len(self.plugins):,} community plugins{suffix}")
        return GLib.SOURCE_REMOVE

    def _installed_worker(self) -> None:
        try:
            if not shutil.which("omarchy"):
                raise CatalogError("Omarchy's `omarchy` CLI is not on PATH")
            result = subprocess.run(
                ["omarchy", "plugin", "list", "--json"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            parsed = installed_map(result.stdout)
            GLib.idle_add(self._installed_loaded, parsed, None)
        except (OSError, subprocess.SubprocessError, CatalogError) as error:
            GLib.idle_add(self._installed_loaded, None, str(error))

    def _installed_loaded(self, result, error) -> bool:
        self.installed_loading = False
        self._update_refresh_button()
        if error:
            self.installed_ready = False
            self.installed = {}
            self.status.set_text(f"Installed-plugin state unavailable: {error}")
            self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
            self._selection_changed(self.selection, None)
        else:
            self.installed = result
            self.installed_ready = True
            self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
            self._selection_changed(self.selection, None)
        self.filter_buttons["installed"].set_sensitive(self.installed_ready)
        return GLib.SOURCE_REMOVE

    def _update_refresh_button(self) -> None:
        self.refresh_button.set_sensitive(
            not self.catalog_loading and not self.installed_loading and not self.busy
        )

    def _setup_list_row(self, _factory, list_item) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(10)
        title = Gtk.Label()
        title.set_xalign(0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.add_css_class("heading")
        meta = Gtk.Label()
        meta.set_xalign(0)
        meta.set_ellipsize(Pango.EllipsizeMode.END)
        meta.add_css_class("dim-label")
        box.append(title)
        box.append(meta)
        list_item.set_child(box)

    def _bind_list_row(self, _factory, list_item) -> None:
        item = list_item.get_item()
        if item is None:
            return
        plugin = item.plugin
        box = list_item.get_child()
        title = box.get_first_child()
        meta = title.get_next_sibling()
        title.set_text(plugin.name)
        installed = self.installed.get(plugin.id)
        install_status = "Installed · " if installed else ""
        availability = "Installable" if plugin.install_available else "Source only"
        meta.set_text(f"{install_status}{plugin.category} · {availability} · {plugin.author}")

    def _matches_filter(self, item) -> bool:
        if item is None:
            return False
        return bool(search_plugins(
            [item.plugin], self.search.get_text(), self.installed, self.filter_mode
        ))

    def _filter_changed(self, _entry) -> None:
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)

    def _filter_mode_changed(self, button, mode: str) -> None:
        if not button.get_active():
            return
        self.filter_mode = mode
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)

    def _selection_changed(self, _selection, _parameter) -> None:
        selected = self.selection.get_selected_item()
        self._show_plugin(selected.plugin if selected else None)

    @staticmethod
    def _clear_box(box: Gtk.Box) -> None:
        child = box.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            box.remove(child)
            child = following

    def _label(self, text: str, css_class: str | None = None) -> Gtk.Label:
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        label.set_wrap(True)
        label.set_selectable(True)
        if css_class:
            label.add_css_class(css_class)
        return label

    def _show_plugin(self, plugin: Plugin | None) -> None:
        self._clear_box(self.details)
        if plugin is None:
            self.details.append(self._label("Select a plugin to view details."))
            return

        self.details.append(self._label(plugin.name, "title-1"))
        self.details.append(self._label(
            f"{plugin.id} · {plugin.version} · by {plugin.author}", "dim-label"
        ))
        self.details.append(self._label(plugin.description))
        metadata = (
            f"Category: {plugin.category}"
            + (f" · Type: {plugin.kind}" if plugin.kind else "")
            + f"\nLicense: {plugin.license}"
            + f"\nTags: {', '.join(plugin.tags) if plugin.tags else 'None'}"
        )
        self.details.append(self._label(metadata, "dim-label"))

        if plugin.verification_status == "verified":
            verification = (
                "Marketplace status: verified listing. Verification applies to a "
                "listed snapshot; the current upstream install may differ."
            )
            if plugin.verification_coverage == "update-unverified":
                verification += " Current upstream changes are unverified."
        else:
            verification = (
                "Marketplace status: unverified. No current verification record "
                "is available for the listed snapshot."
            )
        if plugin.upstream_status == "failed":
            verification += " Compatibility checks failed; automatic installation is disabled."
        self.details.append(self._label(verification, "dim-label"))

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        source = Gtk.Button(label="View source ↗")
        source.connect("clicked", self._open_source, plugin)
        action_row.append(source)

        installed = self.installed.get(plugin.id) if self.installed_ready else None
        if installed is not None:
            state_text = "Installed and enabled" if installed["enabled"] else "Installed but disabled"
            self.details.append(self._label(state_text, "dim-label"))
        if not self.installed_ready:
            source.set_sensitive(True)
        elif installed is None and plugin.install_available:
            install = Gtk.Button(label="Install & enable")
            install.add_css_class("suggested-action")
            install.set_sensitive(not self.busy)
            install.connect("clicked", self._ask_to_install, plugin)
            action_row.append(install)
        elif installed is not None and not installed["enabled"] and not installed["firstParty"]:
            enable = Gtk.Button(label="Enable (runs code)")
            enable.add_css_class("suggested-action")
            enable.set_sensitive(not self.busy)
            enable.connect("clicked", self._ask_to_enable, plugin)
            action_row.append(enable)

        if installed is not None and not installed["firstParty"]:
            remove = Gtk.Button(label="Remove")
            remove.add_css_class("destructive-action")
            remove.set_sensitive(not self.busy)
            remove.connect("clicked", self._ask_to_remove, plugin)
            action_row.append(remove)
        elif installed is not None:
            action_row.append(self._label("Included with Omarchy"))
        elif not self.installed_ready:
            action_row.append(self._label("Installed state unavailable", "dim-label"))
        elif not plugin.install_available:
            action_row.append(self._label(
                plugin.install_note or "Automatic installation is unavailable for this repository layout.",
                "dim-label",
            ))
        self.details.append(action_row)

        self.details.append(self._label(
            "Repository: " + plugin.repo_url.removesuffix(".git"), "dim-label"
        ))

    def _open_source(self, _button, plugin: Plugin) -> None:
        uri = github_repository(plugin.repo_url)
        if not uri:
            self.status.set_text("The repository URL failed validation.")
            return
        try:
            Gio.AppInfo.launch_default_for_uri(uri.removesuffix(".git"), None)
        except GLib.Error as error:
            self.status.set_text(f"Could not open the repository: {error.message}")

    def _ask_to_install(self, _button, plugin: Plugin) -> None:
        self._confirm_action(
            "Install and enable plugin?",
            f"Install {plugin.name} from {plugin.repo_url.removesuffix('.git')} at its current GitHub HEAD, then enable it?\n\n"
            "This runs third-party code unsandboxed with your user permissions. The install is not pinned to the marketplace-checked or verified commit. Review the source and dependencies first.",
            "Install & enable",
            "install",
            plugin,
        )

    def _ask_to_enable(self, _button, plugin: Plugin) -> None:
        self._confirm_action(
            "Enable plugin?",
            f"Enable {plugin.name}? Its installed code will run unsandboxed with your user permissions. Review its files first.",
            "Enable",
            "enable",
            plugin,
        )

    def _ask_to_remove(self, _button, plugin: Plugin) -> None:
        self._confirm_action(
            "Remove plugin?",
            f"Remove {plugin.name}? Omarchy will disable it and remove its plugin checkout. Data the plugin stored separately is not included.",
            "Remove",
            "remove",
            plugin,
        )

    def _confirm_action(self, title: str, body: str, confirm: str, operation: str, plugin: Plugin) -> None:
        dialog = Adw.AlertDialog.new(title, body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("accept", confirm)
        dialog.set_response_appearance(
            "accept",
            Adw.ResponseAppearance.DESTRUCTIVE
            if operation == "remove"
            else Adw.ResponseAppearance.SUGGESTED,
        )
        dialog.set_close_response("cancel")
        dialog.set_default_response("cancel")
        dialog.choose(self, None, self._confirmation_chosen, (operation, plugin))

    def _confirmation_chosen(self, dialog, result, user_data) -> None:
        operation, plugin = user_data
        response = dialog.choose_finish(result)
        if response != "accept":
            return
        args = {
            "install": install_args,
            "enable": enable_args,
            "remove": remove_args,
        }[operation](plugin)
        if not args:
            self.status.set_text("This plugin is not eligible for that operation.")
            return
        if not shutil.which("omarchy"):
            self.status.set_text("Omarchy's `omarchy` CLI is not on PATH.")
            return
        self.busy = True
        self._update_refresh_button()
        self._show_plugin(plugin)
        self.status.set_text(f"Running Omarchy plugin {operation}…")
        threading.Thread(target=self._action_worker, args=(operation, args), daemon=True).start()

    def _action_worker(self, operation: str, args: list[str]) -> None:
        try:
            completed = subprocess.run(
                ["omarchy", *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            output = (completed.stderr or completed.stdout or "").strip()[:1000]
            result = (completed.returncode, output)
        except (OSError, subprocess.SubprocessError) as error:
            result = (1, str(error)[:1000])
        GLib.idle_add(self._action_finished, operation, result)

    def _action_finished(self, operation: str, result: tuple[int, str]) -> bool:
        self.busy = False
        exit_code, output = result
        if exit_code == 0:
            self.status.set_text(f"Plugin {operation} completed.")
        else:
            detail = f" — {output}" if output else ""
            self.status.set_text(
                f"Plugin {operation} failed (exit {exit_code}).{detail}"
            )
        self._refresh_installed()
        selected = self.selection.get_selected_item()
        self._show_plugin(selected.plugin if selected else None)
        return GLib.SOURCE_REMOVE


class StoreApplication(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="org.omarchy.Store",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = StoreWindow(self)
        self.window.present()


def main() -> int:
    Adw.init()
    app = StoreApplication()
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
