# Packaging cross-OS — vers un installer seamless

## Objectif

dicton doit être distribuable comme une application native installable en un double-clic, sur Linux, macOS et Windows, sans que l'user ait à connaître Python, `uv`, ou la ligne de commande. Référence d'UX : Whisperflow, Wispr Flow, Superwhisper.

## Décisions de stack

### Garder Python (pas de réécriture Rust/Swift)

Le code Python actuel suffit. PyInstaller, Briefcase et Nuitka bundlent du Python standard avec ses dépendances natives (SDL2 via pygame, PortAudio via sounddevice, libssl via httpx). Aucune réécriture nécessaire.

### Pas de Docker

Docker isole du host. dicton **est** un agent qui parle au host : clipboard, injection de touches, mic, listener Fn-key, MPRIS. Docker = mauvais outil :

- `/dev/input/eventN` exige `--privileged` et user dans `input`. Pas grand public.
- macOS/Windows Docker = VM Linux dans une VM → 2 couches de virtualisation pour atteindre le clipboard hôte qu'on ne peut pas atteindre.
- Docker répond à _« contrôler les dépendances serveur »_, pas _« être un démon desktop multi-OS »_.

### Bundler avec Briefcase (recommandé) ou PyInstaller

| Outil                   | Pour                                                                                                                         | Contre                                                      |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| **Briefcase** (BeeWare) | Conçu pour packager Python en `.app` macOS signé, `.msi` Windows, AppImage Linux. Recipes officielles pour beaucoup de libs. | Recipes parfois en retard sur les versions arm64.           |
| **PyInstaller**         | Le plus universel, gros écosystème de hooks.                                                                                 | Sortie macOS non signée par défaut, plus de travail manuel. |
| **Nuitka**              | Compile Python en C — exécutable plus rapide, plus opaque.                                                                   | Plus lent à compiler, plus de surprises avec libs natives.  |

Briefcase est le défaut. PyInstaller en repli si une lib clé ne se bundle pas.

## Stratégie par OS

### Windows

- **Dépendances système à installer** : aucune. Paste = `ctypes.user32`/`kernel32`, déjà tout en process.
- **Bundling** : Briefcase produit un `.msi` (WiX), ou PyInstaller produit un `.exe` + installer Inno Setup.
- **Permissions** : aucune élévation au runtime. UAC seulement à l'install si on choisit d'installer dans `Program Files` (sinon `%LOCALAPPDATA%` sans UAC).
- **Signature** : Authenticode (cert EV ~200 €/an). Sans, SmartScreen affiche un warning rouge. Acceptable de skip au début — beaucoup d'apps OSS le font.
- **Autostart** : déjà géré par `os_.autostart` via clé `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

### macOS

- **Dépendances système à installer** : aucune. `pbcopy`, `osascript`, AppKit sont natifs. `playerctl` n'existe pas (MPRIS = Linux) — pas une régression, juste un no-op gracieux.
- **Bundling** : Briefcase produit un `.app` puis un `.dmg` (drag-to-Applications).
- **Permissions runtime** : deux dialogs Apple natifs au premier lancement :
  - **Accessibility** (pour hotkey global et envoi de Cmd+V). System Settings > Privacy & Security > Accessibility.
  - **Microphone**. Standard `NSMicrophoneUsageDescription` dans `Info.plist`.
  - L'app doit être **signée** pour que ces permissions soient persistantes (sinon redemandées à chaque mise à jour).
- **Signature + notarisation** : Apple Developer Program (99 $/an) + `xcrun notarytool` dans le CI. Indispensable sinon Gatekeeper bloque l'installer.
- **Autostart** : déjà géré par `os_.autostart` via plist LaunchAgent.

### Linux

C'est l'OS le plus complexe — fragmentation des distros et dépendances binaires externes.

- **Dépendances système actuelles** : `xdotool`, `wl-clipboard` (`wl-copy`, `wl-paste`), `wtype`, `xclip`, `playerctl`. Chacun pèse ~50-200 KB.
- **Approche recommandée — AppImage avec binaires bundlés** :
  - Embarquer `xdotool`, `wl-copy`, `wtype`, `xclip`, `playerctl` dans l'AppImage.
  - Au lancement, l'app ajoute son répertoire interne au `PATH`.
  - **Zéro sudo, zéro install, zéro réseau au premier lancement.**
  - L'user double-clique un seul fichier `.AppImage`.
  - Coût : ~5-10 MB de plus.
  - Modèle : Cursor, OBS Studio, Inkscape AppImage.
- **Alternatives écartées** :
  - `.deb` / `.rpm` : fragmente par distro, exige `apt install`/`dnf install` à l'install, sudo au moment du package install — moins seamless.
  - Flatpak + portals : portals clipboard/keystroke marchent mal pour notre cas (hotkey global = trou du sandbox). Combat perdu d'avance.
- **Autostart** : `os_.autostart` génère un unit systemd `--user` dans `~/.config/systemd/user/`. Pas de sudo.

## Onboarding install — comment demander les permissions/installs

### Le pattern à utiliser : agent d'auth natif, pas un terminal embarqué

| OS      | Mécanisme                                                            | UX                                                                 |
| ------- | -------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Linux   | `pkexec <commande>`                                                  | Dialog Polkit standard du DE (GNOME/KDE) — reconnu comme légitime. |
| macOS   | `osascript -e 'do shell script "..." with administrator privileges'` | Dialog Apple natif avec Touch ID.                                  |
| Windows | `ShellExecute(..., "runas", ...)` ou `Start-Process -Verb RunAs`     | Prompt UAC standard.                                               |

**Ne pas embarquer de pseudo-terminal** type xterm. Un `QTextEdit` PySide6 en mode log-streamer (auto-scroll, readonly) suffit pour montrer la sortie du subprocess. Le password prompt est géré par l'OS hors du process — c'est ce qui fait la différence entre « installer légitime » et « phishing ».

Stack technique :

- **UI** : PySide6 — `QTextEdit` readonly + `QProgressBar`.
- **Run** : `QProcess` (intégré au Qt event loop, gère stdout/stderr en signals).
- **Auth** : `pkexec <cmd>` (Linux) ; Polkit fait l'UI password.
- **Détection préalable** : `shutil.which("xdotool")`, `id -nG`, `os.environ.get("WAYLAND_DISPLAY")` — décide quoi configurer.

### Le SEUL sudo inévitable sur Linux : groupe `input`

Le `FnKeyListener` lit `/dev/input/eventN`, qui exige que l'user soit dans le groupe `input` :

```
sudo usermod -aG input $USER
# puis re-login
```

Pas évitable. Donc l'onboarding doit :

1. Détecter si l'user est déjà dans `input` : `id -nG | grep -qw input`.
2. Si non, prompter via Polkit : `pkexec usermod -aG input <user>`.
3. Afficher un warning : « Relogue-toi pour activer la touche Fn ».
4. **Fallback** : si l'user refuse, désactiver la feature Fn-key (pipeline continue avec pynput seul — moins bien, mais fonctionnel).

Le « mini-terminal embarqué » que l'user avait imaginé devient un **log view de 5 lignes** affichant la sortie de cette unique commande. Pas un xterm.

## Phasing recommandé

1. **Phase 1 — Refactor `os_/`** ([`os-abstraction.md`](./os-abstraction.md), [`plan.md`](../../plan.md)). Bénéfice direct : les hooks d'analyse statique de Briefcase/PyInstaller tracent les imports OS-spécifiques proprement.
2. **Phase 2 — POC bundling sur UNE OS** : Briefcase + macOS d'abord (pas Linux : les deps système masquent les vrais bugs pygame/sounddevice). Objectif : un `.app` qui se lance, capture la mic, paste correctement. 1-2 jours. C'est le **test de viabilité** — à faire tôt.
3. **Phase 3 — CI matrix GitHub Actions** : `ubuntu-latest`, `macos-14` (arm64), `windows-latest`. Artefacts dans GitHub Releases. Ajouter l'AppImage Linux avec binaires bundlés.
4. **Phase 4 — Signature/notarisation** : Apple Developer Program + `xcrun notarytool` (macOS), éventuellement Authenticode (Windows). Le pas le plus chiant mais isolable.
5. **Phase 5 — UI onboarding GUI** : PySide6 wizard avec dialogs natifs Polkit/Apple/UAC. Tray icon. Remplace la TTY actuelle pour les users packagés (la CLI typer/rich reste pour les devs `uv tool install`).
6. **Phase 6 — Auto-update** : Sparkle (macOS), WinSparkle (Windows), GitHub Releases JSON manifest (cross-OS) pour AppImage. Remplace `dicton update` actuel.

## Risque identifié — basculer vers Tauri si pygame ne bundle pas

Si la phase 2 (POC macOS) révèle que pygame ou sounddevice ne se bundlent pas proprement sur macOS arm64 (recipes Briefcase pas à jour, lib C manquante), basculer vers :

- **Tauri + sidecar Python** : UI Rust qui spawne un process Python en arrière-plan. Le visualizer devient du HTML/CSS dans une webview, le pipeline Python tourne en sidecar et communique via stdin/stdout JSON. Coût : réécrire le rendu donut en CSS/Canvas. Bénéfice : packaging trivial, taille bundle bien plus petite (~10 MB vs ~100 MB).
- **PySide6 packagé** : UI Qt native, tout en Python. Plus simple à intégrer que Tauri mais bundle plus gros.

À décider seulement si la phase 2 échoue.

## Coût financier estimé pour publier

- Apple Developer Program : 99 USD/an _(obligatoire pour macOS signé)_.
- Authenticode EV cert : ~200 EUR/an _(optionnel — sans, warning SmartScreen Windows)_.
- GitHub Actions : gratuit pour repo public.
- Domaine pour Sparkle update manifest : déjà couvert (static.crqpt.com).

Total minimum viable : **99 USD/an** (macOS notarisé + Win/Linux non signés).

## Liens

- Couche `os_/` (prérequis) : [`os-abstraction.md`](./os-abstraction.md)
- Plan d'exécution du refactor : [`../../plan.md`](../../plan.md)
