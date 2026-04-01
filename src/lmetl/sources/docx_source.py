"""DocxSource: parse docx documents into chunks for the ETL pipeline."""

import logging
from pathlib import Path

import pathway as pw
from pwetl.sources import BaseSource

from lmetl.chunking.docx_chunker import DocxChunker

logger = logging.getLogger(__name__)


class DocxSource(BaseSource):
    """Reads a docx file, chunks it by headings, and returns a pw.Table of chunks."""

    required_config = ["file_path"]
    optional_config = {
        "chunking": {"strategy": "heading", "max_tokens": 4000, "overlap_tokens": 200},
        "image_mode": "metadata_only",
    }

    def setup(self) -> None:
        file_path = self.config["file_path"]
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        chunking_config = self.config.get("chunking", {})
        self.chunker = DocxChunker(
            max_tokens=chunking_config.get("max_tokens", 4000),
            overlap_tokens=chunking_config.get("overlap_tokens", 200),
            strategy=chunking_config.get("strategy", "heading"),
            image_mode=self.config.get("image_mode", "metadata_only"),
        )
        logger.info("DocxSource '%s' setup complete: %s", self.name, file_path)

    def read(self) -> pw.Table:
        file_path = self.config["file_path"]
        chunks = self.chunker.chunk(file_path)

        if not chunks:
            logger.warning("No chunks produced from %s", file_path)

        schema = self._get_schema()
        if schema is None:
            raise ValueError(
                f"Source '{self.name}' requires a schema configuration. "
                "Please specify 'schema' in your config.yaml"
            )

        # Convert chunk dicts to tuples in schema field order
        field_names = list(schema.__annotations__.keys())
        rows = []
        for chunk in chunks:
            row = tuple(chunk.get(f, "" if isinstance(chunk.get(f), str) else 0) for f in field_names)
            rows.append(row)

        logger.info("DocxSource '%s': %d chunks -> pw.Table", self.name, len(rows))
        return pw.debug.table_from_rows(schema=schema, rows=rows)

    def _get_schema(self):
        from pwetl.utils.schema import SchemaParser

        schema_config = self.config.get("schema")
        if schema_config:
            return SchemaParser.parse(schema_config)
        return None
