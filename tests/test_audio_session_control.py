from dicton.adapters import audio_session_control as asc


def _setup_mocks(monkeypatch, has_cmds, wpctl_mute=None, pactl_mute=None):
    calls: list[list[str]] = []

    def fake_has_cmd(name: str) -> bool:
        return has_cmds.get(name, False)

    def fake_run(args: list[str]):
        calls.append(args)

        class _Result:
            stdout = ""

        return _Result()

    monkeypatch.setattr(asc, "_has_cmd", fake_has_cmd)
    monkeypatch.setattr(asc, "_run", fake_run)
    monkeypatch.setattr(asc, "_get_wpctl_mute", lambda target: wpctl_mute)
    monkeypatch.setattr(asc, "_get_pactl_mute", lambda target: pactl_mute)

    return calls


def test_unmute_uses_pulseaudio_backend_when_configured(monkeypatch):
    calls = _setup_mocks(
        monkeypatch,
        has_cmds={"wpctl": True, "pactl": True},
        pactl_mute=False,
    )
    adapter = asc.AudioSessionControlAdapter()

    adapter._mute_sink("pulseaudio")
    adapter._unmute_sink()

    assert ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"] in calls
    assert ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"] in calls
    assert not any(call[0] == "wpctl" for call in calls)


def test_unmute_uses_wpctl_when_auto_and_available(monkeypatch):
    calls = _setup_mocks(
        monkeypatch,
        has_cmds={"wpctl": True, "pactl": True},
        wpctl_mute=False,
    )
    adapter = asc.AudioSessionControlAdapter()

    adapter._mute_sink("auto")
    adapter._unmute_sink()

    assert ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"] in calls
    assert ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"] in calls
    assert not any(call[0] == "pactl" for call in calls)
