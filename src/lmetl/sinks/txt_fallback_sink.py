"""TxtFallbackSink: writes unstructured/failed extraction results to TXT."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pathway as pw
from pwetl.sinks import BaseSink

logger = logging.getLogger(__name__)


class TxtFallbackSink(BaseSink):
    """Collects failed/unstructured LLM extraction results and writes to TXT."""

    required_config = ["output_dir"]
    optional_config = {}

    def setup(self) -> None:
        output_dir = Path(self.config["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir = output_dir
        self._temp_path = output_dir / "_temp_fallback.jsonl"
        logger.info("TxtFallbackSink '%s' setup: %s", self.name, output_dir)

    def write(self, table: pw.Table) -> None:
        pw.io.jsonlines.write(table, str(self._temp_path))

    def teardown(self) -> None:
        """Post-process: read JSONL, filter unstructured results, write TXT."""
        if not self._temp_path.exists():
            logger.warning("No temp fallback found at %s", self._temp_path)
            return

        fallback_blocks = []
        with open(self._temp_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    llm_result_str = row.get("llm_result", "{}")
                    llm_result = json.loads(llm_result_str)

                    if not llm_result.get("is_structured"):
                        block = self._format_fallback_block(llm_result)
                        fallback_blocks.append(block)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse JSONL row: %s", e)

        if fallback_blocks:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = self._output_dir / f"fallback_{timestamp}.txt"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(fallback_blocks))
            logger.info("Wrote %d fallback blocks to %s", len(fallback_blocks), output_path)
        else:
            logger.info("No fallback results to write")

        self._temp_path.unlink(missing_ok=True)

    def _format_fallback_block(self, result: dict) -> str:
        chunk_id = result.get("chunk_id", "unknown")
        source_file = result.get("source_file", "unknown")
        source_page = result.get("source_page", 0)
        source_section = result.get("source_section", "")
        extracted_at = result.get("extracted_at", "")
        fallback_text = result.get("fallback_text", "")

        return (
            f"{'=' * 60}\n"
            f"CHUNK: {chunk_id}\n"
            f"SOURCE: {source_file}, Page {source_page}\n"
            f"SECTION: {source_section}\n"
            f"EXTRACTED AT: {extracted_at}\n"
            f"{'-' * 60}\n"
            f"{fallback_text}\n"
            f"{'=' * 60}"
        )
