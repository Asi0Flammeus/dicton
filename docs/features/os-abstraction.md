# Couche d'abstraction OS — `src/dicton/os_/`

## Invariant cible

Toute interaction OS-spécifique (binaire système, API kernel, registre Windows, plist macOS, evdev, fcntl, ctypes Win32, AppleScript, systemctl, playerctl, etc.) vit exclusivement sous `src/dicton/os_/`. Le reste du code appelle une API neutre, sans branche `sys.platform`.

Vérifié par test :

```
grep -rn "sys.platform" src/dicton/ \
  | grep -v '^src/dicton/os_/' \
  | grep -v '^src/dicton/visualizer.py'
# → 0 ligne
```

## Exception légitime — `visualizer.py`

`src/dicton/visualizer.py:50-52` reste exempté. Le couplage X11/XShape/SDL/colorkey Win32 est intrinsèque au rendu de la fenêtre donut click-through. Le concentrer dans un seul fichier (déjà fait depuis le commit `0013d27`) est cohérent ; l'abstraire derrière une façade neutre serait du sur-design.

## Décision d'architecture — Option 1 retenue

Choix entre trois organisations :

| Option                                              | Description                                                                                       | Trade-off                                                                                                                             |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Par fonction, sous-module per-OS** _(retenue)_ | `os_/paste/{__init__,_linux,_darwin,_windows}.py`, `os_/autostart/...`, etc.                      | Mirror stdlib (`posixpath`/`ntpath`). Cohésion par capacité, un fichier par OS par capacité. Plus de fichiers mais chacun ≤ ~100 LOC. |
| 2. Par OS, fichier unique                           | `os_linux.py`, `os_darwin.py`, `os_windows.py` contenant chacun paste + autostart + audio + lock. | Faible cohésion, junk drawer. Douloureux quand une seule capacité évolue.                                                             |
| 3. Par fonction, branches internes                  | Statu quo : `output.py` avec `if sys.platform` dedans.                                            | Connaissance OS reste disséminée. Pas de barrière statique. Ne respecte pas l'invariant.                                              |

**Pourquoi l'Option 1** : c'est la seule qui transforme l'invariant en propriété **vérifiable** (par test pytest + grep CI) tout en gardant la cohésion par capacité. Un dev qui débogue le paste sur Wayland n'ouvre qu'un fichier : `os_/paste/_linux.py`.

## Arborescence cible

```
src/dicton/
  os_/
    __init__.py
    paste/
      __init__.py            # def paste(text: str) -> None
      _linux.py              # wl-copy/xclip + wtype/xdotool
      _darwin.py             # pbcopy + osascript
      _windows.py            # ctypes user32/kernel32
    autostart/
      __init__.py            # enable_autostart() / disable_autostart()
      _linux.py              # systemd --user
      _darwin.py             # launchd plist
      _windows.py            # HKCU\Run via winreg
    fn_key/
      __init__.py            # FnKeyListener, capture_keycode (façade)
      _linux.py              # backend evdev
    single_instance.py       # acquire() — fcntl/msvcrt, fichier unique car petit
    audio_session.py         # pause_active_players / resume_players (no-op hors Linux)
    hotkey.py                # pynput_primary_key() — résout Key.fn sur macOS
    service.py               # systemd_unit_active / restart_systemd_unit / Win update helpers
    probes.py                # wizard: clipboard probe, capture_primary support
  gesture.py                 # DoubleTapRecognizer (extrait de fn_key, pur Python)
  visualizer.py              # INTACT (exemption affichage)
```

`DoubleTapRecognizer` n'est pas OS-spécifique (pur `threading.Timer`) → migre vers `gesture.py`, hors de `os_/`.

## API publique des adaptateurs

Chaque façade `os_.<capacity>.__init__` réexporte une API qui ne mentionne **jamais** d'OS dans sa signature. Les backends sont privés (`_linux.py`, `_darwin.py`, `_windows.py`).

| Module                | API publique                                                                                                               | Comportement hors OS supportée                                |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `os_.paste`           | `paste(text: str) -> None`                                                                                                 | `raise RuntimeError("unsupported platform")`                  |
| `os_.autostart`       | `enable_autostart() -> bool` ; `disable_autostart() -> bool`                                                               | `return False`                                                |
| `os_.single_instance` | `acquire() -> IO[str] \| None`                                                                                             | always available (POSIX ou Win)                               |
| `os_.audio_session`   | `pause_active_players() -> list[str]` ; `resume_players(list[str]) -> None`                                                | `return []` / no-op                                           |
| `os_.fn_key`          | `FnKeyListener(on_tap)` ; `capture_keycode(t)` ; `FN_KEYCODES: set[int]`                                                   | `start()` retourne `False`, `capture_keycode` retourne `None` |
| `os_.hotkey`          | `pynput_primary_key() -> object \| None`                                                                                   | retourne `None` partout sauf macOS                            |
| `os_.service`         | `systemd_unit_active()` ; `restart_systemd_unit()` ; `kill_stale_dicton()` ; `spawn_detached_upgrade(cmd, restart_daemon)` | `False` / no-op hors OS cible                                 |
| `os_.probes`          | `clipboard_tools_status() -> Literal["ok","missing","na"]` ; `capture_primary_key_supported() -> bool`                     | `"na"` / `False` hors Linux                                   |

Côté appelant :

```python
from .os_ import paste, autostart, audio_session, single_instance, fn_key, hotkey, service, probes
```

ou granulaire : `from .os_.paste import paste`.

## Garde-fou — `tests/test_no_platform_leak.py`

```python
from pathlib import Path
import re

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
```

Tout futur PR qui réintroduit un `sys.platform` hors `os_/` ou `visualizer.py` casse pytest.

## Fichiers actuellement non-conformes (état avant refactor)

Audit effectué le 2026-05-28 :

| Fichier                                 | Type d'OS-code                      | Destination cible                             |
| --------------------------------------- | ----------------------------------- | --------------------------------------------- |
| `src/dicton/visualizer.py:50-52`        | X11 + Windows window setup          | **Reste sur place** (exemption)               |
| `src/dicton/platform.py`                | autostart (systemd/launchd/winreg)  | `os_/autostart/`                              |
| `src/dicton/output.py`                  | paste (wl-copy/xclip/pbcopy/ctypes) | `os_/paste/`                                  |
| `src/dicton/fn_key.py`                  | evdev Linux + DoubleTapRecognizer   | Split : `os_/fn_key/_linux.py` + `gesture.py` |
| `src/dicton/audio_session.py`           | playerctl Linux                     | `os_/audio_session.py`                        |
| `src/dicton/singleton.py`               | fcntl/msvcrt                        | `os_/single_instance.py`                      |
| `src/dicton/cli.py:181,259,269,375,385` | systemctl + Windows update helpers  | `os_/service.py`                              |
| `src/dicton/wizard.py:92,178`           | clipboard probe + Linux capture     | `os_/probes.py`                               |
| `src/dicton/pipeline.py:142`            | `darwin` pour `keyboard.Key.fn`     | `os_/hotkey.py`                               |

Soit **9 fichiers** dispersant la connaissance OS aujourd'hui, à consolider en 1 sous-package.

## Référence d'exécution

Plan d'exécution atomique (10 commits) : voir [`plan.md`](../../plan.md) à la racine du repo.

## Liens

- Commit déclencheur (rationale du refactor) : `0013d27` — _refactor(trigger+viz): single X connection, taptap-symmetric, anti-mitraille_
- Stratégie de packaging qui dépend de cette couche : [`cross-os-packaging.md`](./cross-os-packaging.md)
