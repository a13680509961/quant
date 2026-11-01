# -*- coding: utf-8 -*-
"""Stooq 数据源（需联网）：免费 CSV 日线兜底源，覆盖美股/指数/外汇/部分加密货币。

美股代码带 ".us" 后缀（如 aapl.us）；用户可直接输入 aapl.us 或 aapl。
"""
from __future__ import annotations

import io
import time
import urllib.parse
import urllib.request

import pandas as pd

from .base import DataSource


def _http_get_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(
            f"无法访问 Stooq 数据（HTTP {e.code}）：可能网络不通或该区域被限制，"
            "可改用「模拟数据」离线演示"
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError("无法访问 Stooq 数据：网络不可用，请检查联网后重试") from e


class StooqSource(DataSource):
    id = "stooq"
    label = "Stooq（日线兜底，需联网）"
    requires_network = True
    intervals = ("1d",)
    hidden = True  # 已并入「股票」顶层源，仅作内部兜底通道

    def default_symbols(self):
        return ["aapl.us", "msft.us", "^spx", "usdjpy", "btcusd"]

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        if interval != "1d":
            raise ValueError("Stooq 免费源仅提供日线数据，请选择周期 = 1d")
        code = symbol.strip().lower()
        if code and not any(code.endswith(s) for s in (".us", ".de", ".jp", ".hk", ".uk", ".pl")):
            if code.startswith("^") or code.isalpha() and len(code) == 6 and not code.endswith("usd"):
                pass
            elif code.isalpha() and len(code) <= 5:
                code = code + ".us"   # 默认按美股处理
        url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(code)}&i=d"
        text = _http_get_text(url)
        df = pd.read_csv(io.StringIO(text))
        if df.empty or "Date" not in df.columns:
            raise ValueError(f"Stooq 未返回数据：请确认代码（美股如 aapl.us，指数如 ^spx）")
        df = df.rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
        df = df.dropna().sort_values("date").reset_index(drop=True)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            code = symbol.strip().lower()
            if len(code) <= 5 and code.isalpha():
                code += ".us"
            text = _http_get_text(
                f"https://stooq.com/q/l/?s={urllib.parse.quote(code)}&f=sd2t2ohlcv&h&e=csv",
                timeout=8,
            )
            df = pd.read_csv(io.StringIO(text))
            if df.empty:
                return None
            row = df.iloc[0]
            return {
                "symbol": symbol,
                "price": round(float(row["Close"]), 4),
                "change": round(float(row["Close"]) - float(row["Open"]), 4),
                "change_pct": round((float(row["Close"]) - float(row["Open"])) / float(row["Open"]) * 100, 4),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception:
            return None
