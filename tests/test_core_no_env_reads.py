from pathlib import Path

FORBIDDEN_ENV_READS = (
    "import os",
    "from os import",
    "os.getenv",
    "os.environ",
    "os.environ[",
)


def test_core_modules_do_not_read_environment_directly():
    core_dir = Path(__file__).resolve().parents[1] / "src" / "dicton" / "core"

    for path in sorted(core_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if path.name == "__init__.py" and not source.strip():
            continue

        for forbidden in FORBIDDEN_ENV_READS:
            assert forbidden not in source, f"{path} contains forbidden env read: {forbidden}"
