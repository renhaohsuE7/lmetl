"""Tests for DocxChunker."""

from lmetl.chunking.docx_chunker import DocxChunker


class TestDocxChunker:
    def test_chunk_produces_results(self, sample_docx):
        chunker = DocxChunker(max_tokens=4000)
        chunks = chunker.chunk(sample_docx)
        assert len(chunks) > 0

    def test_chunk_has_required_fields(self, sample_docx):
        chunker = DocxChunker(max_tokens=4000)
        chunks = chunker.chunk(sample_docx)
        required = {
            "chunk_id", "source_file", "source_page", "source_page_end",
            "source_section", "source_position", "chunk_index", "content",
            "content_type", "image_refs", "token_estimate",
        }
        for chunk in chunks:
            assert required.issubset(chunk.keys()), f"Missing fields: {required - chunk.keys()}"

    def test_chunk_sections_detected(self, sample_docx):
        chunker = DocxChunker(max_tokens=4000)
        chunks = chunker.chunk(sample_docx)
        sections = {c["source_section"] for c in chunks}
        # Should detect at least some headings
        assert any("前言" in s for s in sections) or any("地質" in s for s in sections)

    def test_small_max_tokens_splits(self, sample_docx):
        chunker = DocxChunker(max_tokens=50)
        chunks = chunker.chunk(sample_docx)
        # With very small token limit, should produce more chunks
        assert len(chunks) >= 3

    def test_token_estimation(self):
        chunker = DocxChunker()
        # Pure CJK text
        assert chunker._estimate_tokens("你好世界") > 0
        # Pure ASCII
        assert chunker._estimate_tokens("hello world") > 0
        # Empty
        assert chunker._estimate_tokens("") == 0

    def test_source_file_in_chunks(self, sample_docx):
        chunker = DocxChunker(max_tokens=4000)
        chunks = chunker.chunk(sample_docx)
        for chunk in chunks:
            assert chunk["source_file"] == "test_report.docx"
