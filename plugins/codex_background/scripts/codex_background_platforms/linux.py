"""Experimental Linux lifecycle integration."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import time

from .base import BackgroundError, PlatformAdapter, debug_switches


def desktop_exec_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


class LinuxPlatform(PlatformAdapter):
    key = "linux"
    display_name = "Linux"
    maturity = "experimental"

    @property
    def autostart_path(self) -> Path:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_home / "autostart" / "codex-background-monitor.desktop"

    def find_app(self) -> Path:
        if self.running_in_wsl():
            raise BackgroundError(
                "WSL Agent 模式尚未支持；请切换到 Windows 原生 PowerShell Agent。"
            )
        override = os.environ.get("CODEX_BACKGROUND_APP")
        candidates = [
            Path(override).expanduser() if override else None,
            Path(shutil.which("chatgpt")) if shutil.which("chatgpt") else None,
            Path("/usr/bin/chatgpt"),
            Path("/usr/local/bin/chatgpt"),
            Path("/opt/chatgpt/chatgpt"),
            Path("/opt/ChatGPT/chatgpt"),
        ]
        for candidate in candidates:
            if candidate is not None and candidate.is_file():
                return candidate.resolve()
        raise BackgroundError(
            "找不到 Linux ChatGPT/Codex 可执行文件。"
            "请确认 chatgpt 命令可用，或设置 CODEX_BACKGROUND_APP。"
        )

    @staticmethod
    def running_in_wsl() -> bool:
        try:
            version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        return "microsoft" in version.lower()

    def doctor_problems(self) -> list[str]:
        if self.running_in_wsl():
            return [
                "当前运行环境是 WSL。Windows 桌面应用适配器需要在 Windows 原生 "
                "PowerShell Agent 中运行；WSL 桥接尚未支持。"
            ]
        return super().doctor_problems()

    def app_pids(self) -> set[int]:
        executable = self.find_app()
        pids: set[int] = set()
        proc = Path("/proc")
        if not proc.is_dir():
            return pids
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                target = (entry / "exe").resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if target == executable:
                pids.add(int(entry.name))
        return pids

    def app_debug_pids(self, port: int) -> set[int]:
        flag = f"--remote-debugging-port={port}"
        matches: set[int] = set()
        for pid in self.app_pids():
            try:
                command = (
                    (Path("/proc") / str(pid) / "cmdline")
                    .read_bytes()
                    .replace(b"\0", b" ")
                )
            except OSError:
                continue
            if flag.encode("utf-8") in command:
                matches.add(pid)
        return matches

    def quit_app(self) -> None:
        pids = self.app_pids()
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        remaining = self.wait_for_pids_to_exit(pids, timeout=5)
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if pids:
            time.sleep(1)

    def launch_app(self, port: int | None) -> int:
        command = [str(self.find_app())]
        if port is not None:
            command.extend(debug_switches(port))
        return self._popen(command).pid

    def desktop_entry_content(self) -> str:
        parts = [
            str(self.context.python_executable),
            str(self.context.script_path),
            "_monitor",
        ]
        override = os.environ.get("CODEX_BACKGROUND_APP")
        if override:
            parts = ["/usr/bin/env", f"CODEX_BACKGROUND_APP={override}", *parts]
        command = " ".join(desktop_exec_quote(part) for part in parts)
        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Codex Background Monitor\n"
            f"Exec={command}\n"
            "Terminal=false\n"
            "NoDisplay=true\n"
            "X-GNOME-Autostart-enabled=true\n"
        )

    def autostart_description(self) -> str:
        return str(self.autostart_path)

    def enable_autostart(self) -> str:
        if self.running_in_wsl():
            raise BackgroundError(
                "WSL Agent 模式尚未支持；不能安装 Linux 桌面自动启动项。"
            )
        path = self.autostart_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.desktop_entry_content(), encoding="utf-8")
        return str(path)

    def disable_autostart(self) -> None:
        if self.running_in_wsl():
            raise BackgroundError(
                "WSL Agent 模式尚未支持；没有可管理的 Linux 桌面自动启动项。"
            )
        try:
            self.autostart_path.unlink()
        except FileNotFoundError:
            pass
