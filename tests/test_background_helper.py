#!/usr/bin/env python3
"""Offline tests for the background helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "codex_background"
    / "scripts"
    / "codex_background.py"
)
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("codex_background", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureSocket:
    def __init__(self) -> None:
        self.payload = b""

    def sendall(self, payload: bytes) -> None:
        self.payload += payload


class PortProbeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def bind(self, _address) -> None:
        return None

    def getsockname(self):
        return ("127.0.0.1", 54321)


def decode_client_frame(frame: bytes) -> bytes:
    assert frame[0] == 0x81
    second = frame[1]
    assert second & 0x80
    length = second & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", frame[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        length = struct.unpack("!Q", frame[offset : offset + 8])[0]
        offset += 8
    mask = frame[offset : offset + 4]
    offset += 4
    payload = frame[offset : offset + length]
    return bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


def main() -> None:
    config = module.load_config()
    from codex_background_platforms.base import (
        PlatformContext,
        parse_posix_process_table,
    )
    from codex_background_platforms.macos import MacOSPlatform

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        context = PlatformContext(
            plugin_root=temporary,
            script_path=temporary / "codex_background.py",
            runtime_dir=temporary / ".runtime",
            log_path=temporary / ".runtime" / "background.log",
        )
        launch_agent = MacOSPlatform(context).launch_agent_payload()
    assert launch_agent["Label"] == "com.codex-background.monitor"
    assert launch_agent["ProgramArguments"][-1] == "_monitor"
    assert launch_agent["RunAtLoad"] is True
    assert config["backgroundOpacity"] == 1.0
    assert config["panelOpacity"] == 0.3
    assert config["debugPort"] == 0
    original_socket = module.socket.socket
    try:
        module.socket.socket = lambda *_args, **_kwargs: PortProbeSocket()
        automatic_port = module.choose_debug_port(config)
    finally:
        module.socket.socket = original_socket
    assert automatic_port == 54321
    process_table = """
      101 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT
      102 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT --remote-debugging-port=9229
      103 /bin/zsh -c echo /Applications/ChatGPT.app/Contents/MacOS/ChatGPT
    """
    executable = Path("/Applications/ChatGPT.app/Contents/MacOS/ChatGPT")
    assert parse_posix_process_table(process_table, executable) == {101, 102}
    expression = module.injection_expression(config)
    assert len(expression) > 1_000
    assert "MutationObserver" in expression
    assert "data:image/png;base64," in expression
    assert "/Applications/ChatGPT.app" not in expression
    assert "body > #root" in expression
    assert "body > *:not(" not in expression
    assert "pointer-events: none" in expression

    assert module.is_main_renderer_target(
        {
            "type": "page",
            "url": "app://-/index.html",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9000/devtools/page/main",
        }
    )
    assert not module.is_main_renderer_target(
        {
            "type": "page",
            "url": "app://-/index.html?initialRoute=%2Favatar-overlay",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9000/devtools/page/overlay",
        }
    )
    assert not module.is_main_renderer_target(
        {
            "type": "page",
            "url": "https://example.com/",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9000/devtools/page/browser",
        }
    )

    capture = CaptureSocket()
    connection = object.__new__(module.DevToolsSocket)
    connection.sock = capture
    message = json.dumps(
        {"id": 1, "method": "Runtime.evaluate", "params": {"expression": expression}}
    ).encode()
    connection.send_frame(message)
    assert decode_client_frame(capture.payload) == message

    calls: list[str] = []
    original_targets = module.eligible_targets
    original_evaluate = module.cdp_evaluate
    try:
        module.eligible_targets = lambda _port: [
            {"title": "Mock Codex", "webSocketDebuggerUrl": "ws://mock/devtools/page/1"}
        ]

        def fake_evaluate(_url: str, script: str):
            calls.append(script)
            if "MutationObserver" in script:
                return {"installed": True}
            return {"installed": False}

        module.cdp_evaluate = fake_evaluate
        injected, failures = module.inject_all(config, 9229)
    finally:
        module.eligible_targets = original_targets
        module.cdp_evaluate = original_evaluate

    assert injected == 1
    assert failures == 0
    assert len(calls) == 2

    original_endpoint_available = module.endpoint_available
    original_debug_pids = module.PLATFORM.app_debug_pids
    try:
        module.endpoint_available = lambda _port: True
        module.PLATFORM.app_debug_pids = lambda _port: {999}
        assert module.debug_endpoint_owned_by_app(9229) is True
        module.PLATFORM.app_debug_pids = lambda _port: set()
        assert module.debug_endpoint_owned_by_app(9229) is False
    finally:
        module.endpoint_available = original_endpoint_available
        module.PLATFORM.app_debug_pids = original_debug_pids

    originals = (
        module.launch_app,
        module.wait_for_endpoint,
        module.app_pids,
        module.write_state,
        module.log,
    )
    launches: list[int | None] = []
    try:
        module.launch_app = lambda port: launches.append(port) or 123
        module.wait_for_endpoint = lambda _port: False
        module.app_pids = lambda: {123}
        module.write_state = lambda **_values: None
        module.log = lambda _message: None
        fixed_port_config = dict(config, debugPort=54321)
        managed, selected_port, ready = module.launch_managed_background(
            fixed_port_config, "test", quit_first=False
        )
    finally:
        (
            module.launch_app,
            module.wait_for_endpoint,
            module.app_pids,
            module.write_state,
            module.log,
        ) = originals
    assert launches == [selected_port]
    assert managed == {123}
    assert ready is False

    print("offline helper tests passed")
    print(f"injection expression bytes: {len(expression.encode('utf-8'))}")
    print(f"websocket frame bytes: {len(capture.payload)}")


if __name__ == "__main__":
    main()
