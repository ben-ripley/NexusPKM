"""Token-aware document chunker using LlamaIndex SentenceSplitter.

Spec: F-002 FR-2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from nexuspkm.models.document import Document

logger = structlog.get_logger(__name__)


@dataclass
class ChunkingConfig:
    chunk_size: int = 512
    chunk_overlap: int = 50


class DocumentChunker:
    """Split a Document into overlapping text chunks using SentenceSplitter."""

    _splitter: Any  # llama_index.core.node_parser.SentenceSplitter (ignore_missing_imports)

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        if config is None:
            config = ChunkingConfig()
        self._config = config
        from llama_index.core.node_parser import SentenceSplitter  # noqa: PLC0415

        self._splitter = SentenceSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

    def chunk(self, document: Document) -> list[str]:
        """Split document.content into overlapping text chunks.

        Deterministic: same input always produces the same output.
        Returns an empty list if the document content produces no chunks.
        """
        texts: list[str] = self._splitter.split_text(document.content)
        logger.debug("chunker.split", document_id=document.id, chunk_count=len(texts))
        return texts
