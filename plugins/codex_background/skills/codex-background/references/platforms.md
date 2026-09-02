# Platform behavior

Read only the section for the user's current platform.

## macOS

- Default executable: `/Applications/ChatGPT.app/Contents/MacOS/ChatGPT`.
- Clean quit uses the application bundle identifier.
- Autostart uses `~/Library/LaunchAgents/com.codex-background.monitor.plist`.
- Background mode profile: `~/Library/Application Support/codex_background/Profile`.
- `launchctl print gui/<uid>/com.codex-background.monitor` can verify the login monitor.
- This adapter is stable and has been exercised on a real macOS installation.

## Native Windows

- Run the helper from the Windows-native PowerShell Agent, not WSL.
- Discovery checks common per-user install paths, then the current user's AppX packages for `ChatGPT.exe`.
- If discovery fails, ask the user to locate `ChatGPT.exe` and set `CODEX_BACKGROUND_APP` for the current session. Never guess a private user path.
- Enabling autostart captures the current `CODEX_BACKGROUND_APP` value in the local startup file so the override survives sign-in. Reinstall the startup item after the path changes.
- Autostart uses `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Codex Background Monitor.cmd`.
- Background mode profile: `%LOCALAPPDATA%\codex_background\Profile`.
- `start` first closes the matching executable's processes, then launches the executable with loopback-only Chromium debugging switches.
- The Microsoft Store/MSIX build may reject direct executable launch or strip switches. If the endpoint does not become ready, collect `doctor`, `status`, and `.runtime/background.log`; restore the original launch before proposing another mechanism.
- Treat this adapter as experimental until `doctor`, `start`, `status`, `restore`, and one normal auto-loaded launch succeed on a real Windows device.

## Linux

- The official Linux desktop app is in preview. Treat this adapter as experimental.
- Discovery prefers `CODEX_BACKGROUND_APP`, then the `chatgpt` command and common `/usr` or `/opt` locations.
- Process matching uses `/proc/<pid>/exe`.
- Autostart uses `${XDG_CONFIG_HOME:-~/.config}/autostart/codex-background-monitor.desktop`.
- Background mode profile: `${XDG_DATA_HOME:-~/.local/share}/codex_background/Profile`.
- WSL is deliberately rejected because it does not represent a native Linux desktop app and cannot safely control the Windows app through this adapter.
- Do not mark Linux stable until it passes the same lifecycle checks as Windows on a supported `.deb` or `.rpm` installation.
