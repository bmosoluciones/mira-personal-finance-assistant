# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Protocol tests for the optional MCP stdio server.

The stdio transport is newline-delimited JSON-RPC (one message per line, no
headers). These tests pin that framing down, because getting it wrong makes the
server unusable with a real MCP client while every unit test still passes.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from mira import mcp_server


class _FakeStdin:
    """Minimal stand-in for ``sys.stdin`` with a binary buffer."""

    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


class _FakeStdout:
    """Captures what the server writes, keeping the framing observable."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    @property
    def lines(self) -> list[bytes]:
        raw = self.buffer.getvalue()
        return [line for line in raw.split(b"\n") if line]


def _encode(message: dict[str, Any]) -> bytes:
    return json.dumps(message).encode("utf-8") + b"\n"


def _request(method: str, message_id: Any = 1, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def _modern_request(method: str, message_id: Any = 1, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _request(method, message_id, params or {})
    payload["params"]["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    return payload


def _serve(payload: bytes, monkeypatch: pytest.MonkeyPatch, db_path: str = "/tmp/mira.db") -> tuple[int, list[dict[str, Any]]]:
    stdout = _FakeStdout()
    monkeypatch.setattr(mcp_server.sys, "stdin", _FakeStdin(payload))
    monkeypatch.setattr(mcp_server.sys, "stdout", stdout)
    exit_code = mcp_server.serve_stdio(db_path)
    return exit_code, [json.loads(line) for line in stdout.lines]


def test_initialize_advertises_protocol_version_and_server_info(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, replies = _serve(_encode(_request("initialize")), monkeypatch)

    assert exit_code == 0
    assert len(replies) == 1
    result = replies[0]["result"]
    assert replies[0]["id"] == 1
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "mira"


def test_modern_discovery_advertises_supported_protocol_and_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _exit_code, replies = _serve(_encode(_modern_request("server/discover")), monkeypatch)

    result = replies[0]["result"]
    assert result["supportedVersions"] == ["2026-07-28"]
    assert result["capabilities"] == {"tools": {}}
    assert result["resultType"] == "complete"
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "mira"


def test_modern_requests_require_metadata_and_reject_unsupported_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = _request("server/discover")
    unsupported = _modern_request("server/discover")
    unsupported["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] = "1900-01-01"
    payload = _encode(missing) + _encode(unsupported)

    _exit_code, replies = _serve(payload, monkeypatch)

    assert replies[0]["error"]["code"] == -32602
    assert replies[1]["error"]["code"] == -32022
    assert replies[1]["error"]["data"]["supported"] == ["2026-07-28"]


def test_modern_tools_list_has_result_type_and_cache_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    _exit_code, replies = _serve(_encode(_modern_request("tools/list")), monkeypatch)

    result = replies[0]["result"]
    assert result["resultType"] == "complete"
    assert result["ttlMs"] > 0
    assert result["cacheScope"] == "private"
    assert len(result["tools"]) == 5


def test_stdio_transport_is_newline_delimited_not_lsp_framed(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = _FakeStdout()
    monkeypatch.setattr(mcp_server.sys, "stdin", _FakeStdin(_encode(_modern_request("server/discover"))))
    monkeypatch.setattr(mcp_server.sys, "stdout", stdout)

    mcp_server.serve_stdio("/tmp/mira.db")

    raw = stdout.buffer.getvalue()
    assert raw.endswith(b"\n")
    assert b"Content-Length" not in raw
    assert b"\r\n" not in raw
    assert len(stdout.lines) == 1


def test_ping_is_removed_from_the_modern_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    _exit_code, replies = _serve(_encode(_modern_request("ping")), monkeypatch)

    assert replies[0]["error"]["code"] == -32601


def test_tools_list_exposes_the_finance_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _exit_code, replies = _serve(_encode(_modern_request("tools/list")), monkeypatch)

    names = [tool["name"] for tool in replies[0]["result"]["tools"]]
    assert names == ["add_income", "add_expense", "transfer", "list_transactions", "report"]
    for tool in replies[0]["result"]["tools"]:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


def test_notifications_and_blank_lines_get_no_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _encode({"jsonrpc": "2.0", "method": "notifications/initialized"}) + b"\n" + b"   \n"
    exit_code, replies = _serve(payload + _encode(_modern_request("server/discover")), monkeypatch)

    assert exit_code == 0
    assert replies[0]["result"]["supportedVersions"] == ["2026-07-28"]


def test_malformed_and_non_object_messages_return_jsonrpc_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"{not json at all}\n" + b"\xff\xfe invalid utf-8\n" + b'["a list is not a request"]\n' + _encode(_modern_request("server/discover"))
    exit_code, replies = _serve(payload, monkeypatch)

    assert exit_code == 0
    assert [reply["error"]["code"] for reply in replies[:3]] == [-32700, -32700, -32600]
    assert replies[3]["result"]["supportedVersions"] == ["2026-07-28"]


def test_unknown_method_returns_method_not_found_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _exit_code, replies = _serve(_encode(_modern_request("resources/list", message_id=7)), monkeypatch)

    assert replies[0]["id"] == 7
    assert replies[0]["error"]["code"] == -32601
    assert "resources/list" in replies[0]["error"]["message"]


def test_tool_failure_is_reported_as_is_error_not_a_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_server, "_mcp_consent_enabled", lambda _db_path: True)

    def _boom(_db_path: str, _name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("Account not found: Nope")

    monkeypatch.setattr(mcp_server, "_call_tool", _boom)
    payload = _encode(_modern_request("tools/call", params={"name": "add_expense", "arguments": {"amount": "1", "account": "Nope"}}))

    exit_code, replies = _serve(payload, monkeypatch)

    assert exit_code == 0
    assert "error" not in replies[0]
    assert replies[0]["result"]["isError"] is True
    assert "Account not found" in replies[0]["result"]["content"][0]["text"]


def test_closed_client_pipe_ends_the_loop_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_mcp_consent_enabled", lambda _db_path: True)

    def _broken(_db_path: str, _name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
        raise OSError("Broken pipe")

    monkeypatch.setattr(mcp_server, "_call_tool", _broken)
    payload = _encode(_modern_request("tools/call", params={"name": "report", "arguments": {}}))

    exit_code, replies = _serve(payload, monkeypatch)

    assert exit_code == 0
    assert replies[0]["result"]["isError"] is True


def test_active_session_rejects_tools_after_consent_is_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    consent_states = iter((True, False))
    executed_tools: list[str] = []
    monkeypatch.setattr(mcp_server, "_mcp_consent_enabled", lambda _db_path: next(consent_states))
    monkeypatch.setattr(
        mcp_server,
        "_call_tool",
        lambda _db_path, name, _arguments: executed_tools.append(name) or {"content": []},
    )
    payload = _encode(_modern_request("tools/call", message_id=1, params={"name": "report", "arguments": {}}))
    payload += _encode(_modern_request("tools/call", message_id=2, params={"name": "add_expense", "arguments": {}}))

    exit_code, replies = _serve(payload, monkeypatch)

    assert exit_code == 0
    assert executed_tools == ["report"]
    assert replies[0]["id"] == 1
    assert replies[0]["result"]["content"] == []
    assert replies[0]["result"]["resultType"] == "complete"
    assert replies[1]["id"] == 2
    assert replies[1]["result"]["isError"] is True
    assert "revoked" in replies[1]["result"]["content"][0]["text"]


def test_eof_without_any_request_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, replies = _serve(b"", monkeypatch)

    assert exit_code == 0
    assert replies == []


def test_cli_argv_maps_each_tool_to_the_matching_command() -> None:
    db_path = "/tmp/mira.db"

    assert mcp_server._cli_argv(db_path, "add_income", {"amount": "10", "account": "Cash"})[-6:] == [
        "income",
        "add",
        "--amount",
        "10",
        "--account",
        "Cash",
    ]
    assert mcp_server._cli_argv(db_path, "add_expense", {"amount": "3", "account": "Cash"})[-6:] == [
        "expense",
        "add",
        "--amount",
        "3",
        "--account",
        "Cash",
    ]
    transfer = mcp_server._cli_argv(db_path, "transfer", {"source": "A", "target": "B", "amount": "5"})
    assert transfer[-7:] == ["transfer", "--from", "A", "--to", "B", "--amount", "5"]
    listing = mcp_server._cli_argv(db_path, "list_transactions", {"limit": 7, "account": "Cash"})
    assert listing[-6:] == ["transactions", "list", "--limit", "7", "--account", "Cash"]
    assert mcp_server._cli_argv(db_path, "report", {})[-1] == "report"
    assert mcp_server._cli_argv(db_path, "list_transactions", {}).count("--limit") == 1
    assert "--require-mcp-consent" in listing


def test_cli_argv_rejects_an_unknown_tool() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        mcp_server._cli_argv("/tmp/mira.db", "drop_database", {})


def test_optional_flags_only_appended_when_supplied() -> None:
    argv = mcp_server._optional_flags(["expense", "add"], {"note": "with a friend", "date": ""})

    assert argv == ["expense", "add", "--note", "with a friend"]


def test_date_filters_are_built_once_per_tool() -> None:
    # report and list_transactions own their --since/--until, so _optional_flags
    # must not add them again: argparse would keep the last value and the
    # duplication hid the fact that neither branch was tested.
    report = mcp_server._cli_argv("/tmp/mira.db", "report", {"since": "2026-01-01"})
    listing = mcp_server._cli_argv(
        "/tmp/mira.db",
        "list_transactions",
        {"limit": 5, "account": "Cash", "since": "2026-01-01", "until": "2026-02-01"},
    )

    assert report[-3:] == ["report", "--since", "2026-01-01"]
    assert report.count("--since") == 1
    assert listing.count("--since") == 1
    assert listing.count("--until") == 1
    assert listing[-4:] == ["--since", "2026-01-01", "--until", "2026-02-01"]


def test_call_tool_returns_the_cli_json_as_text_content(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(argv: list[str], **_kwargs: Any) -> Any:
        assert "--json" in argv
        assert "--require-mcp-consent" in argv
        return type("Completed", (), {"returncode": 0, "stdout": '{"ok": true}', "stderr": ""})()

    monkeypatch.setattr(mcp_server.subprocess, "run", _fake_run)
    result = mcp_server._call_tool("/tmp/mira.db", "report", {})

    assert json.loads(result["content"][0]["text"]) == {"ok": True}


def test_call_tool_raises_on_a_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(_argv: list[str], **_kwargs: Any) -> Any:
        return type("Completed", (), {"returncode": 2, "stdout": "", "stderr": "Account not found: Nope"})()

    monkeypatch.setattr(mcp_server.subprocess, "run", _fake_run)

    with pytest.raises(RuntimeError, match="Account not found"):
        mcp_server._call_tool("/tmp/mira.db", "add_expense", {"amount": "1", "account": "Nope"})


def test_server_imports_no_qt() -> None:
    source = Path(mcp_server.__file__).read_text(encoding="utf-8")

    assert "PySide6" not in source
