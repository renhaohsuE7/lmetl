# lmetl HTTP wrapper

A thin FastAPI service that exposes lmetl's docx extraction over HTTP, so consumers
(e.g. the gsmma_lm `lmetl_extract` worker) can extract structured JSON synchronously
without driving lmetl's CLI/batch flow.

It reuses the plain-Python extraction path (`DocxChunker` → `LLMClient` →
`parse_llm_json`) — the same logic as `lmetl.tools.run_extraction` — and returns the
result instead of writing it to `output/`.

## Contract

```
POST /extract?genre=<genre>
  body: raw docx bytes
  Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document

200 -> { "full_text": str,
         "structured_json": { "genre": str, "chunks": [ {chunk_id, source_section,
                              source_page, extraction, parse_error} ] },
         "title": str, "topics": [str] }
non-2xx -> failure
```

`GET /healthz` → `{"status":"ok"}`.

## Run

Local:
```bash
uv sync && uv pip install fastapi "uvicorn[standard]"
uv run uvicorn wrapper.app:app --host 0.0.0.0 --port 9400
```

Docker (from the lmetl repo root):
```bash
docker build -f wrapper/Dockerfile -t lmetl-extractor .
docker run --rm -p 9400:9400 -e OLLAMA_BASE_URL=<ollama-url> lmetl-extractor
```

## Env

| Var | Default | Purpose |
|---|---|---|
| `LMETL_CONFIG` | `configs/base.yaml` | lmetl config path |
| `LMETL_MAX_UPLOAD_BYTES` | `67108864` (64 MiB) | upload size cap |
| `OLLAMA_BASE_URL`, … | — | lmetl's own LLM settings (extraction is LLM-bound) |

## Notes / caveats

- **Slow + synchronous:** extraction is LLM-bound (minutes for large docx). The
  gsmma_lm caller invokes this from an async worker with a long timeout; run the
  service with a generous keep-alive and enough workers (or front it with a queue).
- **Genre switching:** `POST /extract?genre=physics` overrides `extraction.genre`.
  Confirm `load_lmetl_config` + `PromptBuilder` honour an overridden genre at runtime;
  if a `sync_schemas` step is needed per genre, pre-sync supported genres in the image
  (commented hint in `Dockerfile`).
- **structured_json shape** is opaque to the consumer (stored as the insight content).
  Coordinate with the consumer before changing it.

Origin: spec drafted in the gsmma_lm repo
(`docs/plans/feature/20260522-lmetl-http-wrapper-design.md`, sub-project ② of the
lamp migration).
