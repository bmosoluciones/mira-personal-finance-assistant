# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for the optional HTTP chat client (no local model involved)."""

from __future__ import annotations

import io
import json
from urllib import error

import pytest

from mira.ai.llm_config import LlmConfig
from mira.ai.remote_chat import RemoteChatEngine, _NoRedirect, _normalize_language


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


class _FakeRequest:
    def __init__(self, full_url: str) -> None:
        self.full_url = full_url


class _RaisingOpener:
    """Opener whose open() always raises, like a real transport error."""

    def __init__(self, raiser: object) -> None:
        self._raiser = raiser

    def open(self, req: object, timeout: int = 0) -> _FakeResponse:
        return self._raiser(req, timeout)  # type: ignore[operator, no-any-return]


class _Opener:
    """Stand-in for the opener built by request.build_opener."""

    def __init__(self, handler: object, payload: object) -> None:
        self.handler = handler
        self.requests: list[object] = []
        self._payload = payload

    def open(self, req: object, timeout: int = 0) -> _FakeResponse:
        assert timeout > 0
        self.requests.append(req)
        return _FakeResponse(self._payload)


class _Recorder:
    def __init__(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> None:
        self.openers: list[_Opener] = []

        def _build_opener(*handlers: object) -> _Opener:
            opener = _Opener(handlers, payload)
            self.openers.append(opener)
            return opener

        monkeypatch.setattr("mira.ai.remote_chat.request.build_opener", _build_opener)

    @property
    def requests(self) -> list[object]:
        return self.openers[-1].requests if self.openers else []

    @property
    def handler(self) -> object:
        return self.openers[-1].handler

    @property
    def last(self) -> object:
        return self.requests[-1]


def _config(**overrides: object) -> LlmConfig:
    payload: dict[str, object] = {
        "provider": "openai_compatible",
        "base_url": "http://localhost:1234/v1",
        "model": "local-model",
        "api_key": "",
        "interaction_mode": "chat",
        "third_party_ack": False,
        "ack_host": "",
    }
    payload.update(overrides)
    return LlmConfig(**payload)  # type: ignore[arg-type]


def test_normalize_language_only_supports_spanish_and_english() -> None:
    assert _normalize_language("es") == "es"
    assert _normalize_language("ES") == "es"
    assert _normalize_language("fr") == "en"
    assert _normalize_language(None) == "en"


def test_parse_is_not_available_in_chat_mode() -> None:
    engine = RemoteChatEngine(_config())

    with pytest.raises(NotImplementedError):
        engine.parse("received 500 salary")


def test_openai_compatible_chat_posts_prompt_and_user_text_only(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(
        {"choices": [{"message": {"content": "  Hello there  "}}]},
        monkeypatch,
    )
    engine = RemoteChatEngine(_config(api_key="sk-test"), language="es")

    reply = engine.chat("como voy este mes?")

    assert reply == "Hello there"
    req = recorder.last
    assert req.full_url == "http://localhost:1234/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer sk-test"
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "local-model"
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1] == {"role": "user", "content": "como voy este mes?"}


def test_remote_http_endpoint_is_rejected_before_sending_text_or_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder({"choices": [{"message": {"content": "never"}}]}, monkeypatch)
    config = _config(
        base_url="http://api.example.com/v1",
        api_key="sk-secret",
        third_party_ack=True,
        ack_host="api.example.com",
    )

    with pytest.raises(RuntimeError, match="requires HTTPS"):
        RemoteChatEngine(config).chat("private financial details")

    assert recorder.requests == []


def test_openai_compatible_chat_does_not_send_api_key_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder({"choices": [{"message": {"content": "ok"}}]}, monkeypatch)

    RemoteChatEngine(_config()).chat("hola")

    assert recorder.last.get_header("Authorization") is None


def test_openai_compatible_chat_rejects_empty_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    _Recorder({"choices": []}, monkeypatch)

    with pytest.raises(RuntimeError, match="no choices"):
        RemoteChatEngine(_config()).chat("hola")


def test_openai_compatible_chat_rejects_empty_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _Recorder({"choices": [{"message": {"content": "   "}}]}, monkeypatch)

    with pytest.raises(RuntimeError, match="empty message"):
        RemoteChatEngine(_config()).chat("hola")


def test_anthropic_chat_uses_messages_endpoint_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder({"content": [{"text": "答复"}]}, monkeypatch)
    engine = RemoteChatEngine(
        _config(provider="anthropic", base_url="", model="claude-3-5-haiku-latest", api_key="ant-key"),
        language="en",
    )

    reply = engine.chat("hi")

    assert reply == "答复"
    req = recorder.last
    assert req.full_url == "https://api.anthropic.com/v1/messages"
    assert req.get_header("X-api-key") == "ant-key"
    assert req.get_header("Anthropic-version") == "2023-06-01"
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "claude-3-5-haiku-latest"
    assert isinstance(body["system"], str) and body["system"]
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_http_error_is_reported_as_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _open(req: object, timeout: int = 0) -> _FakeResponse:
        raise error.HTTPError(
            "http://localhost:1234/v1/chat/completions",
            500,
            "boom",
            hdrs=None,  # type: ignore[arg-type]
            fp=io.BytesIO(b"server exploded"),
        )

    monkeypatch.setattr("mira.ai.remote_chat.request.build_opener", lambda *_handlers: _RaisingOpener(_open))

    with pytest.raises(RuntimeError, match="HTTP 500"):
        RemoteChatEngine(_config()).chat("hola")


def test_unreachable_endpoint_is_reported_as_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _open(req: object, timeout: int = 0) -> _FakeResponse:
        raise error.URLError("connection refused")

    monkeypatch.setattr("mira.ai.remote_chat.request.build_opener", lambda *_handlers: _RaisingOpener(_open))

    with pytest.raises(RuntimeError, match="unreachable"):
        RemoteChatEngine(_config()).chat("hola")


def test_redirects_are_not_followed_so_the_api_key_cannot_change_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 307 would carry Authorization to a host the consent never covered."""
    recorder = _Recorder({"choices": [{"message": {"content": "ok"}}]}, monkeypatch)

    RemoteChatEngine(_config(api_key="sk-test")).chat("hola")

    handler = recorder.handler
    assert isinstance(handler, tuple) and len(handler) == 1
    assert isinstance(handler[0], _NoRedirect)
    with pytest.raises(error.HTTPError, match="redirects are not followed"):
        handler[0].redirect_request(
            _FakeRequest("http://localhost:1234/v1/chat/completions"),
            None,
            307,
            "Temporary Redirect",
            {},
            "https://evil.example/collect",
        )


def test_anthropic_chat_without_api_key_fails_before_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder({"content": [{"text": "never"}]}, monkeypatch)
    engine = RemoteChatEngine(_config(provider="anthropic", base_url="", model="claude-3-5-haiku-latest"), language="en")

    with pytest.raises(RuntimeError, match="needs an API key"):
        engine.chat("hi")

    assert recorder.requests == []


def test_anthropic_chat_treats_a_blank_api_key_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder({"content": [{"text": "never"}]}, monkeypatch)
    engine = RemoteChatEngine(
        _config(provider="anthropic", base_url="", model="claude-3-5-haiku-latest", api_key="   "),
        language="en",
    )

    with pytest.raises(RuntimeError, match="needs an API key"):
        engine.chat("hi")

    assert recorder.requests == []


def test_non_object_json_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _Recorder(["not", "an", "object"], monkeypatch)

    with pytest.raises(RuntimeError, match="non-object"):
        RemoteChatEngine(_config()).chat("hola")


def test_set_language_normalizes_to_supported_values() -> None:
    engine = RemoteChatEngine(_config())

    engine.set_language("es")
    assert engine._language == "es"

    engine.set_language("de")
    assert engine._language == "en"
