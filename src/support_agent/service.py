"""Application service: one function to run a conversation turn (used by CLI and API)."""

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import select

from support_agent.graph.builder import get_graph
from support_agent.db.models import Ticket
from support_agent.db.session import get_session

RECURSION_LIMIT = 25


@dataclass(frozen=True, slots=True)
class TurnResult:
    reply: str
    intent: str | None
    sentiment: str | None
    tools_used: list[str] = field(default_factory=list)


def run_turn(message: str, thread_id: str) -> TurnResult:
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }
    state = get_graph().invoke({"messages": [HumanMessage(message)]}, config)

    # Collect tools called during THIS turn only (messages after the latest human message).
    tools_used: list[str] = []
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, ToolMessage) and msg.name:
            tools_used.append(msg.name)

    return TurnResult(
        reply=str(state["messages"][-1].content),
        intent=state.get("intent"),
        sentiment=state.get("sentiment"),
        tools_used=list(reversed(tools_used)),
    )


def get_history(thread_id: str) -> list[dict[str, str]]:
    """Customer-facing transcript: user messages and final assistant replies only."""
    snapshot = get_graph().get_state({"configurable": {"thread_id": thread_id}})
    messages = snapshot.values.get("messages", []) if snapshot else []

    history: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            history.append({"role": "user", "content": str(message.content)})
        elif (
            isinstance(message, AIMessage)
            and message.content
            and not message.tool_calls
        ):
            history.append({"role": "assistant", "content": str(message.content)})
    return history


def list_tickets(limit: int = 50) -> list[Ticket]:
    with get_session() as session:
        return list(
            session.scalars(
                select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
            )
        )
