# -*- coding: utf-8 -*-
"""Yahoo Finance 数据源（需联网）：美股、指数、加密货币、外汇等。

直接调用 Yahoo 公开 chart JSON 接口（仅标准库 urllib，无需任何第三方包）。
标的示例：AAPL、MSFT、SPY、QQQ、BTC-USD、EURUSD=X、^GSPC 等。
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

from .base import DataSource

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# interval -> (yahoo interval, range)
_RANGE_MAP = {
    "1d": ("1d", "5y"),
    "1h": ("1h", "3mo"),
    "15m": ("15m", "60d"),
    "1m": ("1m", "7d"),
}


def _http_get_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise ValueError(
            f"无法访问 Yahoo 数据（HTTP {e.code}）：可能网络不通或该区域被限制，"
            "可改用「模拟数据」离线演示"
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError("无法访问 Yahoo 数据：网络不可用，请检查联网后重试") from e


class YahooSource(DataSource):
    id = "yahoo"
    label = "Yahoo Finance（美股/指数/加密/外汇，需联网）"
    requires_network = True
    hidden = True  # 已并入「股票/指数」顶层源，仅作内部通道

    def default_symbols(self):
        return ["AAPL", "MSFT", "SPY", "QQQ", "BTC-USD", "EURUSD=X"]

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        y_interval, y_range = _RANGE_MAP.get(interval, ("1d", "5y"))
        qs = urllib.parse.quote(symbol.strip())
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{qs}"
               f"?interval={y_interval}&range={y_range}&includePrePost=false")
        data = _http_get_json(url)
        res = data["chart"]["result"][0]
        ts = res.get("timestamp") or []
        quote = (res.get("indicators", {}).get("quote") or [{}])[0]
        if not ts:
            raise ValueError(f"未获取到数据：请确认标的代码 {symbol} 是否正确（美股直接用代码，指数加 ^，加密如 BTC-USD）")

        fmt = "%Y-%m-%d" if interval == "1d" else "%Y-%m-%d %H:%M:%S"
        df = pd.DataFrame({
            "date": [time.strftime(fmt, time.localtime(t)) for t in ts],
            "open": np.asarray(quote.get("open") or [], dtype=float),
            "high": np.asarray(quote.get("high") or [], dtype=float),
            "low": np.asarray(quote.get("low") or [], dtype=float),
            "close": np.asarray(quote.get("close") or [], dtype=float),
            "volume": np.asarray(quote.get("volume") or [], dtype=float),
        })
        df = df.replace(0.0, np.nan).dropna(subset=["open", "high", "low", "close"])
        df["volume"] = df["volume"].fillna(0.0)
        df = df.reset_index(drop=True)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            qs = urllib.parse.quote(symbol.strip())
            data = _http_get_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{qs}?interval=1d&range=1d",
                timeout=8,
            )
            res = data["chart"]["result"][0]
            meta = res.get("meta", {})
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is None:
                return None
            change = round(price - prev, 4) if prev is not None else None
            pct = round((price - prev) / prev * 100, 4) if prev else None
            return {
                "symbol": symbol,
                "price": round(float(price), 4),
                "change": change,
                "change_pct": pct,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception:
            return None
