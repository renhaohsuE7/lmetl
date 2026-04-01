# Project Overview

ETL pipeline using LLMs to extract structured information from geological/geothermal government research reports. Built as a downstream extension of pwetl.

## Status

Phase 1 implementation complete. Pending Docker build and end-to-end testing.

## Key Dependencies

- pwetl (Pathway-based ETL framework)
- python-docx (docx parsing)
- openai (LLM client, OpenAI-compatible)
- pydantic (schema validation)

## Inspired By

[pwetl](https://github.com/sw-willie-wu/pwetl) — Plugin architecture, YAML config, Factory/Registry pattern.
