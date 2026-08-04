"""Wrapper all_info wiring — structured_json.all_info alongside chunks (§9e).

DocxChunker and LLMClient are monkeypatched: canned chunks whose fake LLM
responses carry complementary well info. The response must contain the
rule-merged document-level table, while the chunks array keeps its exact
pre-existing per-entry shape (all_info is an additive key, nothing else moves).
The parse_only fast lane must stay LLM-free and all_info-free.
"""

import json

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _chunk(cid, section, content):
    return {
        "chunk_id": cid,
        "chunk_index": 0,
        "source_file": "t.docx",
        "source_page": 1,
        "source_page_end": 1,
        "source_section": section,
        "source_position": "p1",
        "content": content,
        "token_estimate": 10,
    }


CHUNKS = [
    _chunk("c1", "第一章", "泰安溫泉區第一口井。"),
    _chunk("c2", "第二章", "同一口井的溫度與第二口井。"),
    _chunk("c3", "第三章", "這段的 LLM 回覆會壞掉。"),
]

RESPONSES = [
    json.dumps({
        "title": "地熱報告",
        "key_findings": ["A"],
        "confidence_score": 0.9,
        "thinking": "…",
        "wells": [{"name": "TH-1", "depth": "1200m"}],
    }, ensure_ascii=False),
    json.dumps({
        "key_findings": ["B", "A"],
        "confidence_score": 0.7,
        "wells": [
            {"name": "TH-1", "temperature": "180℃"},
            {"name": "TH-2", "depth": "800m"},
        ],
    }, ensure_ascii=False),
    "this is not json {",
]


class FakeChunker:
    def __init__(self, **kwargs):
        pass

    def chunk(self, path):
        return [dict(c) for c in CHUNKS]


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.latency_ms = 1
        self.token_usage_input = 1
        self.token_usage_output = 1


class FakeLLM:
    instances = 0
    responses = []

    def __init__(self, llm_config):
        FakeLLM.instances += 1

    def extract(self, system_prompt, user_prompt):
        return FakeResponse(FakeLLM.responses.pop(0))


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("OLLAMA_ENDPOINT", "http://127.0.0.1:9")
    import wrapper.app as wrapper_app

    FakeLLM.instances = 0
    FakeLLM.responses = list(RESPONSES)
    monkeypatch.setattr(wrapper_app, "DocxChunker", FakeChunker)
    monkeypatch.setattr(wrapper_app, "LLMClient", FakeLLM)
    return fastapi_testclient.TestClient(wrapper_app.app)


def _post(client, **params):
    return client.post(
        "/extract",
        params=params,
        content=b"fake docx bytes",
        headers={"Content-Type": DOCX_MIME},
    )


def test_all_info_merges_across_chunks(client):
    resp = _post(client, genre="geology")
    assert resp.status_code == 200
    sj = resp.json()["structured_json"]
    assert sj["genre"] == "geology"

    info = sj["all_info"]
    wells = info["wells"]
    assert len(wells) == 2
    th1, th2 = wells
    assert th1["name"] == "TH-1"
    assert th1["depth"] == "1200m"
    assert th1["temperature"] == "180℃"
    assert th1["source_chunk_ids"] == ["c1", "c2"]
    assert th1["conflicts"] == []
    assert th2["name"] == "TH-2"
    assert th2["depth"] == "800m"

    assert info["title"] == "地熱報告"
    assert info["key_findings"] == ["A", "B"]
    assert "thinking" not in info
    stats = info["_stats"]
    assert stats["chunks_merged"] == 2
    assert stats["chunks_failed"] == 1
    assert stats["confidence_min"] == 0.7
    assert stats["confidence_avg"] == pytest.approx(0.8)


def test_chunks_array_shape_unchanged(client):
    resp = _post(client, genre="geology")
    chunks = resp.json()["structured_json"]["chunks"]
    assert len(chunks) == 3
    for entry in chunks:
        assert set(entry.keys()) == {
            "chunk_id", "source_section", "source_page", "extraction", "parse_error",
        }
    assert chunks[2]["extraction"] is None
    assert chunks[2]["parse_error"]


def test_parse_only_fast_lane_has_no_all_info_and_no_llm(client):
    resp = _post(client, genre="geology", parse_only="true")
    assert resp.status_code == 200
    sj = resp.json()["structured_json"]
    assert sj["parse_only"] is True
    assert "all_info" not in sj
    assert FakeLLM.instances == 0
