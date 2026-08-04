"""Wrapper end of ④b: a request for an existing NON-DEFAULT genre must use
that genre's fields (previously: silently degraded to core-only)."""

import json
import textwrap

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class FakeChunker:
    def __init__(self, **kwargs):
        pass

    def chunk(self, path):
        return [{
            "chunk_id": "c1", "chunk_index": 0, "source_file": "t.docx",
            "source_page": 1, "source_page_end": 1, "source_section": "s",
            "source_position": "p1", "content": "內容", "token_estimate": 3,
        }]


class FakeResponse:
    content = json.dumps({"title": "t"})
    latency_ms = 1
    token_usage_input = 1
    token_usage_output = 1


class FakeLLM:
    def __init__(self, llm_config):
        pass

    def extract(self, system_prompt, user_prompt):
        return FakeResponse()


@pytest.fixture()
def client_with_custom_genres(monkeypatch, tmp_path):
    (tmp_path / "genres").mkdir()
    (tmp_path / "base.yaml").write_text(textwrap.dedent("""\
        lmetl:
          extraction:
            core: true
            genre: defaultgenre
          schemas:
            core:
              fields:
                - name: title
                  type: str?
                  description: t
    """))
    (tmp_path / "genres" / "defaultgenre.yaml").write_text(
        "fields:\n  - name: default_field\n    type: str?\n    description: d\n")
    (tmp_path / "genres" / "othergenre.yaml").write_text(
        "fields:\n  - name: other_field\n    type: str?\n    description: o\n")

    monkeypatch.setenv("OLLAMA_ENDPOINT", "http://127.0.0.1:9")
    import wrapper.app as wrapper_app

    monkeypatch.setattr(wrapper_app, "CONFIG_PATH", str(tmp_path / "base.yaml"))
    monkeypatch.setattr(wrapper_app, "DocxChunker", FakeChunker)
    monkeypatch.setattr(wrapper_app, "LLMClient", FakeLLM)
    return fastapi_testclient.TestClient(wrapper_app.app)


def _extract(client, genre):
    resp = client.post(
        "/extract", params={"genre": genre},
        content=b"fake docx", headers={"Content-Type": DOCX_MIME},
    )
    assert resp.status_code == 200
    return resp.json()["structured_json"]["all_info"]


def test_non_default_genre_fields_are_loaded(client_with_custom_genres):
    info = _extract(client_with_custom_genres, "othergenre")
    assert "other_field" in info, (
        "④b: requesting an existing non-default genre must load its fields "
        "(previously silently degraded to core-only)"
    )
    assert "default_field" not in info


def test_default_genre_still_works(client_with_custom_genres):
    info = _extract(client_with_custom_genres, "defaultgenre")
    assert "default_field" in info
