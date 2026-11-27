# Releasing

## Build installers (GitHub Actions)

1. Update the version in `app/package.json`, `app/src-tauri/Cargo.toml` and `app/src-tauri/tauri.conf.json`.
2. Commit, then tag and push: `git tag v1.0.0 && git push origin v1.0.0`.
3. The **Release** workflow builds on GitHub's machines and attaches the installers to a **draft** release:
   - Windows: `.msi` and `.exe` (NSIS)
   - macOS: universal `.dmg` (Apple Silicon + Intel)
   - Linux: `.deb` and `.AppImage`
4. Check the draft, then publish it.

The **CI** workflow runs on every push / pull request: UI type-check + build, Rust unit tests on Linux,
and a compile + unit-test run on macOS and Windows.

## Signing (optional, needs paid certificates)

Unsigned builds work, but users see warnings:

- **macOS** — Gatekeeper says the app is from an unidentified developer (right-click → Open the first time).
  To sign and notarize: an Apple Developer account (99 USD/year), then add these repository secrets and
  pass them to `tauri-action` as env: `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`,
  `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`.
- **Windows** — SmartScreen may warn on first run. A code-signing certificate (OV/EV) removes it; configure
  `bundle.windows.certificateThumbprint` or a signing command in `tauri.conf.json`.
- **Linux** — no signing needed.

See https://v2.tauri.app/distribute/sign/ for the details.

## Before the first public release

- Verify on a real **Windows** PC and a real **Mac** with TeamLogger installed (plan milestone 7):
  install path detection, **Connect** (restart with `--remote-debugging-port`), take break / resume,
  notifications and sounds. These adapters are written but unverified.
- TeamLogger is another company's product: keep the "unofficial, not affiliated" note everywhere.
