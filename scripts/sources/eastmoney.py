"""数据源模块 — 天天基金

天天基金 API 提供净值历史、分红公告、基金经理变更等信息。
接口基于 fund.eastmoney.com。
"""

import json
import urllib.request
from typing import Optional


def fetch_fund_history(fund_code: str, page: int = 1) -> Optional[dict]:
    """
    获取基金净值历史
    
    API: https://api.fund.eastmoney.com/f10/lsjz
    """
    url = (
        f"https://api.fund.eastmoney.com/f10/lsjz"
        f"?callback=jQuery&fundCode={fund_code}&pageIndex={page}&pageSize=20"
    )
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://fundf10.eastmoney.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            # 去掉 JSONP 包装
            json_str = raw[raw.index("(") + 1:raw.rindex(")")]
            return json.loads(json_str)
    except Exception as e:
        print(f"[WARN] 天天基金获取净值历史失败: {fund_code} - {e}")
    return None


def fetch_dividends(fund_code: str) -> Optional[list]:
    """
    获取基金分红公告
    
    API: https://api.fund.eastmoney.com/f10/fhxx
    """
    url = (
        f"https://api.fund.eastmoney.com/f10/fhxx"
        f"?callback=jQuery&fundCode={fund_code}&pageIndex=1&pageSize=10"
    )
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://fundf10.eastmoney.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            json_str = raw[raw.index("(") + 1:raw.rindex(")")]
            data = json.loads(json_str)
            return data.get("Data", [])
    except Exception as e:
        print(f"[WARN] 天天基金获取分红失败: {fund_code} - {e}")
    return None


def fetch_manager_changes(fund_code: str) -> Optional[list]:
    """
    获取基金经理变更
    
    API: https://api.fund.eastmoney.com/f10/jjjl
    """
    url = (
        f"https://api.fund.eastmoney.com/f10/jjjl"
        f"?callback=jQuery&fundCode={fund_code}&pageIndex=1&pageSize=10"
    )
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://fundf10.eastmoney.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            json_str = raw[raw.index("(") + 1:raw.rindex(")")]
            data = json.loads(json_str)
            return data.get("Data", [])
    except Exception as e:
        print(f"[WARN] 天天基金获取经理变更失败: {fund_code} - {e}")
    return None