"""Marketplace data and safe Omarchy CLI arguments for Omarchy Store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import Any


CATALOG_URL = "https://plugins.omarchy.org/catalog.json"
MAX_CATALOG_BYTES = 24 * 1024 * 1024
MAX_CATALOG_ENTRIES = 20_000
MAX_ENGAGEMENT_BYTES = 4 * 1024 * 1024

_PLUGIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_GITHUB_REPO = re.compile(
    r"^https://github\.com/"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?)"
    r"(?:\.git)?/?$"
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ACCENTS = {"lime", "violet", "amber", "cyan", "coral", "blue", "mint", "rose"}
_INITIALS = re.compile(r"^[A-Z0-9]{1,3}$")
_PREVIEW_PATH = re.compile(
    r"^assets/img/plugins/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*"
    r"[A-Za-z0-9][A-Za-z0-9._-]*\.(?:webp|png|jpe?g)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    description: str
    author: str
    initials: str
    accent: str
    version: str
    category: str
    kind: str
    tags: tuple[str, ...]
    repo_url: str
    license: str
    verification_status: str
    verification_coverage: str
    verification_method: str
    preview_url: str
    listed_at: str
    install_note: str
    upstream_status: str
    install_available: bool
    stars: int

    @property
    def search_text(self) -> str:
        return " ".join(
            (self.name, self.id, self.description, self.author, self.category,
             self.kind, " ".join(self.tags))
        ).casefold()


class CatalogError(ValueError):
    """The remote marketplace response is not a usable catalog."""


def safe_text(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return _CONTROL_CHARS.sub(" ", value[:limit])


def valid_plugin_id(value: Any, *, allow_reserved: bool = False) -> bool:
    if not isinstance(value, str) or not _PLUGIN_ID.fullmatch(value):
        return False
    return ".." not in value and (
        allow_reserved or not value.casefold().startswith("omarchy.")
    )


def github_repository(value: Any) -> str:
    """Return a canonical clone URL only for a plain github.com repo URL."""
    if not isinstance(value, str):
        return ""
    match = _GITHUB_REPO.fullmatch(value)
    if not match:
        return ""
    owner, repository = match.groups()
    if ".." in repository:
        return ""
    return f"https://github.com/{owner}/{repository.removesuffix('.git')}.git"


def marketplace_preview_url(value: Any) -> str:
    """Allow only static image assets under the marketplace's image directory."""
    if not isinstance(value, str) or not _PREVIEW_PATH.fullmatch(value) or ".." in value:
        return ""
    return "https://plugins.omarchy.org/" + value


def normalize_plugin(raw: Any) -> Plugin | None:
    if not isinstance(raw, dict) or raw.get("sourceType") != "community":
        return None
    plugin_id = raw.get("id")
    name = safe_text(raw.get("name"), 120)
    repo_url = github_repository(raw.get("repo"))
    if not valid_plugin_id(plugin_id) or not name or not repo_url:
        return None

    raw_tags = raw.get("tags")
    tags = tuple(
        text for item in raw_tags[:16] if (text := safe_text(item, 40))
    ) if isinstance(raw_tags, list) else ()
    upstream_status = safe_text(raw.get("upstreamCheckStatus"), 40)
    layout = safe_text(raw.get("repositoryLayout"), 40)
    initials = safe_text(raw.get("initials"), 3).upper()
    if not _INITIALS.fullmatch(initials):
        words = name.split()
        initials = "".join(word[0] for word in words[:2]).upper() if len(words) > 1 else name[:2].upper()
        initials = re.sub(r"[^A-Z0-9]", "", initials) or "OM"
    accent = safe_text(raw.get("accent"), 20)
    if accent not in _ACCENTS:
        accent = "coral"
    stars_value = raw.get("stars", 0)
    stars = max(0, min(1_000_000_000, stars_value)) if isinstance(stars_value, int) and not isinstance(stars_value, bool) else 0
    install_available = (
        raw.get("installAvailable") is True
        and upstream_status != "failed"
        and layout == "root-plugin"
    )

    return Plugin(
        id=plugin_id,
        name=name,
        description=safe_text(raw.get("description"), 1200),
        author=safe_text(raw.get("author"), 100) or "Unknown",
        initials=initials,
        accent=accent,
        version=safe_text(raw.get("version"), 64) or "Unknown",
        category=safe_text(raw.get("category"), 80) or "Other",
        kind=safe_text(raw.get("kind"), 80),
        tags=tags,
        repo_url=repo_url,
        license=safe_text(raw.get("license"), 80) or "Unknown",
        verification_status=safe_text(raw.get("verificationStatus"), 40) or "unverified",
        verification_coverage=safe_text(raw.get("verificationCoverage"), 40),
        verification_method=safe_text(raw.get("verificationMethod"), 60),
        preview_url=marketplace_preview_url(raw.get("previewThumbnail") or raw.get("previewImage")),
        listed_at=safe_text(raw.get("listedAt"), 40),
        install_note=safe_text(raw.get("installNote"), 500),
        upstream_status=upstream_status,
        install_available=install_available,
        stars=stars,
    )


def normalize_catalog(data: Any) -> tuple[list[Plugin], str]:
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise CatalogError("Marketplace response is not a plugin catalog")
    if len(data["plugins"]) > MAX_CATALOG_ENTRIES:
        raise CatalogError("Marketplace catalog has too many entries")

    plugins: list[Plugin] = []
    seen: set[str] = set()
    for raw in data["plugins"]:
        plugin = normalize_plugin(raw)
        if plugin is None or plugin.id in seen:
            continue
        seen.add(plugin.id)
        plugins.append(plugin)
    plugins.sort(key=lambda item: (not item.install_available, item.name.casefold()))
    return plugins, safe_text(data.get("generatedAt"), 40)


def listing_time(plugin: Plugin) -> datetime | None:
    try:
        value = plugin.listed_at
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def recently_added(
    plugins: list[Plugin], *, hours: int = 24, now: datetime | None = None
) -> list[Plugin]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    cutoff = current - timedelta(hours=max(1, hours))
    result = [
        (listing_time(plugin), plugin)
        for plugin in plugins
    ]
    return [
        plugin for timestamp, plugin in sorted(
            (pair for pair in result if pair[0] is not None and cutoff <= pair[0] <= current),
            key=lambda pair: pair[0],
            reverse=True,
        )
    ]


def listing_age(plugin: Plugin, *, now: datetime | None = None) -> str:
    timestamp = listing_time(plugin)
    if timestamp is None:
        return "RECENTLY ADDED"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    minutes = max(0, int((current.astimezone(timezone.utc) - timestamp).total_seconds() // 60))
    if minutes < 1:
        return "JUST NOW"
    if minutes < 60:
        return f"{minutes}M AGO"
    hours = minutes // 60
    return f"{hours}H AGO" if hours < 24 else f"{hours // 24}D AGO"


def normalize_engagement(data: Any) -> dict[str, dict[str, int]]:
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), dict):
        raise CatalogError("Marketplace engagement response is invalid")
    source = data["plugins"]
    if len(source) > MAX_CATALOG_ENTRIES:
        raise CatalogError("Marketplace engagement response has too many entries")
    result: dict[str, dict[str, int]] = {}
    for plugin_id, counts in source.items():
        if not valid_plugin_id(plugin_id) or not isinstance(counts, dict):
            continue
        result[plugin_id] = {
            key: max(0, min(1_000_000_000, value))
            if isinstance(value, int) and not isinstance(value, bool) else 0
            for key, value in (("views", counts.get("views")),
                               ("copies", counts.get("copies")),
                               ("hearts", counts.get("hearts")))
        }
    return result


def parse_engagement(raw: bytes) -> dict[str, dict[str, int]]:
    if len(raw) > MAX_ENGAGEMENT_BYTES:
        raise CatalogError("Marketplace engagement response exceeded the size limit")
    try:
        return normalize_engagement(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogError("Marketplace engagement response is not valid JSON") from error


def install_rate_score(plugin: Plugin, counts: dict[str, int]) -> float | None:
    if not plugin.install_available:
        return None
    views = counts.get("views", 0)
    copies = min(counts.get("copies", 0), views)
    if views < 20:
        return None
    if copies == 0:
        return 0.0
    rate = copies / views
    z = 1.96
    center = rate + z * z / (2 * views)
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * views)) / views)
    return (center - margin) / (1 + z * z / views)


def highlighted_plugins(
    plugins: list[Plugin], stats: dict[str, dict[str, int]], *, limit: int = 9
) -> list[tuple[Plugin, float]]:
    if not plugins:
        return []
    view_counts = sorted(stats.get(plugin.id, {}).get("views", 0) for plugin in plugins)
    threshold = view_counts[min(len(view_counts) - 1, int(len(view_counts) * 0.75))]
    rates = []
    for plugin in plugins:
        counts = stats.get(plugin.id, {})
        score = install_rate_score(plugin, counts)
        if score is not None:
            views = counts.get("views", 0)
            rates.append(min(counts.get("copies", 0), views) / views)
    rates.sort()
    median = None
    if rates:
        middle = len(rates) // 2
        median = rates[middle] if len(rates) % 2 else (rates[middle - 1] + rates[middle]) / 2

    gems = []
    for plugin in plugins:
        counts = stats.get(plugin.id, {})
        views = counts.get("views", 0)
        score = install_rate_score(plugin, counts)
        if (
            plugin.verification_status != "verified"
            or not plugin.preview_url
            or score is None
            or views >= threshold
        ):
            continue
        copies = min(counts.get("copies", 0), views)
        ratio = copies / views if views else 0
        times = ratio / median if median else 0
        gems.append((plugin, score, views, times))
    gems.sort(key=lambda item: (-item[1], -item[2], item[0].name.casefold()))
    return [(plugin, times) for plugin, _score, _views, times in gems[:max(0, limit)]]


def carousel_target(
    current: float,
    page_size: float,
    cycle: float,
    maximum: float,
    direction: int,
    *,
    wrap: bool,
) -> float:
    """Return a bounded manual carousel step, even when motion is disabled."""
    step = max(218.0, page_size * 0.8)
    target = current + (1 if direction >= 0 else -1) * step
    if wrap and cycle > 0 and maximum >= cycle:
        if direction >= 0 and target >= cycle:
            return 0.0
        if direction < 0 and target < 0:
            return max(0.0, cycle - step)
        return max(0.0, min(cycle, target))
    return max(0.0, min(maximum, target))


def catalog_page(total: int, page: int, page_size: int = 6) -> tuple[int, int, int, int]:
    """Return the current page, page count, and half-open slice for a catalog page."""
    size = max(1, int(page_size))
    count = max(0, int(total))
    pages = max(1, (count + size - 1) // size)
    current = min(max(1, int(page)), pages)
    start = (current - 1) * size
    return current, pages, start, min(count, start + size)


def feed_motion_offset(value: float, cycle: float, step: float) -> float:
    """Advance a duplicated marquee and wrap inside one copy of the track."""
    if cycle <= 0:
        return 0.0
    return (value + step) % cycle


_THEME_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _theme_hex(value: Any, fallback: str) -> str:
    if isinstance(value, str) and _THEME_HEX.fullmatch(value):
        return value.lower()
    return fallback


def readable_contrast(color: str) -> str:
    """Pick text that stays readable on a theme accent, including dark accents."""
    value = _theme_hex(color, "#000000")[1:]
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]

    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * linear(channels[0]) + 0.7152 * linear(channels[1]) + 0.0722 * linear(channels[2])
    return "#14110e" if luminance > 0.42 else "#f7edd8"


def store_palette(values: dict[str, Any] | None) -> dict[str, str]:
    """Map an Omarchy colors.toml table onto store roles.

    Only validated hex colors are used, so a theme file cannot inject CSS.
    """
    source = values if isinstance(values, dict) else {}
    accent = _theme_hex(source.get("accent"), "#c45c38")
    background = _theme_hex(source.get("background"), "#14110e")
    dark_background = _theme_hex(source.get("dark_background"), "#0d0b09")
    return {
        "mode": source.get("mode") if source.get("mode") in {"dark", "light"} else "dark",
        "bg": _theme_hex(source.get("darker_background"), dark_background),
        "panel": background,
        "raised": _theme_hex(source.get("lighter_background"), "#2a231c"),
        "line": _theme_hex(source.get("selection"), "#3a2e22"),
        "line_strong": _theme_hex(source.get("muted"), "#8a7a64"),
        "fg": _theme_hex(source.get("foreground"), "#e6d3b0"),
        "heading": _theme_hex(source.get("bright_foreground"), _theme_hex(source.get("light_foreground"), "#f7edd8")),
        "muted": _theme_hex(source.get("dark_foreground"), "#a89878"),
        "faint": _theme_hex(source.get("muted"), "#8a7a64"),
        "accent": accent,
        "accent_fg": readable_contrast(accent),
        "warning": _theme_hex(source.get("yellow"), _theme_hex(source.get("orange"), accent)),
        "stable": _theme_hex(source.get("green"), "#8a9a62"),
        "danger": _theme_hex(source.get("red"), accent),
        "brass": _theme_hex(source.get("yellow"), _theme_hex(source.get("orange"), accent)),
        "water": _theme_hex(source.get("cyan"), _theme_hex(source.get("blue"), "#7f9a96")),
    }


def store_stylesheet(colors: dict[str, str]) -> str:
    """Build store CSS from the active palette, not the marketplace's default orange theme."""
    palette = store_palette(colors)
    for key, value in list(palette.items()):
        if key != "mode" and not _THEME_HEX.fullmatch(value):
            palette[key] = "#000000"
    css = """
@define-color window_bg_color {bg};
@define-color window_fg_color {fg};
@define-color view_bg_color {bg};
@define-color view_fg_color {fg};
@define-color headerbar_bg_color {panel};
@define-color headerbar_fg_color {heading};
@define-color card_bg_color {panel};
@define-color card_fg_color {fg};
@define-color popover_bg_color {panel};
@define-color popover_fg_color {fg};
@define-color dialog_bg_color {panel};
@define-color dialog_fg_color {fg};
@define-color accent_bg_color {accent};
@define-color accent_fg_color {accent_fg};
@define-color accent_color {accent};
@define-color destructive_bg_color {danger};
@define-color success_color {stable};
@define-color warning_color {warning};
window.store-window, .store-root {{ background: {bg}; color: {fg}; }}
headerbar.store-header {{ background: {panel}; color: {heading}; border-bottom: 2px solid {accent}; }}
.header-brand {{ font-family: monospace; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: {heading}; }}
.header-brand .brand-mark, .brand-mark {{ color: {accent}; }}
.theme-pill {{ border: 1px solid {brass}; border-radius: 4px; padding: 3px 7px; color: {brass}; font-family: monospace; font-size: 8px; font-weight: 700; }}
.theme-swatch {{ min-width: 9px; min-height: 9px; border-radius: 2px; border: 1px solid {line_strong}; }}
.swatch-accent {{ background: {accent}; }}
.swatch-brass {{ background: {brass}; }}
.swatch-sail {{ background: {fg}; }}
.swatch-water {{ background: {water}; }}
button.view-button {{ min-height: 28px; padding: 0 12px; border: 1px solid {line}; border-radius: 5px; background: {panel}; color: {muted}; font-family: monospace; font-size: 10px; }}
button.view-button:checked {{ border-color: {accent}; background: {accent}; color: {accent_fg}; font-weight: 800; }}
.store-content, scrolledwindow.page-scroll, .status-bar {{ background: {bg}; }}
.status-bar {{ border-top: 1px solid {line}; padding: 6px 16px; }}
.hero-panel {{ background: {panel}; border: 1px solid {line}; border-top: 3px solid {brass}; border-radius: 10px; }}
.hero-art {{ opacity: 0.55; }}
.hero-scrim {{ background: alpha({bg}, 0.72); }}
.hero-copy-box {{ padding: 22px 26px; }}
.eyebrow {{ color: {brass}; font-family: monospace; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
.hero-title {{ color: {heading}; font-family: monospace; font-size: 30px; font-weight: 800; }}
.hero-copy, .hero-count-caption {{ color: {fg}; font-size: 13px; }}
.hero-count {{ color: {heading}; font-family: monospace; font-size: 27px; font-weight: 800; }}
.hero-count-caption {{ font-family: monospace; font-size: 9px; letter-spacing: 1px; }}
.security-strip {{ background: {raised}; border: 1px solid {line}; border-left: 3px solid {warning}; border-radius: 6px; padding: 9px 12px; }}
.security-icon {{ color: {warning}; font-family: monospace; font-weight: 800; }}
.security-copy {{ color: {fg}; font-size: 11px; }}
entry.search-entry {{ min-height: 42px; border: 1px solid {line_strong}; border-radius: 6px; background: {panel}; color: {heading}; }}
entry.search-entry:focus-within {{ border-color: {accent}; box-shadow: 0 0 0 1px {accent}; }}
button.mode-button, button.carousel-arrow, button.source-button {{ border: 1px solid {line}; border-radius: 5px; background: {panel}; color: {muted}; font-family: monospace; font-size: 10px; }}
button.mode-button {{ min-height: 31px; padding: 0 13px; }}
button.mode-button:checked, button.install-button {{ border-color: {accent}; background: {accent}; color: {accent_fg}; font-weight: 800; }}
button.carousel-arrow {{ min-width: 30px; min-height: 28px; }}
button.carousel-arrow:hover, button.source-button:hover {{ border-color: {accent}; color: {accent}; }}
dropdown.category-filter > button {{ min-height: 32px; border: 1px solid {line}; border-radius: 5px; background: {panel}; color: {fg}; font-family: monospace; font-size: 10px; }}
.result-label, .recent-summary, .plugin-author, .plugin-footer {{ color: {faint}; font-family: monospace; }}
.recent-heading {{ color: {brass}; font-family: monospace; font-size: 10px; font-weight: 800; letter-spacing: 1px; }}
.recent-summary {{ font-size: 9px; }}
button.recent-card {{ min-width: 218px; border: 1px solid {line}; border-radius: 7px; background: {panel}; padding: 8px; }}
button.recent-card:hover {{ border-color: {accent}; background: {raised}; }}
button.recent-card label.recent-name, .plugin-title, .detail-title {{ color: {heading}; }}
button.recent-card label.recent-name {{ font-size: 11px; font-weight: 750; }}
button.recent-card label.recent-byline {{ color: {muted}; font-family: monospace; font-size: 8px; }}
.plugin-title {{ font-size: 14px; font-weight: 750; }}
.plugin-author {{ font-size: 9px; }}
.plugin-description, .detail-meta, .detail-info {{ color: {fg}; }}
.plugin-description {{ font-size: 11px; }}
.plugin-footer {{ font-size: 9px; }}
.catalog-scroll, .detail-scroll, gridview {{ background: transparent; }}
gridview > child {{ padding: 5px; }}
gridview > child:selected {{ background: transparent; }}
.plugin-card {{ min-height: 198px; background: {panel}; border: 1px solid {line}; border-radius: 8px; padding: 14px; }}
.plugin-card:hover {{ background: {raised}; border-color: {line_strong}; }}
.plugin-card.selected {{ background: {raised}; border-color: {accent}; }}
.plugin-mark, .detail-mark {{ border: 1px solid {line}; background: {raised}; font-family: monospace; font-weight: 800; }}
.plugin-mark {{ min-width: 42px; min-height: 42px; border-radius: 6px; font-size: 12px; }}
.preview-frame {{ min-height: 98px; border: 1px solid {line}; border-radius: 6px; background: {raised}; }}
.preview-placeholder {{ min-height: 98px; background: {bg}; }}
.preview-placeholder label {{ font-family: monospace; font-size: 24px; font-weight: 800; }}
.plugin-badge {{ border: 1px solid {line_strong}; border-radius: 4px; padding: 3px 6px; color: {muted}; font-family: monospace; font-size: 8px; font-weight: 700; }}
.plugin-badge.available {{ border-color: {brass}; background: {panel}; color: {brass}; }}
.plugin-badge.installed {{ border-color: {stable}; background: {panel}; color: {stable}; }}
.browse-masthead {{ padding: 2px 2px 8px; }}
.browse-title {{ color: {heading}; font-family: monospace; font-size: 28px; font-weight: 800; }}
.browse-count {{ color: {heading}; font-family: monospace; font-size: 22px; font-weight: 800; }}
.control-deck {{ background: {panel}; border: 1px solid {line}; border-top: 2px solid {brass}; border-radius: 8px; padding: 10px; }}
.kbd-hint {{ border: 1px solid {line_strong}; border-radius: 4px; padding: 2px 6px; color: {faint}; font-family: monospace; font-size: 9px; }}
.pager-bar {{ border-top: 1px solid {line}; padding-top: 8px; }}
.pager-entry {{ min-width: 52px; min-height: 32px; }}
.fact-label {{ color: {brass}; font-family: monospace; font-size: 8px; font-weight: 700; letter-spacing: 1px; }}
.fact-value {{ color: {heading}; font-size: 12px; }}
.tag-chip {{ border: 1px solid {line}; border-radius: 99px; padding: 3px 8px; color: {fg}; font-family: monospace; font-size: 9px; }}
.empty-state {{ padding: 36px 20px; }}
.preview-dialog, .preview-dialog .details-panel {{ background: {panel}; }}
.details-panel {{ background: {panel}; border: 1px solid {line}; border-radius: 8px; padding: 16px; }}
.detail-mark {{ min-width: 54px; min-height: 54px; border-radius: 8px; font-size: 17px; }}
.detail-title {{ font-size: 22px; font-weight: 800; }}
.detail-meta {{ font-family: monospace; font-size: 10px; }}
.detail-description {{ color: {fg}; font-size: 13px; }}
.detail-section-label {{ color: {brass}; font-family: monospace; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
.detail-info {{ font-size: 11px; }}
.detail-warning {{ background: {bg}; border-left: 3px solid {warning}; padding: 10px; color: {fg}; font-size: 10px; }}
button.install-button {{ min-height: 36px; border-radius: 5px; font-family: monospace; font-size: 10px; }}
button.install-button:hover {{ background: {brass}; color: {bg}; }}
button.source-button {{ min-height: 34px; background: transparent; color: {fg}; }}
.empty-mark {{ color: {accent}; font-family: monospace; font-size: 34px; font-weight: 800; }}
.accent-lime {{ color: {stable}; }} .accent-violet {{ color: {water}; }}
.accent-amber {{ color: {brass}; }} .accent-cyan {{ color: {water}; }}
.accent-coral {{ color: {accent}; }} .accent-blue {{ color: {water}; }}
.accent-mint {{ color: {stable}; }} .accent-rose {{ color: {danger}; }}
label.dim-label {{ color: {faint}; }}
button.flat.refresh-button {{ color: {muted}; }}
button.flat.refresh-button:hover {{ color: {accent}; background: {raised}; }}
scrolledwindow.feed-scroll scrollbar, scrolledwindow.feed-scroll scrollbar slider {{ opacity: 0; min-width: 0; min-height: 0; }}
"""
    return css.format(**palette)


def parse_catalog(raw: bytes) -> tuple[list[Plugin], str]:
    if len(raw) > MAX_CATALOG_BYTES:
        raise CatalogError("Marketplace catalog exceeded the 24 MiB size limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogError("Marketplace response is not valid UTF-8 JSON") from error
    return normalize_catalog(data)


def installed_map(raw: str) -> dict[str, dict[str, bool]]:
    try:
        rows = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise CatalogError("Omarchy returned invalid JSON for installed plugins")
    if not isinstance(rows, list):
        raise CatalogError("Omarchy installed-plugin response is not a list")
    result: dict[str, dict[str, bool]] = {}
    for row in rows:
        if not isinstance(row, dict) or not valid_plugin_id(row.get("id"), allow_reserved=True):
            continue
        result[row["id"]] = {
            "enabled": row.get("enabled") is True,
            "firstParty": row.get("firstParty") is True,
        }
    return result


def search_plugins(plugins: list[Plugin], query: str, installed: dict[str, Any], mode: str) -> list[Plugin]:
    terms = (query or "").casefold().split()
    result = []
    for plugin in plugins:
        is_installed = plugin.id in installed
        if mode == "installed" and not is_installed:
            continue
        if mode == "installable" and (not plugin.install_available or is_installed):
            continue
        if all(term in plugin.search_text for term in terms):
            result.append(plugin)
    return result


def install_args(plugin: Plugin) -> list[str]:
    if not plugin.install_available or not valid_plugin_id(plugin.id):
        return []
    url = github_repository(plugin.repo_url)
    return ["plugin", "add", url, "--enable", "--yes"] if url else []


def enable_args(plugin: Plugin) -> list[str]:
    return ["plugin", "enable", plugin.id] if valid_plugin_id(plugin.id) else []


def remove_args(plugin: Plugin) -> list[str]:
    return ["plugin", "remove", plugin.id, "--yes"] if valid_plugin_id(plugin.id) else []
