# Omarchy Store

A native Quickshell app-store style browser for the [Omarchy Plugin Marketplace](https://plugins.omarchy.org/). Browse and search marketplace listings, see whether a plugin is installed, inspect its source and listing status, and install, enable, or remove supported plugins from a panel.

## Install

```sh
omarchy plugin add https://github.com/Nate-Slater/OmarchyStore.git --enable
```

Omarchy validates the plugin folder before enabling it. The store appears as a **Store** widget on the bar. Click it to open the catalog.

## Security and installation behavior

Omarchy plugins run unsandboxed inside the long-running `omarchy-shell` process with your user permissions. This plugin itself fetches only the public `https://plugins.omarchy.org/catalog.json` catalog. It does not load remote images, execute catalog-provided install commands, evaluate listing text as code, or write local files.

All marketplace text is rendered as plain text. Automatic installation is limited to listings marked available for a root-level plugin repository, with a successful compatibility status and a strict `https://github.com/owner/repository` URL. The store constructs fixed argument vectors for Omarchy's own plugin CLI; it never sends a catalog-provided command to a shell. It delegates installation, enablement, and removal to `omarchy plugin`.

Before installing or enabling, the store asks you to review and explicitly confirm. It warns that plugin code is unsandboxed and that `omarchy plugin add` installs the repository's current GitHub HEAD, not a commit-bound marketplace snapshot. Marketplace verification is not a security audit or a guarantee. Review the source, requested capabilities, dependencies, and removal instructions before continuing. Monorepos, suites, failed compatibility checks, and other unsupported layouts are source-only.

The store uses `omarchy plugin list --json` to show installed state. It does not automatically update plugins. Removing a plugin uses Omarchy's removal command and removes its checkout; it does not offer to erase any separate data a plugin may have created.

## Remove

```sh
omarchy plugin remove nate.omarchystore
```

## Dependencies and data

Runtime dependencies are Omarchy Quickshell/Qt networking and the `omarchy` plugin CLI. The catalog request requires an internet connection. Source links open in the system browser only after the repository URL passes validation. No analytics or telemetry are sent by this plugin. The plugin stores no user data.

## Development checks

```sh
omarchy plugin validate .
node --test test-model.js
qmllint -I "$OMARCHY_PATH/shell" BarWidget.qml Panel.qml
```

## License

MIT. See [LICENSE](LICENSE).
