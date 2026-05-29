import re
from pathlib import Path

ALLOWED_FILES = {"visualizer.py"}
ALLOWED_DIR = "os_"
SRC = Path(__file__).resolve().parents[1] / "src" / "dicton"


def test_no_sys_platform_outside_os_layer() -> None:
    offenders: list[str] = []
    for py in SRC.rglob("*.py"):
        rel = py.relative_to(SRC)
        if rel.parts[0] == ALLOWED_DIR:
            continue
        if rel.name in ALLOWED_FILES:
            continue
        text = py.read_text(encoding="utf-8")
        if re.search(r"\bsys\.platform\b", text):
            offenders.append(str(rel))
    assert not offenders, f"sys.platform leaked outside os_/ : {offenders}"
