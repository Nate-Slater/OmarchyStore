# Omarchy Store

Omarchy Store is a standalone GTK 4 / libadwaita desktop application for browsing the [Omarchy Plugin Marketplace](https://plugins.omarchy.org/). Its dark, accent-colored card catalog makes it easy to search community plugins, review listing and verification metadata, check installed state, and install, enable, or remove supported plugins.

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

The catalog can be browsed without Omarchy. Install, enable, remove, and installed-state features use the `omarchy` CLI and require an Omarchy installation.

## Security

The app is a separate process from `omarchy-shell`, but it is **not sandboxed**: it runs with your user permissions. Review [SECURITY.md](SECURITY.md) before using plugin-management actions.

Marketplace data is untrusted input. The app displays listing fields as GTK text, ignores marketplace-provided install commands, and only offers automatic installs for compatible root-level repositories with strict `https://github.com/owner/repository` URLs. It invokes `omarchy plugin` with fixed argument vectors; it does not invoke a shell or run downloaded code itself.

Install and enable actions require an explicit confirmation explaining that third-party plugin code will run unsandboxed and that Omarchy installs mutable upstream HEAD, not a commit-bound verified snapshot. Marketplace verification is not a security audit or guarantee. Review plugin source, dependencies, and requested access before proceeding. Monorepos, suites, failed compatibility checks, and unsupported layouts are source-only.

The app does not automatically update installed plugins. Removal delegates to Omarchy and does not delete data a plugin may have stored elsewhere.

Remove the standalone app with `./uninstall.sh`. This removes only its launcher, desktop entry, and two installed program files; it leaves any unexpected files in the app directory untouched.

## Network and data

The app fetches the public `https://plugins.omarchy.org/catalog.json` over HTTPS. It loads no remote images or scripts and sends no telemetry. It stores no catalog cache or user data. Repository links open in the system browser only after GitHub URL validation.

## Development checks

```sh
python3 -m unittest -v
python3 -c 'import ast; ast.parse(open("app.py", encoding="utf-8").read())'
```

## License

MIT. See [LICENSE](LICENSE).
