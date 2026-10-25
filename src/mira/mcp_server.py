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

from mira import __version__
from mira.ai.llm_config import mcp_enabled
from mira.db.database import Database

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2026-07-28"
_SERVER_INFO = {"name": "mira", "version": __version__}
_SERVER_INFO_META = {"io.modelcontextprotocol/serverInfo": _SERVER_INFO}

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
            logger.debug("Received a malformed MCP message from stdin.")
            return {"__mcp_parse_error__": True}
        if not isinstance(payload, dict):
            logger.debug("Received an MCP message that is not a JSON-RPC object.")
            return {"__mcp_invalid_request__": True}
        return payload


def _write_message(payload: dict[str, Any]) -> None:
    """Write one newline-delimited JSON-RPC message to stdout."""
    sys.stdout.buffer.write(json.dumps(payload).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _cli_argv(db_path: str, tool: str, arguments: dict[str, Any]) -> list[str]:
    """Map an MCP tool call to a mira-cli command."""
    base = [
        sys.executable,
        "-m",
        "mira.cli",
        "--db",
        db_path,
        "--json",
        "--require-mcp-consent",
    ]
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
        for key, flag in (("account", "--account"), ("since", "--since"), ("until", "--until")):
            if arguments.get(key):
                argv.extend([flag, str(arguments[key])])
        return argv
    if tool == "report":
        argv = [*base, "report"]
        if arguments.get("since"):
            argv.extend(["--since", str(arguments["since"])])
        return argv
    raise ValueError(f"Unknown tool: {tool}")


def _optional_flags(argv: list[str], arguments: dict[str, Any]) -> list[str]:
    """Append optional CLI flags when the client sent them."""
    for key, flag in (("description", "--description"), ("category", "--category"), ("date", "--date"), ("note", "--note")):
        if arguments.get(key):
            argv.extend([flag, str(arguments[key])])
    return argv


def _mcp_consent_enabled(db_path: str) -> bool:
    """Re-read MCP consent from the database before exposing finance tools."""
    db = Database(path=db_path)
    try:
        db.connect()
        try:
            return mcp_enabled(db)
        finally:
            db.close()
    except Exception as exc:
        raise RuntimeError(f"Unable to verify MCP consent: {exc}") from exc


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
    legacy_initialized = False
    while True:
        message = _read_message()
        if message is None:
            return 0
        if message.get("__mcp_parse_error__"):
            _write_message({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
            continue
        if message.get("__mcp_invalid_request__"):
            _write_message({"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}})
            continue
        message_id = message.get("id")
        method_value = message.get("method")
        if message.get("jsonrpc") != "2.0" or not isinstance(method_value, str):
            response = {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}}
            if isinstance(message_id, (str, int)) and not isinstance(message_id, bool):
                response["id"] = message_id
            _write_message(response)
            continue
        if "id" in message and (message_id is None or isinstance(message_id, bool) or not isinstance(message_id, (str, int))):
            _write_message({"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}})
            continue
        method = method_value
        if method == "notifications/initialized" or message_id is None:
            continue
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        has_request_meta = "_meta" in params
        raw_request_meta = params.get("_meta")
        request_meta = raw_request_meta if isinstance(raw_request_meta, dict) else {}
        modern = has_request_meta

        # 2026-07-28 is stateless: every request carries protocol metadata.
        # Keep the initialize handshake below for clients on earlier revisions.
        if modern:
            requested_version = request_meta.get("io.modelcontextprotocol/protocolVersion")
            client_capabilities = request_meta.get("io.modelcontextprotocol/clientCapabilities")
            if not isinstance(requested_version, str) or not isinstance(client_capabilities, dict):
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid params: _meta must include protocolVersion and clientCapabilities.",
                        },
                    }
                )
                continue
            if requested_version != _PROTOCOL_VERSION:
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "error": {
                            "code": -32022,
                            "message": "Unsupported protocol version",
                            "data": {"supported": [_PROTOCOL_VERSION], "requested": requested_version},
                        },
                    }
                )
                continue

            def modern_result(result: dict[str, Any]) -> dict[str, Any]:
                result.setdefault("resultType", "complete")
                result["_meta"] = {**result.get("_meta", {}), **_SERVER_INFO_META}
                return {"jsonrpc": "2.0", "id": message_id, "result": result}

            if method == "server/discover":
                _write_message(
                    modern_result(
                        {
                            "supportedVersions": [_PROTOCOL_VERSION],
                            "capabilities": {"tools": {}},
                            "ttlMs": 300000,
                            "cacheScope": "private",
                        }
                    )
                )
                continue
            if method == "initialize":
                _write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": message_id,
                        "error": {
                            "code": -32601,
                            "message": "Method not found: initialize; use server/discover for supported protocol versions.",
                            "data": {"supported": [_PROTOCOL_VERSION]},
                        },
                    }
                )
                continue
            if method == "ping":
                _write_message(
                    {"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": "Method not found: ping"}}
                )
                continue
        elif method != "initialize" and not legacy_initialized:
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "error": {"code": -32602, "message": "Invalid params: request metadata is required."},
                }
            )
            continue
        if method == "initialize":
            legacy_initialized = True
            _write_message(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": _SERVER_INFO,
                    },
                }
            )
            continue
        if method == "tools/list":
            result = {"tools": list(_TOOLS)}
            if modern:
                result.update({"ttlMs": 300000, "cacheScope": "private"})
                _write_message(modern_result(result))
            else:
                _write_message({"jsonrpc": "2.0", "id": message_id, "result": result})
            continue
        if method == "ping":
            _write_message({"jsonrpc": "2.0", "id": message_id, "result": {}})
            continue
        if method == "tools/call":
            name = str(params.get("name") or "")
            raw_arguments = params.get("arguments")
            arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            try:
                if not _mcp_consent_enabled(db_path):
                    raise PermissionError("MCP is disabled or its consent has been revoked in Settings.")
                result = _call_tool(db_path, name, arguments)
            except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
                error_result = {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                }
                if modern:
                    _write_message(modern_result(error_result))
                else:
                    _write_message({"jsonrpc": "2.0", "id": message_id, "result": error_result})
                continue
            _write_message(modern_result(result) if modern else {"jsonrpc": "2.0", "id": message_id, "result": result})
            continue
        _write_message(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )
