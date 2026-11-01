# -*- coding: utf-8 -*-
"""场外基金数据源（天天基金，需联网）：开放式基金历史净值，净值日线。

- 标的：6 位基金代码，如 110022（易方达消费行业）、005827（易方达蓝筹精选）
- 注意：本源的 000001 是华夏成长混合基金，与 A股源的平安银行无关（各自数据源独立解释代码）
- 用累计净值（Data_ACWorthTrend）构建 K 线，自动处理分红（等价于前复权）
- 场内 ETF/LOF 请直接用 A股源（代码 51x/15x/16x）
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://fund.eastmoney.com/",
}


def _get_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"天天基金请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"天天基金网络不可用（{type(e).__name__}）") from e


class FundSource(DataSource):
    id = "fund"
    label = "场外基金（天天基金，需联网，净值日线）"
    requires_network = True
    intervals = ["1d"]

    def default_symbols(self):
        return ["110022", "005827", "161725", "000001"]

    @staticmethod
    def resolve(symbol: str):
        s = symbol.strip()
        if not s.isdigit() or len(s) != 6:
            raise ValueError(f"基金代码应为 6 位数字，如 110022，当前输入：{symbol}")
        return s

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        code = self.resolve(symbol)
        if interval != "1d":
            raise ValueError("场外基金只有每日净值，请选择周期 1d（场内 ETF 请用 A股源）")
        text = _get_text(f"https://fund.eastmoney.com/pingzhongdata/{code}.js")
        if "fS_name" not in text:
            raise ValueError(f"未获取到基金 {code} 的数据，请确认代码（如 110022）")
        name = re.search(r'var fS_name\s*=\s*"([^"]*)"', text)
        m = re.search(r"Data_ACWorthTrend\s*=\s*(\[.*?\]);", text, re.S)
        if not m:
            m = re.search(r"Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.S)
        if not m:
            raise ValueError(f"基金 {code} 无净值数据")
        arr = json.loads(m.group(1))
        rows = []
        for it in arr:
            if isinstance(it, (list, tuple)):
                # Data_ACWorthTrend: [毫秒时间戳, 累计净值]
                x, y = it[0], it[1] if len(it) > 1 else None
            else:
                # Data_netWorthTrend: {"x": 毫秒时间戳, "y": 单位净值, ...}
                x, y = it.get("x"), it.get("y")
                if isinstance(y, list):
                    y = y[0] if y else None
            if x is None or y is None:
                continue
            date = time.strftime("%Y-%m-%d", time.localtime(float(x) / 1000))
            rows.append({"date": date, "open": y, "high": y, "low": y, "close": y, "volume": 0.0})
        if not rows:
            raise ValueError(f"基金 {code} 无净值数据")
        df = pd.DataFrame(rows)
        df = df.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_name(self, symbol: str):
        """基金名称（pingzhongdata 的 fS_name）。"""
        try:
            code = self.resolve(symbol)
            text = _get_text(f"https://fund.eastmoney.com/pingzhongdata/{code}.js", timeout=8)
            m = re.search(r'var fS_name\s*=\s*"([^"]*)"', text)
            if m:
                return m.group(1)
        except Exception:
            pass
        return symbol

    def get_quote(self, symbol: str):
        """实时估值（盘中估算净值），接口不可用时返回 None。"""
        try:
            code = self.resolve(symbol)
            text = _get_text(f"https://fundgz.1234567.com.cn/js/{code}.js?rt={int(time.time() * 1000)}",
                             timeout=8)
            m = re.search(r"jsonpgz\((.*)\);?", text, re.S)
            if not m:
                return None
            d = json.loads(m.group(1))
            gsz = d.get("gsz")  # 盘中估算净值
            dwjz = d.get("dwjz")  # 最新单位净值
            price = float(gsz or dwjz or 0)
            if not price:
                return None
            return {
                "symbol": symbol,
                "name": d.get("name", ""),
                "price": round(price, 4),
                "change_pct": round(float(d.get("gszzl") or 0), 2),
                "ts": d.get("gztime") or d.get("jzrq") or time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except ValueError:
            return None
        except Exception:
            return None
