# Omarchy Store

Omarchy Store is a standalone GTK 4 / libadwaita desktop application for browsing the [Omarchy Plugin Marketplace](https://plugins.omarchy.org/). Colors, accents, and the hero artwork come from the active Omarchy theme and update live when that theme changes. **Discover** shows **Hidden Gems** and the animated two-row **Just Landed** feed. **Browse** is the full catalog: search, category and install-state filters, sorting, and plugin details.

## Run

On Arch Linux / Omarchy, install the system UI dependencies if needed:

```sh
sudo pacman -S gtk4 libadwaita python-gobject
```

Then install it for your user (no root access required):

```sh
./install.sh
omarchy-store
```

You can also run it directly from the checkout with `./omarchy-store` or `python3 app.py`.

Discover scrolls through the feeds. Clicking a plugin there opens its preview, showing the full marketplace screenshot when one is provided, and returns to Discover when the preview closes. Browse fills the page with plugins. Click a card to open its preview, with artwork and the install action. Press Ctrl+K to jump to search. The catalog can be browsed without Omarchy; install, enable, remove, and installed-state features use the `omarchy` CLI and require an Omarchy installation.

## Security

The app is a separate process from `omarchy-shell`, but it is **not sandboxed**: it runs with your user permissions. Review [SECURITY.md](SECURITY.md) before using plugin-management actions.

Marketplace data is untrusted input. The app displays listing fields as GTK text, ignores marketplace-provided install commands, and only offers automatic installs for compatible root-level repositories with strict `https://github.com/owner/repository` URLs. It invokes `omarchy plugin` with fixed argument vectors; it does not invoke a shell or run downloaded code itself.

Install and enable actions require an explicit confirmation explaining that third-party plugin code will run unsandboxed and that Omarchy installs mutable upstream HEAD, not a commit-bound verified snapshot. Marketplace verification is not a security audit or guarantee. Review plugin source, dependencies, and requested access before proceeding. Monorepos, suites, failed compatibility checks, and unsupported layouts are source-only.

The app does not automatically update installed plugins. Removal delegates to Omarchy and does not delete data a plugin may have stored elsewhere.

Remove the standalone app with `./uninstall.sh`. This removes its launcher, desktop entry, program files, and generated Python bytecode; it leaves any unexpected files in the app directory untouched.

## Network and data

The app fetches the public `https://plugins.omarchy.org/catalog.json` and aggregate engagement stats from `https://api.omarchyplugins.com/v1/stats` over HTTPS. It loads listing thumbnails only from validated marketplace image paths. Image downloads are size-limited, redirect-free, and cached in memory; arbitrary hosts and scripts are never loaded. Requests disclose normal network metadata to these hosts. The app sends no engagement events, telemetry, or user data and stores no catalog cache. Repository links open in the system browser only after GitHub URL validation.

## Development checks

```sh
python3 -m unittest -v
python3 -c 'import ast; ast.parse(open("app.py", encoding="utf-8").read())'
```

## License

MIT. See [LICENSE](LICENSE).
