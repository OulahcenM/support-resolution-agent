"""Application service: run conversation turns (sync and streaming), history and tickets."""

from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from support_agent.db.models import Ticket
from support_agent.db.session import get_session
from support_agent.graph.builder import get_graph

RECURSION_LIMIT = 25
STREAMED_NODES = frozenset({"agent"})


@dataclass(frozen=True, slots=True)
class TurnResult:
    thread_id: str
    reply: str
    intent: str | None
    sentiment: str | None
    tools_used: list[str] = field(default_factory=list)


def _config(thread_id: str) -> RunnableConfig:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }


def _tools_used_this_turn(messages: list[AnyMessage]) -> list[str]:
    """Tools called after the latest human message, in call order."""
    tools: list[str] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage) and message.name:
            tools.append(message.name)
    return list(reversed(tools))


def _result_from_state(thread_id: str, state: dict[str, Any]) -> TurnResult:
    messages = state["messages"]
    return TurnResult(
        thread_id=thread_id,
        reply=str(messages[-1].content),
        intent=state.get("intent"),
        sentiment=state.get("sentiment"),
        tools_used=_tools_used_this_turn(messages),
    )


def run_turn(message: str, thread_id: str) -> TurnResult:
    state = get_graph().invoke({"messages": [HumanMessage(message)]}, _config(thread_id))
    return _result_from_state(thread_id, state)


def stream_turn(message: str, thread_id: str) -> Iterator[dict[str, Any]]:
    """Yield {"type": "token"} events while the agent writes, then one final {"type": "done"}.

    The "done" event carries the authoritative reply; clients should replace streamed text with it.
    """
    graph = get_graph()
    config = _config(thread_id)

    for chunk, metadata in graph.stream(
        {"messages": [HumanMessage(message)]}, config, stream_mode="messages"
    ):
        if (
            metadata.get("langgraph_node") in STREAMED_NODES
            and isinstance(chunk, AIMessageChunk)
            and isinstance(chunk.content, str)
            and chunk.content
        ):
            yield {"type": "token", "content": chunk.content}

    final_state = graph.get_state(config).values
    yield {"type": "done", **asdict(_result_from_state(thread_id, final_state))}


def get_history(thread_id: str) -> list[dict[str, str]]:
    """Customer-facing transcript: user messages and final assistant replies only."""
    snapshot = get_graph().get_state(_config(thread_id))
    messages = snapshot.values.get("messages", []) if snapshot else []

    history: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            history.append({"role": "user", "content": str(message.content)})
        elif isinstance(message, AIMessage) and message.content and not message.tool_calls:
            history.append({"role": "assistant", "content": str(message.content)})
    return history


def list_tickets(limit: int = 50) -> list[Ticket]:
    with get_session() as session:
        return list(session.scalars(select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)))
