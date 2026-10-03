# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Optional MCP stdio server. Each tool runs a mira-cli command. No Qt.

The stdio transport is newline-delimited JSON-RPC, as required by the Model
Context Protocol specification. LSP-style ``Content-Length`` headers are not
used: real MCP clients would not understand them.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)

_TOOLS = (
    {
        "name": "add_income",
        "description": "Record an income in the local MIRA database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "string"},
                "account": {"type": "string"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "date": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["amount", "account"],
        },
    },
    {
        "name": "add_expense",
        "description": "Record an expense in the local MIRA database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "amount": {"type": "string"},
                "account": {"type": "string"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "date": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["amount", "account"],
        },
    },
    {
        "name": "transfer",
        "description": "Transfer money between two local accounts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "amount": {"type": "string"},
                "date": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["source", "target", "amount"],
        },
    },
    {
        "name": "list_transactions",
        "description": "List recent local transactions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "account": {"type": "string"},
                "since": {"type": "string"},
                "until": {"type": "string"},
            },
        },
    },
    {
        "name": "report",
        "description": "Return a local financial summary.",
        "inputSchema": {"type": "object", "properties": {"since": {"type": "string"}}},
    },
)


def _read_message() -> dict[str, Any] | None:
    """Read one newline-delimited JSON-RPC message from stdin."""
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("Ignored a malformed MCP message from stdin.")
            continue
        if not isinstance(payload, dict):
            logger.debug("Ignored an MCP message that is not a JSON-RPC object.")
            continue
        return payload


def _write_message(payload: dict[str, Any]) -> None:
    """Write one newline-delimited JSON-RPC message to stdout."""
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _cli_argv(db_path: str, tool: str, arguments: dict[str, Any]) -> list[str]:
    """Map an MCP tool call to a mira-cli command."""
    base = [sys.executable, "-m", "mira.cli", "--db", db_path, "--json"]
    if tool == "add_income":
        return [*base, "income", "add", "--amount", str(arguments["amount"]), "--account", str(arguments["account"])]
    if tool == "add_expense":
        return [*base, "expense", "add", "--amount", str(arguments["amount"]), "--account", str(arguments["account"])]
    if tool == "transfer":
        return [
            *base,
            "transfer",
            "--from",
            str(arguments["source"]),
            "--to",
            str(arguments["target"]),
            "--amount",
            str(arguments["amount"]),
        ]
    if tool == "list_transactions":
        argv = [*base, "transactions", "list", "--limit", str(int(arguments.get("limit") or 50))]
        if arguments.get("account"):
            argv.extend(["--account", str(arguments["account"])])
        return argv
    if tool == "report":
        argv = [*base, "report"]
        if arguments.get("since"):
            argv.extend(["--since", str(arguments["since"])])
        return argv
    raise ValueError(f"Unknown tool: {tool}")


def _optional_flags(argv: list[str], arguments: dict[str, Any]) -> list[str]:
    """Append optional CLI flags when the client sent them."""
    for key, flag in (("description", "--description"), ("category", "--category"), ("date", "--date"), ("note", "--note"), ("since", "--since"), ("until", "--until")):
        if arguments.get(key):
            argv.extend([flag, str(arguments[key])])
    return argv


def _call_tool(db_path: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run the matching mira-cli command and return its JSON stdout."""
    argv = _optional_flags(_cli_argv(db_path, name, arguments), arguments)
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "mira-cli failed")
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        parsed = {"ok": True, "text": completed.stdout}
    return {"content": [{"type": "text", "text": json.dumps(parsed, default=str)}]}


def serve_stdio(db_path: str) -> int:
    """Serve MCP tools over stdio until the client closes the stream."""
    while True:
        message = _read_message()
        if message is None:
            return 0
        method = str(message.get("method") or "")
        message_id = message.get("id")
        if method == "notifications/initialized" or message_id is None:
            continue
        if method == "initialize":
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "mira", "version": "0.0.1"},
                    },
                }
            )
            continue
        if method == "tools/list":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {"tools": list(_TOOLS)}})
            continue
        if method == "ping":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {}})
            continue
        if method == "tools/call":
            raw_params = message.get("params")
            params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
            name = str(params.get("name") or "")
            raw_arguments = params.get("arguments")
            arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            try:
                result = _call_tool(db_path, name, arguments)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True},
                    }
                )
                continue
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": result})
            continue
        _write_message(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )
