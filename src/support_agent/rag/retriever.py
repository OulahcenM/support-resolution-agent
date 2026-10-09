"""Knowledge-base retrieval used by the agent.

Quick manual check:  uv run python -m support_agent.rag.retriever "your question"
"""

import sys
from dataclasses import dataclass

from support_agent.rag.store import get_vector_store

DEFAULT_K = 4
# Cosine relevance below this is treated as "not in the knowledge base".
MIN_RELEVANCE = 0.35


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    content: str
    source: str
    section: str | None
    score: float


def search_knowledge_base(
    query: str, k: int = DEFAULT_K, min_relevance: float = MIN_RELEVANCE
) -> list[RetrievedChunk]:
    if not query.strip():
        return []

    results = get_vector_store().similarity_search_with_relevance_scores(query, k=k)
    return [
        RetrievedChunk(
            content=doc.page_content,
            source=doc.metadata.get("source", "unknown"),
            section=doc.metadata.get("section"),
            score=round(score, 3),
        )
        for doc, score in results
        if score >= min_relevance
    ]


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as an LLM-ready context block with source labels."""
    if not chunks:
        return "No relevant policy information was found in the knowledge base."
    return "\n\n---\n\n".join(
        f"[Source: {c.source}{f' > {c.section}' if c.section else ''}]\n{c.content}" for c in chunks
    )


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Can I return a clearance item?"
    hits = search_knowledge_base(question)
    print(f"\nQ: {question}\n")
    if not hits:
        print("(no relevant chunks)")
    for hit in hits:
        print(f"{hit.score:.3f}  {hit.source} > {hit.section}")
