"""数据源模块 — 腾讯财经

腾讯财经 API web.sqt.gtimg.cn 提供实时指数和基金估值数据。

指数格式: v_sh000698="1~名称~代码~当前价~昨收~今开~..."
  字段: [3]=当前价, [4]=昨收, [5]=今开, [30]=日期, [31]=时间

基金格式: v_jj008764="代码~名称~...~单位净值~累计净值~估算涨幅~..."
  字段: [5]=单位净值, [6]=累计净值, [7]=估算涨幅(%)
"""

import re
import subprocess
import sys
from typing import Optional


def safe_curl(url: str, timeout: int = 15) -> str:
    """执行 curl 并处理编码"""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            raw = result.stdout
            try:
                return raw.decode("gbk", errors="replace").strip()
            except Exception:
                return raw.decode("utf-8", errors="replace").strip()
    except Exception as e:
        print(f"[WARN] curl {url} 失败: {e}", file=sys.stderr)
    return ""


def parse_index(raw_line: str) -> Optional[dict]:
    """解析腾讯指数数据"""
    match = re.search(r'="(.+)"', raw_line)
    if not match:
        return None
    fields = match.group(1).split("~")
    if len(fields) < 32:
        return None
    current = float(fields[3]) if fields[3] else 0
    prev_close = float(fields[4]) if fields[4] else 0
    if prev_close <= 0:
        return None
    change_pct = round(((current - prev_close) / prev_close) * 100, 2)
    return {
        "name": fields[1],
        "code": fields[2],
        "current": current,
        "prev_close": prev_close,
        "open": float(fields[5]) if fields[5] else 0,
        "change_pct": change_pct,
        "date": fields[30],
        "time": fields[31],
    }


def parse_fund(raw_line: str) -> Optional[dict]:
    """解析腾讯基金数据"""
    match = re.search(r'="(.+)"', raw_line)
    if not match:
        return None
    fields = match.group(1).split("~")
    if len(fields) < 8:
        return None
    szrate = fields[7]
    if szrate and szrate != "-":
        change_pct = round(float(szrate), 2)
    else:
        change_pct = 0.0
    dwjz = float(fields[5]) if fields[5] and fields[5] != "-" else 0
    ljjz = float(fields[6]) if fields[6] and fields[6] != "-" else 0
    return {
        "fund_code": fields[0],
        "name": fields[1],
        "dwjz": dwjz,
        "ljjz": ljjz,
        "szrate": change_pct,
    }


def fetch(tickers: list[str]) -> dict[str, dict]:
    """
    批量获取腾讯财经数据（指数 + 基金）
    
    Args:
        tickers: ticker 列表，如 ["sh000698", "jj018147"]
    
    Returns:
        {ticker_key: parsed_data}
    """
    if not tickers:
        return {}
    ticker_str = ",".join(tickers)
    url = f"https://web.sqt.gtimg.cn/q={ticker_str}"
    raw = safe_curl(url)
    if not raw:
        return {}
    
    results = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        match = re.match(r'v_(\w+)="', line)
        if not match:
            continue
        ticker_key = match.group(1)
        if ticker_key.startswith("jj"):
            data = parse_fund(line)
        else:
            data = parse_index(line)
        if data:
            results[ticker_key] = data
    return results