"""Tests for the Language Server (protocol framing + request handling)."""

from __future__ import annotations

import io
import json
from typing import Any

from al_arabiya.lsp.protocol import read_message, write_message
from al_arabiya.lsp.server import LanguageServer, serve


def make_server() -> tuple[LanguageServer, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    return LanguageServer(send=sent.append), sent


def open_doc(server: LanguageServer, text: str, uri: str = "file.arb") -> None:
    server.handle(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": uri, "text": text}},
        }
    )


def last_diagnostics(sent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    publishes = [m for m in sent if m.get("method") == "textDocument/publishDiagnostics"]
    assert publishes, "no diagnostics were published"
    result: list[dict[str, Any]] = publishes[-1]["params"]["diagnostics"]
    return result


def hover_at(
    server: LanguageServer, character: int, uri: str = "file.arb"
) -> dict[str, Any] | None:
    return server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": 0, "character": character},
            },
        }
    )


# ------------------------------------------------------------------ protocol


def test_protocol_round_trip():
    buffer = io.BytesIO()
    message = {"jsonrpc": "2.0", "id": 7, "result": {"نجاح": True}}
    write_message(buffer, message)
    buffer.seek(0)
    assert read_message(buffer) == message


def test_protocol_eof_returns_none():
    assert read_message(io.BytesIO(b"")) is None


def test_protocol_frame_has_content_length_header():
    buffer = io.BytesIO()
    write_message(buffer, {"a": 1})
    assert buffer.getvalue().startswith(b"Content-Length: ")


# --------------------------------------------------------------- lifecycle


def test_initialize_advertises_capabilities():
    server, _ = make_server()
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response is not None
    caps = response["result"]["capabilities"]
    assert caps["hoverProvider"] is True
    assert caps["completionProvider"] is not None
    assert caps["documentSymbolProvider"] is True


def test_unknown_request_returns_method_not_found():
    server, _ = make_server()
    response = server.handle({"jsonrpc": "2.0", "id": 5, "method": "nope/nope", "params": {}})
    assert response is not None
    assert response["error"]["code"] == -32601


def test_notification_returns_no_response():
    server, _ = make_server()
    assert server.handle({"jsonrpc": "2.0", "method": "initialized", "params": {}}) is None


# -------------------------------------------------------------- diagnostics


def test_clean_document_publishes_no_diagnostics():
    server, sent = make_server()
    open_doc(server, "اطبع 1\n")
    assert last_diagnostics(sent) == []


def test_syntax_error_is_published():
    server, sent = make_server()
    open_doc(server, "خلي = 5\n")
    codes = [d["code"] for d in last_diagnostics(sent)]
    assert "E2005" in codes


def test_type_error_is_published():
    server, sent = make_server()
    open_doc(server, 'خلي س : رقم = "نص"\n')
    diags = last_diagnostics(sent)
    assert diags[0]["code"] == "E5001"
    assert diags[0]["severity"] == 1
    assert diags[0]["source"] == "arabic"


def test_did_change_recomputes_diagnostics():
    server, sent = make_server()
    open_doc(server, "خلي = 5\n")
    assert last_diagnostics(sent)  # has errors
    server.handle(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {"uri": "file.arb"},
                "contentChanges": [{"text": "اطبع 1\n"}],
            },
        }
    )
    assert last_diagnostics(sent) == []


def test_did_close_clears_diagnostics():
    server, sent = make_server()
    open_doc(server, "خلي = 5\n")
    server.handle(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didClose",
            "params": {"textDocument": {"uri": "file.arb"}},
        }
    )
    assert last_diagnostics(sent) == []


def test_diagnostic_range_is_zero_based():
    server, sent = make_server()
    open_doc(server, 'خلي س : رقم = "نص"\n')
    rng = last_diagnostics(sent)[0]["range"]
    assert rng["start"]["line"] == 0
    assert rng["start"]["character"] >= 0


# --------------------------------------------------------- hover/completion


def test_hover_on_keyword():
    server, _ = make_server()
    open_doc(server, "اطبع 1\n")
    response = hover_at(server, 1)
    assert response is not None
    assert "اطبع" in response["result"]["contents"]["value"]


def test_hover_on_builtin():
    server, _ = make_server()
    open_doc(server, 'اطبع طول("x")\n')
    response = hover_at(server, 6)
    assert response is not None
    assert response["result"] is not None
    assert "طول" in response["result"]["contents"]["value"]


def test_hover_on_nothing_returns_null():
    server, _ = make_server()
    open_doc(server, "اطبع 123\n")
    response = hover_at(server, 6)
    assert response is not None
    assert response["result"] is None


def test_completion_includes_keywords_builtins_and_types():
    server, _ = make_server()
    open_doc(server, "")
    response = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "textDocument/completion", "params": {}}
    )
    assert response is not None
    labels = {item["label"] for item in response["result"]["items"]}
    assert {"اطبع", "دالة", "طول", "رقم"} <= labels


# -------------------------------------------------------- document symbols


def test_document_symbols_list_functions_and_variables():
    server, _ = make_server()
    open_doc(server, "دالة س ()\n    رجّع 1\nخلاص\nخلي ع = 5\n")
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": "file.arb"}},
        }
    )
    assert response is not None
    names = {s["name"]: s["kind"] for s in response["result"]}
    assert names.get("س") == 12  # function
    assert names.get("ع") == 13  # variable


# -------------------------------------------------------------- serve loop


def test_serve_loop_initializes_and_exits():
    stdin = io.BytesIO()
    write_message(stdin, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    write_message(stdin, {"jsonrpc": "2.0", "method": "exit"})
    stdin.seek(0)
    stdout = io.BytesIO()
    assert serve(stdin, stdout) == 0
    stdout.seek(0)
    first = read_message(stdout)
    assert first is not None
    assert first["id"] == 1
    assert "capabilities" in first["result"]


def test_serve_publishes_diagnostics_over_stdio():
    stdin = io.BytesIO()
    write_message(
        stdin,
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": "f.arb", "text": "خلي = 5\n"}},
        },
    )
    write_message(stdin, {"jsonrpc": "2.0", "method": "exit"})
    stdin.seek(0)
    stdout = io.BytesIO()
    serve(stdin, stdout)
    stdout.seek(0)
    published = read_message(stdout)
    assert published is not None
    assert published["method"] == "textDocument/publishDiagnostics"
    assert any(d["code"] == "E2005" for d in published["params"]["diagnostics"])


def test_json_payload_is_utf8_not_ascii_escaped():
    buffer = io.BytesIO()
    write_message(buffer, {"m": "اطبع"})
    body = buffer.getvalue().split(b"\r\n\r\n", 1)[1]
    assert "اطبع" in body.decode("utf-8")
    assert json.loads(body.decode("utf-8"))["m"] == "اطبع"
