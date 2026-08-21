"""Shared platform primitives for the codex_background helper."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class BackgroundError(RuntimeError):
    """User-facing helper failure."""


@dataclass(frozen=True)
class PlatformContext:
    plugin_root: Path
    script_path: Path
    runtime_dir: Path
    log_path: Path

    @property
    def python_executable(self) -> Path:
        return Path(sys.executable).resolve()


def debug_switches(port: int) -> list[str]:
    return [
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--remote-allow-origins=http://127.0.0.1:{port}",
    ]


def parse_posix_process_table(process_table: str, executable: Path) -> set[int]:
    prefix = str(executable)
    pids: set[int] = set()
    for line in process_table.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid_text, command = parts
        if command != prefix and not command.startswith(prefix + " "):
            continue
        try:
            pids.add(int(pid_text))
        except ValueError:
            continue
    return pids


class PlatformAdapter:
    """Operating-system boundary used by the cross-platform core."""

    key = "unknown"
    display_name = "Unknown"
    maturity = "unsupported"
    autostart_starts_immediately = False

    def __init__(self, context: PlatformContext) -> None:
        self.context = context

    def find_app(self) -> Path:
        raise NotImplementedError

    def app_description(self) -> str:
        return str(self.find_app())

    def app_pids(self) -> set[int]:
        raise NotImplementedError

    def app_debug_pids(self, port: int) -> set[int]:
        return set()

    def quit_app(self) -> None:
        raise NotImplementedError

    def launch_app(self, port: int | None) -> int:
        raise NotImplementedError

    def autostart_description(self) -> str:
        raise NotImplementedError

    def enable_autostart(self) -> str:
        raise NotImplementedError

    def disable_autostart(self) -> None:
        raise NotImplementedError

    def doctor_problems(self) -> list[str]:
        try:
            self.find_app()
        except BackgroundError as exc:
            return [str(exc)]
        return []

    def process_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    def terminate_process(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return

    def _popen(self, command: list[str], *, log_handle=None) -> subprocess.Popen[bytes]:
        kwargs: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": log_handle if log_handle is not None else subprocess.DEVNULL,
            "stderr": subprocess.STDOUT
            if log_handle is not None
            else subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = int(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            ) | int(getattr(subprocess, "DETACHED_PROCESS", 0))
        else:
            kwargs["start_new_session"] = True
        try:
            return subprocess.Popen(command, **kwargs)
        except OSError as exc:
            raise BackgroundError(f"无法启动进程：{exc}") from exc

    def spawn_helper(self, mode: str) -> int:
        self.context.runtime_dir.mkdir(parents=True, exist_ok=True)
        log_handle = self.context.log_path.open("a", encoding="utf-8")
        try:
            process = self._popen(
                [
                    str(self.context.python_executable),
                    str(self.context.script_path),
                    mode,
                ],
                log_handle=log_handle,
            )
        finally:
            log_handle.close()
        return process.pid

    @staticmethod
    def wait_for_pids_to_exit(pids: set[int], timeout: float = 5.0) -> set[int]:
        deadline = time.monotonic() + timeout
        remaining = set(pids)
        while remaining and time.monotonic() < deadline:
            alive: set[int] = set()
            for pid in remaining:
                try:
                    os.kill(pid, 0)
                    alive.add(pid)
                except OSError:
                    pass
            remaining = alive
            if remaining:
                time.sleep(0.2)
        return remaining
