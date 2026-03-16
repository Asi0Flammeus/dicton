from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dicton"

DISALLOWED_APPLICATION_DEPENDENCIES = {
    "anthropic",
    "evdev",
    "fastapi",
    "gi",
    "google",
    "pyaudio",
    "pygame",
    "pyudev",
    "uvicorn",
    "vispy",
}


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def test_application_layer_avoids_low_level_dependencies():
    application_dir = SRC / "orchestration"
    assert application_dir.exists()

    for path in application_dir.glob("*.py"):
        imports = _module_imports(path)
        forbidden = imports & DISALLOWED_APPLICATION_DEPENDENCIES
        assert not forbidden, f"{path.name} imports low-level dependencies: {sorted(forbidden)}"


def test_bootstrap_module_exists_as_composition_root():
    container = SRC / "orchestration" / "container.py"
    assert container.exists()
    imports = _module_imports(container)
    assert "dicton" not in imports


def test_runtime_entry_still_flows_through_main_module():
    main_file = SRC / "__main__.py"
    content = main_file.read_text(encoding="utf-8")
    assert "run_config_server" in content

    cli_file = SRC / "interfaces" / "cli.py"
    cli_content = cli_file.read_text(encoding="utf-8")
    assert "build_runtime_service" in cli_content
