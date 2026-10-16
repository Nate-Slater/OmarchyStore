# Security review

## Trust boundaries

Omarchy runs plugins as unsandboxed code in the user's long-running `omarchy-shell` process. This plugin has network access to the public marketplace catalog and can start the Omarchy plugin-management CLI after an in-panel confirmation. Anyone installing this plugin must trust its source with the permissions of their user account.

The catalog is untrusted input. The store filters and bounds fields, renders text with `Text.PlainText`, ignores marketplace-provided install commands, and accepts automatic-install repositories only when they match a strict HTTPS GitHub owner/repository URL. It only offers automatic installation for root-level repositories marked available and not marked compatibility-failed. The final CLI invocation is a fixed executable plus argument vector; no shell command string is assembled from listing data.

Installing or enabling third-party plugin code requires a separate confirmation that explains the unsandboxed execution boundary and mutable upstream HEAD behavior. The marketplace's verification status is displayed as listing metadata, not as an endorsement or security certification. The installer does not pin to a marketplace commit because Omarchy's plugin add command does not support exact-SHA installation.

## Network and persistence

- One HTTPS GET to `https://plugins.omarchy.org/catalog.json` retrieves catalog metadata. The plugin supplies no credentials or authorization headers.
- No remote preview images, scripts, or other listing assets are loaded.
- Source links are opened only for validated GitHub repositories.
- The plugin does not persist catalog data, user data, or telemetry.
- The Omarchy CLI performs the git clone/update/removal filesystem operations. This plugin does not implement its own downloader or installer.

## Verification

```sh
omarchy plugin validate .
node --test test-model.js
qmllint -I "$OMARCHY_PATH/shell" BarWidget.qml Panel.qml
```

The Node tests cover repository URL validation, catalog filtering, unsupported layouts, failed compatibility status, fixed argv generation, metadata search, and installed-list parsing. QML lint and runtime checks require an Omarchy Quickshell installation.
