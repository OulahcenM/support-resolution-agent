"""Application service: one function to run a conversation turn (used by CLI and API)."""

from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, ToolMessage

from support_agent.graph.builder import get_graph

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
