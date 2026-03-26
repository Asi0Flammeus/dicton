from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import dicton
from dicton.shared.update_checker import GITHUB_API_URL

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_is_at_least_latest_git_tag():
    """Source __version__ must be >= the latest git version tag (vX.Y.Z)."""
    result = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        pytest.skip("no git version tags found")

    latest_tag = result.stdout.strip().splitlines()[0].lstrip("v")
    from packaging.version import Version

    assert Version(dicton.__version__) >= Version(latest_tag), (
        f"Source version {dicton.__version__} is behind latest tag v{latest_tag}"
    )


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

    def fake_run_config_server(*, port: int) -> None:
        calls.append(port)

    # Replace the cached module in sys.modules so the lazy import in _run_config_ui
    # gets our stub instead of the real FastAPI server.
    fake_module = types.SimpleNamespace(run_config_server=fake_run_config_server)
    monkeypatch.setitem(sys.modules, "dicton.interfaces.config_server", fake_module)
    monkeypatch.setattr(sys, "argv", ["dicton", "--config-ui", "--config-port", "9999"])

    cli.main()

    assert calls == [9999]


def test_cli_config_alias_works_without_full_app_startup(monkeypatch):
    import types

    cli = importlib.import_module("dicton.__main__")
    calls: list[int] = []

    def fake_run_config_server(*, port: int) -> None:
        calls.append(port)

    fake_module = types.SimpleNamespace(run_config_server=fake_run_config_server)
    monkeypatch.setitem(sys.modules, "dicton.interfaces.config_server", fake_module)
    monkeypatch.setattr(sys, "argv", ["dicton", "--config", "--config-port", "8877"])

    cli.main()

    assert calls == [8877]


def test_input_and_output_module_import_does_not_require_pynput(monkeypatch):
    real_import = __import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pynput" or name.startswith("pynput."):
            raise ImportError("pynput blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    for mod in list(sys.modules):
        if "dicton.input" in mod or "dicton.output" in mod:
            sys.modules.pop(mod, None)

    hl_module = importlib.import_module("dicton.adapters.input.hotkey_listener")
    base_module = importlib.import_module("dicton.adapters.output.base")
    factory_module = importlib.import_module("dicton.adapters.output.factory")

    assert hasattr(hl_module, "HotkeyListener")
    assert hasattr(base_module, "TextOutput")
    assert hasattr(factory_module, "get_text_output")


@pytest.mark.parametrize(
    ("relative_path", "forbidden", "required"),
    [
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
    assert "name: Test (Python 3.12)" in workflow
    assert "name: Test Compatibility (Python ${{ matrix.python-version }})" in workflow
    assert "if: github.event_name == 'schedule'" in workflow
    assert 'python-version: ["3.10", "3.11"]' in workflow


def test_config_server_field_maps_cover_saved_configuration():
    from dicton.interfaces.config_server import (
        CONFIG_BOOL_FIELDS,
        CONFIG_FIELD_MAP,
        CONFIG_STRING_FIELDS,
    )

    assert CONFIG_STRING_FIELDS | CONFIG_BOOL_FIELDS == set(CONFIG_FIELD_MAP)
    assert "mistral_api_key" in CONFIG_FIELD_MAP
    assert "stt_provider" in CONFIG_FIELD_MAP


def test_windows_packaging_files_exist():
    assert (ROOT / "packaging" / "windows" / "dicton.spec").exists()
    assert (ROOT / "packaging" / "windows" / "pyinstaller_entry.py").exists()
    assert (ROOT / "scripts" / "build-windows.ps1").exists()
    assert (ROOT / "docs" / "windows-packaging.md").exists()
    spec = (ROOT / "packaging" / "windows" / "dicton.spec").read_text(encoding="utf-8")
    assert "__file__" not in spec
    assert "SPECPATH" in spec
    assert 'project_root / "packaging" / "windows" / "pyinstaller_entry.py"' in spec
    assert '"assets/setup_ui.html"' in spec
    assert '"assets/config_ui.html"' in spec
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
    assert '"assets/setup_ui.html"' in spec
    assert '"assets/config_ui.html"' in spec
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


def test_config_ui_embedded_script_has_valid_javascript():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available in this environment")

    for relative_path in ("config_ui.html", "setup_ui.html"):
        html = (ROOT / "src" / "dicton" / "assets" / relative_path).read_text(encoding="utf-8")
        start = html.index("<script>") + len("<script>")
        end = html.index("</script>", start)
        script = html[start:end].strip()

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(script)
            tmp_path = Path(tmp.name)

        try:
            result = subprocess.run(
                [node, "--check", str(tmp_path)],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        assert result.returncode == 0, f"{relative_path}: {result.stderr}"


def test_setup_status_endpoint_defaults_to_speech_step(monkeypatch, tmp_path):
    TestClient = pytest.importorskip("fastapi.testclient").TestClient

    import dicton.interfaces.config_server as config_server

    monkeypatch.setattr(config_server.Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(
        config_server,
        "get_autostart_state",
        lambda: {"supported": True, "enabled": False, "path": str(tmp_path / "dicton.desktop")},
    )
    monkeypatch.setattr(config_server, "has_display_session", lambda: True)
    monkeypatch.setattr(config_server, "read_env_file", lambda: {})
    monkeypatch.setattr(
        config_server,
        "_hotkey_status",
        lambda env_vars: {"ready": True, "mode": "fn", "detail": "ready"},
    )
    monkeypatch.setattr(
        config_server,
        "_text_output_status",
        lambda: {"ready": True, "detail": "ready"},
    )
    config_server._setup_state["first_test_passed"] = False
    config_server._setup_state["last_test_text"] = ""

    client = TestClient(config_server.create_app())
    response = client.get("/api/setup/status")

    assert response.status_code == 200
    data = response.json()
    assert data["next_step"] == "speech"
    assert data["checks"]["stt"]["ready"] is False


def test_setup_save_persists_speech_provider_fields(monkeypatch, tmp_path):
    TestClient = pytest.importorskip("fastapi.testclient").TestClient

    import dicton.interfaces.config_server as config_server

    monkeypatch.setattr(config_server.Config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(
        config_server,
        "get_autostart_state",
        lambda: {"supported": True, "enabled": False, "path": str(tmp_path / "dicton.desktop")},
    )
    monkeypatch.setattr(config_server, "has_display_session", lambda: True)
    monkeypatch.setattr(
        config_server,
        "_hotkey_status",
        lambda env_vars: {"ready": True, "mode": "fn", "detail": "ready"},
    )
    monkeypatch.setattr(
        config_server,
        "_text_output_status",
        lambda: {"ready": True, "detail": "ready"},
    )

    client = TestClient(config_server.create_app())
    response = client.post(
        "/api/setup/save",
        json={"stt_provider": "mistral", "mistral_api_key": "test-key"},
    )

    assert response.status_code == 200
    env_vars = config_server.read_env_file()
    assert env_vars["STT_PROVIDER"] == "mistral"
    assert env_vars["MISTRAL_API_KEY"] == "test-key"
