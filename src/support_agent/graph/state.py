"""Graph state definition."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps

Intent = Literal[
    "order_status",
    "return_refund",
    "cancellation",
    "policy_question",
    "human_handoff",
    "greeting",
    "off_topic",
]
Sentiment = Literal["positive", "neutral", "frustrated", "angry"]


class SupportState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Intent
    sentiment: Sentiment
    blocked: bool
    remaining_steps: RemainingSteps
