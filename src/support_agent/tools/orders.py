"""Order lookup and cancellation tools."""

from typing import Any

from langchain_core.tools import tool

from support_agent.config import get_settings
from support_agent.db.models import OrderStatus, Refund, RefundStatus
from support_agent.db.session import get_session
from support_agent.tools._common import (
    VERIFICATION_FAILED,
    fail,
    get_verified_order,
    money,
    ok,
    serialize_order,
)
from support_agent.tools.policies import CANCELLABLE_STATUSES, is_likely_lost


@tool
def lookup_order(order_id: str, email: str) -> dict[str, Any]:
    """Look up an order's status, items, shipping/tracking details and existing refunds.

    Requires BOTH the order number (e.g. ORD-1001) and the email used at checkout.
    Use for: "where is my order", tracking, delivery dates, order contents, refund status.
    If the result has likely_lost=true, offer to escalate to a human for an investigation.
    """
    settings = get_settings()
    with get_session() as session:
        order = get_verified_order(session, order_id, email)
        if order is None:
            return fail(VERIFICATION_FAILED)
        return ok(
            order=serialize_order(order),
            likely_lost=is_likely_lost(order, settings.lost_package_threshold_days),
        )


@tool
def cancel_order(order_id: str, email: str) -> dict[str, Any]:
    """Cancel an order that has NOT shipped yet (status pending or processing) and refund it in full.

    Only call this AFTER the customer has explicitly confirmed they want to cancel.
    Requires BOTH the order number and the email used at checkout.
    """
    with get_session() as session:
        order = get_verified_order(session, order_id, email)
        if order is None:
            return fail(VERIFICATION_FAILED)

        if order.status not in CANCELLABLE_STATUSES:
            return fail(
                f"Order {order.id} is '{order.status.value}' and can no longer be cancelled. "
                "If it has shipped, the customer can request a return after delivery.",
                status=order.status.value,
            )

        order.status = OrderStatus.CANCELLED
        order.refunds.append(
            Refund(
                amount_cents=order.total_cents,
                reason="Order cancelled by customer before shipping",
                status=RefundStatus.APPROVED,
            )
        )
        return ok(
            order_id=order.id,
            status=OrderStatus.CANCELLED.value,
            refund_amount=money(order.total_cents),
            refund_timing="5-10 business days to the original payment method",
        )
