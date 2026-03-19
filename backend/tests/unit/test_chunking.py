"""Unit tests for DocumentChunker.

Spec: F-002 FR-2
"""

from __future__ import annotations

import datetime

from nexuspkm.engine.chunking import ChunkingConfig, DocumentChunker
from nexuspkm.models.document import Document, DocumentMetadata, SourceType

NOW = datetime.datetime(2026, 3, 18, 12, 0, 0, tzinfo=datetime.UTC)


def _make_doc(content: str, doc_id: str = "d1") -> Document:
    return Document(
        id=doc_id,
        content=content,
        metadata=DocumentMetadata(
            source_type=SourceType.OBSIDIAN_NOTE,
            source_id="note-1",
            title="Test Note",
            created_at=NOW,
            updated_at=NOW,
            synced_at=NOW,
        ),
    )


class TestDocumentChunker:
    def test_short_content_returns_single_chunk(self) -> None:
        chunker = DocumentChunker()
        doc = _make_doc("Hello world.")
        chunks = chunker.chunk(doc)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world."

    def test_chunk_returns_strings(self) -> None:
        chunker = DocumentChunker()
        doc = _make_doc("Some content here.")
        chunks = chunker.chunk(doc)
        assert all(isinstance(c, str) for c in chunks)

    def test_long_content_produces_multiple_chunks(self) -> None:
        # Generate content well above the default 512-token chunk size
        long_text = " ".join(["word"] * 600)
        chunker = DocumentChunker()
        doc = _make_doc(long_text)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_each_chunk_is_non_empty(self) -> None:
        long_text = " ".join(["word"] * 600)
        chunker = DocumentChunker()
        doc = _make_doc(long_text)
        for chunk in chunker.chunk(doc):
            assert len(chunk) > 0

    def test_deterministic_same_input_same_output(self) -> None:
        content = " ".join([f"token{i}" for i in range(300)])
        chunker = DocumentChunker()
        doc = _make_doc(content)
        result_a = chunker.chunk(doc)
        result_b = chunker.chunk(doc)
        assert result_a == result_b

    def test_custom_chunk_size_produces_more_chunks(self) -> None:
        content = " ".join(["word"] * 200)
        small_chunker = DocumentChunker(ChunkingConfig(chunk_size=50, chunk_overlap=10))
        large_chunker = DocumentChunker(ChunkingConfig(chunk_size=200, chunk_overlap=10))
        small_chunks = small_chunker.chunk(_make_doc(content))
        large_chunks = large_chunker.chunk(_make_doc(content))
        assert len(small_chunks) >= len(large_chunks)

    def test_overlap_adjacent_chunks_share_text(self) -> None:
        # With overlap, adjacent chunks should share some tokens
        content = " ".join([f"token{i}" for i in range(300)])
        chunker = DocumentChunker(ChunkingConfig(chunk_size=100, chunk_overlap=20))
        chunks = chunker.chunk(_make_doc(content))
        if len(chunks) >= 2:
            # The end of chunk[0] and start of chunk[1] should overlap
            words_0 = set(chunks[0].split()[-10:])
            words_1 = set(chunks[1].split()[:10])
            # Some tokens should appear in both (overlap)
            assert len(words_0 & words_1) > 0

    def test_config_stored_correctly(self) -> None:
        config = ChunkingConfig(chunk_size=256, chunk_overlap=25)
        chunker = DocumentChunker(config)
        assert chunker._config.chunk_size == 256
        assert chunker._config.chunk_overlap == 25

    def test_default_config_values(self) -> None:
        config = ChunkingConfig()
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
