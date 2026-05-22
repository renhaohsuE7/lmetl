"""Thin HTTP wrapper around lmetl's docx extraction.

Exposes ``POST /extract`` so consumers (e.g. gsmma_lm's lmetl_extract worker) can
turn an uploaded docx into a structured-extraction JSON synchronously over HTTP.
lmetl itself has no HTTP API; this reuses the plain-Python extraction path
(DocxChunker -> LLMClient -> parse_llm_json), the same logic as
``lmetl.tools.run_extraction``.

Contract (fixed by the consumer):
    POST /extract?genre=<genre>
        body: raw docx bytes
        Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
    200 -> {"full_text": str, "structured_json": object, "title": str, "topics": [str]}
    non-2xx -> failure

Run:
    uv run uvicorn wrapper.app:app --host 0.0.0.0 --port 9400
Env:
    LMETL_CONFIG (default configs/base.yaml), LMETL_MAX_UPLOAD_BYTES (default 64 MiB),
    plus lmetl's own LLM env (OLLAMA_BASE_URL, etc.).
"""

import os
import tempfile

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from lmetl.chunking.docx_chunker import DocxChunker
from lmetl.llm.client import LLMClient
from lmetl.llm.prompts import PromptBuilder
from lmetl.utils.config import load_lmetl_config
from lmetl.utils.json_parser import parse_llm_json

CONFIG_PATH = os.getenv("LMETL_CONFIG", "configs/base.yaml")
MAX_BYTES = int(os.getenv("LMETL_MAX_UPLOAD_BYTES", str(64 << 20)))  # 64 MiB

app = FastAPI(title="lmetl-extractor")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/extract")
async def extract(request: Request, genre: str = Query(default="")) -> JSONResponse:
    data = await request.body()
    if not data:
        return JSONResponse({"error": "empty body"}, status_code=400)
    if len(data) > MAX_BYTES:
        return JSONResponse({"error": "upload too large"}, status_code=413)

    # Load config; override the genre when provided. Genre fields/prompts come from
    # configs/genres/<genre>.yaml; load_lmetl_config is expected to honour
    # extraction.genre. If a per-genre sync_schemas step is required, pre-sync the
    # supported genres at image build (see Dockerfile / README).
    config = load_lmetl_config(CONFIG_PATH)
    if genre:
        config.setdefault("extraction", {})["genre"] = genre

    with tempfile.NamedTemporaryFile(suffix=".docx") as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            chunks = DocxChunker(max_tokens=4000, overlap_tokens=200).chunk(tmp.name)
        except Exception as e:  # noqa: BLE001 -- surface docx parse failures as 422
            return JSONResponse({"error": f"docx parse failed: {e}"}, status_code=422)

    client = LLMClient(config.get("llm", {}))
    builder = PromptBuilder(config)

    results = []
    for chunk in chunks:
        resp = client.extract(builder.build_system_prompt(), builder.build_user_prompt(chunk))
        parsed, err = parse_llm_json(resp.content)
        results.append(
            {
                "chunk_id": chunk["chunk_id"],
                "source_section": chunk["source_section"],
                "source_page": chunk["source_page"],
                "extraction": parsed,
                "parse_error": err,
            }
        )

    full_text = "\n\n".join(c["content"] for c in chunks)
    return JSONResponse(
        {
            "full_text": full_text,
            "structured_json": {
                "genre": genre or config.get("extraction", {}).get("genre", ""),
                "chunks": results,
            },
            "title": "",  # consumer sets its own title
            "topics": [],
        }
    )
