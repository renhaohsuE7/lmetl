"""V3 (2026-08-04 chain-verification finding): one in-flight slow extraction
must NOT block the event loop — /healthz (liveness) and the parse_only fast
lane have to keep answering while a full-lane LLM extraction runs.

Before the fix the handler was `async def` running synchronous chunker+LLM
code inline: a single slow request froze every other request (observed live:
/healthz timed out for the whole 17-minute miaoli extraction).

NOTE: this test boots a REAL uvicorn server (single shared event loop, like
production). starlette's TestClient dispatches each request on its own loop,
so it structurally cannot reproduce single-loop blocking — do not "simplify"
this back to TestClient.
"""

import json
import threading
import time

import pytest

httpx = pytest.importorskip("httpx")
uvicorn = pytest.importorskip("uvicorn")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

SLOW_SECONDS = 3.0


class FakeChunker:
    def __init__(self, **kwargs):
        pass

    def chunk(self, path):
        return [{
            "chunk_id": "c1", "chunk_index": 0, "source_file": "t.docx",
            "source_page": 1, "source_page_end": 1, "source_section": "s",
            "source_position": "p1", "content": "內容", "token_estimate": 3,
        }]


class SlowResponse:
    content = json.dumps({"title": "t", "confidence_score": 0.5})
    latency_ms = 1
    token_usage_input = 1
    token_usage_output = 1


class SlowLLM:
    def __init__(self, llm_config):
        pass

    def extract(self, system_prompt, user_prompt):
        time.sleep(SLOW_SECONDS)
        return SlowResponse()


@pytest.fixture()
def live_server(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENDPOINT", "http://127.0.0.1:9")
    import wrapper.app as wrapper_app

    monkeypatch.setattr(wrapper_app, "DocxChunker", FakeChunker)
    monkeypatch.setattr(wrapper_app, "LLMClient", SlowLLM)

    config = uvicorn.Config(
        wrapper_app.app, host="127.0.0.1", port=0, log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn did not start within 10s")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


def test_healthz_answers_while_slow_extraction_runs(live_server):
    started = threading.Event()
    done = {}

    def slow_extract():
        started.set()
        resp = httpx.post(
            f"{live_server}/extract", params={"genre": "base"},
            content=b"fake docx", headers={"Content-Type": DOCX_MIME},
            timeout=SLOW_SECONDS + 10,
        )
        done["status"] = resp.status_code

    worker = threading.Thread(target=slow_extract)
    worker.start()
    started.wait(timeout=2)
    time.sleep(0.5)  # let the extract reach the (slow) LLM call

    t0 = time.monotonic()
    health = httpx.get(f"{live_server}/healthz", timeout=SLOW_SECONDS + 10)
    elapsed = time.monotonic() - t0

    worker.join(timeout=SLOW_SECONDS + 10)
    assert done.get("status") == 200  # the slow lane itself still succeeds

    assert health.status_code == 200
    assert elapsed < 1.5, (
        f"/healthz took {elapsed:.2f}s while a slow extraction was in flight — "
        "the event loop is blocked (V3)"
    )
