# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

"""MIRA application entry point."""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
from pathlib import Path
import sys
from typing import Any

from mira import __version__ as APP_VERSION
from mira.db.errors import DatabaseSchemaError
from mira.db.helpers import default_db_path_for_display

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _set_windows_app_user_model_id(app_id: str) -> None:
    """Ensure Windows taskbar uses this app identity instead of python.exe."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        logging.debug("Could not set Windows AppUserModelID", exc_info=True)


def _resolve_app_icon_path() -> Path | None:
    """Resolve icon path for both source and installed package layouts."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "ui" / "icons" / "mira.ico",
        here / "ui" / "icons" / "256x256.png",
        here / "ui" / "icons" / "scalable.svg",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _check_display_available() -> None:
    """On Linux, exit with a clear message when no display server is reachable.

    Qt calls ``qFatal()`` → ``abort()`` when it cannot connect to a display,
    which terminates the process at the C level and bypasses Python's exception
    handling entirely.  This function detects the missing display *before* any
    Qt code runs, so the user always sees an actionable error message.

    The check is skipped when:
    * Running on Windows or macOS (they handle display differently).
    * ``QT_QPA_PLATFORM`` is already set (e.g. ``offscreen`` for headless CI).
    * ``DISPLAY`` (X11) or ``WAYLAND_DISPLAY`` is present in the environment.
    """
    if sys.platform in ("win32", "darwin"):
        return
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return
    print(
        "Error: No display server detected. "
        "DISPLAY and WAYLAND_DISPLAY are both unset.\n"
        "To run MIRA you need a graphical environment (X11 or Wayland).\n"
        "For headless testing set QT_QPA_PLATFORM=offscreen before running mira,\n"
        "or use:  xvfb-run -a mira",
        file=sys.stderr,
    )
    sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mira",
        description="MIRA – Personal Finance Assistant",
    )
    parser.add_argument(
        "--model",
        metavar="PATH",
        help="Path to a GGUF model file for optional local chat mode.",
        default=None,
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help=f"Path to the SQLite database file. Defaults to {default_db_path_for_display()}.",
        default=None,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def main() -> None:
    """Start the MIRA desktop application."""
    args = _parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Fail early with a clear Python-level message when no display server is
    # reachable.  Without this check Qt would call qFatal() → abort(), which
    # terminates the process at the C level and shows no Python traceback.
    _check_display_available()

    # Import here so the module is importable without PySide6 installed
    # (useful for running tests)
    try:
        from PySide6.QtWidgets import QApplication
    except (ImportError, OSError) as exc:
        print(f"Error: PySide6 is required to run MIRA. {exc}", file=sys.stderr)
        sys.exit(1)

    qt_icon_type: Any = None
    try:
        from PySide6.QtGui import QIcon as qt_icon_type
    except ImportError:
        pass

    from mira.ai.model_registry import discover_gguf_models, find_model_path_by_name
    from mira.ai.pipeline import Pipeline
    from mira.db.database import Database
    from mira.ui.main_window import MainWindow

    # Initialise database
    db = Database(path=args.db)
    try:
        db.connect()
    except DatabaseSchemaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    # Resolve model preference (CLI has priority; otherwise use persisted selected model)
    startup_alert: str | None = None
    model_path: str | None = args.model
    selected_model = (db.setting.get("preferred_model") or "").strip()
    if model_path is None and selected_model:
        candidate = find_model_path_by_name(selected_model)
        if candidate is not None and candidate.is_file():
            model_path = str(candidate)
            logging.info("Loading user-selected model: %s", selected_model)
        else:
            startup_alert = (
                f"El modelo seleccionado '{selected_model}' ya no está disponible en disco. "
                "El modo chat seguirá desactivado hasta seleccionar otro modelo."
            )
            db.setting.set("preferred_model", "")

    discovered = discover_gguf_models()
    if not discovered:
        logging.info("No GGUF models found in configured model directories.")

    # Initialise AI pipeline
    pipeline: Pipeline | None = None
    try:
        pipeline = Pipeline(
            db=db,
            model_path=model_path,
        )

        # Start Qt application
        _set_windows_app_user_model_id("solutions.bmogroup.MIRA")

        app = QApplication(sys.argv)
        app.setApplicationName("MIRA")
        app.setApplicationDisplayName("MIRA – Personal Finance Assistant")
        app.setApplicationVersion(APP_VERSION)

        app_icon = None
        icon_path = _resolve_app_icon_path()
        if icon_path is not None and qt_icon_type is not None:
            candidate_icon = qt_icon_type(str(icon_path))
            if not candidate_icon.isNull():
                app_icon = candidate_icon

        if app_icon is not None and hasattr(app, "setWindowIcon"):
            app.setWindowIcon(app_icon)

        window = MainWindow(db=db, pipeline=pipeline, startup_alert=startup_alert)
        if getattr(window, "_startup_cancelled", False):
            sys.exit(0)
        if app_icon is not None and hasattr(window, "setWindowIcon"):
            window.setWindowIcon(app_icon)
        window.show()

        exit_code = app.exec()
        sys.exit(exit_code)
    finally:
        try:
            if pipeline is not None:
                pipeline.shutdown()
        finally:
            db.close()


if __name__ == "__main__":
    main()
