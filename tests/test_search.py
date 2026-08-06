"""Asset search candidate normalization."""

from fund_monitor.domain import AssetKind
from fund_monitor.providers.search import EastmoneySearchProvider


def test_fund_search_item_is_classified_as_fund() -> None:
    candidate = EastmoneySearchProvider._candidate(
        {"Code": "019860", "Name": "银华上证科创板100ETF联接C", "SecurityTypeName": "基金", "MktNum": 150}
    )

    assert candidate is not None
    assert candidate.code == "019860"
    assert candidate.kind == AssetKind.FUND
    assert candidate.to_identifiers() == {"eastmoney": "019860", "tencent": "jj019860"}


def test_index_item_is_classified_with_shanghai_prefix() -> None:
    candidate = EastmoneySearchProvider._candidate(
        {"Code": "000688", "Name": "科创50", "SecurityTypeName": "指数", "MktNum": 1}
    )

    assert candidate is not None
    assert candidate.kind == AssetKind.CN_INDEX
    assert candidate.market == "sh"
    assert candidate.to_identifiers() == {"tencent": "sh000688"}


def test_shenzhen_index_gets_sz_prefix() -> None:
    candidate = EastmoneySearchProvider._candidate(
        {"Code": "399006", "Name": "创业板指", "SecurityTypeName": "指数", "MktNum": 0}
    )

    assert candidate is not None
    assert candidate.market == "sz"
    assert candidate.to_identifiers() == {"tencent": "sz399006"}


def test_etf_item_is_classified_as_etf() -> None:
    candidate = EastmoneySearchProvider._candidate(
        {"Code": "588030", "Name": "科创100ETF博时", "SecurityTypeName": "基金", "MktNum": 1}
    )

    assert candidate is not None
    assert candidate.kind == AssetKind.ETF
    assert candidate.to_identifiers() == {"eastmoney": "588030", "tencent": "sh588030"}


def test_etf_on_shenzhen_gets_sz_prefix() -> None:
    candidate = EastmoneySearchProvider._candidate(
        {"Code": "159915", "Name": "创业板ETF易方达", "SecurityTypeName": "基金", "MktNum": 0}
    )

    assert candidate is not None
    assert candidate.to_identifiers() == {"eastmoney": "159915", "tencent": "sz159915"}


def test_candidate_exposes_prefix_hints() -> None:
    candidate = EastmoneySearchProvider._candidate(
        {"Code": "588900", "Name": "科创100ETF南方", "SecurityTypeName": "基金", "MktNum": 1}
    )

    assert candidate is not None
    assert "sh588900（场内）" in candidate.ticker_hints
    assert "jj588900（场外）" in candidate.ticker_hints


def test_prefixed_query_is_normalized() -> None:
    assert EastmoneySearchProvider.normalize_query("sh588900") == "588900"
    assert EastmoneySearchProvider.normalize_query("jj019860") == "019860"
    assert EastmoneySearchProvider.normalize_query("sz399006") == "399006"
    assert EastmoneySearchProvider.normalize_query("科创50") == "科创50"


def test_stock_items_are_filtered_out() -> None:
    assert EastmoneySearchProvider._candidate(
        {"Code": "600519", "Name": "贵州茅台", "SecurityTypeName": "沪A", "MktNum": 1}
    ) is None
    assert EastmoneySearchProvider._candidate(
        {"Code": "000001", "Name": "平安银行", "SecurityTypeName": "深A", "MktNum": 0}
    ) is None


def test_missing_fields_are_rejected() -> None:
    assert EastmoneySearchProvider._candidate({}) is None
    assert EastmoneySearchProvider._candidate({"Code": "", "Name": "x", "SecurityTypeName": "基金"}) is None
