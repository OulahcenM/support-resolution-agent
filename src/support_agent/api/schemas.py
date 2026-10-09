"""Request and response models for the public API."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

ThreadId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
UserMessage = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: ThreadId | None = None


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    intent: str | None
    sentiment: str | None
    tools_used: list[str]


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[HistoryMessage]


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: str
    customer_email: str | None
    order_id: str | None
    category: str
    priority: str
    status: str
    summary: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model: str
