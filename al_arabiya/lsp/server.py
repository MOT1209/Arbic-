"""A dependency-free Language Server for AlArabiya.

It reuses the existing frontend (lexer/parser) and the gradual type checker to
provide live diagnostics, and offers hover, completion and document symbols.
The server logic is separated from the stdio loop so it can be unit-tested by
feeding it decoded JSON-RPC messages directly.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from al_arabiya.compiler.ast.nodes import FunctionDeclaration, VariableDeclaration
from al_arabiya.compiler.checker import check_types
from al_arabiya.compiler.diagnostics.diagnostics import Diagnostic
from al_arabiya.compiler.frontend import compile_source
from al_arabiya.compiler.lexer.lexer import Lexer
from al_arabiya.compiler.lexer.tokens import KEYWORDS, TokenType
from al_arabiya.lsp.protocol import read_message, write_message
from al_arabiya.runtime.builtins import BUILTINS

__all__ = ["LanguageServer", "main", "serve"]

# LSP enums ------------------------------------------------------------------
_SEVERITY_ERROR = 1
_SEVERITY_WARNING = 2
_KIND_FUNCTION_COMPLETION = 3
_KIND_KEYWORD = 14
_KIND_CLASS = 7
_SYMBOL_FUNCTION = 12
_SYMBOL_VARIABLE = 13
_METHOD_NOT_FOUND = -32601

# Hover help -----------------------------------------------------------------
_KEYWORD_HELP: dict[str, str] = {
    "اطبع": "اطبع <تعبير> — بتطبع قيمة على الشاشة",
    "خلي": "خلي <اسم> = <قيمة> — بتعرّف متغيّر",
    "لو": "لو <شرط> ... غير كده ... خلاص — جملة شرطية",
    "غير": "غير كده — الفرع البديل للشرط",
    "كده": "غير كده — الفرع البديل للشرط",
    "خلاص": "خلاص — بتقفل أي كتلة (شرط/حلقة/دالة/حاول)",
    "كرر": "كرر <عدد> مرات ... خلاص — حلقة بعدد ثابت",
    "مرات": "كرر <عدد> مرات — كلمة التكرار",
    "طالما": "طالما <شرط> ... خلاص — حلقة بشرط",
    "دالة": "دالة <اسم> (<معاملات>) ... خلاص — تعريف دالة",
    "رجّع": "رجّع <قيمة> — بترجّع قيمة من الدالة",
    "اكسر": "اكسر — بتوقف أقرب حلقة",
    "كمل": "كمل — بتروح للّفة اللي بعدها",
    "لكل": "لكل <اسم> في <قائمة> ... خلاص — حلقة على العناصر",
    "استورد": "استورد \"ملف\" — بيجيب أسماء من ملف تاني",
    "باسم": "استورد \"ملف\" باسم <اسم> — استيراد كـ namespace",
    "من": "من \"ملف\" استورد أ، ب — استيراد انتقائي",
    "حاول": "حاول ... امسك ... أخيرا ... خلاص — معالجة أخطاء",
    "امسك": "امسك [اسم] — بتمسك الخطأ",
    "أخيرا": "أخيرا — بتشتغل دايمًا (تنظيف)",
    "ارم": "ارم <قيمة> — بترمي خطأ",
    "فراغ": "فراغ — القيمة الفارغة (null)",
    "صح": "صح — القيمة المنطقية true",
    "غلط": "غلط — القيمة المنطقية false",
}

_BUILTIN_HELP: dict[str, str] = {
    "طول": "طول(x) — طول نص/قائمة/قاموس",
    "نوع": "نوع(x) — اسم نوع القيمة",
    "رقم": "رقم(x) — تحويل لرقم",
    "نص": "نص(x) — تحويل لنص",
    "منطقي": "منطقي(x) — القيمة المنطقية",
    "اقرأ": "اقرأ([رسالة]) — قراءة سطر من المستخدم",
    "مطلق": "مطلق(x) — القيمة المطلقة",
    "قرّب": "قرّب(x) — تقريب لأقرب عدد صحيح",
    "جذر": "جذر(x) — الجذر التربيعي",
    "اس": "اس(أساس، قوة) — الأساس مرفوع للقوة",
    "اضف": "اضف(قائمة، قيمة) — يضيف عنصرًا",
    "احذف": "احذف(قائمة، فهرس) — يشيل عنصرًا",
    "مدى": "مدى(ن) / مدى(ا، ن) — قائمة أرقام",
    "مجموع": "مجموع(قائمة) — مجموع الأرقام",
    "اكبر": "اكبر(قائمة) — أكبر رقم",
    "اصغر": "اصغر(قائمة) — أصغر رقم",
    "رتب": "رتب(قائمة) — قائمة مرتّبة",
    "اعكس": "اعكس(x) — عكس قائمة أو نص",
    "يحتوي": "يحتوي(حاوية، عنصر) — هل العنصر موجود؟",
    "مفاتيح": "مفاتيح(قاموس) — قائمة المفاتيح",
    "قيم": "قيم(قاموس) — قائمة القيم",
    "قسّم": "قسّم(نص، فاصل) — تقسيم لقائمة",
    "ادمج": "ادمج(قائمة، فاصل) — دمج في نص",
    "استبدل": "استبدل(نص، قديم، جديد) — استبدال",
}

_TYPE_NAMES = ("رقم", "نص", "منطقي", "فراغ", "قائمة", "قاموس", "دالة", "أي")


def _offset_at(text: str, line: int, character: int) -> int:
    """Convert a 0-based LSP (line, character) to a code-point offset."""
    lines = text.split("\n")
    if line < 0:
        return 0
    if line >= len(lines):
        return len(text)
    offset = sum(len(current) + 1 for current in lines[:line])
    return offset + min(max(character, 0), len(lines[line]))


def _to_lsp_range(diagnostic: Diagnostic) -> dict[str, Any]:
    start = diagnostic.span.start
    end = diagnostic.span.end
    # LSP is 0-based; keep end >= start.
    start_pos = {"line": start.line - 1, "character": start.column - 1}
    end_line = max(end.line - 1, start.line - 1)
    end_char = end.column - 1 if end.line >= start.line else start.column
    return {"start": start_pos, "end": {"line": end_line, "character": max(end_char, 0)}}


def _to_lsp_diagnostic(diagnostic: Diagnostic) -> dict[str, Any]:
    message = diagnostic.message
    if diagnostic.suggestion:
        message = f"{message}\n💡 {diagnostic.suggestion}"
    return {
        "range": _to_lsp_range(diagnostic),
        "severity": _SEVERITY_ERROR if diagnostic.is_error else _SEVERITY_WARNING,
        "code": str(diagnostic.code),
        "source": "arabic",
        "message": message,
    }


class LanguageServer:
    """Handles decoded JSON-RPC messages; sends server notifications via ``send``."""

    def __init__(self, send: Callable[[dict[str, Any]], None]) -> None:
        self._send = send
        self._documents: dict[str, str] = {}
        self.shutdown_requested = False

    # ------------------------------------------------------------- dispatch

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            return self._respond(msg_id, self._initialize())
        if method == "shutdown":
            self.shutdown_requested = True
            return self._respond(msg_id, None)
        if method in ("initialized", "exit"):
            return None
        if method == "textDocument/didOpen":
            self._did_open(params)
            return None
        if method == "textDocument/didChange":
            self._did_change(params)
            return None
        if method == "textDocument/didClose":
            self._did_close(params)
            return None
        if method == "textDocument/hover":
            return self._respond(msg_id, self._hover(params))
        if method == "textDocument/completion":
            return self._respond(msg_id, self._completion())
        if method == "textDocument/documentSymbol":
            return self._respond(msg_id, self._document_symbol(params))

        if msg_id is None:
            return None  # unknown notification: ignore
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": _METHOD_NOT_FOUND, "message": f"method not found: {method}"},
        }

    @staticmethod
    def _respond(msg_id: Any, result: Any) -> dict[str, Any] | None:
        if msg_id is None:
            return None
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # ------------------------------------------------------------- lifecycle

    @staticmethod
    def _initialize() -> dict[str, Any]:
        return {
            "capabilities": {
                "textDocumentSync": 1,  # full document sync
                "hoverProvider": True,
                "completionProvider": {"triggerCharacters": []},
                "documentSymbolProvider": True,
            },
            "serverInfo": {"name": "al-arabiya-lsp", "version": "0.1.0"},
        }

    # --------------------------------------------------------- document sync

    def _did_open(self, params: dict[str, Any]) -> None:
        document = params.get("textDocument", {})
        uri = document.get("uri", "")
        self._documents[uri] = document.get("text", "")
        self._publish_diagnostics(uri)

    def _did_change(self, params: dict[str, Any]) -> None:
        uri = params.get("textDocument", {}).get("uri", "")
        changes = params.get("contentChanges", [])
        if changes:
            # full sync: the last change carries the whole document
            self._documents[uri] = changes[-1].get("text", "")
            self._publish_diagnostics(uri)

    def _did_close(self, params: dict[str, Any]) -> None:
        uri = params.get("textDocument", {}).get("uri", "")
        self._documents.pop(uri, None)
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": []},
            }
        )

    def _publish_diagnostics(self, uri: str) -> None:
        text = self._documents.get(uri, "")
        diagnostics = [_to_lsp_diagnostic(d) for d in self.compute_diagnostics(text, uri)]
        self._send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diagnostics},
            }
        )

    @staticmethod
    def compute_diagnostics(text: str, uri: str) -> list[Diagnostic]:
        """Syntax (+ lexer) diagnostics plus static type diagnostics."""
        result = compile_source(text, uri)
        diagnostics: list[Diagnostic] = list(result.diagnostics)
        if result.program is not None:
            diagnostics.extend(check_types(result.program))
        return diagnostics

    # --------------------------------------------------------------- hover

    def _hover(self, params: dict[str, Any]) -> dict[str, Any] | None:
        uri = params.get("textDocument", {}).get("uri", "")
        position = params.get("position", {})
        text = self._documents.get(uri)
        if text is None:
            return None
        offset = _offset_at(text, position.get("line", 0), position.get("character", 0))
        word = self._word_at(text, offset)
        if word is None:
            return None
        description = _KEYWORD_HELP.get(word) or _BUILTIN_HELP.get(word)
        if description is None:
            return None
        return {"contents": {"kind": "plaintext", "value": description}}

    @staticmethod
    def _word_at(text: str, offset: int) -> str | None:
        for token in Lexer(text).tokenize():
            if token.type in (TokenType.EOF, TokenType.NEWLINE):
                continue
            start = token.span.start.offset
            end = token.span.end.offset
            if start <= offset < end or (start == end == offset):
                return token.raw
        return None

    # ------------------------------------------------------------ completion

    def _completion(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for word in KEYWORDS:
            items.append(
                {
                    "label": word,
                    "kind": _KIND_KEYWORD,
                    "detail": _KEYWORD_HELP.get(word, "كلمة مفتاحية"),
                }
            )
        for builtin in BUILTINS:
            items.append(
                {
                    "label": builtin.name,
                    "kind": _KIND_FUNCTION_COMPLETION,
                    "detail": _BUILTIN_HELP.get(builtin.name, "دالة مدمجة"),
                }
            )
        for type_name in _TYPE_NAMES:
            items.append(
                {"label": type_name, "kind": _KIND_CLASS, "detail": "نوع"}
            )
        return {"isIncomplete": False, "items": items}

    # -------------------------------------------------------- documentSymbol

    def _document_symbol(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        uri = params.get("textDocument", {}).get("uri", "")
        text = self._documents.get(uri)
        if text is None:
            return []
        result = compile_source(text, uri)
        if result.program is None:
            return []
        symbols: list[dict[str, Any]] = []
        for statement in result.program.body:
            if isinstance(statement, FunctionDeclaration):
                symbols.append(
                    self._symbol(statement.name, _SYMBOL_FUNCTION, statement.span)
                )
            elif isinstance(statement, VariableDeclaration):
                symbols.append(
                    self._symbol(statement.name, _SYMBOL_VARIABLE, statement.span)
                )
        return symbols

    @staticmethod
    def _symbol(name: str, kind: int, span: Any) -> dict[str, Any]:
        rng = {
            "start": {"line": span.start.line - 1, "character": span.start.column - 1},
            "end": {
                "line": max(span.end.line - 1, span.start.line - 1),
                "character": max(span.end.column - 1, 0),
            },
        }
        return {"name": name, "kind": kind, "range": rng, "selectionRange": rng}


def serve(stdin: Any, stdout: Any) -> int:
    """Run the stdio read/dispatch/write loop until the client exits."""
    server = LanguageServer(send=lambda message: write_message(stdout, message))
    while True:
        message = read_message(stdin)
        if message is None:
            break
        response = server.handle(message)
        if response is not None:
            write_message(stdout, response)
        if message.get("method") == "exit":
            break
    return 0


def main() -> int:
    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
