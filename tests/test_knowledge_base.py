"""Guards against drift between business rules in code and the published policies."""

from support_agent.config import get_settings


def _doc(name: str) -> str:
    return (get_settings().knowledge_base_dir / name).read_text(encoding="utf-8")


def test_return_rules_match_config() -> None:
    settings = get_settings()
    text = _doc("returns_and_refunds.md")
    assert f"within {settings.return_window_days} days of delivery" in text
    assert f"${settings.auto_refund_limit:.0f}" in text
    assert f"${settings.return_label_fee}" in text


def test_lost_package_threshold_matches_config() -> None:
    days = get_settings().lost_package_threshold_days
    assert f"within {days} days of shipping" in _doc("shipping_policy.md")
