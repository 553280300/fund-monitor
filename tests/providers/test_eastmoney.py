from decimal import Decimal

from fund_monitor.domain import Asset, AssetKind
from fund_monitor.providers.eastmoney import EastmoneyProvider


def test_eastmoney_history_normalizes_latest_confirmed_nav() -> None:
    asset = Asset(
        id=1,
        name="Example fund",
        kind=AssetKind.FUND,
        identifiers={"eastmoney": "019860"},
    )
    payload = {
        "Data": {
            "LSJZList": [
                {"FSRQ": "2026-08-05", "DWJZ": "1.2350", "JZZZL": "0.42"}
            ]
        }
    }

    result = EastmoneyProvider.parse_history(asset, payload)

    assert result.observation is not None
    assert result.observation.value == Decimal("1.2350")
    assert result.observation.change_percent == Decimal("0.42")
    assert result.observation.confirmed is True
