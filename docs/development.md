# Development

```bash
# Install runtime dependencies only
uv sync

# Install dev dependencies
uv sync --dev

# Run the CLI locally
uv run holded-tt --help

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing
```

If you prefer plain `pip` for local development:

```bash
pip install -e .
```
