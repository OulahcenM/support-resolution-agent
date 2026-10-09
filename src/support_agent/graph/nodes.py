"""Graph nodes and routing functions."""

from datetime import datetime, timezone
from typing import Any, Literal

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    trim_messages,
)

from support_agent.config import get_settings
from support_agent.graph.llm import Classification, get_agent_model, get_classifier
from support_agent.graph.prompts import (
    AGENT_SYSTEM_PROMPT,
    CLASSIFIER_PROMPT,
    DECLINE_MESSAGE,
    SENTIMENT_GUIDANCE,
    STEP_LIMIT_MESSAGE,
)
from support_agent.graph.state import SupportState

MAX_HISTORY_MESSAGES = 30
CLASSIFIER_CONTEXT_MESSAGES = 6
MIN_STEPS_TO_CONTINUE = 3


def _transcript(messages: list[AnyMessage], limit: int) -> str:
    """Compact human/assistant transcript for the classifier (tool messages excluded)."""
    lines = []
    for message in messages:
        if isinstance(message, HumanMessage):
            lines.append(f"Customer: {message.content}")
        elif isinstance(message, AIMessage) and message.content:
            lines.append(f"Assistant: {message.content}")
    return "\n".join(lines[-limit:])


def classify(state: SupportState) -> dict[str, Any]:
    settings = get_settings()
    result: Classification = get_classifier().invoke(
        [
            SystemMessage(CLASSIFIER_PROMPT.format(store_name=settings.store_name)),
            HumanMessage(_transcript(state["messages"], CLASSIFIER_CONTEXT_MESSAGES)),
        ]
    )
    return {
        "intent": result.intent,
        "sentiment": result.sentiment,
        "blocked": result.intent == "off_topic" or result.is_manipulation_attempt,
    }


def route_after_classify(state: SupportState) -> Literal["agent", "decline"]:
    return "decline" if state["blocked"] else "agent"


def decline(state: SupportState) -> dict[str, Any]:
    store_name = get_settings().store_name
    return {"messages": [AIMessage(DECLINE_MESSAGE.format(store_name=store_name))]}


def agent(state: SupportState) -> dict[str, Any]:
    if state["remaining_steps"] < MIN_STEPS_TO_CONTINUE:
        return {"messages": [AIMessage(STEP_LIMIT_MESSAGE)]}

    settings = get_settings()
    system_prompt = AGENT_SYSTEM_PROMPT.format(
        store_name=settings.store_name,
        today=datetime.now(timezone.utc).date().isoformat(),
        intent=state["intent"],
        sentiment=state["sentiment"],
        sentiment_guidance=SENTIMENT_GUIDANCE.get(state["sentiment"], ""),
    )
    # Keep recent history only; start on a human turn so tool-call pairs are never split.
    history = trim_messages(
        state["messages"],
        max_tokens=MAX_HISTORY_MESSAGES,
        token_counter=len,
        strategy="last",
        start_on="human",
    )
    response = get_agent_model().invoke([SystemMessage(system_prompt), *history])
    return {"messages": [response]}
