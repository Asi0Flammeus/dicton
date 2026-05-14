import sys

import pytest

from dicton import output


def test_linux_output_requires_clipboard(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(output.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError):
        output.paste("x")
