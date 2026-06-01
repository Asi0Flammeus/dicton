import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "dicton"


def test_runtime_does_not_import_x_clients_before_xinitthreads() -> None:
    tree = ast.parse((SRC / "runtime.py").read_text(encoding="utf-8"))

    top_level_relative_imports = {
        node.module for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 1
    }
    assert "pipeline" not in top_level_relative_imports
    assert "visualizer" not in top_level_relative_imports

    run_fn = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    statements = run_fn.body
    xinit_index = next(
        index
        for index, stmt in enumerate(statements)
        if isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and isinstance(stmt.value.func.value, ast.Name)
        and stmt.value.func.value.id == "x11"
        and stmt.value.func.attr == "init_threads"
    )
    import_indices = [
        index
        for index, stmt in enumerate(statements)
        if isinstance(stmt, ast.ImportFrom)
        and stmt.level == 1
        and stmt.module in {"pipeline", "visualizer"}
    ]

    assert import_indices
    assert all(index > xinit_index for index in import_indices)
