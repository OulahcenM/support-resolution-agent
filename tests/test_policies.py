"""Unit tests for pure business rules."""

from datetime import UTC, datetime, timedelta

import pytest

from support_agent.db.models import Order, OrderItem, OrderStatus, Refund, RefundStatus
from support_agent.tools.policies import (
    compute_refund_cents,
    evaluate_return_eligibility,
    is_likely_lost,
)

NOW = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)
WINDOW = 30


def make_order(
    status: OrderStatus = OrderStatus.DELIVERED,
    delivered_days_ago: int | None = 5,
    shipped_days_ago: int | None = 8,
    items: list[OrderItem] | None = None,
    refunds: list[Refund] | None = None,
) -> Order:
    order = Order(
        id="ORD-TEST",
        status=status,
        total_cents=0,
        shipped_at=NOW - timedelta(days=shipped_days_ago) if shipped_days_ago is not None else None,
        delivered_at=(
            NOW - timedelta(days=delivered_days_ago) if delivered_days_ago is not None else None
        ),
    )
    order.items = items or [
        OrderItem(sku="MUG", product_name="Mug", quantity=2, unit_price_cents=1500)
    ]
    order.refunds = refunds or []
    return order


def test_delivered_order_within_window_is_eligible() -> None:
    result = evaluate_return_eligibility(make_order(), WINDOW, now=NOW)
    assert result.eligible
    assert result.eligible_amount_cents == 3000
    assert result.days_left == 25


def test_last_day_of_window_is_still_eligible() -> None:
    result = evaluate_return_eligibility(make_order(delivered_days_ago=WINDOW), WINDOW, now=NOW)
    assert result.eligible


def test_order_outside_window_is_not_eligible() -> None:
    result = evaluate_return_eligibility(make_order(delivered_days_ago=WINDOW + 1), WINDOW, now=NOW)
    assert not result.eligible
    assert result.eligible_amount_cents == 0


@pytest.mark.parametrize("status", [OrderStatus.PROCESSING, OrderStatus.SHIPPED])
def test_undelivered_order_is_not_eligible(status: OrderStatus) -> None:
    order = make_order(status=status, delivered_days_ago=None)
    assert not evaluate_return_eligibility(order, WINDOW, now=NOW).eligible


def test_final_sale_items_are_excluded_from_refund() -> None:
    order = make_order(
        items=[
            OrderItem(
                sku="RUG", product_name="Rug", quantity=1, unit_price_cents=4500, is_final_sale=True
            ),
            OrderItem(sku="PIL", product_name="Pillow", quantity=2, unit_price_cents=1950),
        ]
    )
    result = evaluate_return_eligibility(order, WINDOW, now=NOW)
    assert result.eligible
    assert result.eligible_amount_cents == 3900


def test_order_with_only_final_sale_items_is_not_eligible() -> None:
    order = make_order(
        items=[
            OrderItem(
                sku="RUG", product_name="Rug", quantity=1, unit_price_cents=4500, is_final_sale=True
            )
        ]
    )
    assert not evaluate_return_eligibility(order, WINDOW, now=NOW).eligible


@pytest.mark.parametrize("refund_status", [RefundStatus.APPROVED, RefundStatus.PENDING_REVIEW])
def test_existing_refund_blocks_new_return(refund_status: RefundStatus) -> None:
    order = make_order(refunds=[Refund(amount_cents=1000, reason="test", status=refund_status)])
    assert not evaluate_return_eligibility(order, WINDOW, now=NOW).eligible


def test_rejected_refund_does_not_block_new_return() -> None:
    order = make_order(
        refunds=[Refund(amount_cents=1000, reason="test", status=RefundStatus.REJECTED)]
    )
    assert evaluate_return_eligibility(order, WINDOW, now=NOW).eligible


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("no_longer_needed", 5402),
        ("other", 5402),
        ("damaged_or_defective", 5997),
        ("wrong_item", 5997),
    ],
)
def test_return_label_fee_is_waived_only_for_seller_faults(reason: str, expected: int) -> None:
    assert compute_refund_cents(5997, reason, label_fee_cents=595) == expected


def test_refund_never_goes_negative() -> None:
    assert compute_refund_cents(300, "no_longer_needed", label_fee_cents=595) == 0


@pytest.mark.parametrize(
    ("status", "shipped_days_ago", "expected"),
    [
        (OrderStatus.SHIPPED, 14, True),
        (OrderStatus.SHIPPED, 10, True),
        (OrderStatus.SHIPPED, 9, False),
        (OrderStatus.DELIVERED, 30, False),
    ],
)
def test_likely_lost_detection(status: OrderStatus, shipped_days_ago: int, expected: bool) -> None:
    order = make_order(status=status, shipped_days_ago=shipped_days_ago, delivered_days_ago=None)
    assert is_likely_lost(order, threshold_days=10, now=NOW) is expected
