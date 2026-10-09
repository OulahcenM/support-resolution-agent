"""Build the knowledge-base vector index from markdown documents.

Run with:  uv run python -m support_agent.rag.ingest
"""

import hashlib
import logging
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from support_agent.config import get_settings
from support_agent.rag.store import get_vector_store

logger = logging.getLogger(__name__)

HEADERS_TO_SPLIT_ON = [("#", "doc_title"), ("##", "section")]
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def load_markdown_files(directory: Path) -> list[Document]:
    files = sorted(directory.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No markdown files found in {directory}")
    return [
        Document(
            page_content=path.read_text(encoding="utf-8"),
            metadata={"source": path.name},
        )
        for path in files
    ]


def split_documents(documents: list[Document]) -> list[Document]:
    """Split by markdown headers first, then by size for long sections."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON, strip_headers=False
    )
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    chunks: list[Document] = []
    for document in documents:
        sections = header_splitter.split_text(document.page_content)
        for section in sections:
            section.metadata = {**document.metadata, **section.metadata}
        chunks.extend(size_splitter.split_documents(sections))
    return chunks


def _chunk_id(chunk: Document, index: int) -> str:
    key = f"{chunk.metadata['source']}|{index}|{chunk.page_content}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def ingest() -> int:
    """Rebuild the collection from scratch so edited or deleted docs never leave stale chunks."""
    settings = get_settings()
    chunks = split_documents(load_markdown_files(settings.knowledge_base_dir))

    store = get_vector_store()
    store.reset_collection()
    store.add_documents(chunks, ids=[_chunk_id(c, i) for i, c in enumerate(chunks)])
    return len(chunks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    count = ingest()
    logger.info("Indexed %d chunks into %s", count, get_settings().chroma_dir)
