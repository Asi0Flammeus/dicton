from dicton.config import Config, load_config, save_config


def test_config_roundtrip(tmp_path) -> None:
    path = tmp_path / "config.toml"
    save_config(Config(groq_api_key="secret", cleanup_model="llama-3.1-8b-instant"), path)
    loaded = load_config(path)
    assert loaded.groq_api_key == "secret"
    assert loaded.cleanup_model == "llama-3.1-8b-instant"
    assert oct(path.stat().st_mode)[-3:] == "600"
