# CLAUDE.md - Dicton Project Guidelines

## Versioning Convention

This project uses semantic versioning tied to `.claude/TODO.md` progress:

- **## (Heading 2) completed** → Bump **minor version** (e.g., v1.0.0 → v1.1.0)
  - Push tags: `git tag -a vX.Y.0 -m "Phase description"`
  - Create GitHub release

- **### (Heading 3) completed** → Bump **patch version** (e.g., v1.0.0 → v1.0.1)
  - Push tags: `git tag -a vX.Y.Z -m "Section description"`
  - Push to GitHub

- **After ### release** → Remove that subsection from `.claude/TODO.md`
  - Keep only pending work in TODO.md
  - Completed sections are tracked via git tags/releases

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New features
- `fix:` - Bug fixes
- `chore:` - Maintenance tasks (deps, configs)
- `docs:` - Documentation changes
- `refactor:` - Code refactoring without feature changes
- `test:` - Adding or updating tests
- `style:` - Code style/formatting changes

Examples:
```
feat: add visualizer color configuration
fix: skip DC component in FFT to fix first frequency spike
chore: update install script
```

## Project Structure

- `src/` - Main source code
  - `visualizer.py` - Pygame-based audio visualizer
  - `visualizer_vispy.py` - VisPy-based audio visualizer (alternative)
  - `config.py` - Configuration management
  - `speech_recognition_engine.py` - Main STT engine
  - `keyboard_handler.py` - Keyboard input handling

## Configuration

Key environment variables:
- `VISUALIZER_BACKEND` - "pygame" (default) or "vispy"
- `VISUALIZER_STYLE` - "toric", "classic", "legacy", "minimalistic", "terminal"
- `ANIMATION_POSITION` - "top-right", "top-left", "center", etc.
