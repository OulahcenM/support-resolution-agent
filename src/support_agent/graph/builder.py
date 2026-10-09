"""Graph assembly and the cached, persistent application graph."""

import sqlite3
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from support_agent.config import get_settings
from support_agent.graph.nodes import agent, classify, decline, route_after_classify
from support_agent.graph.state import SupportState
from support_agent.tools import ALL_TOOLS


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    graph = StateGraph(SupportState)

    graph.add_node("classify", classify)
    graph.add_node("decline", decline)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify", route_after_classify, {"agent": "agent", "decline": "decline"}
    )
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    graph.add_edge("decline", END)

    return graph.compile(checkpointer=checkpointer)


@lru_cache
def get_graph() -> CompiledStateGraph:
    """Application graph with SQLite-backed conversation memory."""
    path = get_settings().checkpoint_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    return build_graph(checkpointer=SqliteSaver(connection))
