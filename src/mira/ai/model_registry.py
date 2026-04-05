# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""Model discovery, lookup, and download helpers for GGUF assets."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from urllib import request
from urllib.parse import unquote, urlparse

from mira import __version__ as APP_VERSION

DEFAULT_MODEL_DOWNLOAD_URL = "https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/blob/main/" "Qwen3.5-0.8B-Q4_0.gguf"


class DownloadCancelledError(RuntimeError):
    """Raised when a model download is cancelled by the user."""


def get_user_models_dir() -> Path:
    """Return writable user-scoped models directory."""
    env_models = os.environ.get("MIRA_MODELS_DIR", "").strip()
    if env_models:
        return Path(env_models).expanduser()
    return Path.home() / ".mira" / "models"


def get_model_search_dirs() -> list[Path]:
    """Return candidate directories where optional GGUF models may exist."""
    package_models = Path(__file__).resolve().parent.parent / "models"
    candidates: list[Path] = [package_models, get_user_models_dir()]
    candidates.append(Path("/app/share/mira/models"))
    candidates.append(Path(sys.executable).resolve().parent / "models")
    candidates.append(Path(sys.prefix) / "share" / "mira" / "models")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def get_default_model_download_url() -> str:
    """Return the current default GGUF model URL placeholder."""
    return DEFAULT_MODEL_DOWNLOAD_URL


def normalize_model_download_url(url: str) -> str:
    """Normalize known hosting URLs into direct-download URLs when possible."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host.endswith("huggingface.co") and "/blob/" in parsed.path:
        return parsed._replace(path=parsed.path.replace("/blob/", "/resolve/", 1)).geturl()
    return parsed.geturl()


def model_filename_from_url(url: str) -> str:
    """Extract model filename from URL."""
    normalized = normalize_model_download_url(url)
    parsed = urlparse(normalized)
    filename = Path(unquote(parsed.path)).name
    if not filename:
        raise ValueError("Could not infer filename from model URL")
    return filename


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".mira-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def get_writable_models_dir() -> Path:
    """Return the best writable models directory for downloads."""
    candidates = [
        get_user_models_dir(),
        Path(sys.executable).resolve().parent / "models",
    ]
    for candidate in candidates:
        if _is_writable_dir(candidate):
            return candidate
    fallback = get_user_models_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_builtin_models_dir() -> Path:
    """Return the primary packaged GGUF models directory."""
    for candidate in get_model_search_dirs():
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent / "models"


def discover_gguf_models(models_dir: str | Path | None = None) -> list[Path]:
    """Discover available GGUF models in *models_dir* or configured search dirs."""
    roots = [Path(models_dir)] if models_dir else get_model_search_dirs()
    discovered: dict[Path, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() == ".gguf":
                discovered[path.resolve(strict=False)] = path
    return sorted(discovered.values(), key=lambda p: p.name.lower())


def find_model_path_by_name(model_name: str) -> Path | None:
    """Return first discovered model matching *model_name* case-insensitively."""
    name = model_name.strip().lower()
    if not name:
        return None
    for model in discover_gguf_models():
        if model.name.lower() == name:
            return model
    return None


def download_model_to(
    url: str,
    destination_dir: str | Path | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    on_response_opened: Callable[[object | None], None] | None = None,
    timeout: float = 60.0,
) -> Path:
    """Download GGUF model and return final path."""
    normalized_url = normalize_model_download_url(url)
    filename = model_filename_from_url(normalized_url)
    target_dir = Path(destination_dir) if destination_dir else get_writable_models_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    final_path = target_dir / filename
    if final_path.is_file():
        if progress_callback is not None:
            size = final_path.stat().st_size
            progress_callback(size, size)
        return final_path

    tmp_path = target_dir / f"{filename}.part"
    req = request.Request(normalized_url, headers={"User-Agent": f"MIRA/{APP_VERSION}"})
    downloaded = 0
    total = 0

    try:
        with request.urlopen(req, timeout=timeout) as response:
            if on_response_opened is not None:
                on_response_opened(response)
            with tmp_path.open("wb") as handle:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    total = int(content_length)

                while True:
                    if is_cancelled is not None and is_cancelled():
                        raise DownloadCancelledError("Model download cancelled")
                    try:
                        chunk = response.read(1024 * 1024)
                    except Exception as exc:
                        if is_cancelled is not None and is_cancelled():
                            raise DownloadCancelledError("Model download cancelled") from exc
                        raise
                    if is_cancelled is not None and is_cancelled():
                        raise DownloadCancelledError("Model download cancelled")
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded, total)

        if is_cancelled is not None and is_cancelled():
            raise DownloadCancelledError("Model download cancelled")
        tmp_path.replace(final_path)
        if progress_callback is not None:
            final_size = final_path.stat().st_size
            progress_callback(final_size, final_size)
        return final_path
    finally:
        if on_response_opened is not None:
            on_response_opened(None)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


class ModelRegistry:
    """Object-oriented wrapper around GGUF model registry helpers."""

    def discover_models(self, models_dir: str | Path | None = None) -> list[Path]:
        return discover_gguf_models(models_dir)

    def find_by_name(self, name: str) -> Path | None:
        return find_model_path_by_name(name)

    def download(
        self,
        url: str,
        destination_dir: str | Path | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        on_response_opened: Callable[[object | None], None] | None = None,
        timeout: float = 60.0,
    ) -> Path:
        return download_model_to(
            url=url,
            destination_dir=destination_dir,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            on_response_opened=on_response_opened,
            timeout=timeout,
        )

    def default_download_url(self) -> str:
        return get_default_model_download_url()

    def writable_models_dir(self) -> Path:
        return get_writable_models_dir()

    def model_filename(self, url: str) -> str:
        return model_filename_from_url(url)
