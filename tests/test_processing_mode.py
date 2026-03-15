import importlib


def test_basic_and_translation_enabled_by_default(clean_env, monkeypatch):
    monkeypatch.delenv("ENABLE_ADVANCED_MODES", raising=False)

    import dicton.shared.config as config_module
    import dicton.shared.processing_mode as processing_mode

    importlib.reload(config_module)
    importlib.reload(processing_mode)

    assert processing_mode.is_mode_enabled(processing_mode.ProcessingMode.BASIC) is True
    assert processing_mode.is_mode_enabled(processing_mode.ProcessingMode.TRANSLATION) is True
    assert processing_mode.is_mode_enabled(processing_mode.ProcessingMode.REFORMULATION) is False
    assert processing_mode.is_mode_enabled(processing_mode.ProcessingMode.ACT_ON_TEXT) is False


def test_advanced_modes_can_be_reenabled(clean_env, monkeypatch):
    monkeypatch.setenv("ENABLE_ADVANCED_MODES", "true")

    import dicton.shared.config as config_module
    import dicton.shared.processing_mode as processing_mode

    importlib.reload(config_module)
    importlib.reload(processing_mode)

    assert processing_mode.is_mode_enabled(processing_mode.ProcessingMode.REFORMULATION) is True
    assert processing_mode.is_mode_enabled(processing_mode.ProcessingMode.ACT_ON_TEXT) is True
