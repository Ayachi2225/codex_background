#!/usr/bin/env python3
"""Offline tests for macOS, Windows, and Linux platform adapters."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT_DIR = (
    Path(__file__).resolve().parents[1] / "plugins" / "codex_background" / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

from codex_background_platforms import create_platform  # noqa: E402
from codex_background_platforms.base import (  # noqa: E402
    BackgroundError,
    PlatformContext,
    debug_switches,
)
from codex_background_platforms.linux import LinuxPlatform, desktop_exec_quote  # noqa: E402
from codex_background_platforms.macos import MacOSPlatform  # noqa: E402
from codex_background_platforms.windows import (  # noqa: E402
    WindowsPlatform,
    parse_pid_lines,
    powershell_quote,
)


class FakeProcess:
    pid = 4242


def make_context(root: Path) -> PlatformContext:
    return PlatformContext(
        plugin_root=root,
        script_path=root / "scripts" / "codex_background.py",
        runtime_dir=root / ".runtime",
        log_path=root / ".runtime" / "background.log",
    )


def capture_launch(adapter, port: int | None, profile: Path | None = None) -> list[str]:
    captured: list[str] = []

    def fake_popen(command: list[str], **_kwargs):
        captured.extend(command)
        return FakeProcess()

    adapter._popen = fake_popen
    assert adapter.launch_app(port, profile) == 4242
    return captured


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        fake_app = root / "ChatGPT.exe"
        fake_app.write_bytes(b"test")
        context = make_context(root)

        with patch.dict(
            os.environ, {"CODEX_BACKGROUND_APP": str(fake_app)}, clear=False
        ):
            mac = MacOSPlatform(context)
            windows = WindowsPlatform(context)
            linux = LinuxPlatform(context)
            assert mac.find_app() == fake_app.resolve()
            assert windows.find_app() == fake_app.resolve()
            assert linux.find_app() == fake_app.resolve()
            profile = root / "isolated profile"
            expected = debug_switches(9229, profile)
            assert capture_launch(mac, 9229, profile)[1:] == expected
            assert capture_launch(windows, 9229, profile)[1:] == expected
            assert capture_launch(linux, 9229, profile)[1:] == expected
            assert expected[0] == f"--user-data-dir={profile}"
            resolved_fake_app = fake_app.resolve()
            mac._process_table = lambda: (
                f"101 {resolved_fake_app} --remote-debugging-port=9229\n"
                f"102 {resolved_fake_app}\n"
            )
            assert mac.app_debug_pids(9229) == {101}

            windows._run_powershell = lambda _script: SimpleNamespace(
                returncode=0,
                stdout="303\n404\n",
                stderr="",
            )
            assert windows.app_debug_pids(9229) == {303, 404}

        with patch.dict(os.environ, {"APPDATA": str(root / "AppData")}, clear=False):
            windows = WindowsPlatform(context)
            startup = windows.startup_file_content()
            assert startup.startswith("@echo off")
            assert "_monitor" in startup
            assert windows.startup_path.name == "Codex Background Monitor.cmd"

        with patch.dict(
            os.environ,
            {"LOCALAPPDATA": str(root / "LocalAppData")},
            clear=False,
        ):
            assert WindowsPlatform(context).profile_dir() == (
                root / "LocalAppData" / "codex_background" / "Profile"
            )

        with patch.dict(
            os.environ,
            {
                "APPDATA": str(root / "AppData"),
                "CODEX_BACKGROUND_APP": str(fake_app),
            },
            clear=False,
        ):
            windows = WindowsPlatform(context)
            assert 'set "CODEX_BACKGROUND_APP=' in windows.startup_file_content()
            installed = Path(windows.enable_autostart())
            assert installed.is_file()
            assert "_monitor" in installed.read_text(encoding="utf-8")
            windows.disable_autostart()
            assert not installed.exists()

        with patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
            },
            clear=False,
        ):
            linux = LinuxPlatform(context)
            assert linux.profile_dir() == root / "data" / "codex_background" / "Profile"
            desktop_entry = linux.desktop_entry_content()
            assert desktop_entry.startswith("[Desktop Entry]")
            assert "X-GNOME-Autostart-enabled=true" in desktop_entry
            assert "_monitor" in desktop_entry
            installed = Path(linux.enable_autostart())
            assert installed.is_file()
            linux.disable_autostart()
            assert not installed.exists()

        with patch.object(LinuxPlatform, "running_in_wsl", return_value=True):
            assert "WSL" in LinuxPlatform(context).doctor_problems()[0]

        assert (
            create_platform(
                root,
                context.script_path,
                context.runtime_dir,
                context.log_path,
                platform_name="darwin",
            ).key
            == "macos"
        )
        assert (
            create_platform(
                root,
                context.script_path,
                context.runtime_dir,
                context.log_path,
                platform_name="win32",
            ).key
            == "windows"
        )
        assert (
            create_platform(
                root,
                context.script_path,
                context.runtime_dir,
                context.log_path,
                platform_name="linux",
            ).key
            == "linux"
        )
        try:
            create_platform(
                root,
                context.script_path,
                context.runtime_dir,
                context.log_path,
                platform_name="plan9",
            )
        except BackgroundError as exc:
            assert "plan9" in str(exc)
        else:
            raise AssertionError("unsupported platform must fail")

    assert powershell_quote("C:\\O'Brien\\ChatGPT.exe") == "'C:\\O''Brien\\ChatGPT.exe'"
    assert parse_pid_lines("101\ninvalid\n202\n") == {101, 202}
    assert desktop_exec_quote('/opt/Chat GPT/"app"') == '"/opt/Chat GPT/\\"app\\""'
    print("platform adapter tests passed")


if __name__ == "__main__":
    main()
