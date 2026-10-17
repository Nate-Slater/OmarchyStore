#!/usr/bin/env python3
"""Standalone GTK application for browsing and managing Omarchy plugins."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import shutil
import subprocess
import sys
import threading
import re
import tomllib
import urllib.parse
import urllib.error
import urllib.request
import weakref
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from store_model import (
    CATALOG_URL,
    MAX_CATALOG_BYTES,
    CatalogError,
    Plugin,
    enable_args,
    github_repository,
    install_args,
    installed_map,
    listing_age,
    marketplace_preview_url,
    parse_catalog,
    recently_added,
    remove_args,
    search_plugins,
)


SECURITY_NOTICE = (
    "Third-party plugins run unsandboxed with your user permissions. "
    "Marketplace verification is not a security audit. Omarchy installs the "
    "repository's current GitHub HEAD, not a verified commit. Review source "
    "and dependencies before installing."
)
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
MAX_CACHED_PREVIEWS = 40


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler())

APP_CSS = """
window.store-window, .store-root { background: #000; color: #d7d7d9; }
headerbar.store-header { background: #0b0b0d; border-bottom: 1px solid #28282c; }
.header-brand { font-family: monospace; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
.header-brand .brand-mark { color: #ff5a36; }
.theme-pill { border: 1px solid #3a3a3f; border-radius: 4px; padding: 3px 7px; color: #ff5a36; font-family: monospace; font-size: 8px; font-weight: 700; }
.store-content { background: #000; }
.hero-panel { background: #0b0b0d; border: 1px solid #28282c; border-radius: 10px; padding: 22px 26px; }
.eyebrow { color: #ff5a36; font-family: monospace; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
.hero-title { color: #eee; font-family: monospace; font-size: 30px; font-weight: 800; }
.hero-copy { color: #aaaab0; font-size: 13px; }
.hero-count { color: #eee; font-family: monospace; font-size: 27px; font-weight: 800; }
.hero-count-caption { color: #aaaab0; font-family: monospace; font-size: 9px; letter-spacing: 1px; }
.security-strip { background: #100c0b; border: 1px solid #40251f; border-radius: 6px; padding: 9px 12px; }
.security-icon { color: #ff5a36; font-family: monospace; font-weight: 800; }
.security-copy { color: #c4b8b5; font-size: 11px; }
entry.search-entry { min-height: 42px; border: 1px solid #3a3a3f; border-radius: 6px; background: #0b0b0d; color: #eee; }
entry.search-entry:focus-within { border-color: #ff5a36; box-shadow: 0 0 0 1px #ff5a36; }
button.mode-button { min-height: 31px; padding: 0 13px; border: 1px solid #28282c; border-radius: 5px; background: #0b0b0d; color: #aaaab0; font-family: monospace; font-size: 10px; }
button.mode-button:checked { border-color: #ff5a36; background: #ff5a36; color: #111; font-weight: 800; }
dropdown.category-filter > button { min-height: 32px; border: 1px solid #28282c; border-radius: 5px; background: #0b0b0d; color: #d7d7d9; font-family: monospace; font-size: 10px; }
.result-label { color: #7d7d84; font-family: monospace; font-size: 10px; letter-spacing: 1px; }
.catalog-scroll, .detail-scroll { background: transparent; }
gridview { background: transparent; }
gridview > child { padding: 5px; }
gridview > child:selected { background: transparent; }
.plugin-card { min-height: 198px; background: #0b0b0d; border: 1px solid #28282c; border-radius: 8px; padding: 14px; }
.plugin-card:hover { background: #101012; border-color: #4a4a50; }
.plugin-card.selected { background: #111012; border-color: #ff5a36; }
.plugin-mark { min-width: 42px; min-height: 42px; border: 1px solid #28282c; border-radius: 6px; background: #151416; font-family: monospace; font-size: 12px; font-weight: 800; }
.preview-frame { min-height: 98px; border: 1px solid #28282c; border-radius: 6px; background: #101012; }
.preview-placeholder { min-height: 98px; background: linear-gradient(135deg, #151416, #0b0b0d); }
.preview-placeholder label { font-family: monospace; font-size: 24px; font-weight: 800; }
.preview-image { min-height: 98px; }
.recent-section { background: transparent; }
.recent-heading { color: #aaaab0; font-family: monospace; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
.recent-summary { color: #7d7d84; font-family: monospace; font-size: 9px; }
button.carousel-arrow { min-width: 30px; min-height: 28px; border: 1px solid #28282c; border-radius: 5px; background: #0b0b0d; color: #aaaab0; }
button.carousel-arrow:hover { border-color: #ff5a36; color: #ff5a36; }
button.recent-card { min-width: 218px; border: 1px solid #28282c; border-radius: 7px; background: #0b0b0d; padding: 8px; }
button.recent-card:hover { border-color: #ff5a36; background: #101012; }
button.recent-card label.recent-name { color: #eee; font-size: 11px; font-weight: 750; }
button.recent-card label.recent-byline { color: #7d7d84; font-family: monospace; font-size: 8px; }
.plugin-title { color: #eee; font-size: 14px; font-weight: 750; }
.plugin-author { color: #7d7d84; font-family: monospace; font-size: 9px; }
.plugin-description { color: #aaaab0; font-size: 11px; }
.plugin-footer { color: #7d7d84; font-family: monospace; font-size: 9px; }
.plugin-badge { border: 1px solid #39393f; border-radius: 4px; padding: 3px 6px; color: #aaaab0; font-family: monospace; font-size: 8px; font-weight: 700; }
.plugin-badge.available { border-color: #553322; background: #21140e; color: #ff9b72; }
.plugin-badge.installed { border-color: #43522c; background: #151b10; color: #b4c96f; }
.details-panel { background: #0b0b0d; border: 1px solid #28282c; border-radius: 8px; padding: 19px; }
.detail-mark { min-width: 54px; min-height: 54px; border: 1px solid #39393f; border-radius: 8px; background: #151416; font-family: monospace; font-size: 17px; font-weight: 800; }
.detail-title { color: #eee; font-size: 22px; font-weight: 800; }
.detail-meta { color: #aaaab0; font-family: monospace; font-size: 10px; }
.detail-description { color: #d7d7d9; font-size: 13px; line-height: 1.5; }
.detail-section-label { color: #7d7d84; font-family: monospace; font-size: 9px; font-weight: 700; letter-spacing: 1px; }
.detail-info { color: #aaaab0; font-size: 11px; }
.detail-warning { background: #100c0b; border-left: 2px solid #ff5a36; padding: 10px; color: #c4b8b5; font-size: 10px; }
button.install-button { min-height: 36px; border: 1px solid #ff5a36; border-radius: 5px; background: #ff5a36; color: #111; font-family: monospace; font-size: 10px; font-weight: 800; }
button.install-button:hover { background: #ff7655; }
button.source-button { min-height: 34px; border: 1px solid #3a3a3f; border-radius: 5px; background: transparent; color: #d7d7d9; font-family: monospace; font-size: 10px; }
button.source-button:hover { border-color: #ff5a36; color: #ff795c; }
.empty-mark { color: #ff5a36; font-family: monospace; font-size: 34px; font-weight: 800; }
.accent-lime { color: #b7ef51; } .accent-violet { color: #a78bfa; }
.accent-amber { color: #f4bd62; } .accent-cyan { color: #68d6e8; }
.accent-coral { color: #f18c75; } .accent-blue { color: #74a7f7; }
.accent-mint { color: #69d4a7; } .accent-rose { color: #e896ba; }
label.dim-label { color: #7d7d84; }
button.flat.refresh-button { color: #aaaab0; }
button.flat.refresh-button:hover { color: #ff5a36; background: #171719; }
"""


THEME_COLORS = {
    "store_bg": "dark_background",
    "store_panel": "background",
    "store_panel_raised": "lighter_background",
    "store_line": "selection",
    "store_line_strong": "muted",
    "store_fg": "foreground",
    "store_heading": "bright_foreground",
    "store_muted": "dark_foreground",
    "store_faint": "muted",
    "store_accent": "accent",
    "store_accent_soft": "selection",
    "store_warning": "yellow",
    "store_stable": "green",
    "store_danger": "red",
}
THEME_COLOR_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
CSS_COLOR_TOKENS = {
    "#000": "store_bg", "#000000": "store_bg",
    "#0b0b0d": "store_panel", "#101012": "store_panel_raised",
    "#171719": "store_panel_raised",
    "#111012": "store_panel_raised", "#151416": "store_panel_raised",
    "#151b10": "store_panel_raised", "#28282c": "store_line",
    "#39393f": "store_line_strong", "#3a3a3f": "store_line_strong",
    "#4a4a50": "store_line_strong", "#d7d7d9": "store_fg",
    "#eee": "store_heading", "#eeeeee": "store_heading",
    "#aaaab0": "store_muted", "#c4b8b5": "store_muted",
    "#7d7d84": "store_faint", "#ff5a36": "store_accent",
    "#ff7655": "store_accent", "#ff795c": "store_accent",
    "#40251f": "store_accent_soft", "#553322": "store_accent_soft",
    "#21140e": "store_accent_soft", "#f4bd62": "store_warning",
    "#b4c96f": "store_stable", "#43522c": "store_stable",
    "#ff9b72": "store_accent", "#100c0b": "store_panel_raised",
    "#111": "store_bg",
}
DEFAULT_THEME_COLORS = {
    "mode": "dark",
    "accent": "#ff5a36",
    "selection": "#40251f",
    "muted": "#7d7d84",
    "background": "#0b0b0d",
    "dark_background": "#000000",
    "lighter_background": "#101012",
    "foreground": "#d7d7d9",
    "dark_foreground": "#aaaab0",
    "bright_foreground": "#eeeeee",
    "red": "#ff5a36",
    "yellow": "#f4bd62",
    "green": "#b4c96f",
}


def current_omarchy_theme() -> tuple[str, str, dict[str, str]]:
    state_dir = Path.home() / ".local/state/omarchy/current"
    values = dict(DEFAULT_THEME_COLORS)
    theme_id = "dark"
    try:
        candidate = (state_dir / "theme.name").read_text(encoding="utf-8")[:80].strip()
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", candidate):
            theme_id = candidate
    except OSError:
        pass
    try:
        raw = (state_dir / "theme/colors.toml").read_bytes()
        if len(raw) <= 64 * 1024:
            parsed = tomllib.loads(raw.decode("utf-8"))
            for key in values:
                value = parsed.get(key)
                if key == "mode":
                    if isinstance(value, str) and value in {"dark", "light"}:
                        values[key] = value
                elif isinstance(value, str) and THEME_COLOR_HEX.fullmatch(value):
                    values[key] = value.lower()
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        pass
    palette = {token: values[color_name] for token, color_name in THEME_COLORS.items()}
    label = " ".join(word.capitalize() for word in theme_id.split("-"))
    return theme_id, label, {"mode": values["mode"], **palette}


def themed_app_css(colors: dict[str, str]) -> str:
    definitions = "\n".join(
        f"@define-color {name} {colors[name]};" for name in THEME_COLORS
    )
    color_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    css = color_pattern.sub(
        lambda match: f"@{CSS_COLOR_TOKENS[match.group().lower()]}"
        if match.group().lower() in CSS_COLOR_TOKENS else match.group(),
        APP_CSS,
    )
    return definitions + "\n" + css


def install_app_css(colors: dict[str, str]):
    display = Gdk.Display.get_default()
    if display is None:
        return None
    provider = Gtk.CssProvider()
    provider.load_from_data(themed_app_css(colors).encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return provider


class PluginItem(GObject.Object):
    def __init__(self, plugin: Plugin):
        super().__init__()
        self.plugin = plugin


class PreviewArt(Gtk.Overlay):
    def __init__(self, height: int):
        super().__init__()
        self.image_url = ""
        self.generation = 0
        self.add_css_class("preview-frame")
        self.set_size_request(-1, height)
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.add_css_class("preview-image")
        self.set_child(self.picture)

        self.placeholder = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.placeholder.set_halign(Gtk.Align.FILL)
        self.placeholder.set_valign(Gtk.Align.FILL)
        self.placeholder.set_hexpand(True)
        self.placeholder.set_vexpand(True)
        self.placeholder.set_homogeneous(True)
        self.placeholder.add_css_class("preview-placeholder")
        self.mark = Gtk.Label()
        self.mark.add_css_class("accent-coral")
        self.placeholder.append(self.mark)
        self.add_overlay(self.placeholder)

    def load(self, plugin: Plugin, request_image) -> None:
        self.generation += 1
        self.image_url = plugin.preview_url
        for accent in ("lime", "violet", "amber", "cyan", "coral", "blue", "mint", "rose"):
            self.mark.remove_css_class(f"accent-{accent}")
        self.mark.add_css_class(f"accent-{plugin.accent}")
        self.mark.set_text(plugin.initials)
        self.set_measure_overlay(self.placeholder, True)
        self.picture.set_paintable(None)
        self.placeholder.set_visible(True)
        if self.image_url:
            request_image(self.image_url, self, self.generation)

    def set_texture(self, url: str, generation: int, texture) -> None:
        if self.image_url != url or self.generation != generation:
            return
        if texture is None:
            return
        self.picture.set_paintable(texture)
        self.placeholder.set_visible(False)


class PluginCard(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.window = window
        self.add_css_class("plugin-card")

        self.preview = PreviewArt(98)
        self.append(self.preview)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.mark = Gtk.Label()
        self.mark.add_css_class("plugin-mark")
        head.append(self.mark)

        title_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_column.set_hexpand(True)
        self.title = Gtk.Label()
        self.title.set_xalign(0)
        self.title.set_wrap(True)
        self.title.set_lines(2)
        self.title.add_css_class("plugin-title")
        title_column.append(self.title)
        self.byline = Gtk.Label()
        self.byline.set_xalign(0)
        self.byline.set_ellipsize(Pango.EllipsizeMode.END)
        self.byline.add_css_class("plugin-author")
        title_column.append(self.byline)
        head.append(title_column)

        self.badge = Gtk.Label()
        self.badge.add_css_class("plugin-badge")
        head.append(self.badge)
        self.append(head)

        self.description = Gtk.Label()
        self.description.set_xalign(0)
        self.description.set_yalign(0)
        self.description.set_wrap(True)
        self.description.set_lines(3)
        self.description.set_ellipsize(Pango.EllipsizeMode.END)
        self.description.add_css_class("plugin-description")
        self.set_vexpand(False)
        self.append(self.description)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(separator)
        self.footer = Gtk.Label()
        self.footer.set_xalign(0)
        self.footer.set_ellipsize(Pango.EllipsizeMode.END)
        self.footer.add_css_class("plugin-footer")
        self.append(self.footer)

    def bind(self, plugin: Plugin, installed: dict | None, selected: bool) -> None:
        for accent in ("lime", "violet", "amber", "cyan", "coral", "blue", "mint", "rose"):
            self.mark.remove_css_class(f"accent-{accent}")
        self.mark.add_css_class(f"accent-{plugin.accent}")
        self.mark.set_text(plugin.initials)
        self.title.set_text(plugin.name)
        self.byline.set_text(f"BY {plugin.author.upper()} · {plugin.category.upper()}")
        self.description.set_text(plugin.description or "No description was provided.")
        if installed:
            self.badge.set_text("INSTALLED")
            self.badge.remove_css_class("available")
            self.badge.add_css_class("installed")
        elif plugin.install_available:
            self.badge.set_text("AVAILABLE")
            self.badge.add_css_class("available")
            self.badge.remove_css_class("installed")
        else:
            self.badge.set_text("SOURCE ONLY")
            self.badge.remove_css_class("available")
            self.badge.remove_css_class("installed")
        stars = f"★ {plugin.stars:,}  ·  " if plugin.stars else ""
        tag = plugin.tags[0].upper() if plugin.tags else plugin.kind.upper()
        self.footer.set_text(f"{stars}{tag or 'COMMUNITY PLUGIN'}")
        self.set_selected(selected)
        self.preview.load(plugin, self.window.request_preview)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.add_css_class("selected")
        else:
            self.remove_css_class("selected")


class RecentPluginCard(Gtk.Button):
    def __init__(self, window, plugin: Plugin):
        super().__init__()
        self.add_css_class("recent-card")
        self.set_size_request(218, -1)
        self.connect("clicked", window._select_recent_plugin, plugin)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.preview = PreviewArt(104)
        content.append(self.preview)
        self.name = Gtk.Label(label=plugin.name)
        self.name.set_xalign(0)
        self.name.set_ellipsize(Pango.EllipsizeMode.END)
        self.name.add_css_class("recent-name")
        content.append(self.name)
        self.byline = Gtk.Label(label=f"{plugin.author}  ·  {listing_age(plugin)}")
        self.byline.set_xalign(0)
        self.byline.set_ellipsize(Pango.EllipsizeMode.END)
        self.byline.add_css_class("recent-byline")
        content.append(self.byline)
        self.set_child(content)
        self.preview.load(plugin, window.request_preview)


def fetch_catalog() -> tuple[list[Plugin], str]:
    request = urllib.request.Request(
        CATALOG_URL,
        headers={"Accept": "application/json", "User-Agent": "OmarchyStore/1.0"},
        method="GET",
    )
    try:
        with NO_REDIRECT_OPENER.open(request, timeout=25) as response:
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
        self.set_default_size(1320, 860)
        self.set_size_request(880, 620)
        self.add_css_class("store-window")

        self.plugins: list[Plugin] = []
        self.installed: dict[str, dict[str, bool]] = {}
        self.catalog_ready = False
        self.installed_ready = False
        self.catalog_loading = False
        self.installed_loading = False
        self.busy = False
        self.filter_mode = "all"
        self.category = ""
        self.preview_cache = OrderedDict()
        self.pending_previews = {}
        self.image_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="omarchy-store-image")
        self.theme_id, self.theme_name, self.theme_palette = application.theme
        self.css_provider = application.css_provider
        self.theme_monitor = None
        self.theme_reload_source = 0

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.add_css_class("store-root")
        self.set_content(root)

        header = Adw.HeaderBar()
        header.add_css_class("store-header")
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        brand_name = Gtk.Label(label="OMARCHY")
        brand_name.add_css_class("header-brand")
        brand_name.add_css_class("brand-mark")
        brand.append(brand_name)
        brand_slash = Gtk.Label(label="/")
        brand_slash.add_css_class("header-brand")
        brand.append(brand_slash)
        brand_market = Gtk.Label(label="PLUGIN MARKETPLACE")
        brand_market.add_css_class("header-brand")
        brand.append(brand_market)
        header.set_title_widget(brand)
        website_button = Gtk.Button(label="Browse web ↗")
        website_button.add_css_class("source-button")
        website_button.connect("clicked", self._open_marketplace)
        header.pack_start(website_button)
        refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_button.add_css_class("flat")
        refresh_button.add_css_class("refresh-button")
        refresh_button.set_tooltip_text("Refresh marketplace and installed plugins")
        refresh_button.connect("clicked", self._refresh)
        self.refresh_button = refresh_button
        header.pack_end(refresh_button)
        root.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.add_css_class("store-content")
        content.set_margin_top(18)
        content.set_margin_bottom(16)
        content.set_margin_start(24)
        content.set_margin_end(24)
        content.set_vexpand(True)
        root.append(content)

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        hero.add_css_class("hero-panel")
        hero.set_margin_bottom(2)
        hero_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        hero_copy.set_hexpand(True)
        kicker = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        eyebrow = Gtk.Label(label="COMMUNITY REGISTRY")
        eyebrow.set_xalign(0)
        eyebrow.add_css_class("eyebrow")
        kicker.append(eyebrow)
        self.theme_caption = Gtk.Label(label=self.theme_name.upper())
        self.theme_caption.add_css_class("theme-pill")
        kicker.append(self.theme_caption)
        hero_copy.append(kicker)
        hero_title = Gtk.Label(label="discover omarchy plugins")
        hero_title.set_xalign(0)
        hero_title.add_css_class("hero-title")
        hero_copy.append(hero_title)
        hero_subtitle = Gtk.Label(
            label="Find the tools that make your shell yours. Browse, inspect, and install community-built plugins."
        )
        hero_subtitle.set_xalign(0)
        hero_subtitle.set_wrap(True)
        hero_subtitle.add_css_class("hero-copy")
        hero_copy.append(hero_subtitle)
        hero.append(hero_copy)

        hero_count = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        hero_count.set_valign(Gtk.Align.CENTER)
        hero_count.set_halign(Gtk.Align.END)
        self.hero_total = Gtk.Label(label="—")
        self.hero_total.add_css_class("hero-count")
        hero_count.append(self.hero_total)
        hero_count_caption = Gtk.Label(label="COMMUNITY PLUGINS")
        hero_count_caption.add_css_class("hero-count-caption")
        hero_count.append(hero_count_caption)
        hero.append(hero_count)
        content.append(hero)

        self.recent_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.recent_section.add_css_class("recent-section")
        recent_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        recent_title = Gtk.Label(label="JUST LANDED")
        recent_title.set_xalign(0)
        recent_title.add_css_class("recent-heading")
        recent_header.append(recent_title)
        self.recent_summary = Gtk.Label(label="")
        self.recent_summary.set_xalign(0)
        self.recent_summary.add_css_class("recent-summary")
        recent_header.append(self.recent_summary)
        recent_spacer = Gtk.Box()
        recent_spacer.set_hexpand(True)
        recent_header.append(recent_spacer)
        self.recent_back = Gtk.Button(label="‹")
        self.recent_back.add_css_class("carousel-arrow")
        self.recent_back.set_tooltip_text("Previous recently added plugins")
        self.recent_back.connect("clicked", self._scroll_recent, -1)
        recent_header.append(self.recent_back)
        self.recent_forward = Gtk.Button(label="›")
        self.recent_forward.add_css_class("carousel-arrow")
        self.recent_forward.set_tooltip_text("Next recently added plugins")
        self.recent_forward.connect("clicked", self._scroll_recent, 1)
        recent_header.append(self.recent_forward)
        self.recent_section.append(recent_header)

        self.recent_cards = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.recent_scroll = Gtk.ScrolledWindow()
        self.recent_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.recent_scroll.set_min_content_height(174)
        self.recent_scroll.set_child(self.recent_cards)
        self.recent_section.append(self.recent_scroll)
        self.recent_section.set_visible(False)
        content.append(self.recent_section)

        warning = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        warning.add_css_class("security-strip")
        warning_icon = Gtk.Label(label="!")
        warning_icon.add_css_class("security-icon")
        warning.append(warning_icon)
        warning_text = Gtk.Label(label=SECURITY_NOTICE)
        warning_text.set_xalign(0)
        warning_text.set_wrap(True)
        warning_text.add_css_class("security-copy")
        warning.append(warning_text)
        content.append(warning)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        content.append(controls)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search name, author, category, tag, or plugin ID")
        self.search.add_css_class("search-entry")
        self.search.connect("search-changed", self._filter_changed)
        controls.append(self.search)

        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.append(filter_row)
        self.filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for index, (mode, label) in enumerate((
            ("all", "All"), ("installable", "Installable"), ("installed", "Installed")
        )):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("mode-button")
            if index:
                button.set_group(self.filter_buttons["all"])
            button.connect("toggled", self._filter_mode_changed, mode)
            filter_row.append(button)
            self.filter_buttons[mode] = button

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        filter_row.append(spacer)
        self.category_filter = Gtk.DropDown.new_from_strings(["All categories"])
        self.category_filter.add_css_class("category-filter")
        self.category_filter.connect("notify::selected", self._category_changed)
        filter_row.append(self.category_filter)

        count_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.status = Gtk.Label(label="Loading marketplace and installed plugins…")
        self.status.set_xalign(0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.set_hexpand(True)
        self.status.add_css_class("result-label")
        count_row.append(self.status)
        self.result_count = Gtk.Label(label="…")
        self.result_count.add_css_class("result-label")
        count_row.append(self.result_count)
        content.append(count_row)

        self.store = Gio.ListStore.new(PluginItem)
        self.custom_filter = Gtk.CustomFilter.new(self._matches_filter)
        self.filtered_store = Gtk.FilterListModel.new(self.store, self.custom_filter)
        self.selection = Gtk.SingleSelection.new(self.filtered_store)
        self.selection.set_autoselect(True)
        self.selection.connect("notify::selected-item", self._selection_changed)
        self.filter_buttons["all"].set_active(True)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_card)
        factory.connect("bind", self._bind_card)
        self.grid_view = Gtk.GridView.new(self.selection, factory)
        self.grid_view.set_min_columns(1)
        self.grid_view.set_max_columns(3)
        self.grid_view.set_single_click_activate(False)

        list_scroll = Gtk.ScrolledWindow()
        list_scroll.add_css_class("catalog-scroll")
        list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        list_scroll.set_min_content_width(510)
        list_scroll.set_child(self.grid_view)

        self.details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.details.add_css_class("details-panel")
        self.details.set_margin_top(18)
        self.details.set_margin_bottom(18)
        self.details.set_margin_start(20)
        self.details.set_margin_end(20)
        detail_scroll = Gtk.ScrolledWindow()
        detail_scroll.add_css_class("detail-scroll")
        detail_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        detail_scroll.set_child(self.details)

        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        panes.set_wide_handle(True)
        panes.set_start_child(list_scroll)
        panes.set_end_child(detail_scroll)
        panes.set_position(820)
        panes.set_resize_start_child(False)
        panes.set_shrink_start_child(False)
        panes.set_shrink_end_child(True)
        panes.set_vexpand(True)
        content.append(panes)

        self.connect("close-request", self._on_close_request)
        self._watch_theme_changes()
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
        self.category_filter.set_model(Gtk.StringList.new([
            "All categories", *sorted({plugin.category for plugin in self.plugins}, key=str.casefold)
        ]))
        self.category = ""
        self._rebuild_store()
        self._populate_recent()
        suffix = f" · catalog updated {generated_at[:10]}" if generated_at else ""
        self.status.set_text(f"COMMUNITY REGISTRY{suffix}")
        self.hero_total.set_text(f"{len(self.plugins):,}")
        self._update_result_count()
        return GLib.SOURCE_REMOVE

    def _populate_recent(self) -> None:
        self._clear_box(self.recent_cards)
        fresh = recently_added(self.plugins, hours=24)
        week = recently_added(self.plugins, hours=24 * 7)
        carousel = fresh if fresh else week
        self.recent_section.set_visible(bool(carousel))
        if not carousel:
            return
        self.recent_summary.set_text(
            f"{len(fresh)} NEW IN 24H  ·  {len(week)} IN 7 DAYS"
            if fresh else f"NO NEW LISTINGS TODAY  ·  {len(week)} IN 7 DAYS"
        )
        for plugin in carousel[:12]:
            self.recent_cards.append(RecentPluginCard(self, plugin))

    def _scroll_recent(self, _button, direction: int) -> None:
        adjustment = self.recent_scroll.get_hadjustment()
        step = max(220, adjustment.get_page_size() * 0.75)
        target = adjustment.get_value() + direction * step
        maximum = max(0, adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(max(0, min(maximum, target)))

    def _select_recent_plugin(self, _button, plugin: Plugin) -> None:
        self.filter_buttons["all"].set_active(True)
        self.filter_mode = "all"
        self.search.set_text("")
        self.category_filter.set_selected(0)
        self.category = ""
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_result_count()
        for position in range(self.filtered_store.get_n_items()):
            item = self.filtered_store.get_item(position)
            if item.plugin.id == plugin.id:
                self.selection.set_selected(position)
                self.grid_view.scroll_to(position, Gtk.ListScrollFlags.FOCUS)
                break

    def request_preview(self, url: str, preview: PreviewArt, generation: int) -> None:
        if not url or marketplace_preview_url(urllib.parse.urlsplit(url).path.lstrip("/")) != url:
            return
        if url in self.preview_cache:
            texture = self.preview_cache[url]
            self.preview_cache.move_to_end(url)
            preview.set_texture(url, generation, texture or None)
            return
        self.pending_previews.setdefault(url, []).append((weakref.ref(preview), generation))
        if len(self.pending_previews[url]) == 1:
            self.image_pool.submit(self._download_preview, url)

    def _download_preview(self, url: str) -> None:
        try:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname != "plugins.omarchy.org" or parsed.port:
                raise ValueError("image URL is outside the marketplace asset origin")
            request = urllib.request.Request(
                url,
                headers={"Accept": "image/webp,image/png,image/jpeg", "User-Agent": "OmarchyStore/1.0"},
                method="GET",
            )
            with NO_REDIRECT_OPENER.open(request, timeout=12) as response:
                if response.geturl() != url:
                    raise ValueError("image request redirected")
                if response.headers.get_content_type() not in {"image/webp", "image/png", "image/jpeg"}:
                    raise ValueError("unsupported image type")
                data = response.read(MAX_PREVIEW_BYTES + 1)
            if len(data) > MAX_PREVIEW_BYTES:
                raise ValueError("image exceeded the size limit")
        except Exception:
            data = None
        GLib.idle_add(self._preview_loaded, url, data)

    def _preview_loaded(self, url: str, data: bytes | None) -> bool:
        texture = None
        if data:
            try:
                texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                if texture.get_width() > 1600 or texture.get_height() > 1200:
                    texture = None
            except GLib.Error:
                texture = None
        self.preview_cache[url] = texture or False
        self.preview_cache.move_to_end(url)
        while len(self.preview_cache) > MAX_CACHED_PREVIEWS:
            self.preview_cache.popitem(last=False)
        for preview_ref, generation in self.pending_previews.pop(url, []):
            preview = preview_ref()
            if preview is not None:
                preview.set_texture(url, generation, texture)
        return GLib.SOURCE_REMOVE

    def _on_close_request(self, _window) -> bool:
        if self.theme_monitor is not None:
            self.theme_monitor.cancel()
        if self.theme_reload_source:
            GLib.source_remove(self.theme_reload_source)
        self.image_pool.shutdown(wait=False, cancel_futures=True)
        return False

    def _watch_theme_changes(self) -> None:
        current_dir = Path.home() / ".local/state/omarchy/current"
        try:
            self.theme_monitor = Gio.File.new_for_path(str(current_dir)).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self.theme_monitor.connect("changed", self._theme_state_changed)
        except GLib.Error:
            self.theme_monitor = None

    def _theme_state_changed(self, _monitor, file, other_file, _event) -> None:
        names = {file.get_basename() if file else "", other_file.get_basename() if other_file else ""}
        if not names.intersection({"theme", "theme.name"}):
            return
        if self.theme_reload_source:
            GLib.source_remove(self.theme_reload_source)
        self.theme_reload_source = GLib.timeout_add(250, self._reload_theme)

    def _reload_theme(self) -> bool:
        self.theme_reload_source = 0
        theme_id, theme_name, palette = current_omarchy_theme()
        if self.css_provider is not None:
            try:
                self.css_provider.load_from_data(themed_app_css(palette).encode("utf-8"))
            except GLib.Error as error:
                self.status.set_text(f"Could not apply Omarchy theme: {error.message}")
                return GLib.SOURCE_REMOVE
        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_LIGHT if palette["mode"] == "light" else Adw.ColorScheme.FORCE_DARK
        )
        self.theme_id = theme_id
        self.theme_name = theme_name
        self.theme_palette = palette
        self.theme_caption.set_text(theme_name.upper())
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
        else:
            self.installed = result
            self.installed_ready = True
        self._rebuild_store()
        self.filter_buttons["installed"].set_sensitive(self.installed_ready)
        return GLib.SOURCE_REMOVE

    def _rebuild_store(self) -> None:
        selected = self.selection.get_selected_item()
        selected_id = selected.plugin.id if selected else ""
        self.store.splice(0, self.store.get_n_items(), [PluginItem(p) for p in self.plugins])
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
        if selected_id:
            for position in range(self.filtered_store.get_n_items()):
                item = self.filtered_store.get_item(position)
                if item.plugin.id == selected_id:
                    self.selection.set_selected(position)
                    break
        self._selection_changed(self.selection, None)
        self._update_result_count()

    def _update_result_count(self) -> None:
        total = self.filtered_store.get_n_items() if hasattr(self, "filtered_store") else 0
        self.result_count.set_text(f"SHOWING {total:,} / {len(self.plugins):,}")

    def _update_refresh_button(self) -> None:
        self.refresh_button.set_sensitive(
            not self.catalog_loading and not self.installed_loading and not self.busy
        )

    def _setup_card(self, _factory, list_item) -> None:
        list_item.set_child(PluginCard(self))
        list_item.connect("notify::selected", self._card_selection_changed)

    def _bind_card(self, _factory, list_item) -> None:
        item = list_item.get_item()
        if item is None:
            return
        list_item.get_child().bind(
            item.plugin,
            self.installed.get(item.plugin.id) if self.installed_ready else None,
            list_item.get_selected(),
        )

    @staticmethod
    def _card_selection_changed(list_item, _pspec) -> None:
        card = list_item.get_child()
        if card is not None:
            card.set_selected(list_item.get_selected())

    def _matches_filter(self, item) -> bool:
        if item is None:
            return False
        if self.category and item.plugin.category != self.category:
            return False
        return bool(search_plugins(
            [item.plugin], self.search.get_text(), self.installed, self.filter_mode
        ))

    def _filter_changed(self, _entry) -> None:
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_result_count()

    def _filter_mode_changed(self, button, mode: str) -> None:
        if not button.get_active():
            return
        self.filter_mode = mode
        self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_result_count()

    def _category_changed(self, dropdown, _pspec) -> None:
        selected = dropdown.get_selected_item()
        value = selected.get_string() if selected else "All categories"
        self.category = "" if value == "All categories" else value
        if hasattr(self, "custom_filter"):
            self.custom_filter.changed(Gtk.FilterChange.DIFFERENT)
            self._update_result_count()

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
            mark = self._label("OM", "empty-mark")
            mark.set_halign(Gtk.Align.START)
            self.details.append(mark)
            self.details.append(self._label("Pick a plugin", "detail-title"))
            self.details.append(self._label(
                "Select a marketplace card to see its details, compatibility, and install options.",
                "detail-info",
            ))
            return

        self.details.append(self._label("PLUGIN DETAILS", "eyebrow"))
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        mark = self._label(plugin.initials, "detail-mark")
        mark.add_css_class(f"accent-{plugin.accent}")
        title_row.append(mark)
        title_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title_column.set_hexpand(True)
        title = self._label(plugin.name, "detail-title")
        title_column.append(title)
        author = self._label(f"BY {plugin.author.upper()}", "plugin-author")
        title_column.append(author)
        title_row.append(title_column)
        self.details.append(title_row)

        subhead = self._label(
            f"{plugin.category.upper()}  ·  {plugin.kind.upper() or 'PLUGIN'}  ·  {plugin.version}",
            "detail-meta",
        )
        self.details.append(subhead)
        self.details.append(self._label(
            plugin.description or "No description was provided.", "detail-description"
        ))

        self.details.append(self._label("LISTING", "detail-section-label"))
        metadata = (
            f"ID       {plugin.id}\n"
            f"LICENSE  {plugin.license}\n"
            f"TAGS     {', '.join(plugin.tags) if plugin.tags else 'None'}"
        )
        self.details.append(self._label(metadata, "detail-info"))

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
        verification_badge = self._label(
            "VERIFIED SNAPSHOT" if plugin.verification_status == "verified" else "UNVERIFIED LISTING",
            "plugin-badge",
        )
        verification_badge.add_css_class(
            "installed" if plugin.verification_status == "verified" else "available"
        )
        self.details.append(verification_badge)
        self.details.append(self._label(verification, "detail-warning"))

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        source = Gtk.Button(label="View source ↗")
        source.add_css_class("source-button")
        source.connect("clicked", self._open_source, plugin)
        action_row.append(source)

        installed = self.installed.get(plugin.id) if self.installed_ready else None
        if installed is not None:
            state_text = "Installed and enabled" if installed["enabled"] else "Installed but disabled"
            self.details.append(self._label(state_text.upper(), "plugin-badge"))
        if not self.installed_ready:
            pass
        elif installed is None and plugin.install_available:
            install = Gtk.Button(label="Install & enable")
            install.add_css_class("install-button")
            install.set_sensitive(not self.busy)
            install.connect("clicked", self._ask_to_install, plugin)
            action_row.append(install)
        elif installed is not None and not installed["enabled"] and not installed["firstParty"]:
            enable = Gtk.Button(label="Enable (runs code)")
            enable.add_css_class("install-button")
            enable.set_sensitive(not self.busy)
            enable.connect("clicked", self._ask_to_enable, plugin)
            action_row.append(enable)

        if installed is not None and not installed["firstParty"]:
            remove = Gtk.Button(label="Remove")
            remove.add_css_class("source-button")
            remove.set_sensitive(not self.busy)
            remove.connect("clicked", self._ask_to_remove, plugin)
            action_row.append(remove)
        elif installed is not None:
            action_row.append(self._label("Included with Omarchy", "detail-info"))
        elif not self.installed_ready:
            action_row.append(self._label("Installed state unavailable", "detail-info"))
        elif not plugin.install_available:
            action_row.append(self._label(
                plugin.install_note or "Automatic installation is unavailable for this repository layout.",
                "detail-info",
            ))
        self.details.append(action_row)

        self.details.append(self._label(
            "REPOSITORY  " + plugin.repo_url.removesuffix(".git"), "detail-meta"
        ))

    def _open_marketplace(self, _button) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri("https://plugins.omarchy.org/index.html", None)
        except GLib.Error as error:
            self.status.set_text(f"Could not open the marketplace: {error.message}")

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
        self.theme = current_omarchy_theme()
        self.css_provider = None

    def do_activate(self):
        if self.window is None:
            self.window = StoreWindow(self)
        self.window.present()


def main() -> int:
    Adw.init()
    theme = current_omarchy_theme()
    Adw.StyleManager.get_default().set_color_scheme(
        Adw.ColorScheme.FORCE_LIGHT if theme[2]["mode"] == "light" else Adw.ColorScheme.FORCE_DARK
    )
    app = StoreApplication()
    app.theme = theme
    app.css_provider = install_app_css(theme[2])
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
