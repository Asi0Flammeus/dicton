# Development Setup

This guide covers setting up Dicton for development. For general installation, see [README.md](README.md).

## Prerequisites

- Python 3.10+
- Git
- ElevenLabs API key ([get one here](https://elevenlabs.io/app/settings/api-keys))

### Linux (Debian/Ubuntu)

```bash
sudo apt install python3-venv python3-dev portaudio19-dev xdotool libnotify-bin
```

### Linux (Arch)

```bash
sudo pacman -S python portaudio xdotool libnotify
```

### macOS

```bash
brew install portaudio
```

### Windows

No additional system dependencies required. If PyAudio fails to install:
```cmd
pip install pipwin
pipwin install pyaudio
```

## Development Installation

```bash
# Clone the repository
git clone https://github.com/asi0flammern/dicton.git
cd dicton

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install in editable mode with dev dependencies
# Windows: add platform extras for the supported fallback path
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env and add one STT API key
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=dicton --cov-report=term

# Run specific test file
pytest tests/test_config.py -v
```

## Code Quality

```bash
# Canonical local verification (matches CI stages)
./scripts/check.sh

# Or run individual stages
./scripts/check.sh lint
./scripts/check.sh test
./scripts/check.sh build

# Auto-fix lint issues
ruff check . --fix

# Auto-format
ruff format .
```

## Running the Application

```bash
# From package
dicton

# Or as module
python -m dicton
```

## Configuration

Edit `.env` to customize behavior:

```bash
ELEVENLABS_API_KEY=your_key_here   # Required
ELEVENLABS_MODEL=scribe_v1         # STT model
HOTKEY_MODIFIER=alt                # alt or ctrl
HOTKEY_KEY=g                       # any key
LANGUAGE=auto                      # auto, en, fr, de, etc.
MIC_DEVICE=auto                    # auto or device index
DEBUG=false                        # enable debug output
```

## Project Structure

```
dicton/
├── src/dicton/          # Main package
│   ├── main.py          # Application entry
│   ├── config.py        # Configuration
│   ├── keyboard_handler.py
│   ├── speech_recognition_engine.py
│   ├── visualizer.py
│   └── ...
├── tests/               # Test suite
├── .github/workflows/   # CI/CD
├── pyproject.toml       # Package config
└── ...
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Fork/branch workflow
- Commit conventions
- Code style
- Pull request process
