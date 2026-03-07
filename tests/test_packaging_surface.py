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


def test_windows_packaging_files_exist():
    assert (ROOT / "packaging" / "windows" / "dicton.spec").exists()
    assert (ROOT / "packaging" / "windows" / "pyinstaller_entry.py").exists()
    assert (ROOT / "scripts" / "build-windows.ps1").exists()
    assert (ROOT / "docs" / "windows-packaging.md").exists()
    spec = (ROOT / "packaging" / "windows" / "dicton.spec").read_text(encoding="utf-8")
    assert "__file__" not in spec
    assert "SPECPATH" in spec
    assert 'project_root / "packaging" / "windows" / "pyinstaller_entry.py"' in spec


def test_windows_package_job_present():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-package:" in workflow
    assert r".\scripts\build-windows.ps1" in workflow
    assert "dicton-windows-x64.zip" in workflow


def test_linux_packaging_files_exist():
    assert (ROOT / "packaging" / "linux" / "dicton.spec").exists()
    assert (ROOT / "scripts" / "build-linux-package.sh").exists()
    assert (ROOT / "docs" / "linux-packaging.md").exists()
    spec = (ROOT / "packaging" / "linux" / "dicton.spec").read_text(encoding="utf-8")
    assert 'project_root / "packaging" / "windows" / "pyinstaller_entry.py"' in spec


def test_linux_package_job_present():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "linux-package:" in workflow
    assert "./scripts/build-linux-package.sh" in workflow
    assert "dicton-linux-x64.tar.gz" in workflow
    assert "dicton_*_amd64.deb" in workflow


def test_release_workflow_present():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "tags:" in workflow
    assert "v*" in workflow
    assert "softprops/action-gh-release" in workflow
    assert "windows-package" in workflow
    assert "linux-package" in workflow
    assert "python-dist" in workflow


def test_auto_tag_release_workflow_present():
    workflow = (ROOT / ".github" / "workflows" / "auto-tag-release.yml").read_text(encoding="utf-8")
    assert "branches: [main]" in workflow
    assert "contents: write" in workflow
    assert "src/dicton/__init__.py" in workflow
    assert 'echo "tag=v${version}"' in workflow
    assert 'git push origin "${{ steps.version.outputs.tag }}"' in workflow
