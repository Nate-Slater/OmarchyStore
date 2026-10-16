# Security review

## Trust boundary

Omarchy Store runs as a standalone GTK process, separate from `omarchy-shell`. It is not sandboxed and has the permissions of the logged-in user. It can fetch the public plugin catalog and run Omarchy's plugin-management CLI after an in-app confirmation. Installing or enabling a third-party plugin runs that plugin as unsandboxed code in Omarchy's shell; separating the store process does not isolate an installed plugin.

## Untrusted catalog handling

- The only catalog endpoint is `https://plugins.omarchy.org/catalog.json`; redirects to a different URL are rejected.
- Catalog size, entry count, and displayed field lengths are bounded.
- Listing content is rendered as GTK text, not markup or executable code.
- Marketplace-provided install commands are ignored.
- Automatic install is limited to root-level compatible listings and a strict HTTPS GitHub owner/repository URL. The app constructs the git URL itself.
- No remote preview images, scripts, or repository assets are loaded.

## Plugin management

All subprocesses use an argument vector and `shell=False`. The app delegates to `omarchy plugin list --json`, `omarchy plugin add`, `omarchy plugin enable`, and `omarchy plugin remove`; it does not implement a downloader, installer, update mechanism, or privilege escalation. Install and enable require confirmation. Confirmation explains the unsandboxed execution boundary and that `plugin add` uses current upstream HEAD rather than a marketplace-verified commit. The app does not automatically update plugins.

Marketplace verification is listing metadata only, not a security audit, endorsement, or guarantee. Review plugin source and dependencies before installing. The app itself stores no catalog cache or user data and sends no telemetry; Omarchy's CLI writes the installed plugin files when requested.

## Verification

```sh
python3 -m unittest -v
python3 -c 'import ast; ast.parse(open("app.py", encoding="utf-8").read())'
```

The unit tests cover catalog validation, GitHub URL allowlisting, unsupported layouts, fixed CLI arguments, search, and installed-list parsing. UI runtime testing requires a graphical GTK session.
