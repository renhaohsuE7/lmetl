"""Wrapper parse-only fast lane (POST /extract?parse_only=true).

Contract (consumer ask, 2026-07-24 inquiry / implemented 2026-08-04):
- parse_only=true runs the docx parse/chunk stage ONLY: full_text comes back in
  seconds, no LLM call is made at all, structured_json.chunks is empty and
  carries an explicit parse_only marker.
- Default (no param) keeps today's behavior byte-for-byte: every chunk goes
  through the LLM (here: a dead endpoint -> per-chunk parse_error, request
  still 200 thanks to the hardened per-chunk error handling).

The dead-endpoint trick is the proof: if the fast lane touched the LLM at all,
its request would fail/degrade the same way the default lane does.
"""

import os

import pytest

# The wrapper's web deps (fastapi) live in the runtime venv, not in lmetl's
# pyproject — skip cleanly where they are absent instead of erroring.
fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture()
def client(monkeypatch):
    # Point the LLM at a guaranteed-dead endpoint BEFORE the app imports/uses it.
    monkeypatch.setenv("OLLAMA_ENDPOINT", "http://127.0.0.1:9")  # port 9: discard
    monkeypatch.setenv("OLLAMA_MODEL", "does-not-matter")
    from wrapper.app import app

    return fastapi_testclient.TestClient(app)


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _post(client, docx_path, **params):
    with open(docx_path, "rb") as fh:
        return client.post(
            "/extract",
            params=params,
            content=fh.read(),
            headers={"Content-Type": DOCX_MIME},
        )


def test_parse_only_returns_fulltext_without_llm(client, sample_docx):
    resp = _post(client, sample_docx, genre="base", parse_only="true")
    assert resp.status_code == 200
    body = resp.json()

    assert body["full_text"].strip(), "parse-only must still deliver full_text"
    sj = body["structured_json"]
    assert sj["parse_only"] is True
    assert sj["chunks"] == [], "parse-only must not carry LLM extractions"
    # Response envelope stays the consumer-known shape.
    assert set(body.keys()) == {"full_text", "structured_json", "title", "topics"}


def test_default_still_runs_llm_lane(client, sample_docx):
    # Backward compatibility: without parse_only the LLM lane runs for every
    # chunk. Against the dead endpoint that surfaces as per-chunk parse_error —
    # NOT as an empty chunks list, and NOT as a non-200.
    resp = _post(client, sample_docx, genre="base")
    assert resp.status_code == 200
    sj = resp.json()["structured_json"]
    assert "parse_only" not in sj, "default lane keeps today's shape untouched"
    assert sj["chunks"], "default lane must still attempt per-chunk extraction"
    assert all(c["parse_error"] for c in sj["chunks"]), (
        "dead endpoint must surface as per-chunk errors (hardened lane)"
    )


def test_parse_only_false_is_default_lane(client, sample_docx):
    resp = _post(client, sample_docx, genre="base", parse_only="false")
    assert resp.status_code == 200
    sj = resp.json()["structured_json"]
    assert "parse_only" not in sj
    assert sj["chunks"], "explicit false must behave exactly like the default"


def test_parse_only_is_fast(client, sample_docx):
    # Generous ceiling: parse-only is pure python-docx parsing; even on a cold
    # container it finishes in well under a second for the fixture docx. The
    # bound exists to catch a regression that reintroduces LLM latency.
    import time

    t0 = time.time()
    resp = _post(client, sample_docx, genre="base", parse_only="true")
    assert resp.status_code == 200
    assert time.time() - t0 < 5, "parse-only lane must not block on the LLM"


def test_env_is_actually_dead(client):
    # Guard the guard: the endpoint override must be in effect for this module,
    # otherwise test_default_still_runs_llm_lane could silently hit a real LLM.
    assert os.environ["OLLAMA_ENDPOINT"] == "http://127.0.0.1:9"
