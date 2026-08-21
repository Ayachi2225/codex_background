#!/usr/bin/env python3
"""Offline tests for the background helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "codex_background"
    / "scripts"
    / "codex_background.py"
)
spec = importlib.util.spec_from_file_location("codex_background", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureSocket:
    def __init__(self) -> None:
        self.payload = b""

    def sendall(self, payload: bytes) -> None:
        self.payload += payload


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
    launch_agent = module.launch_agent_payload()
    assert launch_agent["Label"] == "com.codex-background.monitor"
    assert launch_agent["ProgramArguments"][-1] == "_monitor"
    assert launch_agent["RunAtLoad"] is True
    assert config["backgroundOpacity"] == 1.0
    assert config["panelOpacity"] == 0.3
    process_table = """
      101 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT
      102 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT --remote-debugging-port=9229
      103 /bin/zsh -c echo /Applications/ChatGPT.app/Contents/MacOS/ChatGPT
    """
    assert module.parse_app_pids(process_table) == {101, 102}
    expression = module.injection_expression(config)
    assert len(expression) > 1_000
    assert "MutationObserver" in expression
    assert "data:image/png;base64," in expression
    assert "/Applications/ChatGPT.app" not in expression

    capture = CaptureSocket()
    connection = object.__new__(module.DevToolsSocket)
    connection.sock = capture
    message = json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expression}}).encode()
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
        injected, failures = module.inject_all(config)
    finally:
        module.eligible_targets = original_targets
        module.cdp_evaluate = original_evaluate

    assert injected == 1
    assert failures == 0
    assert len(calls) == 2
    print("offline helper tests passed")
    print(f"injection expression bytes: {len(expression.encode('utf-8'))}")
    print(f"websocket frame bytes: {len(capture.payload)}")


if __name__ == "__main__":
    main()
