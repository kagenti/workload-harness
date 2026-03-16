# Contributing

Thank you for your interest in contributing to Kagenti Workload Harness.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/kagenti/workload-harness.git
cd workload-harness

# Install pre-commit hooks
pre-commit install

# Install the package with dev dependencies
cd appworld_a2a_runner
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linter
cd .. && make lint
```

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Make your changes with tests
3. Run pre-commit hooks: `pre-commit run --all-files`
4. Run the test suite: `cd appworld_a2a_runner && pytest tests/ -v`
5. Submit a pull request targeting `main`

## Commit Messages

Use [conventional commit](https://www.conventionalcommits.org/) format:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `test:` Test additions or fixes
- `chore:` Maintenance tasks
- `refactor:` Code refactoring (no behavior change)

### DCO Sign-Off

All commits **must** include a `Signed-off-by` trailer (Developer Certificate of Origin):

```bash
git commit -s -m "feat: add new feature"
```

## Code Style

- Python 3.11+ with [ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Line length: 120 characters
- Pre-commit hooks enforce style automatically

## Reporting Issues

- Use [GitHub Issues](https://github.com/kagenti/workload-harness/issues) for bugs and feature requests
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)
