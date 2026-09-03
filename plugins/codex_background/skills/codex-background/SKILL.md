---
name: codex-background
description: Enable, disable, inspect, configure, or replace the user's reversible local background image for the ChatGPT/Codex desktop app on macOS, native Windows, or Linux. Use when the user asks to turn the background on or off, restore the original appearance, check status, change the image, or adjust opacity, blur, fit, or position.
---

# Codex Background

Manage the reversible runtime background supplied by this plugin.

## Boundaries

- Never edit the installed application, `app.asar`, application resources, or its code signature.
- Treat `../../` from this `SKILL.md` directory as the plugin root.
- `start` and `restore` restart the desktop app and interrupt the current UI task. State that before running either command.
- Enabling or disabling login autostart does not restart the already-running app.
- The helper launches background mode with a separate Chromium user-data directory and opens an unauthenticated Chromium debugging endpoint on a random `127.0.0.1` port only while that session is active. Mention both facts when the user asks about security.
- Treat the isolated profile as sensitive local data because it may hold sign-in state, cookies, and preferences. Never inspect, copy, upload, or delete it unless the user explicitly asks.
- Prefer the plugin script over hand-editing runtime state.
- macOS is stable. Native Windows and Linux are experimental until their launch behavior is confirmed on the user's device. WSL Agent mode is not supported.

## Select the command

Resolve the plugin root and Python command:

- macOS/Linux: `python3`
- Native Windows PowerShell: `py -3`, falling back to `python`

Use:

```text
<python> <plugin-root>/scripts/codex_background.py doctor
<python> <plugin-root>/scripts/codex_background.py status
<python> <plugin-root>/scripts/codex_background.py enable-autostart
<python> <plugin-root>/scripts/codex_background.py disable-autostart
<python> <plugin-root>/scripts/codex_background.py start
<python> <plugin-root>/scripts/codex_background.py restore
<python> <plugin-root>/scripts/codex_background.py set-image <absolute-image-path>
```

Run `doctor` before the first platform mutation. If it reports WSL, ask the user to switch the Codex Agent to native Windows PowerShell. If it cannot locate the app, use the `CODEX_BACKGROUND_APP` environment variable only after the user supplies or confirms the executable path.

For platform-specific behavior, validation, and autostart locations, read [references/platforms.md](references/platforms.md) only for the current operating system.

## Enable immediately

1. Run `doctor`.
2. Tell the user the desktop app will restart and the current task connection will be interrupted.
3. Run `start`.
4. After the app reopens, run `status` in a new task if verification is requested. Do not treat loss of the original desktop connection as failure.

## Enable automatically

1. Run `doctor`.
2. Run `enable-autostart`.
3. Explain that the current app is protected and is not restarted. The monitor handles later ordinary launches; Windows/Linux also start the monitor for the current login session.
4. Use `disable-autostart` to remove the platform login item and stop the monitor without restarting the app.

## Restore

1. Tell the user the desktop app will restart.
2. Run `restore`. It disables autostart, stops the helper, and relaunches the app without injection or a debugging port.

## Replace the image

1. Require an absolute PNG, JPEG, or WebP path.
2. Run `set-image`. The helper copies the image into the plugin `assets/` directory and updates `config.json`.
3. Run `start` only after disclosing the restart behavior. If an injected session is already active, `start` refreshes the style without restarting.

## Adjust appearance

Edit only `config.json`. Keep values within these limits:

- `fit`: `cover`, `contain`, or `fill`
- `backgroundOpacity`, `overlayOpacity`, `panelOpacity`: 0 through 1
- `blurPixels`: 0 through 40
- `position`: CSS background-position text using spaces, letters, numbers, `%`, `_`, `.`, `+`, or `-`
- `maintenanceIntervalSeconds`: 10 through 3600; controls active renderer health checks and defaults to 60
- `debugPort`: `0` for an automatically selected loopback port, or 1024 through 65535 for a fixed port

Run `doctor` after edits, then `start` to apply them. `panelOpacity` controls interface panels; `backgroundOpacity` controls only the image layer.

## Success checks

- `doctor` reports the intended platform, executable, config, image, Python runtime, loopback-port policy, and isolated profile path.
- `status` reports `active` and at least one injected page after enabling.
- `restore` relaunches the app without the debugging endpoint.
- On experimental platforms, report the exact failing stage and preserve `.runtime/background.log` for troubleshooting; do not claim platform support from offline tests alone.
