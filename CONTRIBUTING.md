# Contributing to Dicton

Thank you for your interest in contributing to Dicton! This document provides guidelines for contributing to the project.

## Getting Started

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/dicton.git
   cd dicton
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/asi0flammern/dicton.git
   ```

### Development Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or: .venv\Scripts\activate  # Windows
   ```

2. Install in development mode with dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

3. Copy the environment template:
   ```bash
   cp .env.example .env
   # Edit .env with your ElevenLabs API key
   ```

## Development Workflow

### Creating a Branch

Create a feature branch from `main`:
```bash
git checkout main
git pull upstream main
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring

### Making Changes

1. Make your changes
2. Run the project checks:
   ```bash
   ./scripts/check.sh
   ```
3. Commit your changes following the commit convention

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

| Type | Description |
|------|-------------|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation changes |
| `chore:` | Maintenance tasks (deps, configs) |
| `refactor:` | Code refactoring without feature changes |
| `test:` | Adding or updating tests |
| `style:` | Code style/formatting changes |

### Examples

```
feat: add visualizer color configuration
fix: skip DC component in FFT to fix first frequency spike
docs: update installation instructions
chore: update dependencies
```

## Code Style

### Python Style

- Follow PEP 8 guidelines
- Use [ruff](https://github.com/astral-sh/ruff) for linting
- Maximum line length: 100 characters
- Use type hints where appropriate

### Running Checks

```bash
# Run the same checks as CI
./scripts/check.sh

# Or run individual stages
./scripts/check.sh lint
./scripts/check.sh test
./scripts/check.sh build

# Auto-fix lint issues
ruff check --fix .

# Auto-format before re-running checks
ruff format .
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/dicton

# Run specific test file
pytest tests/test_config.py
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Use pytest fixtures for shared setup
- Aim for meaningful test coverage

## Pull Request Process

1. Ensure all tests pass and linting is clean
2. Update documentation if needed
3. Create a pull request against `main`
4. Fill out the PR template
5. Wait for review and address feedback

### PR Checklist

- [ ] Local checks pass (`./scripts/check.sh`)
- [ ] Documentation updated if needed
- [ ] Commit messages follow convention
- [ ] PR description explains the changes

## Reporting Issues

### Bug Reports

When reporting bugs, please include:
- Operating system and version
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages

### Feature Requests

For feature requests, please describe:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Questions?

If you have questions, feel free to:
- Open a GitHub issue
- Check existing issues and discussions

Thank you for contributing!
