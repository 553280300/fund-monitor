from decimal import Decimal

from fund_monitor.domain import Asset, AssetKind
from fund_monitor.providers.yahoo import YahooProvider


def test_yahoo_chart_normalizes_global_index() -> None:
    asset = Asset(
        id=1,
        name="S&P 500",
        kind=AssetKind.GLOBAL_INDEX,
        identifiers={"yahoo": "^GSPC"},
    )
    payload = {"chart": {"result": [{"meta": {
        "shortName": "S&P 500",
        "regularMarketPrice": 6350.0,
        "chartPreviousClose": 6300.0,
    }}]}}

    result = YahooProvider.parse(asset, payload)

    assert result.observation is not None
    assert result.observation.value == Decimal("6350.0")
    assert result.observation.change_percent == Decimal("0.79")
