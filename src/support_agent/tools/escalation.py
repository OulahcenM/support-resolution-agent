"""Human escalation tool."""

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from support_agent.db.models import Order, Ticket, TicketPriority
from support_agent.db.session import get_session
from support_agent.tools._common import normalize_order_id, ok, thread_id_from

Category = Literal[
    "lost_package",
    "billing_dispute",
    "complaint",
    "damaged_item",
    "technical_issue",
    "human_requested",
    "other",
]
Priority = Literal["low", "medium", "high", "urgent"]


@tool
def escalate_to_human(
    summary: str,
    category: Category,
    priority: Priority,
    config: RunnableConfig,
    customer_email: str | None = None,
    order_id: str | None = None,
) -> dict[str, Any]:
    """Hand the conversation over to a human support agent by opening a ticket.

    Use when: the customer asks for a human; a package is likely lost; there is a billing
    dispute or unrecognized charge; the customer is very upset; or the request is outside
    your tools and policies. Write the summary so a human can act WITHOUT reading the chat:
    who, which order, what happened, what was already tried, what the customer wants.
    """
    with get_session() as session:
        linked_order_id = None
        if order_id and session.get(Order, normalize_order_id(order_id)) is not None:
            linked_order_id = normalize_order_id(order_id)

        ticket = Ticket(
            thread_id=thread_id_from(config),
            customer_email=customer_email,
            order_id=linked_order_id,
            category=category,
            priority=TicketPriority(priority),
            summary=summary,
        )
        session.add(ticket)
        session.flush()
        return ok(
            ticket_id=ticket.id,
            priority=priority,
            expected_response="Within 1 business day (Mon-Fri, 9 AM-6 PM EST), by email.",
        )
