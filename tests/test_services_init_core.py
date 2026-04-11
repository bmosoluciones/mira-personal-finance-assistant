# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 - 2026 BMO Soluciones, S.A.

from __future__ import annotations

import pytest

import mira.services as services_module
from mira.services.database_io import DatabaseIOService
from mira.services.model_lifecycle import ModelLifecycle, ModelLifecycleState


def test_services_module_lazy_exports_resolve_known_symbols() -> None:
    assert set(services_module.__all__) == {"DatabaseIOService", "ModelLifecycle", "ModelLifecycleState"}
    assert services_module.__getattr__("DatabaseIOService") is DatabaseIOService
    assert services_module.__getattr__("ModelLifecycle") is ModelLifecycle
    assert services_module.__getattr__("ModelLifecycleState") is ModelLifecycleState


def test_services_module_rejects_unknown_symbol() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'UnknownService'"):
        services_module.__getattr__("UnknownService")
