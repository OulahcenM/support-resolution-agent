"""Knowledge-base search tool."""

from langchain_core.tools import tool

from support_agent.rag.retriever import format_context, search_knowledge_base


@tool
def search_policies(query: str) -> str:
    """Search the store's official policies and FAQ: shipping, delivery times, returns,
    refunds, cancellations, payments, discount codes, product care and support hours.

    ALWAYS call this before answering any policy question. Never answer policy questions
    from memory. If nothing relevant is found, say you don't have that information.
    """
    return format_context(search_knowledge_base(query))
