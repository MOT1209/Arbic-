"""End-to-end tests: a real DAP client over the adapter's stdio."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

PROGRAM = (
    "خلي س = 1\n"
    "دالة زود (ن)\n"
    "    خلي ناتج = ن + س\n"
    "    رجّع ناتج\n"
    "خلاص\n"
    "خلي ص = زود(2)\n"
    'اطبع ص\n'
)


class DAPClient:
    """Minimal DAP client: framing, requests, and a message queue."""

    def __init__(self, program: Path) -> None:
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "al_arabiya", "debug", "--stdio", str(program)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            env=env,
        )
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.outputs: list[str] = []
        self._seq = 0
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        stream = self.process.stdout
        assert stream is not None
        while True:
            headers: dict[str, str] = {}
            while True:
                line = stream.readline()
                if not line:
                    self._queue.put(None)
                    return
                if line in (b"\r\n", b"\n"):
                    break
                name, _, value = line.decode("ascii", "replace").partition(":")
                headers[name.strip().lower()] = value.strip()
            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                self._queue.put(None)
                return
            body = stream.read(length)
            try:
                message = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._queue.put(None)
                return
            if message.get("type") == "event" and message.get("event") == "output":
                self.outputs.append(str(message.get("body", {}).get("output", "")))
            self._queue.put(message)

    def send(self, command: str, arguments: dict[str, Any] | None = None) -> None:
        self._seq += 1
        message = {
            "seq": self._seq,
            "type": "request",
            "command": command,
            "arguments": arguments or {},
        }
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
        assert self.process.stdin is not None
        self.process.stdin.write(header + body)
        self.process.stdin.flush()

    def wait(
        self, predicate: Callable[[dict[str, Any]], bool], timeout: float = 20.0
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError("no matching DAP message within the timeout")
            message = self._queue.get(timeout=remaining)
            if message is None:
                raise AssertionError("the debug adapter closed the connection")
            if predicate(message):
                return message

    def response(self, command: str) -> dict[str, Any]:
        return self.wait(
            lambda message: message.get("type") == "response"
            and message.get("command") == command
        )

    def event(self, name: str) -> dict[str, Any]:
        return self.wait(
            lambda message: message.get("type") == "event"
            and message.get("event") == name
        )

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)


def start(tmp_path: Path, program: str = PROGRAM) -> tuple[DAPClient, Path]:
    path = tmp_path / "main.arb"
    path.write_text(program, encoding="utf-8")
    client = DAPClient(path)
    client.send(
        "initialize",
        {
            "adapterID": "arabic",
            "linesStartAt1": True,
            "columnsStartAt1": True,
            "pathFormat": "path",
        },
    )
    assert client.response("initialize")["success"] is True
    client.event("initialized")
    return client, path


def test_breakpoint_stack_locals_and_step(tmp_path: Path) -> None:
    client, path = start(tmp_path)
    try:
        client.send(
            "setBreakpoints",
            {"source": {"path": str(path)}, "breakpoints": [{"line": 6}]},
        )
        breakpoints = client.response("setBreakpoints")["body"]["breakpoints"]
        assert breakpoints == [{"verified": True, "line": 6}]

        client.send("launch", {"program": str(path)})
        assert client.response("launch")["success"] is True
        client.send("configurationDone")
        assert client.response("configurationDone")["success"] is True

        stopped = client.event("stopped")
        assert stopped["body"]["reason"] == "breakpoint"

        client.send("stackTrace", {"threadId": 1})
        frames = client.response("stackTrace")["body"]["stackFrames"]
        assert frames[0]["line"] == 6
        assert frames[0]["name"] == "<البرنامج>"

        client.send("scopes", {"frameId": 1})
        scopes = client.response("scopes")["body"]["scopes"]
        globals_scope = next(scope for scope in scopes if scope["name"] == "عام")
        client.send("variables", {"variablesReference": globals_scope["variablesReference"]})
        variables = {
            entry["name"]: entry["value"]
            for entry in client.response("variables")["body"]["variables"]
        }
        assert variables["س"] == "1"

        client.send("next")
        assert client.response("next")["success"] is True
        stepped = client.event("stopped")
        assert stepped["body"]["reason"] == "step"
        client.send("stackTrace", {"threadId": 1})
        assert client.response("stackTrace")["body"]["stackFrames"][0]["line"] == 7

        client.send("continue")
        assert client.response("continue")["body"]["allThreadsContinued"] is True
        client.event("terminated")
        assert client.process.wait(timeout=10) == 0
        assert any("3" in chunk for chunk in client.outputs)
    finally:
        client.close()


def test_step_in_stops_inside_a_function_with_parameters(tmp_path: Path) -> None:
    client, path = start(tmp_path)
    try:
        client.send(
            "setBreakpoints",
            {"source": {"path": str(path)}, "breakpoints": [{"line": 6}]},
        )
        client.response("setBreakpoints")
        client.send("launch", {"program": str(path)})
        client.response("launch")
        client.send("configurationDone")
        client.response("configurationDone")
        client.event("stopped")

        client.send("stepIn")
        client.response("stepIn")
        client.event("stopped")

        client.send("stackTrace", {"threadId": 1})
        frames = client.response("stackTrace")["body"]["stackFrames"]
        assert frames[0]["line"] == 3
        assert frames[0]["name"] == "زود"
        assert frames[1]["name"] == "<البرنامج>"

        client.send("scopes", {"frameId": 1})
        scopes = client.response("scopes")["body"]["scopes"]
        local_scope = next(scope for scope in scopes if scope["name"] == "محلي")
        client.send("variables", {"variablesReference": local_scope["variablesReference"]})
        variables = {
            entry["name"]: entry["value"]
            for entry in client.response("variables")["body"]["variables"]
        }
        assert variables["ن"] == "2"

        client.send("continue")
        client.response("continue")
        client.event("terminated")
        assert client.process.wait(timeout=10) == 0
    finally:
        client.close()
