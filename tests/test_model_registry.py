# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Tests for model discovery and download helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from mira.ai import model_registry as registry


def test_normalize_model_download_url_huggingface_blob_to_resolve() -> None:
    url = "https://huggingface.co/org/model/blob/main/model.gguf"
    normalized = registry.normalize_model_download_url(url)
    assert normalized == "https://huggingface.co/org/model/resolve/main/model.gguf"


def test_model_filename_from_url_decodes_encoded_name() -> None:
    url = "https://example.org/models/My%20Model.gguf"
    assert registry.model_filename_from_url(url) == "My Model.gguf"


def test_model_filename_from_url_raises_without_filename() -> None:
    with pytest.raises(ValueError):
        registry.model_filename_from_url("https://example.org")


def test_find_model_path_by_name_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    candidates = [Path("C:/models/FinanceModel.GGUF"), Path("C:/models/other.gguf")]
    monkeypatch.setattr(registry, "discover_gguf_models", lambda: candidates)

    found = registry.find_model_path_by_name("financemodel.gguf")
    assert found == candidates[0]


def test_get_writable_models_dir_prefers_user_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    user_dir = tmp_path / "user-models"
    executable_dir = tmp_path / "bin"
    executable_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(registry, "get_user_models_dir", lambda: user_dir)
    monkeypatch.setattr(registry.sys, "executable", str(executable_dir / "python.exe"))

    def fake_is_writable(path: Path) -> bool:
        return path == user_dir

    monkeypatch.setattr(registry, "_is_writable_dir", fake_is_writable)

    assert registry.get_writable_models_dir() == user_dir


def test_download_model_to_returns_existing_file_without_network(tmp_path: Path) -> None:
    existing = tmp_path / "already.gguf"
    existing.write_bytes(b"abc")

    progress: list[tuple[int, int]] = []
    result = registry.download_model_to(
        "https://example.org/already.gguf",
        destination_dir=tmp_path,
        progress_callback=lambda done, total: progress.append((done, total)),
    )

    assert result == existing
    assert progress[-1] == (3, 3)


class _FakeResponse:
    def __init__(self, chunks: list[bytes], content_length: str = "") -> None:
        self._chunks = chunks
        self.headers = {"Content-Length": content_length} if content_length else {}
        self.closed = False

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def read(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def test_download_model_to_streams_and_reports_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    response = _FakeResponse([b"abc", b"def", b""], content_length="6")
    monkeypatch.setattr(registry.request, "urlopen", lambda *_args, **_kwargs: response)

    progress: list[tuple[int, int]] = []
    result = registry.download_model_to(
        "https://example.org/model.gguf",
        destination_dir=tmp_path,
        progress_callback=lambda done, total: progress.append((done, total)),
    )

    assert result.name == "model.gguf"
    assert result.read_bytes() == b"abcdef"
    assert progress[0] == (3, 6)
    assert progress[-1] == (6, 6)
    assert not (tmp_path / "model.gguf.part").exists()


def test_download_model_to_removes_partial_file_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _BrokenResponse(_FakeResponse):
        def read(self, _size: int) -> bytes:
            raise OSError("network failure")

    response = _BrokenResponse([b""], content_length="10")
    monkeypatch.setattr(registry.request, "urlopen", lambda *_args, **_kwargs: response)

    with pytest.raises(OSError):
        registry.download_model_to("https://example.org/fail.gguf", destination_dir=tmp_path)

    assert not (tmp_path / "fail.gguf.part").exists()
    assert not (tmp_path / "fail.gguf").exists()


def test_download_model_to_cancels_and_removes_partial_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    response = _FakeResponse([b"abc", b"def", b""], content_length="6")
    monkeypatch.setattr(registry.request, "urlopen", lambda *_args, **_kwargs: response)

    cancel_state = {"value": False}
    response_events: list[object | None] = []

    def on_progress(done: int, _total: int) -> None:
        if done >= 3:
            cancel_state["value"] = True

    with pytest.raises(registry.DownloadCancelledError):
        registry.download_model_to(
            "https://example.org/cancel.gguf",
            destination_dir=tmp_path,
            progress_callback=on_progress,
            is_cancelled=lambda: cancel_state["value"],
            on_response_opened=response_events.append,
        )

    assert response_events[0] is response
    assert response_events[-1] is None
    assert not (tmp_path / "cancel.gguf.part").exists()
    assert not (tmp_path / "cancel.gguf").exists()


def test_discover_gguf_models(tmp_path: Path) -> None:
    (tmp_path / "a.gguf").write_text("a", encoding="utf-8")
    (tmp_path / "b.GGUF").write_text("b", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    models = registry.discover_gguf_models(tmp_path)
    assert [model.name for model in models] == ["a.gguf", "b.GGUF"]


def test_discover_gguf_models_uses_configured_search_dirs(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "bundled-models"
    model_dir.mkdir()
    target = model_dir / "BMOSolucionesSmolLM2-135M-Instruct_ModeloFinanzas.gguf"
    target.write_text("stub", encoding="utf-8")

    monkeypatch.setenv("MIRA_MODELS_DIR", str(model_dir))

    models = registry.discover_gguf_models()
    assert any(model.name == target.name for model in models)


def test_get_model_search_dirs_deduplicates_paths(monkeypatch, tmp_path: Path) -> None:
    shared = tmp_path / "shared-models"
    monkeypatch.setattr(registry, "get_user_models_dir", lambda: shared)
    monkeypatch.setattr(registry.sys, "executable", str(shared / "python"))
    monkeypatch.setattr(registry.sys, "prefix", str(shared))

    directories = registry.get_model_search_dirs()

    assert len(directories) == len(set(directories))
    assert directories.count(shared.resolve(strict=False)) == 1


def test_get_builtin_models_dir_uses_first_existing_directory(monkeypatch, tmp_path: Path) -> None:
    first_missing = tmp_path / "missing"
    second_dir = tmp_path / "bundled"
    second_dir.mkdir()
    monkeypatch.setattr(registry, "get_model_search_dirs", lambda: [first_missing, second_dir])

    assert registry.get_builtin_models_dir() == second_dir


def test_get_builtin_models_dir_falls_back_when_no_search_dir_exists(monkeypatch) -> None:
    monkeypatch.setattr(registry, "get_model_search_dirs", lambda: [])

    fallback = registry.get_builtin_models_dir()

    assert fallback.name == "models"
    assert fallback.parent.name == "mira"


def test_model_registry_wrapper_delegates_to_module_helpers(monkeypatch, tmp_path: Path) -> None:
    expected_download = tmp_path / "downloaded.gguf"
    expected_dirs = [tmp_path / "a.gguf"]
    monkeypatch.setattr(
        registry, "discover_gguf_models", lambda models_dir=None: expected_dirs if models_dir == "here" else []
    )
    monkeypatch.setattr(
        registry, "find_model_path_by_name", lambda name: expected_download if name == "model.gguf" else None
    )
    monkeypatch.setattr(registry, "download_model_to", lambda **kwargs: expected_download)
    monkeypatch.setattr(registry, "get_default_model_download_url", lambda: "https://example.org/model.gguf")
    monkeypatch.setattr(registry, "get_writable_models_dir", lambda: tmp_path)
    monkeypatch.setattr(registry, "model_filename_from_url", lambda url: Path(url).name)

    wrapper = registry.ModelRegistry()

    assert wrapper.discover_models("here") == expected_dirs
    assert wrapper.find_by_name("model.gguf") == expected_download
    assert wrapper.download("https://example.org/model.gguf") == expected_download
    assert wrapper.default_download_url() == "https://example.org/model.gguf"
    assert wrapper.writable_models_dir() == tmp_path
    assert wrapper.model_filename("https://example.org/model.gguf") == "model.gguf"
