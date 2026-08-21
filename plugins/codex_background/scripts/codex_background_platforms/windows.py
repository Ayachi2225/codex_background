"""Windows lifecycle integration for the native desktop app."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

from .base import BackgroundError, PlatformAdapter, debug_switches


STARTUP_FILENAME = "Codex Background Monitor.cmd"


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parse_pid_lines(output: str) -> set[int]:
    pids: set[int] = set()
    for line in output.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 0:
            pids.add(pid)
    return pids


class WindowsPlatform(PlatformAdapter):
    key = "windows"
    display_name = "Windows"
    maturity = "experimental"

    @property
    def startup_path(self) -> Path:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise BackgroundError("缺少 APPDATA，无法定位 Windows 启动目录")
        return (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / STARTUP_FILENAME
        )

    def _powershell(self) -> str:
        command = (
            shutil.which("powershell.exe")
            or shutil.which("powershell")
            or shutil.which("pwsh")
        )
        if not command:
            raise BackgroundError(
                "找不到 PowerShell；Windows 原生版本需要 powershell.exe 或 pwsh"
            )
        return command

    def _run_powershell(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self._powershell(),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    def _common_candidates(self) -> list[Path]:
        roots = [
            os.environ.get("LOCALAPPDATA"),
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
        ]
        suffixes = [
            ("Programs", "ChatGPT", "ChatGPT.exe"),
            ("OpenAI", "ChatGPT", "ChatGPT.exe"),
            ("ChatGPT", "ChatGPT.exe"),
        ]
        return [
            Path(root).joinpath(*suffix)
            for root in roots
            if root
            for suffix in suffixes
        ]

    def find_app(self) -> Path:
        override = os.environ.get("CODEX_BACKGROUND_APP")
        if override:
            candidate = Path(override).expanduser()
            if candidate.is_file():
                return candidate.resolve()
            raise BackgroundError(f"CODEX_BACKGROUND_APP 指向的文件不存在：{candidate}")

        for candidate in self._common_candidates():
            if candidate.is_file():
                return candidate.resolve()

        script = (
            "$packages = @(Get-AppxPackage | Where-Object { $_.Name -match 'ChatGPT' }); "
            "foreach ($package in $packages) { "
            "$exe = Get-ChildItem -LiteralPath $package.InstallLocation -Filter ChatGPT.exe "
            "-File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($exe) { $exe.FullName; break } }"
        )
        result = self._run_powershell(script)
        for line in result.stdout.splitlines():
            candidate = Path(line.strip())
            if candidate.is_file():
                return candidate.resolve()
        detail = (result.stderr or result.stdout).strip()
        suffix = f" PowerShell: {detail}" if detail else ""
        raise BackgroundError(
            "找不到 Windows ChatGPT/Codex 可执行文件。"
            "请将 CODEX_BACKGROUND_APP 设置为 ChatGPT.exe 的绝对路径。" + suffix
        )

    def app_pids(self) -> set[int]:
        executable = powershell_quote(str(self.find_app()))
        script = (
            f"$target = [IO.Path]::GetFullPath({executable}); "
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ExecutablePath -and "
            "([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $target) } | "
            "ForEach-Object { $_.ProcessId }"
        )
        result = self._run_powershell(script)
        return parse_pid_lines(result.stdout) if result.returncode == 0 else set()

    def app_debug_pids(self, port: int) -> set[int]:
        executable = powershell_quote(str(self.find_app()))
        flag = powershell_quote(f"*--remote-debugging-port={port}*")
        script = (
            f"$target = [IO.Path]::GetFullPath({executable}); "
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ExecutablePath -and $_.CommandLine -and "
            "([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $target) -and "
            f"($_.CommandLine -like {flag}) }} | "
            "ForEach-Object { $_.ProcessId }"
        )
        result = self._run_powershell(script)
        return parse_pid_lines(result.stdout) if result.returncode == 0 else set()

    def quit_app(self) -> None:
        pids = self.app_pids()
        if not pids:
            return
        ids = ",".join(str(pid) for pid in sorted(pids))
        close_script = (
            f"Get-Process -Id {ids} -ErrorAction SilentlyContinue | "
            "ForEach-Object { [void]$_.CloseMainWindow() }"
        )
        self._run_powershell(close_script)
        time.sleep(3)
        remaining = self.app_pids()
        if remaining:
            force_ids = ",".join(str(pid) for pid in sorted(remaining))
            self._run_powershell(
                f"Stop-Process -Id {force_ids} -Force -ErrorAction SilentlyContinue"
            )
            time.sleep(1)

    def launch_app(self, port: int | None) -> int:
        command = [str(self.find_app())]
        if port is not None:
            command.extend(debug_switches(port))
        return self._popen(command).pid

    def startup_file_content(self) -> str:
        python = str(self.context.python_executable).replace('"', '""')
        script = str(self.context.script_path).replace('"', '""')
        override = os.environ.get("CODEX_BACKGROUND_APP")
        override_line = ""
        if override:
            override_line = (
                f'set "CODEX_BACKGROUND_APP={override.replace("%", "%%")}"\n'
            )
        return (
            "@echo off\n"
            + override_line
            + f'start "" /min "{python}" "{script}" _monitor\n'
        )

    def autostart_description(self) -> str:
        return str(self.startup_path)

    def enable_autostart(self) -> str:
        path = self.startup_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.startup_file_content(), encoding="utf-8")
        return str(path)

    def disable_autostart(self) -> None:
        try:
            self.startup_path.unlink()
        except FileNotFoundError:
            pass

    def doctor_problems(self) -> list[str]:
        problems = super().doctor_problems()
        try:
            self._powershell()
        except BackgroundError as exc:
            problems.append(str(exc))
        return problems
