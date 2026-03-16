# NexusPKM Backend

Python/FastAPI backend for NexusPKM.

## Setup

```bash
uv sync
```

## Development

```bash
uvicorn nexuspkm.main:app --reload
```

## Testing

```bash
pytest                    # All tests
pytest tests/unit         # Unit tests only
pytest tests/integration  # Integration tests only
```

## Linting & Type Checking

```bash
ruff check . && ruff format --check .
mypy src/
```
