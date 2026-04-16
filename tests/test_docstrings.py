import subprocess
import sys
from pathlib import Path

import pytest


def test_pydocstyle_src_mira() -> None:
    python_executable = Path("venv/bin/python")
    if not python_executable.exists():
        python_executable = Path(sys.executable)

    result = subprocess.run(
        [str(python_executable), "-m", "pydocstyle", "src/mira"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 and "No module named pydocstyle" in result.stderr:
        pytest.skip("pydocstyle is not installed in the current environment")

    assert result.returncode == 0, result.stdout + result.stderr
