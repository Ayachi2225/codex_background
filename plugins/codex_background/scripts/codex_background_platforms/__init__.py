"""Platform selection for codex_background."""

from __future__ import annotations

from pathlib import Path
import sys

from .base import BackgroundError, PlatformAdapter, PlatformContext
from .linux import LinuxPlatform
from .macos import MacOSPlatform
from .windows import WindowsPlatform


def create_platform(
    plugin_root: Path,
    script_path: Path,
    runtime_dir: Path,
    log_path: Path,
    *,
    platform_name: str | None = None,
) -> PlatformAdapter:
    name = platform_name or sys.platform
    context = PlatformContext(
        plugin_root=plugin_root,
        script_path=script_path,
        runtime_dir=runtime_dir,
        log_path=log_path,
    )
    if name == "darwin":
        return MacOSPlatform(context)
    if name == "win32" or name.startswith("cygwin"):
        return WindowsPlatform(context)
    if name.startswith("linux"):
        return LinuxPlatform(context)
    raise BackgroundError(f"不支持的操作系统：{name}")


__all__ = [
    "BackgroundError",
    "LinuxPlatform",
    "MacOSPlatform",
    "PlatformAdapter",
    "PlatformContext",
    "WindowsPlatform",
    "create_platform",
]
