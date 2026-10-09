"""Manual smoke test for the agent tools. Re-run the seed afterwards to reset the data."""

from pprint import pprint

from support_agent.tools import (
    cancel_order,
    check_return_eligibility,
    escalate_to_human,
    lookup_order,
    request_refund,
)

CONFIG = {"configurable": {"thread_id": "smoke-test"}}
REFUND_1001 = {
    "order_id": "ORD-1001",
    "email": "sarah.johnson@example.com",
    "reason_category": "no_longer_needed",
    "reason_details": "Changed my mind",
}

CASES = [
    (
        "Wrong email is rejected",
        lookup_order,
        {"order_id": "ORD-1001", "email": "attacker@example.com"},
    ),
    (
        "Lookup in-transit order (messy input)",
        lookup_order,
        {"order_id": " 1002 ", "email": "Sarah.Johnson@Example.com"},
    ),
    (
        "Outside return window",
        check_return_eligibility,
        {"order_id": "ORD-1003", "email": "james.miller@example.com"},
    ),
    (
        "Mixed order with Final Sale item",
        check_return_eligibility,
        {"order_id": "ORD-1006", "email": "aisha.khan@example.com"},
    ),
    ("Auto-approved refund", request_refund, REFUND_1001),
    ("Duplicate refund is blocked", request_refund, REFUND_1001),
    (
        "Large refund goes to human review",
        request_refund,
        {
            "order_id": "ORD-1004",
            "email": "james.miller@example.com",
            "reason_category": "damaged_or_defective",
            "reason_details": "Chair leg is cracked",
        },
    ),
    (
        "Cancel a processing order",
        cancel_order,
        {"order_id": "ORD-1005", "email": "aisha.khan@example.com"},
    ),
    (
        "Cannot cancel a shipped order",
        cancel_order,
        {"order_id": "ORD-1002", "email": "sarah.johnson@example.com"},
    ),
    (
        "Lost package flagged",
        lookup_order,
        {"order_id": "ORD-1007", "email": "lucas.moreau@example.com"},
    ),
    (
        "Escalate to human",
        escalate_to_human,
        {
            "summary": "ORD-1007 shipped 14 days ago with no delivery. Customer wants a replacement.",
            "category": "lost_package",
            "priority": "high",
            "customer_email": "lucas.moreau@example.com",
            "order_id": "ORD-1007",
        },
    ),
]

for title, tool_fn, args in CASES:
    print(f"\n=== {title} ===")
    pprint(tool_fn.invoke(args, config=CONFIG), sort_dicts=False)
