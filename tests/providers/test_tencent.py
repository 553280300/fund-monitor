from decimal import Decimal

from fund_monitor.domain import Asset, AssetKind
from fund_monitor.providers.tencent import TencentProvider


def test_tencent_fund_line_normalizes_estimated_change() -> None:
    asset = Asset(
        id=1,
        name="Example fund",
        kind=AssetKind.FUND,
        identifiers={"tencent": "jj019860"},
    )
    raw = 'v_jj019860="019860~Example fund~~~1.2345~1.2000~-1.28";'

    result = TencentProvider.parse(asset, raw)

    assert result.source == "tencent"
    assert result.observation is not None
    assert result.observation.value == Decimal("1.2345")
    assert result.observation.change_percent == Decimal("-1.28")
    assert result.observation.confirmed is False


def test_tencent_etf_line_uses_stock_layout() -> None:
    asset = Asset(
        id=2,
        name="沪深300ETF",
        kind=AssetKind.ETF,
        identifiers={"tencent": "sh510300"},
    )
    # Real stock layout: name[1], price[3], prev close[4], change percent[32].
    raw = 'v_sh510300="1~沪深300ETF华泰柏瑞~510300~4.709~4.714~4.688~8783560~3833885~4949675~4.708~4645~4.707~3655~4.706~4043~4.705~5290~4.704~4434~4.709~6888~4.710~22861~4.711~5733~4.712~5710~4.713~5229~0~20260806160452~-0.005~-0.11~4.731~4.668";'

    result = TencentProvider.parse(asset, raw)

    assert result.observation is not None
    assert result.observation.value == Decimal("4.709")
    assert result.observation.change_percent == Decimal("-0.11")
    assert result.observation.confirmed is False
