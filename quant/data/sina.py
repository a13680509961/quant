# -*- coding: utf-8 -*-
"""新浪财经行情通道：A股K线与实时报价（需联网），作为 AShareSource 的第三通道。

- 单接口支持日线（scale=240）与分钟线（60/15/5 分钟），股票、指数通用
- 不支持 1 分钟线（最小 5 分钟）
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_SCALE_MAP = {
    "1d": 240,
    "1h": 60,
    "15m": 15,
    "1m": None,  # 新浪最小 5 分钟
}


def _http_bytes(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
        "Referer": "https://finance.sina.com.cn/",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise ValueError(f"新浪行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"新浪行情网络不可用（{type(e).__name__}）") from e


class SinaProvider(DataSource):
    id = "sina"
    label = "新浪财经"
    provider_name = "新浪财经"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        from .ashare import resolve_a_symbol
        market, code = resolve_a_symbol(symbol)
        sym = ("sh" if market == 1 else "sz") + code
        scale = _SCALE_MAP.get(interval, 240)
        if scale is None:
            raise ValueError("新浪通道不支持 1 分钟线（最小 5 分钟）")
        url = (f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
               f"?symbol={sym}&scale={scale}&ma=no&datalen={int(limit)}")
        rows = json.loads(_http_bytes(url).decode("utf-8", "replace"))
        if not rows:
            raise ValueError(f"新浪行情未返回「{symbol}」的K线数据")
        out = []
        for r in rows:
            out.append({
                "date": str(r.get("day", ""))[:16],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume") or 0),
            })
        df = pd.DataFrame(out)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            from .ashare import resolve_a_symbol
            market, code = resolve_a_symbol(symbol)
            sym = ("sh" if market == 1 else "sz") + code
            text = _http_bytes(f"https://hq.sinajs.cn/list={sym}", timeout=8).decode("gbk", "replace")
            if '="' not in text:
                return None
            parts = text.split('="', 1)[1].split(",")
            if len(parts) < 4 or not parts[3]:
                return None
            price = float(parts[3])
            prev = float(parts[2])
            date = parts[-3] if len(parts) > 30 else ""
            tm = parts[-2] if len(parts) > 30 else ""
            ts = f"{date} {tm}" if len(date) == 8 else time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "symbol": symbol,
                "name": parts[0],
                "price": round(price, 3),
                "change": round(price - prev, 3),
                "change_pct": round((price - prev) / prev * 100, 2) if prev else 0.0,
                "ts": ts,
            }
        except ValueError:
            return None
        except Exception:
            return None
