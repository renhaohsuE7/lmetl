# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Dependencies (always use uv, never pip)
uv add <package>             # runtime dependency
uv add --dev <package>       # dev dependency
uv sync                      # install all

# Run
uv run pytest tests/ -v      # tests
uv run python -m lmetl     # application

# Docker
docker compose up app         # run pipeline
docker compose run test       # run tests
```

## Rules

Detailed rules are organized under `.claude/rules/`:

- `project/` — overview, directory conventions, tooling
- `etl/` — extract / transform / load pipeline rules
- `llm/` — LLM provider configuration and usage rules

## Documentation

- `docs/plans/{module}/` — planning docs
- `docs/references/{module}/` — reference docs

All docs and rules must be subdivided by module folder, never placed flat at the category root.

## Architecture

ETL pipeline using LLMs to extract structured info from docx/PDF research reports. Built on pwetl (Pathway-based ETL framework).

```
DocxSource → LLMTransform (Ollama) → JsonExtractionSink + TxtFallbackSink
```

- **Core schema**: always extracted (title, authors, findings, LLM commentary)
- **Genre schema**: pluggable domain-specific extraction (e.g., geology)
- Config-driven via YAML (`configs/`)
