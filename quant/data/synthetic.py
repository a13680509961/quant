# -*- coding: utf-8 -*-
"""离线模拟数据源：几何布朗运动生成 OHLCV，无需联网、开箱即用。

同一 (symbol, interval) 组合永远生成同一段历史数据（确定性），
方便反复实验；实时报价则在此基线上继续随机游走，用于演示"盯盘"。
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import deque

import numpy as np
import pandas as pd

from .base import DataSource

INTERVALS = ("1d", "1h", "15m", "1m")


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


class SyntheticSource(DataSource):
    id = "synthetic"
    label = "模拟数据（离线，无需联网）"
    requires_network = False

    def default_symbols(self):
        return ["SYN:测试股票", "SYN:示例ETF", "SYN:数字资产"]

    def get_name(self, symbol: str) -> str:
        return symbol

    # ------------------------------------------------------------------ 历史
    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        if interval not in INTERVALS:
            interval = "1d"
        limit = max(50, min(int(limit), 5000))
        seed = _seed(symbol + "|" + interval)
        rng = np.random.default_rng(seed)

        n = limit
        pad = 60  # 多生成一段再截尾，规避 pandas 3.0 周末锚点的 off-by-one
        now = pd.Timestamp.now()
        if interval == "1d":
            end = now.floor("D")
            idx = pd.date_range(end=end, periods=n + pad, freq="B")
            idx = idx[idx <= end][-n:]
        elif interval == "1h":
            idx = pd.date_range(end=now.floor("h"), periods=n + pad, freq="h")[-n:]
        elif interval == "15m":
            idx = pd.date_range(end=now.floor("15min"), periods=n + pad, freq="15min")[-n:]
        else:  # 1m
            idx = pd.date_range(end=now.floor("min"), periods=n + pad, freq="min")[-n:]

        base = 20.0 + (seed % 800) / 10.0          # 20 ~ 100
        drift = float(rng.normal(0.0003, 0.0006))   # 每根K线的漂移
        vol = 0.012
        rets = rng.normal(drift, vol, n)
        # 少量趋势切换，让走势更"真实"
        for i in range(0, n, 40):
            rets[i:i + 40] += float(rng.normal(0, 0.004))
        close = base * np.exp(np.cumsum(rets))

        o = np.empty(n)
        h = np.empty(n)
        l = np.empty(n)
        o[0] = base
        for i in range(n):
            if i:
                o[i] = close[i - 1]
            wick = np.abs(rng.normal(0, vol * 0.6, 2)) * close[i]
            h[i] = max(o[i], close[i]) + wick[0]
            l[i] = min(o[i], close[i]) - wick[1]

        volume = rng.integers(100_000, 2_000_000, n).astype(float)

        fmt = "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M:%S"
        df = pd.DataFrame({
            "date": [d.strftime(fmt) for d in idx],
            "open": np.round(o, 4),
            "high": np.round(h, 4),
            "low": np.round(l, 4),
            "close": np.round(close, 4),
            "volume": volume,
        })
        return df

    # ------------------------------------------------------------------ 实时
    _live: dict = {}
    _lock = threading.Lock()

    def get_quote(self, symbol: str):
        with self._lock:
            st = self._live.get(symbol)
            if st is None:
                base = 20.0 + (_seed(symbol) % 800) / 10.0
                st = {"price": float(base), "t": 0, "hist": deque(maxlen=120)}
                self._live[symbol] = st
            rng = np.random.default_rng(_seed(symbol) + st["t"])
            step = float(rng.normal(0.0002, 0.006))
            prev = st["price"]
            st["price"] = max(0.01, prev * (1.0 + step))
            st["t"] += 1
            st["hist"].append(st["price"])
            return {
                "symbol": symbol,
                "price": round(st["price"], 4),
                "change": round(st["price"] - prev, 4),
                "change_pct": round(step * 100.0, 4),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
