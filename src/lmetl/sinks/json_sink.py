"""JsonExtractionSink: writes structured extraction results to JSON."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pathway as pw
from pwetl.sinks import BaseSink

logger = logging.getLogger(__name__)


class JsonExtractionSink(BaseSink):
    """Collects structured LLM extraction results and writes to JSON."""

    required_config = ["output_dir"]
    optional_config = {
        "include_metadata": True,
    }

    def setup(self) -> None:
        output_dir = Path(self.config["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir = output_dir

        # Temp JSONL file for Pathway to write to
        self._temp_path = output_dir / "_temp_output.jsonl"
        logger.info("JsonExtractionSink '%s' setup: %s", self.name, output_dir)

    def write(self, table: pw.Table) -> None:
        pw.io.jsonlines.write(table, str(self._temp_path))

    def teardown(self) -> None:
        """Post-process: read JSONL, filter structured results, write final JSON."""
        if not self._temp_path.exists():
            logger.warning("No temp output found at %s", self._temp_path)
            return

        structured_results = []
        with open(self._temp_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    # Pathway adds metadata columns; our data is in llm_result
                    llm_result_str = row.get("llm_result", "{}")
                    llm_result = json.loads(llm_result_str)

                    if llm_result.get("is_structured"):
                        structured_results.append(llm_result)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse JSONL row: %s", e)

        if structured_results:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            # Group by source file
            by_file: dict = {}
            for result in structured_results:
                src = result.get("source_file", "unknown")
                by_file.setdefault(src, []).append(result)

            for source_file, results in by_file.items():
                safe_name = Path(source_file).stem
                output_path = self._output_dir / f"{safe_name}_{timestamp}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                logger.info("Wrote %d results to %s", len(results), output_path)

        # Clean up temp file
        self._temp_path.unlink(missing_ok=True)
