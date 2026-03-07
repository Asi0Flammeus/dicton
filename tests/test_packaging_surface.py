from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

import pytest

import dicton
from dicton.update_checker import GITHUB_API_URL

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_matches_installed_metadata():
    try:
        installed_version = importlib.metadata.version("dicton")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("dicton package metadata not available in this environment")

    assert dicton.__version__ == installed_version


def test_cli_version_works_without_full_app_startup():
    env = os.environ.copy()
    env.update(
        {
            "DICTON_DISABLE_ENV_FILE_LOAD": "true",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "dicton", "--version"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=True,
    )

    assert result.stdout.strip() == f"Dicton v{dicton.__version__}"


@pytest.mark.parametrize(
    ("relative_path", "forbidden", "required"),
    [
        (
            "install.bat",
            "requirements.txt",
            'pip install -e ".[windows,context-windows,notifications,llm,configui,mistral]"',
        ),
        ("install.bat", "src\\main.py", "python.exe -m dicton"),
        (
            "scripts/install.ps1",
            "requirements.txt",
            'pip install -e ".[windows,context-windows,notifications,llm,configui,mistral]"',
        ),
        ("scripts/install.ps1", "src\\main.py", "python.exe -m dicton"),
        ("run.bat", "src\\main.py", "python -m dicton"),
        ("run.sh", "src/main.py", "python -m dicton"),
    ],
)
def test_launch_scripts_match_current_package_layout(
    relative_path: str, forbidden: str, required: str
):
    content = (ROOT / relative_path).read_text(encoding="utf-8")
    assert forbidden not in content
    assert required in content


def test_update_checker_points_to_canonical_repo():
    assert GITHUB_API_URL == "https://api.github.com/repos/Asi0Flammeus/dicton/releases/latest"


def test_check_script_covers_ci_targets():
    content = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
    assert "lint|test|build|all" in content
    assert "./scripts/check.sh lint" in (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "./scripts/check.sh test" in (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "./scripts/check.sh build" in (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
