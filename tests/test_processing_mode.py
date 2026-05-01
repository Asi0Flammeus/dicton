from dicton.core.processing_mode import ProcessingMode, is_mode_enabled


def test_basic_and_translation_enabled_without_advanced_modes():
    assert is_mode_enabled(ProcessingMode.BASIC, enable_advanced_modes=False) is True
    assert is_mode_enabled(ProcessingMode.TRANSLATION, enable_advanced_modes=False) is True
    assert is_mode_enabled(ProcessingMode.REFORMULATION, enable_advanced_modes=False) is False
    assert is_mode_enabled(ProcessingMode.TRANSLATE_REFORMAT, enable_advanced_modes=False) is False
    assert is_mode_enabled(ProcessingMode.RAW, enable_advanced_modes=False) is False


def test_advanced_modes_can_be_enabled_explicitly():
    assert is_mode_enabled(ProcessingMode.BASIC, enable_advanced_modes=True) is True
    assert is_mode_enabled(ProcessingMode.TRANSLATION, enable_advanced_modes=True) is True
    assert is_mode_enabled(ProcessingMode.REFORMULATION, enable_advanced_modes=True) is True
    assert is_mode_enabled(ProcessingMode.TRANSLATE_REFORMAT, enable_advanced_modes=True) is True
    assert is_mode_enabled(ProcessingMode.RAW, enable_advanced_modes=True) is True
