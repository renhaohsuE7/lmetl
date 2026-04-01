"""Tests for DocxSource (without Pathway dependency for unit tests)."""

from lmetl.chunking.docx_chunker import DocxChunker


class TestDocxSourceChunking:
    """Test the chunking logic that DocxSource relies on."""

    def test_chunk_output_matches_schema_fields(self, sample_docx):
        """Ensure chunk dicts have the fields expected by the pwetl schema config."""
        chunker = DocxChunker(max_tokens=4000)
        chunks = chunker.chunk(sample_docx)

        schema_fields = [
            "chunk_id", "source_file", "source_page", "source_page_end",
            "source_section", "source_position", "chunk_index", "content",
            "content_type", "image_refs", "token_estimate",
        ]

        for chunk in chunks:
            for field in schema_fields:
                assert field in chunk, f"Missing field: {field}"

    def test_chunk_types_correct(self, sample_docx):
        chunker = DocxChunker(max_tokens=4000)
        chunks = chunker.chunk(sample_docx)

        for chunk in chunks:
            assert isinstance(chunk["chunk_id"], str)
            assert isinstance(chunk["source_file"], str)
            assert isinstance(chunk["source_page"], int)
            assert isinstance(chunk["source_page_end"], int)
            assert chunk["source_page_end"] >= chunk["source_page"]
            assert isinstance(chunk["chunk_index"], int)
            assert isinstance(chunk["content"], str)
            assert isinstance(chunk["token_estimate"], int)
            assert isinstance(chunk["image_refs"], str)  # JSON string
