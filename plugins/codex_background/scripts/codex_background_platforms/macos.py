"""macOS lifecycle integration."""

from __future__ import annotations

import os
from pathlib import Path
import plistlib
import subprocess
import time

from .base import (
    BackgroundError,
    PlatformAdapter,
    debug_switches,
    parse_posix_process_table,
)


APP_PATH = Path("/Applications/ChatGPT.app")
DEFAULT_BINARY = APP_PATH / "Contents" / "MacOS" / "ChatGPT"
LAUNCH_AGENT_LABEL = "com.codex-background.monitor"


class MacOSPlatform(PlatformAdapter):
    key = "macos"
    display_name = "macOS"
    maturity = "stable"
    autostart_starts_immediately = True

    @property
    def launch_agent_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"

    def find_app(self) -> Path:
        override = os.environ.get("CODEX_BACKGROUND_APP")
        candidate = Path(override).expanduser() if override else DEFAULT_BINARY
        if not candidate.is_file():
            raise BackgroundError(
                f"找不到 ChatGPT/Codex 应用：{candidate}。"
                "可用 CODEX_BACKGROUND_APP 指定应用可执行文件。"
            )
        return candidate.resolve()

    def app_description(self) -> str:
        return str(
            APP_PATH if not os.environ.get("CODEX_BACKGROUND_APP") else self.find_app()
        )

    def app_pids(self) -> set[int]:
        executable = self.find_app()
        process_table = self._process_table()
        return parse_posix_process_table(process_table, executable)

    @staticmethod
    def _process_table() -> str:
        result = subprocess.run(
            ["ps", "axww", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode:
            return ""
        return result.stdout

    def app_debug_pids(self, port: int) -> set[int]:
        executable = self.find_app()
        flag = f"--remote-debugging-port={port}"
        table = self._process_table()
        return {
            pid
            for pid in parse_posix_process_table(table, executable)
            if any(
                line.strip().startswith(f"{pid} ") and flag in line
                for line in table.splitlines()
            )
        }

    def quit_app(self) -> None:
        subprocess.run(
            ["osascript", "-e", 'tell application id "com.openai.codex" to quit'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        time.sleep(3)

    def launch_app(self, port: int | None) -> int:
        command = [str(self.find_app())]
        if port is not None:
            command.extend(debug_switches(port))
        return self._popen(command).pid

    def launch_agent_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "Label": LAUNCH_AGENT_LABEL,
            "ProgramArguments": [
                str(self.context.python_executable),
                str(self.context.script_path),
                "_monitor",
            ],
            "RunAtLoad": True,
            "ProcessType": "Interactive",
            "LimitLoadToSessionType": "Aqua",
            "StandardOutPath": str(self.context.runtime_dir / "login-agent.log"),
            "StandardErrorPath": str(self.context.runtime_dir / "login-agent.log"),
        }
        override = os.environ.get("CODEX_BACKGROUND_APP")
        if override:
            payload["EnvironmentVariables"] = {"CODEX_BACKGROUND_APP": override}
        return payload

    def _launchctl_domain(self) -> str:
        return f"gui/{os.getuid()}"

    def autostart_description(self) -> str:
        return str(self.launch_agent_path)

    def enable_autostart(self) -> str:
        path = self.launch_agent_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(
            plistlib.dumps(self.launch_agent_payload(), fmt=plistlib.FMT_XML)
        )
        subprocess.run(
            ["launchctl", "bootout", self._launchctl_domain(), str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        result = subprocess.run(
            ["launchctl", "bootstrap", self._launchctl_domain(), str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise BackgroundError(
                f"无法启用登录自动加载：{detail or result.returncode}"
            )
        return str(path)

    def disable_autostart(self) -> None:
        path = self.launch_agent_path
        subprocess.run(
            ["launchctl", "bootout", self._launchctl_domain(), str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        try:
            path.unlink()
        except FileNotFoundError:
            pass
