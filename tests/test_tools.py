"""Integration tests for agent tools against an isolated, seeded database."""

from sqlalchemy import select

from support_agent.db.models import Order, OrderStatus, Refund, RefundStatus, Ticket
from support_agent.db.session import get_session
from support_agent.tools import (
    cancel_order,
    check_return_eligibility,
    escalate_to_human,
    lookup_order,
    request_refund,
)

CONFIG = {"configurable": {"thread_id": "test-thread"}}
SARAH = "sarah.johnson@example.com"
JAMES = "james.miller@example.com"
AISHA = "aisha.khan@example.com"


def refund(order_id: str, email: str, reason: str = "no_longer_needed") -> dict:
    return request_refund.invoke(
        {"order_id": order_id, "email": email, "reason_category": reason, "reason_details": "test"},
        config=CONFIG,
    )


# --- Security -------------------------------------------------------------------------


def test_wrong_email_reveals_nothing() -> None:
    result = lookup_order.invoke({"order_id": "ORD-1001", "email": "attacker@example.com"})
    assert result["ok"] is False
    assert "order" not in result


def test_unknown_order_and_wrong_email_return_identical_errors() -> None:
    wrong_email = lookup_order.invoke({"order_id": "ORD-1001", "email": "x@example.com"})
    unknown_order = lookup_order.invoke({"order_id": "ORD-9999", "email": SARAH})
    assert wrong_email["error"] == unknown_order["error"]


def test_actions_require_verification() -> None:
    assert refund("ORD-1001", "attacker@example.com")["ok"] is False
    assert cancel_order.invoke({"order_id": "ORD-1005", "email": SARAH})["ok"] is False


# --- Lookup ---------------------------------------------------------------------------


def test_lookup_normalizes_messy_input() -> None:
    result = lookup_order.invoke({"order_id": " 1002 ", "email": "Sarah.Johnson@Example.com"})
    assert result["ok"] is True
    assert result["order"]["tracking_number"] == "1Z999AA10123456791"


def test_lookup_flags_likely_lost_package() -> None:
    result = lookup_order.invoke({"order_id": "ORD-1007", "email": "lucas.moreau@example.com"})
    assert result["likely_lost"] is True


# --- Returns & refunds ----------------------------------------------------------------


def test_mixed_order_reports_per_item_eligibility() -> None:
    result = check_return_eligibility.invoke({"order_id": "ORD-1006", "email": AISHA})
    eligibility = {item["product_name"]: item["eligible"] for item in result["items"]}
    assert eligibility == {"Clearance Jute Rug": False, "Linen Pillow Cover": True}
    assert result["eligible_items_value"] == "$39.00"


def test_small_refund_is_auto_approved_with_label_fee() -> None:
    result = refund("ORD-1001", SARAH)
    assert result["refund_status"] == "approved"
    assert result["refund_amount"] == "$54.02"

    with get_session() as session:
        stored = session.scalars(select(Refund).where(Refund.order_id == "ORD-1001")).one()
        assert stored.status == RefundStatus.APPROVED
        assert stored.amount_cents == 5402


def test_duplicate_refund_is_blocked() -> None:
    assert refund("ORD-1001", SARAH)["ok"] is True
    assert refund("ORD-1001", SARAH)["ok"] is False


def test_large_refund_goes_to_human_review_with_ticket() -> None:
    result = refund("ORD-1004", JAMES, reason="damaged_or_defective")
    assert result["refund_status"] == "pending_review"
    assert result["refund_amount"] == "$349.00"

    with get_session() as session:
        ticket = session.get(Ticket, result["ticket_id"])
        assert ticket is not None
        assert ticket.order_id == "ORD-1004"
        assert ticket.thread_id == "test-thread"


def test_refund_outside_window_is_rejected() -> None:
    assert refund("ORD-1003", JAMES)["ok"] is False


# --- Cancellation ---------------------------------------------------------------------


def test_processing_order_can_be_cancelled_with_full_refund() -> None:
    result = cancel_order.invoke({"order_id": "ORD-1005", "email": AISHA})
    assert result["ok"] is True
    assert result["refund_amount"] == "$69.00"
    with get_session() as session:
        assert session.get(Order, "ORD-1005").status == OrderStatus.CANCELLED


def test_shipped_order_cannot_be_cancelled() -> None:
    result = cancel_order.invoke({"order_id": "ORD-1002", "email": SARAH})
    assert result["ok"] is False
    with get_session() as session:
        assert session.get(Order, "ORD-1002").status == OrderStatus.SHIPPED


# --- Escalation -----------------------------------------------------------------------


def test_escalation_ignores_nonexistent_order_ids() -> None:
    result = escalate_to_human.invoke(
        {
            "summary": "Customer needs help",
            "category": "other",
            "priority": "low",
            "order_id": "ORD-9999",
        },
        config=CONFIG,
    )
    with get_session() as session:
        assert session.get(Ticket, result["ticket_id"]).order_id is None
