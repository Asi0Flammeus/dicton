"""COPA architecture guard tests.

Enforce that the layering rules are respected:
  - core:          no imports from adapters or orchestration
  - shared:        no imports from adapters or orchestration
  - adapters:      no imports from orchestration
  - orchestration: no IS_LINUX / IS_WINDOWS platform checks (these belong in factories)
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dicton"


def _relative_imports(path: Path) -> set[str]:
    """Return the set of first-level intra-package segments imported from `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    segments: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level and node.level > 0:
            # Relative import: resolve the leading dots against the file location
            parts = node.module.split(".") if node.module else []
            if parts:
                segments.add(parts[0])
    return segments


def _absolute_dicton_imports(path: Path) -> set[str]:
    """Return top-level sub-package names imported from dicton.* in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    segments: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("dicton."):
                parts = node.module[len("dicton.") :].split(".")
                segments.add(parts[0])
    return segments


def _all_py_files(layer: str) -> list[Path]:
    return list((SRC / layer).rglob("*.py"))


def test_core_does_not_import_adapters():
    """Core layer must not depend on adapters or orchestration."""
    forbidden = {"adapters", "orchestration"}
    for path in _all_py_files("core"):
        rel = _relative_imports(path)
        bad = rel & forbidden
        assert not bad, f"core/{path.name} imports from forbidden layers: {sorted(bad)}"
        # Also check absolute imports
        abs_imports = _absolute_dicton_imports(path)
        bad_abs = abs_imports & forbidden
        assert not bad_abs, f"core/{path.name} has absolute import of: {sorted(bad_abs)}"


# Backward-compat shims that re-export from their canonical adapter/orchestration
# homes are allowed to cross the layer boundary.
_SHARED_SHIM_ALLOWLIST = {"latency_tracker.py", "text_processor.py", "update_checker.py"}


def test_shared_does_not_import_adapters_or_orchestration():
    """Shared utilities must not depend on adapters or orchestration."""
    forbidden = {"adapters", "orchestration"}
    for path in _all_py_files("shared"):
        if path.name in _SHARED_SHIM_ALLOWLIST:
            continue
        rel = _relative_imports(path)
        bad = rel & forbidden
        assert not bad, f"shared/{path.name} imports from forbidden layers: {sorted(bad)}"
        abs_imports = _absolute_dicton_imports(path)
        bad_abs = abs_imports & forbidden
        assert not bad_abs, f"shared/{path.name} has absolute import of: {sorted(bad_abs)}"


def test_adapters_do_not_import_orchestration():
    """Adapters must not import from orchestration."""
    forbidden = {"orchestration"}
    for path in _all_py_files("adapters"):
        rel = _relative_imports(path)
        bad = rel & forbidden
        assert not bad, f"adapters/{path.relative_to(SRC / 'adapters')} imports from: {sorted(bad)}"
        abs_imports = _absolute_dicton_imports(path)
        bad_abs = abs_imports & forbidden
        assert not bad_abs, (
            f"adapters/{path.relative_to(SRC / 'adapters')} absolute import: {sorted(bad_abs)}"
        )


def test_no_platform_checks_in_core_or_orchestration():
    """IS_LINUX / IS_WINDOWS platform guards must not appear in core or orchestration layers."""
    platform_symbols = {"IS_LINUX", "IS_WINDOWS"}
    for layer in ("core", "orchestration"):
        for path in _all_py_files(layer):
            source = path.read_text(encoding="utf-8")
            for sym in platform_symbols:
                assert sym not in source, (
                    f"{layer}/{path.name} contains platform check '{sym}'; "
                    "move it to a factory or shared/platform_utils.py"
                )
