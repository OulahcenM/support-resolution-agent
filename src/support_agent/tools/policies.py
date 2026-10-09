"""Pure business rules (no I/O, no LLM). The LLM decides WHEN to act; this code decides IF it's allowed."""

from dataclasses import dataclass
from datetime import datetime, timezone

from support_agent.db.models import Order, OrderStatus, RefundStatus

CANCELLABLE_STATUSES = frozenset({OrderStatus.PENDING, OrderStatus.PROCESSING})
ACTIVE_REFUND_STATUSES = frozenset({RefundStatus.APPROVED, RefundStatus.PENDING_REVIEW})
FEE_EXEMPT_REASONS = frozenset({"damaged_or_defective", "wrong_item"})


@dataclass(frozen=True, slots=True)
class ItemEligibility:
    sku: str
    product_name: str
    quantity: int
    amount_cents: int
    eligible: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ReturnEligibility:
    eligible: bool
    reason: str
    days_since_delivery: int | None
    days_left: int | None
    items: tuple[ItemEligibility, ...]

    @property
    def eligible_amount_cents(self) -> int:
        return sum(item.amount_cents for item in self.items if item.eligible)


def has_active_refund(order: Order) -> bool:
    return any(refund.status in ACTIVE_REFUND_STATUSES for refund in order.refunds)


def evaluate_return_eligibility(
    order: Order, return_window_days: int, now: datetime | None = None
) -> ReturnEligibility:
    now = now or datetime.now(timezone.utc)

    if has_active_refund(order):
        return ReturnEligibility(
            False, "A refund already exists for this order.", None, None, ()
        )

    if order.status != OrderStatus.DELIVERED or order.delivered_at is None:
        return ReturnEligibility(
            False,
            f"Order status is '{order.status.value}'. Returns are only possible after delivery.",
            None,
            None,
            (),
        )

    days_since = (now - order.delivered_at).days
    if days_since > return_window_days:
        return ReturnEligibility(
            False,
            f"Delivered {days_since} days ago; the return window is {return_window_days} days.",
            days_since,
            0,
            (),
        )

    items = tuple(
        ItemEligibility(
            sku=item.sku,
            product_name=item.product_name,
            quantity=item.quantity,
            amount_cents=item.unit_price_cents * item.quantity,
            eligible=not item.is_final_sale,
            reason="Final Sale items are not returnable."
            if item.is_final_sale
            else "Eligible.",
        )
        for item in order.items
    )
    any_eligible = any(item.eligible for item in items)
    return ReturnEligibility(
        eligible=any_eligible,
        reason="Eligible for return."
        if any_eligible
        else "All items in this order are Final Sale.",
        days_since_delivery=days_since,
        days_left=return_window_days - days_since,
        items=items,
    )


def compute_refund_cents(
    eligible_cents: int, reason_category: str, label_fee_cents: int
) -> int:
    """Return-label fee is waived for damaged/defective or wrong items."""
    if reason_category in FEE_EXEMPT_REASONS:
        return eligible_cents
    return max(eligible_cents - label_fee_cents, 0)


def is_likely_lost(
    order: Order, threshold_days: int, now: datetime | None = None
) -> bool:
    now = now or datetime.now(timezone.utc)
    return (
        order.status == OrderStatus.SHIPPED
        and order.shipped_at is not None
        and (now - order.shipped_at).days >= threshold_days
    )
