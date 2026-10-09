"""Reset and seed the demo store with deterministic support scenarios.

Run with:  uv run python -m support_agent.db.seed
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from support_agent.db.models import (
    Base,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    Refund,
    RefundStatus,
)
from support_agent.db.session import get_engine, get_session


def _days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _to_cents(price: str) -> int:
    return int(Decimal(price) * 100)


def _item(
    sku: str, name: str, qty: int, price: str, final_sale: bool = False
) -> OrderItem:
    return OrderItem(
        sku=sku,
        product_name=name,
        quantity=qty,
        unit_price_cents=_to_cents(price),
        is_final_sale=final_sale,
    )


def _order(
    order_id: str,
    status: OrderStatus,
    items: list[OrderItem],
    placed: int,
    shipped: int | None = None,
    delivered: int | None = None,
    carrier: str | None = None,
    tracking: str | None = None,
) -> Order:
    return Order(
        id=order_id,
        status=status,
        items=items,
        total_cents=sum(i.unit_price_cents * i.quantity for i in items),
        placed_at=_days_ago(placed),
        shipped_at=_days_ago(shipped) if shipped is not None else None,
        delivered_at=_days_ago(delivered) if delivered is not None else None,
        carrier=carrier,
        tracking_number=tracking,
    )


def build_customers() -> list[Customer]:
    sarah = Customer(name="Sarah Johnson", email="sarah.johnson@example.com")
    sarah.orders = [
        # Scenario: eligible return under the auto-refund limit
        _order(
            "ORD-1001",
            OrderStatus.DELIVERED,
            [
                _item("LC-MUG-01", "Ceramic Coffee Mug Set", 2, "14.99"),
                _item("LC-CND-03", "Soy Candle Trio", 1, "29.99"),
            ],
            placed=9,
            shipped=8,
            delivered=5,
            carrier="UPS",
            tracking="1Z999AA10123456784",
        ),
        # Scenario: "Where is my order?" — in transit
        _order(
            "ORD-1002",
            OrderStatus.SHIPPED,
            [_item("LC-LMP-02", "Linen Table Lamp", 1, "89.00")],
            placed=4,
            shipped=2,
            carrier="UPS",
            tracking="1Z999AA10123456791",
        ),
    ]

    james = Customer(name="James Miller", email="james.miller@example.com")
    james.orders = [
        # Scenario: return requested outside the 30-day window
        _order(
            "ORD-1003",
            OrderStatus.DELIVERED,
            [_item("LC-THR-01", "Wool Throw Blanket", 1, "79.00")],
            placed=52,
            shipped=50,
            delivered=45,
            carrier="FedEx",
            tracking="781234567890",
        ),
        # Scenario: refund above auto-refund limit -> human review
        _order(
            "ORD-1004",
            OrderStatus.DELIVERED,
            [_item("LC-CHR-05", "Oak Accent Chair", 1, "349.00")],
            placed=15,
            shipped=13,
            delivered=10,
            carrier="FedEx",
            tracking="781234567891",
        ),
    ]

    aisha = Customer(name="Aisha Khan", email="aisha.khan@example.com")
    aisha.orders = [
        # Scenario: cancellation still possible
        _order(
            "ORD-1005",
            OrderStatus.PROCESSING,
            [_item("LC-VSE-04", "Stoneware Vase", 2, "34.50")],
            placed=0,
        ),
        # Scenario: mixed order — final-sale item is not returnable
        _order(
            "ORD-1006",
            OrderStatus.DELIVERED,
            [
                _item("LC-RUG-CLR", "Clearance Jute Rug", 1, "45.00", final_sale=True),
                _item("LC-PIL-02", "Linen Pillow Cover", 2, "19.50"),
            ],
            placed=12,
            shipped=10,
            delivered=7,
            carrier="USPS",
            tracking="9400111899223344556677",
        ),
    ]

    lucas = Customer(name="Lucas Moreau", email="lucas.moreau@example.com")
    lucas.orders = [
        # Scenario: likely lost package -> escalation
        _order(
            "ORD-1007",
            OrderStatus.SHIPPED,
            [_item("LC-MIR-01", "Round Brass Mirror", 1, "120.00")],
            placed=16,
            shipped=14,
            carrier="DHL",
            tracking="JD014600006281234567",
        ),
        # Scenario: "Where is my refund?"
        _order(
            "ORD-1008",
            OrderStatus.RETURNED,
            [_item("LC-FRM-01", "Walnut Photo Frame", 2, "24.50")],
            placed=27,
            shipped=25,
            delivered=20,
            carrier="USPS",
            tracking="9400111899223344556699",
        ),
    ]
    lucas.orders[1].refunds = [
        Refund(
            amount_cents=_to_cents("49.00"),
            reason="Item arrived damaged",
            status=RefundStatus.APPROVED,
            created_at=_days_ago(3),
        ),
    ]

    return [sarah, james, aisha, lucas]


def seed() -> None:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    customers = build_customers()
    with get_session() as session:
        session.add_all(customers)

    order_count = sum(len(c.orders) for c in customers)
    print(
        f"Seeded {len(customers)} customers and {order_count} orders into {engine.url}"
    )


if __name__ == "__main__":
    seed()
