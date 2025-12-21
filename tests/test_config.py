"""Tests for Dicton configuration module."""


class TestConfigDefaults:
    """Test configuration default values."""

    def test_default_hotkey_modifier(self, clean_env, monkeypatch):
        """Test default hotkey modifier is 'alt'."""
        # Force reimport to pick up clean env
        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.HOTKEY_MODIFIER == "alt"

    def test_default_hotkey_key(self, clean_env, monkeypatch):
        """Test default hotkey key is 'g'."""
        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.HOTKEY_KEY == "g"

    def test_default_theme_color(self, clean_env, monkeypatch):
        """Test default theme color is 'orange'."""
        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.THEME_COLOR == "orange"

    def test_default_visualizer_backend(self, clean_env, monkeypatch):
        """Test default visualizer backend is 'pygame'."""
        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.VISUALIZER_BACKEND == "pygame"

    def test_default_visualizer_style(self, clean_env, monkeypatch):
        """Test default visualizer style is 'toric'."""
        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.VISUALIZER_STYLE == "toric"

    def test_default_debug_false(self, clean_env, monkeypatch):
        """Test debug mode is disabled by default."""
        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.DEBUG is False


class TestConfigFromEnv:
    """Test configuration loading from environment variables."""

    def test_hotkey_from_env(self, clean_env, monkeypatch):
        """Test hotkey can be configured via env vars."""
        monkeypatch.setenv("HOTKEY_MODIFIER", "ctrl")
        monkeypatch.setenv("HOTKEY_KEY", "space")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.HOTKEY_MODIFIER == "ctrl"
        assert config_module.Config.HOTKEY_KEY == "space"

    def test_theme_color_from_env(self, clean_env, monkeypatch):
        """Test theme color can be configured via env var."""
        monkeypatch.setenv("THEME_COLOR", "BLUE")  # uppercase to test normalization

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.THEME_COLOR == "blue"

    def test_debug_from_env(self, clean_env, monkeypatch):
        """Test debug mode can be enabled via env var."""
        monkeypatch.setenv("DEBUG", "true")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.DEBUG is True

    def test_language_from_env(self, clean_env, monkeypatch):
        """Test language can be configured via env var."""
        monkeypatch.setenv("LANGUAGE", "fr")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        assert config_module.Config.LANGUAGE == "fr"


class TestFlexokiColors:
    """Test Flexoki color palette."""

    def test_all_colors_defined(self):
        """Test all expected color names are defined."""
        from dicton.config import FLEXOKI_COLORS

        expected_colors = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta"]
        for color in expected_colors:
            assert color in FLEXOKI_COLORS

    def test_color_structure(self):
        """Test each color has required keys."""
        from dicton.config import FLEXOKI_COLORS

        for color_name, color_data in FLEXOKI_COLORS.items():
            assert "main" in color_data, f"{color_name} missing 'main'"
            assert "mid" in color_data, f"{color_name} missing 'mid'"
            assert "dim" in color_data, f"{color_name} missing 'dim'"
            assert "glow" in color_data, f"{color_name} missing 'glow'"

    def test_color_values_are_rgb_tuples(self):
        """Test color values are RGB tuples."""
        from dicton.config import FLEXOKI_COLORS

        for color_name, color_data in FLEXOKI_COLORS.items():
            for key, value in color_data.items():
                assert isinstance(value, tuple), f"{color_name}.{key} is not a tuple"
                assert len(value) == 3, f"{color_name}.{key} is not RGB (3 values)"
                assert all(0 <= v <= 255 for v in value), (
                    f"{color_name}.{key} has invalid RGB values"
                )


class TestPositionPresets:
    """Test animation position presets."""

    def test_all_positions_defined(self):
        """Test all expected positions are defined."""
        from dicton.config import POSITION_PRESETS

        expected = [
            "top-right",
            "top-left",
            "top-center",
            "bottom-right",
            "bottom-left",
            "bottom-center",
            "center",
        ]
        for position in expected:
            assert position in POSITION_PRESETS

    def test_position_functions_callable(self):
        """Test position values are callable functions."""
        from dicton.config import POSITION_PRESETS

        for name, func in POSITION_PRESETS.items():
            assert callable(func), f"{name} is not callable"

    def test_position_returns_coordinates(self):
        """Test position functions return valid coordinates."""
        from dicton.config import POSITION_PRESETS

        screen_w, screen_h, size = 1920, 1080, 100

        for name, func in POSITION_PRESETS.items():
            result = func(screen_w, screen_h, size)
            assert isinstance(result, tuple), f"{name} did not return tuple"
            assert len(result) == 2, f"{name} did not return (x, y)"
            x, y = result
            assert isinstance(x, int), f"{name} x is not int"
            assert isinstance(y, int), f"{name} y is not int"


class TestConfigMethods:
    """Test Config class methods."""

    def test_get_theme_colors_valid(self, clean_env, monkeypatch):
        """Test get_theme_colors returns valid color palette."""
        monkeypatch.setenv("THEME_COLOR", "blue")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        colors = config_module.Config.get_theme_colors()
        assert "main" in colors
        assert "glow" in colors

    def test_get_theme_colors_fallback(self, clean_env, monkeypatch):
        """Test get_theme_colors falls back to orange for invalid color."""
        monkeypatch.setenv("THEME_COLOR", "invalid_color")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        colors = config_module.Config.get_theme_colors()
        # Should fallback to orange
        from dicton.config import FLEXOKI_COLORS

        assert colors == FLEXOKI_COLORS["orange"]

    def test_get_animation_position_valid(self, clean_env, monkeypatch):
        """Test get_animation_position with valid position."""
        monkeypatch.setenv("ANIMATION_POSITION", "center")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        x, y = config_module.Config.get_animation_position(1920, 1080, 100)
        assert x == (1920 - 100) // 2
        assert y == (1080 - 100) // 2

    def test_get_animation_position_fallback(self, clean_env, monkeypatch):
        """Test get_animation_position falls back to top-right for invalid."""
        monkeypatch.setenv("ANIMATION_POSITION", "invalid_position")

        import importlib

        import dicton.config as config_module

        importlib.reload(config_module)

        x, y = config_module.Config.get_animation_position(1920, 1080, 100)
        # Should fallback to top-right
        assert x == 1920 - 100 - 10
        assert y == 0
