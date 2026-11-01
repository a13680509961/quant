# -*- coding: utf-8 -*-
"""股票顶层数据源：A股 / 港股 / 美股 按代码自动路由。

标的写法：
    A股：600519、sh000001、sz000001（6 位数字或 sh/sz 前缀）
    港股：00700、09988、700、00700.HK（数字，自动补零到 5 位）、hkHSI/hkHSCEI
    美股：AAPL、MSFT、NVDA、TSLA（字母代码，走 Yahoo，Stooq 日线兜底）
"""
from __future__ import annotations

import re

from .base import DataSource


class StocksSource(DataSource):
    id = "stocks"
    label = "股票（A股/港股/美股，需联网）"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")

    def __init__(self):
        self._ashare = None
        self._hk = None
        self._yahoo = None
        self._stooq = None

    def default_symbols(self):
        return ["600519", "00700", "AAPL", "300750", "09988"]

    @staticmethod
    def resolve(symbol: str):
        return symbol.strip()

    def _route(self, symbol: str):
        """返回 (通道名, 通道实例)。"""
        s = symbol.strip().upper()
        # A股：6 位数字 或 sh/sz 前缀
        if re.match(r"^\d{6}$", s) or re.match(r"^(SH|SZ)\d{6}$", s):
            if self._ashare is None:
                from .ashare import AShareSource
                self._ashare = AShareSource()
            return "A股", self._ashare
        # 港股：数字（≤5 位 / .HK 后缀）或恒指代码
        if re.match(r"^(HK)?\d{1,5}(\.HK)?$", s) or s in ("HKHSI", "HSI", "HKHSCEI", "HSCEI"):
            if self._hk is None:
                from .hk import HKSource
                self._hk = HKSource()
            return "港股", self._hk
        # 美股：纯字母
        if re.match(r"^[A-Z][A-Z.\-]{0,9}$", s):
            if self._yahoo is None:
                from .yahoo import YahooSource
                self._yahoo = YahooSource()
            return "美股", self._yahoo
        raise ValueError(
            f"无法识别股票代码「{symbol}」。A股如 600519 / sh000001；港股如 00700 / hkHSI；美股如 AAPL"
        )

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        market, src = self._route(symbol)
        errors = []
        try:
            df = src.get_bars(symbol, interval, limit)
            if df is not None and len(df):
                return df
            errors.append(f"{market}：未返回数据")
        except Exception as e:
            errors.append(f"{market}：{e}")
        # 美股兜底：Stooq 日线（aapl.us 格式）
        if market == "美股" and interval == "1d":
            try:
                if self._stooq is None:
                    from .stooq import StooqSource
                    self._stooq = StooqSource()
                return self._stooq.get_bars(symbol.strip().lower(), "1d", limit)
            except Exception as e:
                errors.append(f"Stooq：{e}")
        raise ValueError(f"股票行情获取失败（{'；'.join(errors)}）。请检查网络后重试")

    def get_quote(self, symbol: str):
        try:
            _market, src = self._route(symbol)
            return src.get_quote(symbol)
        except ValueError:
            return None
        except Exception:
            return None

    def get_name(self, symbol: str) -> str:
        try:
            _market, src = self._route(symbol)
            name = src.get_name(symbol)
            if name and name != symbol:
                return str(name)
        except ValueError:
            pass
        return symbol
