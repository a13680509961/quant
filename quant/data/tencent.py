# -*- coding: utf-8 -*-
"""腾讯行情通道：A股K线与实时报价（需联网），作为 AShareSource 的兜底通道。

- 日线：fqkline 接口（前复权 qfq）；个股节点为 qfqday，指数节点为 day
- 分钟线：mkline 接口（m60/m15/m1）
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

# 周期 -> (腾讯周期参数, fqkline节点key, mkline节点key)
_PERIOD_MAP = {
    "1d": ("day", "qfqday", "day"),
    "1h": ("m60", "m60", "m60"),
    "15m": ("m15", "m15", "m15"),
    "1m": ("m1", "m1", "m1"),
}


def _http_text(url: str, encoding: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
        "Referer": "https://gu.qq.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"腾讯行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"腾讯行情网络不可用（{type(e).__name__}）") from e


class TencentProvider(DataSource):
    id = "tencent"
    label = "腾讯行情"
    provider_name = "腾讯行情"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        from .ashare import resolve_a_symbol
        market, code = resolve_a_symbol(symbol)
        qq = ("sh" if market == 1 else "sz") + code
        period, day_key, min_key = _PERIOD_MAP.get(interval, ("day", "qfqday", "day"))
        if interval == "1d":
            url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                   f"?param={qq},day,,,{int(limit)},qfq")
            data = json.loads(_http_text(url, "utf-8"))
            node = (data.get("data") or {}).get(qq) or {}
            # 个股返回 qfqday，指数返回 day
            rows = node.get(day_key) or node.get("day") or node.get("qfqday") or []
        else:
            url = (f"https://web.ifzq.gtimg.cn/appstock/app/kline/mkline"
                   f"?param={qq},{period},,,{int(limit)}")
            data = json.loads(_http_text(url, "utf-8"))
            node = (data.get("data") or {}).get(qq) or {}
            rows = node.get(min_key)
            if not rows:  # 节点名兜底：找第一个"列表的列表"
                for v in node.values():
                    if isinstance(v, list) and v and isinstance(v[0], list):
                        rows = v
                        break
            rows = rows or []
        if not rows:
            raise ValueError(f"腾讯行情未返回「{symbol}」的K线数据")
        out = []
        for r in rows:
            out.append({  # 腾讯顺序：date, open, close, high, low, volume
                "date": str(r[0])[:16],
                "open": float(r[1]),
                "high": float(r[3]),
                "low": float(r[4]),
                "close": float(r[2]),
                "volume": float(r[5]),
            })
        df = pd.DataFrame(out)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            from .ashare import resolve_a_symbol
            market, code = resolve_a_symbol(symbol)
            qq = ("sh" if market == 1 else "sz") + code
            text = _http_text(f"https://qt.gtimg.cn/q={qq}", "gbk", timeout=8)
            if "=" not in text:
                return None
            parts = text.split("=", 1)[1].strip().strip('";').split("~")
            if len(parts) < 33 or not parts[3]:
                return None
            price = float(parts[3])
            prev = float(parts[4])
            ts_raw = parts[30]  # YYYYMMDDHHMMSS
            ts = (f"{ts_raw[:4]}-{ts_raw[4:6]}-{ts_raw[6:8]} "
                  f"{ts_raw[8:10]}:{ts_raw[10:12]}:{ts_raw[12:14]}" if len(ts_raw) >= 14
                  else time.strftime("%Y-%m-%d %H:%M:%S"))
            return {
                "symbol": symbol,
                "name": parts[1],
                "price": round(price, 3),
                "change": round(price - prev, 3),
                "change_pct": round(float(parts[32]), 2),
                "ts": ts,
            }
        except ValueError:
            return None
        except Exception:
            return None
