"""Shared helpers for agent tools: customer verification, serialization and result shapes."""

from datetime import datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from support_agent.db.models import Order, cents_to_decimal

# Identical message for "not found" and "wrong email" prevents order-number enumeration.
VERIFICATION_FAILED = (
    "No order matches that order number and email address. "
    "Please ask the customer to double-check both."
)


def ok(**data: Any) -> dict[str, Any]:
    return {"ok": True, **data}


def fail(error: str, **data: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, **data}


def money(cents: int) -> str:
    return f"${cents_to_decimal(cents)}"


def normalize_order_id(order_id: str) -> str:
    cleaned = order_id.strip().upper().replace(" ", "")
    return f"ORD-{cleaned}" if cleaned.isdigit() else cleaned


def thread_id_from(config: RunnableConfig | None) -> str:
    return str((config or {}).get("configurable", {}).get("thread_id", "unknown"))


def get_verified_order(session: Session, order_id: str, email: str) -> Order | None:
    """Return the order only if it exists AND belongs to the given email."""
    order = session.scalar(
        select(Order)
        .where(Order.id == normalize_order_id(order_id))
        .options(
            selectinload(Order.items),
            selectinload(Order.refunds),
            selectinload(Order.customer),
        )
    )
    if order is None or order.customer.email.lower() != email.strip().lower():
        return None
    return order


def _date(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def serialize_order(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "status": order.status.value,
        "total": money(order.total_cents),
        "placed_at": _date(order.placed_at),
        "shipped_at": _date(order.shipped_at),
        "delivered_at": _date(order.delivered_at),
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "items": [
            {
                "sku": item.sku,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "line_total": money(item.unit_price_cents * item.quantity),
                "final_sale": item.is_final_sale,
            }
            for item in order.items
        ],
        "refunds": [
            {
                "amount": money(refund.amount_cents),
                "status": refund.status.value,
                "reason": refund.reason,
                "created_at": _date(refund.created_at),
            }
            for refund in order.refunds
        ],
    }
