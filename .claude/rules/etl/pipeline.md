# ETL Pipeline Rules

## Extract (Sources)
- `DocxSource`: parse docx via python-docx, heading-based chunking
- `PDFSource`: future, via pypdf
- Image handling: `metadata_only` (default) or `vision_llm` mode
- All sources extend pwetl `BaseSource`, return `pw.Table`

## Transform
- `LLMTransform`: extends pwetl `BaseTransform`
- Uses `pw.apply()` UDF per chunk row → LLM API call
- Config loaded from `LMETL_CONFIG` env var in `setup()`
- Schema: Core (always) + Genre (pluggable via YAML config)

## Load (Sinks)
- `JsonExtractionSink`: structured results → JSON (primary)
- `TxtFallbackSink`: failed/unstructurable results → TXT (fallback)
- Both use Pathway JSONL write + teardown post-processing pattern
- DB sink: future (SQLite/PostgreSQL)

## Config
- Pipeline config: `configs/*.yaml` (pwetl YAML convention)
- lmetl-specific config: `lmetl:` section in same YAML
