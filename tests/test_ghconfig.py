"""GitHub Actions config generation from local asset/rule state."""

from pathlib import Path

import yaml

from fund_monitor.domain import AlertKind, AlertRule, Asset, AssetKind
from fund_monitor.storage import initialize_database
from fund_monitor.ghconfig import build_config


def _database(tmp_path: Path):
    return initialize_database(tmp_path / "state.db")


def test_config_lists_assets_with_tencent_tickers(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.assets.create(
        Asset(name="科创50", kind=AssetKind.CN_INDEX, identifiers={"tencent": "sh000688"})
    )
    database.assets.create(
        Asset(name="银华科创100联接C", kind=AssetKind.FUND, identifiers={"eastmoney": "019860", "tencent": "jj019860"})
    )

    config = yaml.safe_load(build_config(database))

    codes = [asset["code"] for asset in config["assets"]]
    assert codes == ["sh000688", "jj019860"]
    assert config["timezone"] == "Asia/Shanghai"
    assert "serverchan" in config["channels"]
    assert "pushplus" in config["channels"]
    database.close()


def test_config_includes_first_numeric_threshold(tmp_path: Path) -> None:
    database = _database(tmp_path)
    asset = database.assets.create(
        Asset(name="沪深300", kind=AssetKind.CN_INDEX, identifiers={"tencent": "sh000300"})
    )
    database.rules.create(
        AlertRule(asset_id=asset.id or 0, kind=AlertKind.PERCENT_CHANGE, threshold="-1.0", cooldown_minutes=30)
    )

    config = yaml.safe_load(build_config(database))

    assert config["assets"][0]["threshold"] == -1.0
    database.close()


def test_config_skips_assets_without_monitorable_identifier(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.assets.create(
        Asset(name="无标识资产", kind=AssetKind.FUND, identifiers={"somewhere": "x"})
    )

    config = yaml.safe_load(build_config(database))

    assert config["assets"] == []
    database.close()


def test_fund_with_only_eastmoney_code_gets_jj_ticker(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.assets.create(
        Asset(name="场外基金", kind=AssetKind.FUND, identifiers={"eastmoney": "005827"})
    )

    config = yaml.safe_load(build_config(database))

    assert config["assets"][0]["code"] == "jj005827"
    database.close()
