#!/usr/bin/env python3
"""Reversible runtime background helper for the ChatGPT/Codex desktop app."""

from __future__ import annotations

import argparse
import atexit
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import sys
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from codex_background_platforms import BackgroundError, create_platform


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent


PLUGIN_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = PLUGIN_ROOT / "config.json"
RUNTIME_DIR = PLUGIN_ROOT / ".runtime"
STATE_PATH = RUNTIME_DIR / "state.json"
LOG_PATH = RUNTIME_DIR / "background.log"
MONITOR_GUARD_PATH = RUNTIME_DIR / "monitor-guard.json"
MONITOR_PID_PATH = RUNTIME_DIR / "monitor.pid"
STYLE_ID = "codex-background-plugin-style"
LAYER_ID = "codex-background-plugin-layer"
OBSERVER_KEY = "__codexBackgroundObserver"
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
PLATFORM = create_platform(PLUGIN_ROOT, SCRIPT_PATH, RUNTIME_DIR, LOG_PATH)


def load_config() -> dict[str, Any]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackgroundError(f"无法读取 config.json：{exc}") from exc

    fit = config.get("fit", "cover")
    if fit not in {"cover", "contain", "fill"}:
        raise BackgroundError("config.json 的 fit 必须是 cover、contain 或 fill")

    position = str(config.get("position", "center center"))
    if not re.fullmatch(r"[A-Za-z0-9 ._%+-]+", position):
        raise BackgroundError("config.json 的 position 含有不支持的字符")

    for key in ("backgroundOpacity", "overlayOpacity", "panelOpacity"):
        value = float(config.get(key, 0.5))
        if not 0 <= value <= 1:
            raise BackgroundError(f"config.json 的 {key} 必须在 0 到 1 之间")
        config[key] = value

    blur = int(config.get("blurPixels", 0))
    if not 0 <= blur <= 40:
        raise BackgroundError("config.json 的 blurPixels 必须在 0 到 40 之间")
    config["blurPixels"] = blur

    port = int(config.get("debugPort", 0))
    if port != 0 and not 1024 <= port <= 65535:
        raise BackgroundError(
            "config.json 的 debugPort 必须是 0（自动选择）或 1024 到 65535"
        )
    config["debugPort"] = port

    image = (PLUGIN_ROOT / str(config.get("image", "assets/background.png"))).resolve()
    try:
        image.relative_to(PLUGIN_ROOT.resolve())
    except ValueError as exc:
        raise BackgroundError("背景图片必须位于插件目录内") from exc
    if not image.is_file():
        raise BackgroundError(f"背景图片不存在：{image}")
    if image.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise BackgroundError("背景图片必须是 PNG、JPEG 或 WebP")
    config["imagePath"] = image
    return config


def endpoint(port: int, path: str = "/json/list") -> Any:
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=1.5) as response:
        return json.loads(response.read().decode("utf-8"))


def endpoint_available(port: int) -> bool:
    try:
        endpoint(port, "/json/version")
        return True
    except Exception:
        return False


def choose_debug_port(config: dict[str, Any]) -> int:
    configured = int(config["debugPort"])
    if configured:
        return configured
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def runtime_port(config: dict[str, Any]) -> int | None:
    state = read_state()
    try:
        candidate = int(state.get("port", 0) or 0)
    except (TypeError, ValueError):
        candidate = 0
    if 1024 <= candidate <= 65535:
        return candidate
    configured = int(config["debugPort"])
    return configured or None


def prepare_profile_dir() -> Path:
    profile = PLATFORM.profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    try:
        profile.chmod(0o700)
    except OSError:
        pass
    return profile


def recv_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            raise BackgroundError("调试连接意外关闭")
        chunks.extend(chunk)
    return bytes(chunks)


class DevToolsSocket:
    def __init__(self, websocket_url: str, timeout: float = 20.0) -> None:
        parsed = urlparse(websocket_url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise BackgroundError(f"无效的 DevTools WebSocket 地址：{websocket_url}")
        self.sock = socket.create_connection(
            (parsed.hostname, parsed.port), timeout=timeout
        )
        self.sock.settimeout(timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        request = (
            f"GET {parsed.path or '/'} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = bytearray()
        while b"\r\n\r\n" not in response:
            response.extend(recv_exact(self.sock, 1))
            if len(response) > 65536:
                raise BackgroundError("DevTools WebSocket 握手响应过大")
        status_line = response.split(b"\r\n", 1)[0]
        if b" 101 " not in status_line:
            raise BackgroundError(
                f"DevTools WebSocket 握手失败：{status_line.decode(errors='replace')}"
            )
        expected = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        ).decode("ascii")
        if (
            f"sec-websocket-accept: {expected}".lower().encode("ascii")
            not in bytes(response).lower()
        ):
            raise BackgroundError("DevTools WebSocket 握手校验失败")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def send_frame(self, payload: bytes, opcode: int = 0x1) -> None:
        mask = secrets.token_bytes(4)
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def receive_text(self) -> str:
        fragments = bytearray()
        while True:
            first, second = recv_exact(self.sock, 2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", recv_exact(self.sock, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", recv_exact(self.sock, 8))[0]
            mask = recv_exact(self.sock, 4) if masked else b""
            payload = recv_exact(self.sock, length)
            if masked:
                payload = bytes(
                    byte ^ mask[index % 4] for index, byte in enumerate(payload)
                )
            if opcode == 0x8:
                raise BackgroundError("DevTools WebSocket 已关闭")
            if opcode == 0x9:
                self.send_frame(payload, opcode=0xA)
                continue
            if opcode in (0x0, 0x1):
                fragments.extend(payload)
                if fin:
                    return fragments.decode("utf-8")


def cdp_evaluate(websocket_url: str, expression: str) -> Any:
    connection = DevToolsSocket(websocket_url)
    try:
        message = {
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        }
        connection.send_frame(
            json.dumps(message, separators=(",", ":")).encode("utf-8")
        )
        while True:
            response = json.loads(connection.receive_text())
            if response.get("id") != 1:
                continue
            if "error" in response:
                raise BackgroundError(
                    f"DevTools Runtime.evaluate 失败：{response['error']}"
                )
            result = response.get("result", {}).get("result", {})
            if result.get("subtype") == "error":
                raise BackgroundError(str(result.get("description", "页面注入失败")))
            return result.get("value")
    finally:
        connection.close()


def is_main_renderer_target(target: dict[str, Any]) -> bool:
    if target.get("type") != "page" or not target.get("webSocketDebuggerUrl"):
        return False
    parsed = urlparse(str(target.get("url", "")))
    return (
        parsed.scheme == "app"
        and parsed.netloc == "-"
        and parsed.path == "/index.html"
        and not parsed.query
    )


def eligible_targets(port: int) -> list[dict[str, Any]]:
    targets = endpoint(port)
    return [target for target in targets if is_main_renderer_target(target)]


def status_expression() -> str:
    return (
        "(() => ({installed: Boolean(document.getElementById("
        + json.dumps(STYLE_ID)
        + ")), title: document.title, url: location.href}))()"
    )


def injection_expression(config: dict[str, Any]) -> str:
    image_path: Path = config["imagePath"]
    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    image_url = f"data:{mime};base64,{image_data}"
    panel = float(config["panelOpacity"])
    elevated = min(0.96, panel + 0.20)
    secondary = min(0.92, panel + 0.08)
    overlay = float(config["overlayOpacity"])
    blur = int(config["blurPixels"])
    scale = 1 + blur / 500 if blur else 1

    css = f"""
:root[data-codex-background-image='on'] {{
  --chat-background-color: rgba(3, 10, 28, {panel * 0.35:.3f}) !important;
  --codex-base-surface: transparent !important;
  --color-background-surface-under: transparent !important;
  --color-background-surface: rgba(3, 10, 28, {panel * 0.55:.3f}) !important;
  --color-background-primary: rgba(3, 10, 28, {panel:.3f}) !important;
  --color-background-secondary: rgba(6, 18, 42, {secondary:.3f}) !important;
  --color-background-panel: rgba(5, 16, 38, {secondary:.3f}) !important;
  --color-background-elevated-primary: rgba(4, 14, 34, {elevated:.3f}) !important;
  --color-background-elevated-secondary: rgba(8, 24, 52, {elevated:.3f}) !important;
  --color-background-editor-opaque: rgba(3, 10, 28, {elevated:.3f}) !important;
  --color-background-control: rgba(9, 30, 62, {secondary:.3f}) !important;
}}
html[data-codex-background-image='on'],
html[data-codex-background-image='on'] body {{
  background: transparent !important;
}}
html[data-codex-background-image='on'] body > #root {{
  position: relative;
  z-index: 1;
}}
html[data-codex-background-image='on'] body > #root,
html[data-codex-background-image='on'] .bg-token-main-surface-primary,
html[data-codex-background-image='on'] .bg-surface {{
  background-color: transparent !important;
}}
html[data-codex-background-image='on'] .bg-surface-secondary {{
  background-color: rgba(6, 18, 42, {secondary:.3f}) !important;
}}
html[data-codex-background-image='on'] .bg-surface-tertiary,
html[data-codex-background-image='on'] .bg-surface-elevated,
html[data-codex-background-image='on'] .bg-surface-elevated-secondary,
html[data-codex-background-image='on'] .bg-token-dropdown-background {{
  background-color: rgba(5, 16, 38, {elevated:.3f}) !important;
}}
#{LAYER_ID} {{
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: linear-gradient(rgba(2, 7, 20, {overlay:.3f}), rgba(2, 7, 20, {overlay:.3f})), url({json.dumps(image_url)});
  background-size: {config["fit"]};
  background-position: {config["position"]};
  background-repeat: no-repeat;
  opacity: {float(config["backgroundOpacity"]):.3f};
  filter: blur({blur}px);
  transform: scale({scale:.4f});
}}
"""
    script = f"""
(() => {{
  const styleId = {json.dumps(STYLE_ID)};
  const layerId = {json.dumps(LAYER_ID)};
  let style = document.getElementById(styleId);
  if (!style) {{
    style = document.createElement('style');
    style.id = styleId;
    (document.head || document.documentElement).appendChild(style);
  }}
  style.textContent = {json.dumps(css)};
  let layer = document.getElementById(layerId);
  if (!layer) {{
    layer = document.createElement('div');
    layer.id = layerId;
    (document.body || document.documentElement).prepend(layer);
  }}
  document.documentElement.dataset.codexBackgroundImage = 'on';
  if (window[{json.dumps(OBSERVER_KEY)}]) window[{json.dumps(OBSERVER_KEY)}].disconnect();
  window[{json.dumps(OBSERVER_KEY)}] = new MutationObserver(() => {{
    if (!document.getElementById(styleId)) (document.head || document.documentElement).appendChild(style);
    if (!document.getElementById(layerId)) (document.body || document.documentElement).prepend(layer);
    document.documentElement.dataset.codexBackgroundImage = 'on';
  }});
  window[{json.dumps(OBSERVER_KEY)}].observe(document.documentElement, {{childList: true, subtree: true}});
  return {{installed: true, title: document.title, url: location.href}};
}})()
"""
    return script


def removal_expression() -> str:
    return f"""
(() => {{
  if (window[{json.dumps(OBSERVER_KEY)}]) {{
    window[{json.dumps(OBSERVER_KEY)}].disconnect();
    delete window[{json.dumps(OBSERVER_KEY)}];
  }}
  document.getElementById({json.dumps(STYLE_ID)})?.remove();
  document.getElementById({json.dumps(LAYER_ID)})?.remove();
  delete document.documentElement.dataset.codexBackgroundImage;
  return true;
}})()
"""


def inject_all(
    config: dict[str, Any], port: int, force: bool = False
) -> tuple[int, int]:
    targets = eligible_targets(port)
    injected = 0
    failures = 0
    expression: str | None = None
    for target in targets:
        websocket_url = str(target["webSocketDebuggerUrl"])
        try:
            status = cdp_evaluate(websocket_url, status_expression())
            if force or not isinstance(status, dict) or not status.get("installed"):
                if expression is None:
                    expression = injection_expression(config)
                cdp_evaluate(websocket_url, expression)
                injected += 1
        except Exception as exc:
            failures += 1
            log(f"注入目标失败 {target.get('title', '')}: {exc}")
    return injected, failures


def remove_all(config: dict[str, Any], port: int | None) -> int:
    removed = 0
    if port is None or not endpoint_available(port):
        return removed
    for target in eligible_targets(port):
        try:
            cdp_evaluate(str(target["webSocketDebuggerUrl"]), removal_expression())
            removed += 1
        except Exception as exc:
            log(f"移除目标样式失败 {target.get('title', '')}: {exc}")
    return removed


def log(message: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def write_state(**values: Any) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    state = {"pid": os.getpid(), "updatedAt": time.time(), **values}
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def read_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def pid_alive(pid: int) -> bool:
    return PLATFORM.process_alive(pid)


def stop_supervisor() -> bool:
    state = read_state()
    pid = int(state.get("pid", 0) or 0)
    if pid <= 0 or pid == os.getpid() or not pid_alive(pid):
        try:
            STATE_PATH.unlink()
        except FileNotFoundError:
            pass
        return False
    PLATFORM.terminate_process(pid)
    for _ in range(30):
        if not pid_alive(pid):
            break
        time.sleep(0.1)
    return True


def quit_app() -> None:
    PLATFORM.quit_app()


def app_pids() -> set[int]:
    return PLATFORM.app_pids()


def app_running() -> bool:
    return bool(app_pids())


def debug_endpoint_owned_by_app(port: int) -> bool:
    if not endpoint_available(port):
        return False
    try:
        return bool(PLATFORM.app_debug_pids(port))
    except BackgroundError:
        return False


def launch_app(port: int | None) -> int:
    profile = prepare_profile_dir() if port is not None else None
    return PLATFORM.launch_app(port, profile)


def wait_for_endpoint(port: int, timeout: float = 40.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if endpoint_available(port):
            return True
        time.sleep(0.5)
    return False


def spawn_detached(mode: str) -> int:
    return PLATFORM.spawn_helper(mode)


def supervise() -> int:
    config = load_config()
    port = choose_debug_port(config)
    write_state(status="starting", port=port)
    log("准备重启应用并启用背景")
    quit_app()
    try:
        launch_app(port)
    except Exception as exc:
        write_state(status="error", port=port, error=str(exc))
        log(str(exc))
        return 1
    if not wait_for_endpoint(port):
        message = "应用已启动，但本地调试端口未就绪"
        write_state(status="error", port=port, error=message)
        log(message)
        return 1

    write_state(status="active", port=port)
    log("调试端口已就绪，开始维护背景样式")
    consecutive_failures = 0
    while True:
        try:
            injected, failures = inject_all(config, port)
            if injected:
                log(f"已向 {injected} 个页面注入背景")
            consecutive_failures = consecutive_failures + 1 if failures else 0
            write_state(status="active", port=port, failures=failures)
        except Exception as exc:
            consecutive_failures += 1
            log(f"后台检查失败：{exc}")
        if consecutive_failures >= 20:
            message = "连续注入失败；为避免后台无限重试，本次运行停止维护背景"
            write_state(status="error", port=port, error=message)
            log(message)
            return 1
        if not endpoint_available(port):
            log("应用或调试端口已关闭，背景助手退出")
            break
        time.sleep(2)
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass
    return 0


def restore_worker() -> int:
    config = load_config()
    remove_all(config, runtime_port(config))
    stop_supervisor()
    log("恢复原始外观并正常重启应用")
    quit_app()
    try:
        launch_app(None)
    except Exception as exc:
        log(str(exc))
        return 1
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass
    return 0


def command_doctor() -> int:
    problems = PLATFORM.doctor_problems()
    try:
        config = load_config()
    except BackgroundError as exc:
        problems.append(str(exc))
        config = None
    if sys.version_info < (3, 9):
        problems.append("需要 Python 3.9 或更高版本")
    if problems:
        for problem in problems:
            print(f"✗ {problem}")
        return 1
    assert config is not None
    print(f"✓ 平台：{PLATFORM.display_name}（{PLATFORM.maturity}）")
    print(f"✓ 应用：{PLATFORM.app_description()}")
    print(f"✓ 背景：{config['imagePath']}")
    print(f"✓ Python：{sys.version.split()[0]}")
    port_text = str(config["debugPort"]) if config["debugPort"] else "自动选择"
    print(f"✓ 本地调试端口：{port_text}（仅 127.0.0.1）")
    print(f"✓ 隔离用户数据目录：{PLATFORM.profile_dir()}")
    return 0


def command_status() -> int:
    config = load_config()
    port = runtime_port(config)
    state = read_state()
    pid = int(state.get("pid", 0) or 0)
    monitor_pid = read_monitor_pid()
    if port is None or not endpoint_available(port):
        error = state.get("error")
        if error:
            print(f"error：{error}")
            return 2
        print("inactive：调试端口未开启，原始应用外观未被运行时注入。")
        return 1
    injected = 0
    targets = eligible_targets(port)
    for target in targets:
        try:
            result = cdp_evaluate(
                str(target["webSocketDebuggerUrl"]), status_expression()
            )
            if isinstance(result, dict) and result.get("installed"):
                injected += 1
        except Exception:
            pass
    if pid and pid_alive(pid):
        keeper = "supervisor"
    elif monitor_pid and pid_alive(monitor_pid):
        keeper = "monitor"
    else:
        keeper = "missing"
    print(
        f"active：{injected}/{len(targets)} 个页面已注入；keeper={keeper}；port={port}"
    )
    return 0 if injected else 2


def command_start() -> int:
    config = load_config()
    PLATFORM.find_app()
    port = runtime_port(config)
    stop_supervisor()
    if port is not None and endpoint_available(port):
        if not debug_endpoint_owned_by_app(port):
            raise BackgroundError(
                f"127.0.0.1:{port} 已被占用，但无法确认它属于 ChatGPT/Codex。"
                "请更换 config.json 的 debugPort 后重试。"
            )
        injected, failures = inject_all(config, port, force=True)
        pid = spawn_detached("_watch")
        print(
            f"已刷新背景：注入 {injected} 个页面，失败 {failures} 个；后台 PID {pid}。"
        )
        return 0 if injected else 2
    pid = spawn_detached("_supervise")
    print(f"背景助手已启动（PID {pid}）。应用将在数秒后重启。")
    return 0


def watch() -> int:
    config = load_config()
    port = runtime_port(config)
    if port is None:
        log("后台刷新退出：没有可用的运行时端口")
        return 1
    write_state(status="active", port=port)
    while debug_endpoint_owned_by_app(port):
        try:
            inject_all(config, port)
            write_state(status="active", port=port)
        except Exception as exc:
            log(f"后台刷新失败：{exc}")
        time.sleep(2)
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass
    return 0


def write_monitor_guard(pids: set[int]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not pids:
        try:
            MONITOR_GUARD_PATH.unlink()
        except FileNotFoundError:
            pass
        return
    MONITOR_GUARD_PATH.write_text(
        json.dumps({"createdAt": time.time(), "pids": sorted(pids)}, indent=2) + "\n",
        encoding="utf-8",
    )


def read_monitor_guard(max_age: float = 120.0) -> set[int]:
    try:
        payload = json.loads(MONITOR_GUARD_PATH.read_text(encoding="utf-8"))
        if time.time() - float(payload.get("createdAt", 0)) > max_age:
            return set()
        return {int(pid) for pid in payload.get("pids", []) if int(pid) > 0}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()


def clear_monitor_guard() -> None:
    try:
        MONITOR_GUARD_PATH.unlink()
    except FileNotFoundError:
        pass


def read_monitor_pid() -> int:
    try:
        return int(MONITOR_PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def clear_monitor_pid_if_owned(pid: int) -> None:
    if read_monitor_pid() != pid:
        return
    try:
        MONITOR_PID_PATH.unlink()
    except FileNotFoundError:
        pass


def stop_monitor() -> bool:
    pid = read_monitor_pid()
    if pid <= 0 or pid == os.getpid() or not pid_alive(pid):
        clear_monitor_pid_if_owned(pid)
        return False
    PLATFORM.terminate_process(pid)
    for _ in range(30):
        if not pid_alive(pid):
            break
        time.sleep(0.1)
    clear_monitor_pid_if_owned(pid)
    return True


def launch_managed_background(
    config: dict[str, Any], reason: str, quit_first: bool
) -> tuple[set[int], int, bool]:
    port = choose_debug_port(config)
    log(reason)
    if quit_first:
        quit_app()
    write_state(status="starting", port=port)
    try:
        launch_app(port)
    except Exception as exc:
        message = f"自动启动背景失败：{exc}"
        write_state(status="error", port=port, error=message)
        log(message)
        return app_pids(), port, False
    if not wait_for_endpoint(port):
        message = "自动启动背景后，本地调试端口未就绪"
        write_state(status="error", port=port, error=message)
        log(message)
        return app_pids(), port, False
    injected, failures = inject_all(config, port, force=True)
    ready = injected > 0 and failures == 0
    status = "active" if ready else "error"
    error = None if ready else "没有找到可注入的 Codex 主界面"
    write_state(status=status, port=port, failures=failures, error=error)
    log(f"自动背景已就绪：注入 {injected} 个页面，失败 {failures} 个")
    return app_pids(), port, ready


def monitor_app_launches() -> int:
    """Keep watching normal Codex launches and convert them to background mode."""
    existing_pid = read_monitor_pid()
    if existing_pid and existing_pid != os.getpid() and pid_alive(existing_pid):
        log(f"启动监视器已运行：PID {existing_pid}")
        return 0
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    MONITOR_PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    atexit.register(clear_monitor_pid_if_owned, os.getpid())
    config = load_config()
    port = runtime_port(config)
    ignored_pids = read_monitor_guard()
    managed_pids: set[int] = set()
    failed_pids: set[int] = set()

    current = app_pids()
    if port is not None and debug_endpoint_owned_by_app(port):
        log("启动监视器：接管已经启用背景的 Codex")
        managed_pids = current
    elif port is not None and endpoint_available(port):
        log(f"启动监视器退出：127.0.0.1:{port} 被其他进程占用")
        return 1
    elif ignored_pids & current:
        log("启动监视器：保护安装时已经运行的 Codex，本次不重启")
    elif current:
        managed_pids, port, ready = launch_managed_background(
            config,
            "启动监视器：检测到普通 Codex 启动，自动切换为背景模式",
            quit_first=True,
        )
        if not ready:
            failed_pids = set(managed_pids)
    elif not ignored_pids:
        managed_pids, port, ready = launch_managed_background(
            config,
            "启动监视器：登录后自动启动背景 Codex",
            quit_first=False,
        )
        if not ready:
            failed_pids = set(managed_pids)

    while True:
        if port is not None and debug_endpoint_owned_by_app(port):
            managed_pids = app_pids() or managed_pids
            try:
                inject_all(config, port)
                write_state(status="active", port=port)
            except Exception as exc:
                log(f"启动监视器刷新失败：{exc}")
            time.sleep(2)
            continue

        if port is not None and endpoint_available(port):
            log(f"启动监视器退出：127.0.0.1:{port} 被其他进程占用")
            return 1

        current = app_pids()
        if ignored_pids:
            if current & ignored_pids:
                time.sleep(0.5)
                continue
            ignored_pids.clear()
            clear_monitor_guard()
            log("启动监视器：当前受保护的 Codex 已退出，开始接管后续启动")

        if managed_pids and current & managed_pids:
            failed_pids = current & managed_pids
            managed_pids.clear()
            message = "背景连接已中断；为避免重启循环，本次运行不再自动重试"
            write_state(status="error", port=port, error=message)
            log(f"启动监视器：{message}")

        if failed_pids:
            if current & failed_pids:
                time.sleep(0.5)
                continue
            failed_pids.clear()
            port = None
            log("启动监视器：失败的 Codex 已由用户关闭，可接管下一次启动")

        if not current:
            managed_pids.clear()
            port = None
            time.sleep(0.5)
            continue

        managed_pids, port, ready = launch_managed_background(
            config,
            "启动监视器：检测到普通 Codex 启动，自动切换为背景模式",
            quit_first=True,
        )
        if not ready:
            failed_pids = set(managed_pids)
        time.sleep(1)


def command_enable_autostart() -> int:
    load_config()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    current_pids = app_pids()
    write_monitor_guard(current_pids)
    installed_at = PLATFORM.enable_autostart()
    print(f"已启用 Codex 启动监视器：{installed_at}")
    if not PLATFORM.autostart_starts_immediately:
        monitor_pid = read_monitor_pid()
        if not monitor_pid or not pid_alive(monitor_pid):
            monitor_pid = spawn_detached("_monitor")
            MONITOR_PID_PATH.write_text(f"{monitor_pid}\n", encoding="utf-8")
        print(f"当前登录会话的启动监视器 PID：{monitor_pid}")
    active_port = runtime_port(load_config())
    if current_pids and (
        active_port is None or not endpoint_available(active_port)
    ):
        print("当前 Codex 未被重启；下次普通启动 Codex 时会自动加载背景。")
    return 0


def command_disable_autostart() -> int:
    PLATFORM.disable_autostart()
    stop_monitor()
    clear_monitor_guard()
    print("已关闭 Codex 启动监视器；当前 Codex 不会被重启。")
    return 0


def command_restore() -> int:
    PLATFORM.find_app()
    command_disable_autostart()
    spawn_detached("_restore")
    print("恢复助手已启动。应用将在数秒后以原始方式重启。")
    return 0


def command_remove() -> int:
    config = load_config()
    stop_supervisor()
    removed = remove_all(config, runtime_port(config))
    print(f"已从 {removed} 个页面移除背景。调试端口会在下次正常重启后关闭。")
    return 0


def command_set_image(source_text: str) -> int:
    source = Path(source_text).expanduser().resolve()
    if not source.is_file():
        raise BackgroundError(f"图片不存在：{source}")
    if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise BackgroundError("图片必须是 PNG、JPEG 或 WebP")
    destination = PLUGIN_ROOT / "assets" / f"background{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    old_image = (
        PLUGIN_ROOT / str(config.get("image", "assets/background.png"))
    ).resolve()
    config["image"] = str(destination.relative_to(PLUGIN_ROOT))
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if (
        old_image != destination
        and old_image.is_file()
        and old_image.parent == destination.parent
    ):
        try:
            old_image.unlink()
        except OSError:
            pass
    print(f"已更新背景图片：{destination}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in (
        "doctor",
        "status",
        "start",
        "restore",
        "remove",
        "enable-autostart",
        "disable-autostart",
        "_supervise",
        "_watch",
        "_restore",
        "_monitor",
    ):
        subparsers.add_parser(command)
    set_image = subparsers.add_parser("set-image")
    set_image.add_argument("path")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            return command_doctor()
        if args.command == "status":
            return command_status()
        if args.command == "start":
            return command_start()
        if args.command == "restore":
            return command_restore()
        if args.command == "remove":
            return command_remove()
        if args.command == "enable-autostart":
            return command_enable_autostart()
        if args.command == "disable-autostart":
            return command_disable_autostart()
        if args.command == "set-image":
            return command_set_image(args.path)
        if args.command == "_supervise":
            return supervise()
        if args.command == "_watch":
            return watch()
        if args.command == "_restore":
            return restore_worker()
        if args.command == "_monitor":
            return monitor_app_launches()
    except BackgroundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
