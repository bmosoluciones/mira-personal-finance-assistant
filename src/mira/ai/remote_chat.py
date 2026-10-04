# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""HTTP chat client. Talks to a local server or a cloud API. Does not run a model."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error, request

from mira.ai.base_engine import BaseEngine
from mira.ai.llm_config import LlmConfig, endpoint_transport_allowed
from mira.ai.schema_contract import build_chat_system_prompt

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60


def _normalize_language(language: str | None) -> str:
    """Return a supported chat language."""
    return "es" if str(language or "en").strip().lower() == "es" else "en"


class _NoRedirect(request.HTTPRedirectHandler):
    """Refuse every 30x: the API key travels in the headers we just built.

    Consent is bound to the host of the configured base_url, so a redirect
    would carry that key to a host nobody acknowledged.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Return no redirect request, ever."""
        del fp, msg, newurl
        raise error.HTTPError(req.full_url, code, "Chat endpoint redirects are not followed", headers, None)


class RemoteChatEngine(BaseEngine):
    """Chat engine backed by an OpenAI-compatible or Anthropic HTTP API."""

    def __init__(self, config: LlmConfig, *, language: str = "en") -> None:
        """Initialize the RemoteChatEngine instance."""
        self._config = config
        self._language = _normalize_language(language)

    def parse(self, user_input: str) -> dict[str, Any]:
        """Remote chat does not parse transactions."""
        raise NotImplementedError("Remote chat does not parse transactions")

    def set_language(self, language: str) -> None:
        """Update the chat language."""
        self._language = _normalize_language(language)

    def chat(self, user_input: str) -> str:
        """Send only the system prompt and the user's text."""
        system_prompt = (
            build_chat_system_prompt(self._language) + " Reply conversationally in the user's language. "
            "Do not force JSON in this mode."
        )
        if self._config.provider == "anthropic":
            return self._anthropic_chat(system_prompt, user_input)
        return self._openai_chat(system_prompt, user_input)

    def _openai_chat(self, system_prompt: str, user_input: str) -> str:
        """Return a completion from an OpenAI-compatible endpoint."""
        if not endpoint_transport_allowed(self._config.provider, self._config.base_url):
            raise RuntimeError(
                "Remote chat requires HTTPS for non-local endpoints; HTTP is allowed only for loopback endpoints"
            )
        base = self._config.base_url.rstrip("/")
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        payload: dict[str, Any] = {
            "model": self._config.model,
            "temperature": 0.5,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        body = _post_json(url, payload, headers)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("Chat endpoint returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Chat endpoint returned an empty message")
        return content.strip()

    def _anthropic_chat(self, system_prompt: str, user_input: str) -> str:
        """Return a completion from the Anthropic Messages API."""
        if not str(self._config.api_key or "").strip():
            raise RuntimeError("Anthropic needs an API key: save one in Settings before using chat mode")
        payload = {
            "model": self._config.model,
            "max_tokens": 512,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_input}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
        }
        body = _post_json("https://api.anthropic.com/v1/messages", payload, headers)
        content = body.get("content")
        if not isinstance(content, list) or not content:
            raise RuntimeError("Anthropic returned no content")
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Anthropic returned an empty message")
        return text.strip()


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    """POST JSON and return the decoded object."""
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    opener = request.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.warning("Chat HTTP %s: %s", exc.code, detail[:300])
        raise RuntimeError(f"Chat request failed with HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Chat endpoint unreachable: {exc.reason}") from exc
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("Chat endpoint returned a non-object response")
    return decoded
