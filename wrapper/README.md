# lmetl HTTP wrapper

A thin FastAPI service that exposes lmetl's docx extraction over HTTP, so consumers
(e.g. the gsmma_lm `lmetl_extract` worker) can extract structured JSON synchronously
without driving lmetl's CLI/batch flow.

It reuses the plain-Python extraction path (`DocxChunker` → `LLMClient` →
`parse_llm_json`) — the same logic as `lmetl.tools.run_extraction` — and returns the
result instead of writing it to `output/`.

## Contract

```
POST /extract?genre=<genre>&parse_only=<bool>
  body: raw docx bytes
  Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document

200 -> { "full_text": str,
         "structured_json": { "genre": str, "chunks": [ {chunk_id, source_section,
                              source_page, extraction, parse_error} ],
                              "all_info": { <schema keys>, "_provenance": {...},
                                            "_stats": {chunks_merged, chunks_failed,
                                                       confidence_min, confidence_avg} } },
         "title": str, "topics": [str] }
non-2xx -> failure
```

- `parse_only=true`: fast lane — parse/chunk only, no LLM at all; `chunks` is empty
  with an explicit `"parse_only": true` marker and no `all_info`.
- `all_info` (full lane): document-level master table, rule-merged from every
  chunk's extraction as it completes — keys mirror the genre schema. `list[str]`
  fields union (deduped), scalars keep the first non-null value, and
  `list[object]` entity fields (e.g. geology `wells`) merge per entity by their
  `identity` key with `source_chunk_ids` provenance and field conflicts kept in
  `conflicts` instead of being overwritten.

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

- **Slow lane is LLM-bound** (minutes for large docx) but no longer blocks the
  server: the pipeline runs in the threadpool, so `/healthz` and the
  `parse_only` fast lane keep answering during a slow extraction. Callers
  should still use an async worker with a long timeout.
- **Genre switching:** `POST /extract?genre=physics` loads
  `configs/genres/physics.yaml` per request (fixed 2026-08-04 — previously
  only the config default genre was ever loaded and every other genre
  silently degraded to core-only). ⚠️ A genre with NO yaml file still
  degrades to core-only **silently, by design** — `genre=base` (the gateway
  default) relies on this to mean "core fields only". Typos in genre names
  therefore do not error; check `structured_json.all_info` keys if fields
  look missing.
- **structured_json shape** is opaque to the consumer (stored as the insight content).
  Coordinate with the consumer before changing it.

Origin: spec drafted in the gsmma_lm repo
(`docs/plans/feature/20260522-lmetl-http-wrapper-design.md`, sub-project ② of the
lamp migration).
