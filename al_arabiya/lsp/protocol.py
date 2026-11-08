"""Minimal JSON-RPC 2.0 framing over a byte stream (the LSP base protocol).

No third-party dependencies: messages are ``Content-Length``-framed UTF-8 JSON,
exactly as the Language Server Protocol specifies.
"""

from __future__ import annotations

import json
from typing import Any, BinaryIO

__all__ = ["read_message", "write_message"]


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    """Read one framed JSON-RPC message, or ``None`` at end of stream."""
    content_length = 0
    while True:
        line = stream.readline()
        if not line:
            return None  # EOF
        stripped = line.strip()
        if stripped == b"":
            break  # blank line ends the headers
        key, _, value = stripped.partition(b":")
        if key.strip().lower() == b"content-length":
            try:
                content_length = int(value.strip())
            except ValueError:
                content_length = 0
    if content_length <= 0:
        return None
    body = stream.read(content_length)
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    """Write one framed JSON-RPC message and flush."""
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    stream.write(header)
    stream.write(body)
    stream.flush()
