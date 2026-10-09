"""Agent tool registry."""

from support_agent.tools.escalation import escalate_to_human
from support_agent.tools.knowledge import search_policies
from support_agent.tools.orders import cancel_order, lookup_order
from support_agent.tools.returns import check_return_eligibility, request_refund

ALL_TOOLS = [
    search_policies,
    lookup_order,
    check_return_eligibility,
    request_refund,
    cancel_order,
    escalate_to_human,
]

__all__ = [
    "ALL_TOOLS",
    "cancel_order",
    "check_return_eligibility",
    "escalate_to_human",
    "lookup_order",
    "request_refund",
    "search_policies",
]
