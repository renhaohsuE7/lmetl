"""Run full LLM extraction on a docx file.

Usage:
    uv run python -m lmetl.tools.run_extraction <docx_path>
    uv run python -m lmetl.tools.run_extraction <docx_path> --max-chunks 5
    uv run python -m lmetl.tools.run_extraction <docx_path> --config configs/dig_info_geology.yaml
"""

import argparse
import json
import logging
import os
import sys
import time

from lmetl.chunking.docx_chunker import DocxChunker
from lmetl.llm.client import LLMClient
from lmetl.llm.prompts import PromptBuilder
from lmetl.utils.json_parser import parse_llm_json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def run_extraction(
    docx_path: str,
    config_path: str = "configs/dig_info_geology.yaml",
    output_dir: str = "output/extractions",
    max_chunks: int = 0,
) -> None:
    """Extract structured info from a docx file using LLM."""
    from pathlib import Path

    if not Path(docx_path).exists():
        logger.error("File not found: %s", docx_path)
        sys.exit(1)

    from lmetl.utils.config import load_lmetl_config
    config = load_lmetl_config(config_path)

    chunker = DocxChunker(max_tokens=4000, overlap_tokens=200)
    chunks = chunker.chunk(docx_path)
    logger.info("Total chunks: %d", len(chunks))

    if max_chunks > 0:
        chunks = chunks[:max_chunks]
        logger.info("Limited to first %d chunks", max_chunks)

    client = LLMClient(config.get("llm", {}))
    builder = PromptBuilder(config)

    results = []
    t_start = time.time()

    for i, chunk in enumerate(chunks):
        logger.info(
            "--- Chunk %d/%d: %s (tokens=%d, page=%d-%d) ---",
            i + 1, len(chunks), chunk["source_section"][:50],
            chunk["token_estimate"], chunk["source_page"], chunk["source_page_end"],
        )

        system_prompt = builder.build_system_prompt()
        user_prompt = builder.build_user_prompt(chunk)
        response = client.extract(system_prompt, user_prompt)
        parsed, error = parse_llm_json(response.content)

        provenance = {
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "source_file": chunk["source_file"],
            "source_page": chunk["source_page"],
            "source_page_end": chunk["source_page_end"],
            "source_section": chunk["source_section"],
            "source_position": chunk["source_position"],
            "token_estimate": chunk["token_estimate"],
        }

        if parsed is not None:
            results.append({
                **provenance,
                "extraction": parsed,
                "latency_ms": response.latency_ms,
                "tokens_in": response.token_usage_input,
                "tokens_out": response.token_usage_output,
            })
            conf = parsed.get("confidence_score", "?")
            logger.info("  OK - confidence=%s, latency=%dms", conf, response.latency_ms)
        else:
            results.append({
                **provenance,
                "extraction": None,
                "parse_error": error,
                "raw_response": response.content[:500],
                "latency_ms": response.latency_ms,
            })
            logger.info("  FAIL - %s", error)

    t_total = time.time() - t_start

    # Write results
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(docx_path).stem
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{stem}_{timestamp}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Summary
    success = [r for r in results if r.get("extraction") is not None]
    confidences = [r["extraction"].get("confidence_score", 0) for r in success]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0
    avg_lat = sum(r["latency_ms"] for r in results) / len(results) if results else 0

    logger.info("=== DONE ===")
    logger.info("Total time: %.0fs (%.1f min)", t_total, t_total / 60)
    logger.info("Success: %d/%d", len(success), len(results))
    logger.info("Avg confidence: %.3f", avg_conf)
    logger.info("Avg latency: %.0fms", avg_lat)
    logger.info("Output: %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM extraction on a docx file.")
    parser.add_argument("docx", help="Path to docx file")
    parser.add_argument("--config", default="configs/dig_info_geology.yaml", help="YAML config path")
    parser.add_argument("--output-dir", default="output/extractions", help="Output directory")
    parser.add_argument("--max-chunks", type=int, default=0, help="Limit chunks (0=all)")
    args = parser.parse_args()

    run_extraction(args.docx, args.config, args.output_dir, args.max_chunks)


if __name__ == "__main__":
    main()
