from dicton.platform import install_autostart


def test_install_autostart_linux(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("dicton.platform.autostart_path", lambda: tmp_path / "dicton.service")
    path = install_autostart("dicton")
    assert "ExecStart=dicton" in path.read_text()
