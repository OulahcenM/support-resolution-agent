"""Return eligibility and refund tools."""

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from support_agent.config import get_settings
from support_agent.db.models import Refund, RefundStatus, Ticket, TicketPriority
from support_agent.db.session import get_session
from support_agent.tools._common import (
    VERIFICATION_FAILED,
    fail,
    get_verified_order,
    money,
    ok,
    thread_id_from,
)
from support_agent.tools.policies import (
    compute_refund_cents,
    evaluate_return_eligibility,
)

ReasonCategory = Literal["damaged_or_defective", "wrong_item", "no_longer_needed", "other"]


def _to_cents(value: object) -> int:
    return int(round(float(str(value)) * 100))


@tool
def check_return_eligibility(order_id: str, email: str) -> dict[str, Any]:
    """Check whether an order (and which of its items) can be returned, and the maximum refund.

    Call this BEFORE request_refund, and explain the result to the customer.
    Requires BOTH the order number and the email used at checkout.
    """
    settings = get_settings()
    with get_session() as session:
        order = get_verified_order(session, order_id, email)
        if order is None:
            return fail(VERIFICATION_FAILED)

        result = evaluate_return_eligibility(order, settings.return_window_days)
        return ok(
            order_id=order.id,
            eligible=result.eligible,
            reason=result.reason,
            days_left_to_return=result.days_left,
            items=[
                {
                    "product_name": i.product_name,
                    "eligible": i.eligible,
                    "reason": i.reason,
                    "amount": money(i.amount_cents),
                }
                for i in result.items
            ],
            eligible_items_value=money(result.eligible_amount_cents),
            note=f"A {money(_to_cents(settings.return_label_fee))} return-label fee is deducted "
            "unless the item is damaged, defective or the wrong item.",
        )


@tool
def request_refund(
    order_id: str,
    email: str,
    reason_category: ReasonCategory,
    reason_details: str,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Submit a return and refund for ALL eligible items of a delivered order.

    Only call AFTER check_return_eligibility returned eligible=true AND the customer confirmed.
    Refunds up to the auto-approval limit are approved instantly; larger refunds are sent
    to a human for review and a ticket is created automatically.
    """
    settings = get_settings()
    with get_session() as session:
        order = get_verified_order(session, order_id, email)
        if order is None:
            return fail(VERIFICATION_FAILED)

        eligibility = evaluate_return_eligibility(order, settings.return_window_days)
        if not eligibility.eligible:
            return fail(eligibility.reason)

        refund_cents = compute_refund_cents(
            eligibility.eligible_amount_cents,
            reason_category,
            _to_cents(settings.return_label_fee),
        )
        within_limit = refund_cents <= _to_cents(settings.auto_refund_limit)
        reason = f"[{reason_category}] {reason_details}".strip()

        order.refunds.append(
            Refund(
                amount_cents=refund_cents,
                reason=reason,
                status=RefundStatus.APPROVED if within_limit else RefundStatus.PENDING_REVIEW,
            )
        )

        if within_limit:
            return ok(
                order_id=order.id,
                refund_status=RefundStatus.APPROVED.value,
                refund_amount=money(refund_cents),
                next_steps="A prepaid return label has been emailed. The refund reaches the "
                "original payment method within 5-10 business days.",
            )

        ticket = Ticket(
            thread_id=thread_id_from(config),
            customer_email=order.customer.email,
            order_id=order.id,
            category="refund_review",
            priority=TicketPriority.MEDIUM,
            summary=f"Refund of {money(refund_cents)} for {order.id} exceeds the auto-approval "
            f"limit. Customer reason: {reason}",
        )
        session.add(ticket)
        session.flush()  # assigns ticket.id
        return ok(
            order_id=order.id,
            refund_status=RefundStatus.PENDING_REVIEW.value,
            refund_amount=money(refund_cents),
            ticket_id=ticket.id,
            next_steps="A team member will review this refund within 2 business days "
            "and reply by email.",
        )
