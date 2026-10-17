"""Marketplace data and safe Omarchy CLI arguments for Omarchy Store."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


CATALOG_URL = "https://plugins.omarchy.org/catalog.json"
MAX_CATALOG_BYTES = 24 * 1024 * 1024
MAX_CATALOG_ENTRIES = 20_000

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
