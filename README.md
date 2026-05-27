# dicton

**Dictée vocale française, transcription en moins d'une seconde.**

Appuie sur F2 (ou tape Fn deux fois), parle, appuie à nouveau pour stopper. Le texte propre est collé dans l'app active avant que tu aies fini de dire « anticonstitutionnellement ».

- **Sous la seconde** : 200-300 ms post-stop en cas usuel, jamais plus de 1 s sur des dictées courtes. Conçu pour la performance — un seul provider (Groq), une seule connexion HTTP/2, STT et cleanup partagent le socket TLS.
- **100% francophone** : prompt cleanup figé en français, anglicismes préservés tels quels (`workflow`, `commit`, `pull request`…), modèle Whisper turbo verrouillé sur `language=fr`.
- **Un seul binaire**, trois plateformes (Linux X11/Wayland, macOS, Windows), autostart systemd / launchd / HKCU Run, daemon en arrière-plan, hotkey global.

## Installation

### Recommandé — une seule ligne (Linux & macOS)

Zéro prérequis. Le script installe `uv`, `git`, les libs système **et la toolchain C** (nécessaire pour compiler `evdev`), clone le repo, installe `dicton` et lance le wizard :

```bash
curl -fsSL https://raw.githubusercontent.com/Asi0Flammeus/dicton/main/install.sh | bash
```

Détecte la distro (apt / pacman / dnf / zypper) ou Homebrew sur macOS. Relancer la même commande met à jour une install existante.

### Manuel

Prérequis : **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (gestionnaire Python d'Astral) et **[git](https://git-scm.com/downloads)**.

Une seule ligne par plateforme :

### Linux (Debian / Ubuntu / Mint)

```bash
sudo apt install -y build-essential python3-dev libportaudio2 xclip xdotool wl-clipboard wtype playerctl && git clone https://github.com/Asi0Flammeus/dicton.git && cd dicton && uv tool install --force . && dicton
```

### Linux (Arch / Manjaro)

```bash
sudo pacman -S --needed base-devel python portaudio xclip xdotool wl-clipboard wtype playerctl && git clone https://github.com/Asi0Flammeus/dicton.git && cd dicton && uv tool install --force . && dicton
```

### Linux (Fedora)

```bash
sudo dnf install -y gcc python3-devel portaudio xclip xdotool wl-clipboard wtype playerctl && git clone https://github.com/Asi0Flammeus/dicton.git && cd dicton && uv tool install --force . && dicton
```

### macOS

```bash
brew install portaudio && git clone https://github.com/Asi0Flammeus/dicton.git && cd dicton && uv tool install --force . && dicton
```

### Windows (PowerShell)

```powershell
git clone https://github.com/Asi0Flammeus/dicton.git; cd dicton; uv tool install --force .; dicton
```

Chaque commande fait, dans l'ordre :

1. installe les dépendances système nécessaires (toolchain C pour compiler `evdev`, PortAudio pour la capture audio + utilitaires clipboard/paste),
2. clone le repo,
3. installe `dicton` dans `~/.local/bin` (ou équivalent),
4. lance le daemon — au premier run il enchaîne le **wizard** : check système → clé Groq (à créer sur [console.groq.com/keys](https://console.groq.com/keys)) → choix du hotkey → self-test live des 4 modèles de cleanup avec timings → activation de l'autostart.

À la fin du wizard, si tu as accepté l'autostart, le daemon tourne en arrière-plan via systemd/launchd et te rend la main sur le terminal. F2 marche immédiatement.

### Mise à jour

```bash
dicton update   # réinstalle le dernier main depuis GitHub + restart systemd
```

`dicton update` (sans argument) fait `uv tool install --force --reinstall git+https://github.com/Asi0Flammeus/dicton.git@main`. Il tire donc le code depuis GitHub, pas depuis le clone local — pas besoin de garder le dossier cloné, et un clone déplacé/supprimé ne casse plus la commande. `main` étant une branche mouvante, le `--reinstall` est indispensable (uv cache sinon le commit résolu et ne re-fetch jamais le HEAD). Pour itérer sur des sources locales en dev, utilise `dicton update <path>`.

## Usage

| Geste                          | Effet                    |
| ------------------------------ | ------------------------ |
| **F2** (un click)              | Démarre l'enregistrement |
| **F2** (un autre click)        | Stoppe, transcrit, colle |
| **Fn-Fn** (double-tap, 300 ms) | Démarre l'enregistrement |
| **Fn** (un tap)                | Stoppe, transcrit, colle |

> Le double-tap **Fn** marche sur Linux (via `evdev`, recommandé sur ThinkPad et claviers exposant `KEY_WAKEUP`) et sur macOS (via pynput, claviers Apple internes). Sur Windows et la plupart des laptops non-Apple, le firmware intercepte la touche Fn avant qu'elle atteigne l'OS — utilise **F2** à la place.

Pendant l'enregistrement, un petit anneau orange flotte en haut à droite. Il passe en pulse concentrique pendant le processing (STT + cleanup), puis disparaît quand le texte est collé. Les players audio (Spotify, YouTube, VLC…) sont mis en pause automatiquement pendant que tu parles, et repris à la fin.

## Commandes

| Commande               | Effet                                                                              |
| ---------------------- | ---------------------------------------------------------------------------------- |
| `dicton`               | Lance le daemon (ou délègue au service systemd si autostart actif)                 |
| `dicton wizard`        | Re-lance le setup complet (clé, hotkey, modèle, autostart)                         |
| `dicton config`        | Change uniquement le modèle de cleanup                                             |
| `dicton stats`         | Affiche les totaux : nombre de dictées, latence moyenne, temps de frappe économisé |
| `dicton update`        | Réinstalle le dernier `main` depuis GitHub + restart systemd                       |
| `dicton update <path>` | Reinstall depuis un repo local + restart systemd (dev)                             |

## Performance

Mesures réelles (5 dictées sur ThinkPad T14, i3, Groq depuis Paris) :

```
Avg recording:     13180 ms  (you speaking)
Avg process:         296 ms  (stt + cleanup + paste, post-stop latency)
```

Chaque dictée logge sa décomposition :

```
dictation: 212 chars · recording=13145ms · process=736ms (stt=362ms cleanup=307ms) · chunks=2
```

- `recording_ms` — temps où tu parlais
- `process_ms` — latence post-stop perçue (c'est ce qu'on optimise)
- `stt_ms` — appel Groq Whisper isolé
- `cleanup_ms` — appel Groq LLM isolé
- `chunks` — chunks STT envoyés en parallèle (silence-cut au-delà de 6 s)

Live tail des logs : `journalctl --user -u dicton -f`.

## Architecture

```
src/dicton/
├── pipeline.py     Orchestrateur unique — state machine (IDLE / RECORDING / PROCESSING), hotkey, audio, chunker, HTTP, paste. Soft cap 500 LOC en CI pour décourager le fourre-tout : la logique métier vit dans des modules voisins.
├── runtime.py      Entrypoint daemon : singleton lock + Pipeline + boucle pygame main-thread.
├── chunker.py      Découpage silence-aware avec overlap, RMS dBFS.
├── stt.py          Whisper turbo via httpx HTTP/2 partagé.
├── cleanup.py      LLM cleanup en français, prompt verrouillé.
├── output.py       Clipboard + Ctrl+Shift+V (xclip+xdotool / wl-copy+wtype / pbcopy+osascript / SetClipboardData+SendInput).
├── visualizer.py   Donut FFT pygame, XShape circulaire sur X11, hide via shape-mask (jamais de show/hide window → pas de focus stealing).
├── fn_key.py       Listener evdev pour Fn (KEY_WAKEUP 143 + KEY_FN 464-466), détection double-tap.
├── audio_session.py  Pause/resume MPRIS via playerctl.
├── singleton.py    fcntl.flock pour empêcher deux daemons concurrents.
├── platform.py     Autostart systemd / launchd / HKCU.
├── wizard.py       Setup interactif rich + self-test 4 modèles.
├── config.py       TOML à `~/.config/dicton/config.toml` (`chmod 600` sur la clé).
├── stats.py        JSONL append-only par dictée + résumé.
└── cli.py          Entrypoint typer.
```

`pipeline.py` est la seule pièce où vit le cycle de vie runtime. Tout le reste est plat, sans hiérarchie. Soft cap 500 LOC sur `pipeline.py`, vérifié par `scripts/check.sh lint` — assez de marge pour que le wiring reste lisible, mais qui hurle si on commence à y entasser de la logique métier.

## Développement

```bash
git clone https://github.com/Asi0Flammeus/dicton.git && cd dicton
uv sync --extra dev
./scripts/check.sh all   # ruff + LOC cap + pytest
```

Workflow itératif (après modif du code) :

```bash
dicton update .   # reinstall depuis le path courant + restart systemd
```

CI matrix : Linux × macOS × Windows × Python 3.11 / 3.12. Tag `v*` déclenche `uv publish` automatique.

## Désinstallation

```bash
systemctl --user disable --now dicton.service   # Linux
uv tool uninstall dicton
rm ~/.config/systemd/user/dicton.service        # Linux
rm -rf ~/.config/dicton                          # config + stats (optionnel)
```

## License

MIT — voir [LICENSE](LICENSE).
