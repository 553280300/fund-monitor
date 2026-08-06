import pytest
from pydantic import ValidationError

from fund_monitor.domain import AlertKind, AlertRule, Asset, AssetKind


def test_asset_requires_a_provider_identifier() -> None:
    with pytest.raises(ValidationError):
        Asset(name="Test fund", kind=AssetKind.FUND, identifiers={})


def test_threshold_rule_rejects_zero_cooldown() -> None:
    with pytest.raises(ValidationError):
        AlertRule(
            asset_id=1,
            kind=AlertKind.PERCENT_CHANGE,
            threshold=1.0,
            cooldown_minutes=0,
        )
