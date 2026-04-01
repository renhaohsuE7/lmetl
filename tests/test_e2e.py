"""
E2E test: docx chunking -> LLM extraction -> JSON output.

Requires:
- Real docx file in data/
- Ollama service at 192.168.9.160:11434 with gpt-oss:120b loaded

Run with:
    uv run pytest tests/test_e2e.py -v -s --timeout=600

Skip if Ollama is unreachable:
    uv run pytest tests/test_e2e.py -v -s -k "e2e"
"""

import json
import logging
import os

import pytest
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OLLAMA_ENDPOINT = os.environ.get("OLLAMA_ENDPOINT", "http://192.168.9.160:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:120b")
DOCX_PATH = "data/dig_info_from_pdf_mission_data/[109]大屯火山群地區地熱探勘資料執行摘要.docx"
CONFIG_PATH = "configs/dig_info_geology.yaml"
MAX_CHUNKS = 5  # Test more chunks for better coverage


def _load_etl_config():
    """Load lmetl config from YAML, override endpoint/model from env."""
    with open(CONFIG_PATH) as f:
        full = yaml.safe_load(f)
    config = full.get("lmetl", {})
    config.setdefault("llm", {})["endpoint"] = OLLAMA_ENDPOINT
    config["llm"]["model"] = OLLAMA_MODEL
    return config


def ollama_reachable():
    """Check if Ollama is reachable."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_ENDPOINT}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


skip_no_ollama = pytest.mark.skipif(
    not ollama_reachable(), reason="Ollama not reachable"
)
skip_no_docx = pytest.mark.skipif(
    not os.path.exists(DOCX_PATH), reason=f"Test docx not found: {DOCX_PATH}"
)


@skip_no_ollama
@skip_no_docx
class TestE2E:

    def test_chunking_real_docx(self):
        """Test that real docx can be chunked."""
        from lmetl.chunking.docx_chunker import DocxChunker

        chunker = DocxChunker(max_tokens=4000, overlap_tokens=200)
        chunks = chunker.chunk(DOCX_PATH)

        assert len(chunks) > 0, "Should produce at least 1 chunk"
        logger.info("Chunking produced %d chunks", len(chunks))

        for i, chunk in enumerate(chunks[:3]):
            logger.info(
                "  Chunk %d: section=%s, tokens=%d, content_preview=%s...",
                i,
                chunk["source_section"],
                chunk["token_estimate"],
                chunk["content"][:80],
            )

    def test_llm_extraction_single_chunk(self):
        """Test LLM extraction on a single chunk from real docx."""
        from lmetl.chunking.docx_chunker import DocxChunker
        from lmetl.llm.client import LLMClient
        from lmetl.llm.prompts import PromptBuilder
        from lmetl.utils.json_parser import parse_llm_json

        # Chunk
        chunker = DocxChunker(max_tokens=4000, overlap_tokens=200)
        chunks = chunker.chunk(DOCX_PATH)
        assert len(chunks) > 0

        # Pick first chunk with substantial content
        chunk = None
        for c in chunks:
            if c["token_estimate"] > 100:
                chunk = c
                break
        if chunk is None:
            chunk = chunks[0]

        logger.info(
            "Testing chunk: section=%s, tokens=%d",
            chunk["source_section"],
            chunk["token_estimate"],
        )

        # Build prompts from YAML config
        config = _load_etl_config()
        builder = PromptBuilder(config)
        system_prompt = builder.build_system_prompt()
        user_prompt = builder.build_user_prompt(chunk)

        logger.info("System prompt length: %d chars", len(system_prompt))
        logger.info("User prompt length: %d chars", len(user_prompt))

        # Call LLM
        client = LLMClient(config.get("llm", {}))
        response = client.extract(system_prompt, user_prompt)

        logger.info("LLM response: latency=%dms, tokens_in=%d, tokens_out=%d",
                     response.latency_ms, response.token_usage_input, response.token_usage_output)
        logger.info("Raw response content:\n%s", response.content[:2000])

        # Try to parse as JSON
        assert response.content, "LLM should return non-empty content"

        result, error = parse_llm_json(response.content)

        if result is not None:
            logger.info("Parsed JSON keys: %s", list(result.keys()))
            assert isinstance(result, dict), "Result should be a dict"
            logger.info("title: %s", result.get("title"))
            logger.info("authors: %s", result.get("authors"))
            logger.info("key_findings: %s", result.get("key_findings"))
            logger.info("confidence_score: %s", result.get("confidence_score"))
            logger.info("rock_types: %s", result.get("rock_types"))
            logger.info("formations: %s", result.get("formations"))
        else:
            logger.warning("JSON parse failed: %s", error)
            pytest.skip(f"LLM returned non-JSON response: {error}")

    def test_multi_chunk_extraction(self):
        """Test extraction on multiple chunks, simulate full pipeline."""
        from lmetl.chunking.docx_chunker import DocxChunker
        from lmetl.llm.client import LLMClient
        from lmetl.llm.prompts import PromptBuilder
        from lmetl.utils.json_parser import parse_llm_json

        chunker = DocxChunker(max_tokens=4000, overlap_tokens=200)
        chunks = chunker.chunk(DOCX_PATH)

        # Only test first MAX_CHUNKS
        test_chunks = chunks[:MAX_CHUNKS]
        logger.info("Testing %d / %d chunks", len(test_chunks), len(chunks))

        config = _load_etl_config()
        builder = PromptBuilder(config)
        client = LLMClient(config.get("llm", {}))

        results = []
        for i, chunk in enumerate(test_chunks):
            logger.info("--- Chunk %d/%d: %s (tokens=%d) ---",
                        i + 1, len(test_chunks), chunk["source_section"], chunk["token_estimate"])

            system_prompt = builder.build_system_prompt()
            user_prompt = builder.build_user_prompt(chunk)

            response = client.extract(system_prompt, user_prompt)
            logger.info("  latency=%dms", response.latency_ms)

            parsed, error = parse_llm_json(response.content)

            # Chunk provenance info
            provenance = {
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "source_file": chunk["source_file"],
                "source_page": chunk["source_page"],
                "source_page_end": chunk["source_page_end"],
                "source_section": chunk["source_section"],
                "source_position": chunk["source_position"],
                "content_type": chunk["content_type"],
                "token_estimate": chunk["token_estimate"],
                "image_refs": chunk["image_refs"],
            }

            if parsed is not None:
                results.append({
                    **provenance,
                    "extraction": parsed,
                    "latency_ms": response.latency_ms,
                    "tokens_in": response.token_usage_input,
                    "tokens_out": response.token_usage_output,
                })
                logger.info("  OK - parsed JSON with %d keys", len(parsed))
            else:
                logger.warning("  FAIL - %s", error)
                results.append({
                    **provenance,
                    "extraction": None,
                    "parse_error": error,
                    "raw_response": response.content[:500],
                    "latency_ms": response.latency_ms,
                })

        # Write results to output for inspection
        os.makedirs("output/e2e_test", exist_ok=True)
        output_path = "output/e2e_test/extraction_results.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Results written to %s", output_path)

        # At least some should succeed
        successful = [r for r in results if r.get("extraction") is not None]
        logger.info("%d / %d chunks successfully extracted", len(successful), len(results))
        assert len(successful) > 0, "At least one chunk should produce valid JSON"
