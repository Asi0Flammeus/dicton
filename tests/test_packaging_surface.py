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


def test_cli_config_ui_works_without_full_app_startup(monkeypatch):
    import importlib
    import types

    cli = importlib.import_module("dicton.__main__")
    calls: list[int] = []
    real_import = __import__

    def fake_run_config_server(*, port: int) -> None:
        calls.append(port)

    fake_module = types.SimpleNamespace(run_config_server=fake_run_config_server)

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"dicton.config_server", "config_server"}:
            return fake_module
        if name in {"dicton.main", "main"}:
            raise AssertionError("config-ui should not import dicton.main")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    monkeypatch.setattr(sys, "argv", ["dicton", "--config-ui", "--config-port", "9999"])

    cli.main()

    assert calls == [9999]


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
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "lint|test|build|all" in content
    assert "./scripts/check.sh lint" in workflow
    assert "./scripts/check.sh test" in workflow
    assert "./scripts/check.sh build" in workflow
    assert "paths-ignore:" in workflow
    assert '"**/*.md"' in workflow
    assert '"docs/**"' in workflow
    assert '"LICENSE"' in workflow
    assert 'cron: "0 8 * * 1"' in workflow


def test_windows_packaging_files_exist():
    assert (ROOT / "packaging" / "windows" / "dicton.spec").exists()
    assert (ROOT / "packaging" / "windows" / "pyinstaller_entry.py").exists()
    assert (ROOT / "scripts" / "build-windows.ps1").exists()
    assert (ROOT / "docs" / "windows-packaging.md").exists()
    spec = (ROOT / "packaging" / "windows" / "dicton.spec").read_text(encoding="utf-8")
    assert "__file__" not in spec
    assert "SPECPATH" in spec
    assert 'project_root / "packaging" / "windows" / "pyinstaller_entry.py"' in spec
    assert 'collect_submodules("pynput")' in spec


def test_smoke_job_is_pr_or_schedule_only():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "smoke:" in workflow
    assert "if: github.event_name == 'pull_request' || github.event_name == 'schedule'" in workflow
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow


def test_linux_packaging_files_exist():
    assert (ROOT / "packaging" / "linux" / "dicton.spec").exists()
    assert (ROOT / "scripts" / "build-linux-package.sh").exists()
    assert (ROOT / "docs" / "linux-packaging.md").exists()
    spec = (ROOT / "packaging" / "linux" / "dicton.spec").read_text(encoding="utf-8")
    assert 'project_root / "packaging" / "windows" / "pyinstaller_entry.py"' in spec
    assert 'collect_submodules("pynput")' in spec
    assert 'collect_submodules("Xlib")' in spec


def test_ci_does_not_build_release_packages():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-package:" not in workflow
    assert "linux-package:" not in workflow
    assert "./scripts/build-linux-package.sh" not in workflow
    assert r".\scripts\build-windows.ps1" not in workflow


def test_release_workflow_present():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "push:" not in workflow
    assert "workflow_call:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "softprops/action-gh-release" in workflow
    assert "tag_name: ${{ env.RELEASE_TAG }}" in workflow
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
    assert "uses: ./.github/workflows/release.yml" in workflow
    assert "tag_exists" in workflow
