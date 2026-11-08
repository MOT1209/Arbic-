"""A Debug Adapter Protocol server for AlArabiya (interpreter backend).

The server speaks DAP over a byte stream (normally stdin/stdout) and drives a
:class:`~al_arabiya.runtime.interpreter.interpreter.Interpreter` through a
subclass that reports every statement before it runs.  Stepping is therefore
statement-granular, which is what the language's line-based syntax implies.

Supported requests: ``initialize``, ``launch``, ``setBreakpoints``,
``configurationDone``, ``threads``, ``stackTrace``, ``scopes``, ``variables``,
``continue``, ``next``, ``stepIn``, ``stepOut``, ``terminate`` and
``disconnect``.  The VM backend is not instrumented yet; debugging always runs
on the interpreter.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from al_arabiya.compiler.ast.nodes import ASTNode, Statement
from al_arabiya.compiler.diagnostics.diagnostics import DiagnosticBag, render_diagnostic
from al_arabiya.compiler.diagnostics.errors import DiagnosticError
from al_arabiya.compiler.diagnostics.source import SourceFile
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.positions import Span
from al_arabiya.runtime.builtins import make_global_env
from al_arabiya.runtime.interpreter.environment import Environment
from al_arabiya.runtime.interpreter.interpreter import Interpreter
from al_arabiya.runtime.values import ArabiyaFunction, Value, format_value

__all__ = ["DebugSession", "main"]


class _StopSession(Exception):  # noqa: N818 - control flow, not an error
    """Raised inside a pause when the client disconnects."""


@dataclass
class _Frame:
    """One stack frame as the client sees it."""

    name: str
    line: int
    environment: Environment


class _Transport:
    """DAP framing: ``Content-Length`` headers followed by a JSON body."""

    def __init__(self, reader: BinaryIO, writer: BinaryIO) -> None:
        self._reader = reader
        self._writer = writer
        self._seq = 0

    def read(self) -> dict[str, Any] | None:
        length: int | None = None
        while True:
            line = self._reader.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            if line.lower().startswith(b"content-length:"):
                try:
                    length = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    return None
        if length is None:
            return None
        body = self._reader.read(length)
        if len(body) != length:
            return None
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return decoded if isinstance(decoded, dict) else None

    def send(self, message: dict[str, Any]) -> None:
        self._seq += 1
        message["seq"] = self._seq
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n"
        self._writer.write(header + body)
        self._writer.flush()


class _DebugInterpreter(Interpreter):
    """Interpreter that reports each statement and keeps a frame stack."""

    def __init__(self, session: DebugSession, environment: Environment, base_dir: str) -> None:
        super().__init__(
            environment=environment,
            diagnostics=DiagnosticBag(),
            write=session.output,
            base_dir=base_dir,
        )
        self._session = session
        self.frames: list[_Frame] = [_Frame("<البرنامج>", 1, environment)]

    def visit(self, node: ASTNode) -> Any:
        if isinstance(node, Statement):
            line = node.span.start.line
            frame = self.frames[-1]
            frame.line = line
            frame.environment = self.environment
            self._session.before_statement(line, len(self.frames))
        return super().visit(node)

    def _call_function(
        self, fn: ArabiyaFunction, arguments: list[Value], span: Span
    ) -> Value:
        self.frames.append(_Frame(fn.name, fn.declaration.span.start.line, self.environment))
        try:
            return super()._call_function(fn, arguments, span)
        finally:
            self.frames.pop()


class DebugSession:
    """One debug session: request loop plus the paused program."""

    def __init__(
        self, program: str | None, reader: BinaryIO, writer: BinaryIO
    ) -> None:
        self._transport = _Transport(reader, writer)
        self._program_path = str(Path(program).resolve()) if program else None
        self._breakpoints: set[int] = set()
        self._mode = "continue"
        self._step_depth = 0
        self._paused = False
        self._finished = False
        self._terminated = False
        self._exit_code = 0
        self._interpreter: _DebugInterpreter | None = None
        self._frames: list[_Frame] = []
        self._variables: dict[int, list[tuple[str, str, str]]] = {}
        self._next_reference = 1
        self._line_count = 0
        self._stop_on_entry = False
        self._entry_pending = False

    # ------------------------------------------------------------ event loop

    def serve(self) -> int:
        while not self._finished:
            message = self._transport.read()
            if message is None:
                break
            self._handle(message)
        return self._exit_code

    # ---------------------------------------------------------------- helpers

    def _respond(
        self,
        request: dict[str, Any],
        body: dict[str, Any] | None = None,
        *,
        success: bool = True,
        message: str | None = None,
    ) -> None:
        response: dict[str, Any] = {
            "type": "response",
            "request_seq": request.get("seq", 0),
            "success": success,
            "command": request.get("command", ""),
        }
        if body is not None:
            response["body"] = body
        if message is not None:
            response["message"] = message
        self._transport.send(response)

    def _event(self, name: str, body: dict[str, Any] | None = None) -> None:
        event: dict[str, Any] = {"type": "event", "event": name}
        if body is not None:
            event["body"] = body
        self._transport.send(event)

    def output(self, text: str) -> None:
        """Program output, forwarded as a DAP ``output`` event."""
        self._event("output", {"category": "stdout", "output": text + "\n"})

    def _error_output(self, text: str) -> None:
        self._event("output", {"category": "stderr", "output": text})

    def _source(self) -> dict[str, Any]:
        path = self._program_path or ""
        return {"name": Path(path).name if path else "<البرنامج>", "path": path}

    def _top_frame(self) -> _Frame | None:
        return self._frames[-1] if self._frames else None

    def _root_environment(self, environment: Environment) -> Environment:
        scope = environment
        while scope.parent is not None:
            scope = scope.parent
        return scope

    def _variable_reference(self, items: dict[str, Value]) -> int:
        reference = self._next_reference
        self._next_reference += 1
        rendered: list[tuple[str, str, str]] = []
        for name, value in items.items():
            rendered.append((name, format_value(value), type(value).__name__))
        self._variables[reference] = rendered
        return reference

    # -------------------------------------------------------------- requests

    def _handle(self, request: dict[str, Any]) -> None:
        command = request.get("command")
        arguments = request.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}

        if command == "initialize":
            self._respond(
                request,
                {
                    "supportsConfigurationDoneRequest": True,
                    "supportsTerminateRequest": True,
                    "supportsSetBreakpoints": True,
                    "supportsSingleThreadExecutionRequests": True,
                },
            )
            self._event("initialized")
            return
        if command == "launch":
            self._respond(request, self._launch(arguments))
            return
        if command == "setBreakpoints":
            self._respond(request, self._set_breakpoints(arguments))
            return
        if command == "configurationDone":
            self._respond(request, {})
            self._run()
            return
        if command == "threads":
            self._respond(request, {"threads": [{"id": 1, "name": "البرنامج"}]})
            return
        if command == "stackTrace":
            self._respond(request, self._stack_trace())
            return
        if command == "scopes":
            self._respond(request, self._scopes(arguments))
            return
        if command == "variables":
            self._respond(request, self._variables_body(arguments))
            return
        if command in ("continue", "next", "stepIn", "stepOut"):
            self._resume(command)
            body = {"allThreadsContinued": True} if command == "continue" else {}
            self._respond(request, body)
            return
        if command in ("terminate", "disconnect"):
            self._respond(request, {})
            self._finished = True
            return
        self._respond(
            request,
            success=False,
            message=f"الأمر '{command}' مش مدعوم في مصحّح العربية",
        )

    def _launch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        program = arguments.get("program")
        if isinstance(program, str) and program:
            self._program_path = str(Path(program).resolve())
        stop_on_entry = arguments.get("stopOnEntry")
        self._stop_on_entry = bool(stop_on_entry)
        if self._program_path is None:
            return {}
        try:
            self._line_count = len(
                Path(self._program_path).read_text(encoding="utf-8-sig").splitlines()
            )
        except OSError:
            self._line_count = 0
        return {}

    def _set_breakpoints(self, arguments: dict[str, Any]) -> dict[str, Any]:
        lines = arguments.get("breakpoints")
        requested: list[int] = []
        if isinstance(lines, list):
            for entry in lines:
                if isinstance(entry, dict) and isinstance(entry.get("line"), int):
                    requested.append(int(entry["line"]))
        self._breakpoints = set(requested)
        verified = []
        for line in requested:
            ok = self._line_count == 0 or 1 <= line <= self._line_count
            verified.append({"verified": ok, "line": line})
        return {"breakpoints": verified}

    def _resume(self, command: str) -> None:
        if not self._paused:
            return
        interpreter = self._interpreter
        depth = len(interpreter.frames) if interpreter is not None else 0
        self._paused = False
        self._entry_pending = False
        if command == "continue":
            self._mode = "continue"
        elif command == "next":
            self._mode = "next"
            self._step_depth = depth
        elif command == "stepIn":
            self._mode = "stepIn"
        else:
            self._mode = "stepOut"
            self._step_depth = depth

    # ------------------------------------------------------------------- run

    def _run(self) -> None:
        if self._program_path is None:
            self._error_output("❌ مفيش برنامج للتصحيح\n")
            self._exit_code = 1
            self._send_terminated()
            return
        try:
            source = SourceFile.from_path(self._program_path)
        except OSError:
            self._error_output(f"❌ مش لاقي الملف: {self._program_path}\n")
            self._exit_code = 1
            self._send_terminated()
            return

        result = compile_source(source.text, self._program_path)
        self._line_count = len(source.text.splitlines())
        if result.program is None:
            for diagnostic in result.diagnostics:
                if diagnostic.is_error:
                    self._error_output(
                        render_diagnostic(diagnostic, result.source) + "\n"
                    )
            self._exit_code = 1
            self._send_terminated()
            return

        interpreter = _DebugInterpreter(
            self, make_global_env(), str(Path(self._program_path).parent)
        )
        self._interpreter = interpreter
        self._frame_snapshot()
        self._entry_pending = True
        try:
            interpreter.run(result.program)
        except _StopSession:
            pass
        except DiagnosticError as exc:
            self._error_output(render_diagnostic(exc.diagnostic, result.source) + "\n")
            self._exit_code = 1
        except RecursionError:
            self._error_output("❌ البرنامج وصل لحد العمق المسموح\n")
            self._exit_code = 1
        finally:
            self._send_terminated()

    def _send_terminated(self) -> None:
        if self._terminated:
            return
        self._terminated = True
        self._transport.send(
            {"type": "event", "event": "exited", "body": {"exitCode": self._exit_code}}
        )
        self._transport.send({"type": "event", "event": "terminated"})
        self._finished = True

    def _frame_snapshot(self) -> None:
        interpreter = self._interpreter
        self._frames = list(interpreter.frames) if interpreter is not None else []

    # --------------------------------------------------------------- stop/pause

    def before_statement(self, line: int, depth: int) -> None:
        if self._finished:
            raise _StopSession
        reason: str | None = None
        if line in self._breakpoints:
            reason = "breakpoint"
        elif self._mode == "stepIn":
            reason = "step"
        elif self._mode == "next" and depth <= self._step_depth:
            reason = "step"
        elif self._mode == "stepOut" and depth < self._step_depth:
            reason = "step"
        elif self._entry_pending and self._stop_on_entry:
            reason = "entry"
        if reason is None:
            return
        self._pause(reason)

    def _pause(self, reason: str) -> None:
        self._frame_snapshot()
        self._paused = True
        self._mode = "continue"
        self._step_depth = 0
        top = self._top_frame()
        description = f"توقّف عند سطر {top.line if top is not None else 0}"
        self._event(
            "stopped",
            {
                "reason": reason,
                "threadId": 1,
                "allThreadsStopped": True,
                "description": description,
            },
        )
        while self._paused and not self._finished:
            message = self._transport.read()
            if message is None:
                self._finished = True
                raise _StopSession
            self._handle(message)

    # ------------------------------------------------------------- inspection

    def _stack_trace(self) -> dict[str, Any]:
        frames = []
        for index, frame in enumerate(reversed(self._frames)):
            frames.append(
                {
                    "id": index + 1,
                    "name": frame.name,
                    "line": frame.line,
                    "column": 1,
                    "source": self._source(),
                }
            )
        return {"stackFrames": frames, "totalFrames": len(frames)}

    def _scopes(self, arguments: dict[str, Any]) -> dict[str, Any]:
        frame_id = arguments.get("frameId")
        index = len(self._frames) - int(frame_id) if isinstance(frame_id, int) and frame_id else 0
        if not 0 <= index < len(self._frames):
            index = len(self._frames) - 1
        frame = self._frames[index] if self._frames else None
        environment = frame.environment if frame is not None else make_global_env()
        scopes = [
            {
                "name": "محلي",
                "variablesReference": self._variable_reference(environment.local_items()),
                "expensive": False,
            },
            {
                "name": "عام",
                "variablesReference": self._variable_reference(
                    self._root_environment(environment).local_items()
                ),
                "expensive": False,
            },
        ]
        return {"scopes": scopes}

    def _variables_body(self, arguments: dict[str, Any]) -> dict[str, Any]:
        reference = arguments.get("variablesReference")
        entries = self._variables.get(reference) if isinstance(reference, int) else None
        if entries is None:
            return {"variables": []}
        return {
            "variables": [
                {
                    "name": name,
                    "value": value,
                    "type": type_name,
                    "variablesReference": 0,
                }
                for name, value, type_name in entries
            ]
        }


def main(program: str | None = None) -> int:
    """Run the DAP server on stdio (used by ``arabic debug``)."""
    session = DebugSession(program, sys.stdin.buffer, sys.stdout.buffer)
    return session.serve()
