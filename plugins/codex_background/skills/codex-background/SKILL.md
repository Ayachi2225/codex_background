---
name: codex-background
description: Enable, disable, inspect, configure, or replace the user's reversible local background image for the ChatGPT/Codex desktop app. Use when the user asks to turn the Codex background on or off, restore the original appearance, check background status, change the image, or adjust opacity, blur, fit, or position.
---

# Codex Background

Manage the reversible runtime background supplied by this personal plugin.

## Boundaries

- Never edit `/Applications/ChatGPT.app`, `app.asar`, its resources, or its code signature.
- Treat `../../` from this `SKILL.md` directory as the plugin root.
- Immediate enable or full restore restarts the desktop app and interrupts the current UI session. State that clearly before running either command. Enabling or disabling login autostart never restarts the current app.
- The helper opens a Chromium debugging endpoint on `127.0.0.1` only while the custom background session is active. Mention this when the user asks about security.
- Prefer the plugin script over hand-editing runtime state.

## Commands

Resolve the plugin root, then use:

```bash
python3 <plugin-root>/scripts/codex_background.py doctor
python3 <plugin-root>/scripts/codex_background.py status
python3 <plugin-root>/scripts/codex_background.py enable-autostart
python3 <plugin-root>/scripts/codex_background.py disable-autostart
python3 <plugin-root>/scripts/codex_background.py start
python3 <plugin-root>/scripts/codex_background.py restore
python3 <plugin-root>/scripts/codex_background.py set-image /absolute/path/to/image.png
```

### Enable automatically on normal Codex launches

1. Run `doctor` first.
2. Run `enable-autostart`. It installs a per-user macOS LaunchAgent monitor and does not restart the currently running Codex app.
3. Explain that the monitor stays alive for the login session. On a later normal Codex launch from Dock or Finder, it immediately reopens the unmodified executable with loopback-only debugging enabled, then injects and maintains the background. The user may see one brief reopen.
4. The monitor records and ignores the Codex process that was already running when installed, protecting the active task.
5. At a later macOS login, the monitor can start Codex directly in background mode. After the user quits, it waits for the next manual launch and does not force Codex to remain open.
6. Use `disable-autostart` to remove the monitor without restarting Codex.

### Enable

1. Run `doctor` first.
2. Tell the user the desktop app will restart.
3. Run `start`. It launches a detached local supervisor, quits the current app normally, directly relaunches its unmodified executable with a loopback-only debugging port, and injects the background.
4. Do not treat loss of the current desktop connection as failure; the user should see the app reopen with the background.

### Restore

1. Tell the user the desktop app will restart.
2. Run `restore`. It stops the supervisor and relaunches ChatGPT/Codex normally, with no injection or debugging port.

### Replace the image

1. Require an absolute path to a PNG, JPEG, or WebP file.
2. Run `set-image` with that path. The script copies the image into the plugin's `assets/` directory and updates `config.json`.
3. Run `start` to apply it. If an injected session is already active, `start` refreshes the style without modifying the application bundle.

### Adjust appearance

Edit only `config.json`. Keep values within these limits:

- `fit`: `cover`, `contain`, or `fill`
- `backgroundOpacity`, `overlayOpacity`, `panelOpacity`: 0 through 1
- `blurPixels`: 0 through 40
- `position`: CSS background-position text without punctuation beyond spaces, letters, numbers, `%`, `_`, `.` or `-`

Run `doctor` after edits, then `start` to refresh.

## Success checks

- `doctor` reports a valid app bundle, config, image, and Python runtime.
- `launchctl print gui/<uid>/com.codex-background.monitor` reports the monitor as running after `enable-autostart`.
- `status` reports `active` and at least one injected page after enable.
- `restore` removes the supervisor state and relaunches the app without the debugging endpoint.
