# Tooling Rules

## Package Manager: uv

- Always use `uv` for dependency management, never `pip`
- `uv add <package>` to add runtime dependencies
- `uv add --dev <package>` to add dev dependencies
- `uv sync` to install all dependencies
- `uv run python` / `uv run pytest` to execute
- pyproject.toml is managed via uv commands, avoid direct editing

## Runtime: Docker Compose

- All services defined in `docker-compose.yml`
- Application runs in Docker containers
- Must use `python:3.12` (full image, NOT alpine/slim) — Pathway needs glibc (manylinux wheels), and pwetl git dependency needs git

## Commands Reference

```bash
# Dependencies
uv add python-docx openai pydantic pyyaml
uv add --dev pytest pytest-cov pytest-mock ruff

# Run
uv run python -m lmetl
uv run pytest tests/

# Docker
docker compose up app
docker compose run test
```
