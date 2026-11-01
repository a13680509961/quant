# -*- coding: utf-8 -*-
"""外汇（汇率）数据源：腾讯日线 + 腾讯/新浪双通道实时报价。

标的写法（货币对，6 位字母，大小写均可）：
    EURUSD 欧元/美元    USDJPY 美元/日元    GBPUSD 英镑/美元
    AUDUSD 澳元/美元    USDCHF 美元/瑞郎    NZDUSD 纽元/美元
    USDCAD 美元/加元    USDCNY 美元/在岸人民币
    美元指数：DINIW（或 DXY / 美元指数）
说明：免费接口仅日线；USDCNH（离岸人民币）暂无免费日线源。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_TENCENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://gu.qq.com/",
}
_SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://finance.sina.com.cn/",
}

_NAMES = {
    "USDCNY": "美元人民币", "EURUSD": "欧元美元", "USDJPY": "美元日元",
    "GBPUSD": "英镑美元", "AUDUSD": "澳元美元", "USDCHF": "美元瑞郎",
    "NZDUSD": "纽元美元", "USDCAD": "美元加元", "DINIW": "美元指数",
}
_ALIASES = {"美元指数": "DINIW", "DXY": "DINIW", "CNY": "USDCNY", "RMB": "USDCNY"}


def normalize_forex(symbol: str) -> str:
    s = symbol.strip().upper().lstrip("WH").lstrip("FX_").lstrip("FX")
    if s in _ALIASES:
        return _ALIASES[s]
    if s in _NAMES:
        return s
    if not re.match(r"^[A-Z]{6}$", s):
        raise ValueError(
            f"外汇代码应为货币对（6 位字母，如 EURUSD、USDCNY、USDJPY），"
            f"美元指数输入 DINIW。当前输入：{symbol}"
        )
    return s


def _get_text(url: str, headers: dict, encoding: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"外汇行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"外汇行情网络不可用（{type(e).__name__}）") from e


class TencentForexProvider(DataSource):
    id = "tencent_forex"
    label = "腾讯外汇"
    provider_name = "腾讯"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        code = normalize_forex(symbol)
        if interval != "1d":
            raise ValueError("外汇免费接口仅支持日线，请选择周期 1d")
        url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
               f"?param=wh{code},day,,,{int(limit)},")
        data = json.loads(_get_text(url, _TENCENT_HEADERS, "utf-8"))
        node = (data.get("data") or {}).get(f"wh{code}") or {}
        rows = node.get("day") or node.get("qfqday") or []
        if not rows:
            raise ValueError(f"腾讯未返回「{code}」的外汇日线（该货币对可能无免费数据）")
        out = []
        for r in rows:
            out.append({  # 腾讯顺序：date, open, close, high, low, volume
                "date": str(r[0])[:10],
                "open": float(r[1]),
                "high": float(r[3]),
                "low": float(r[4]),
                "close": float(r[2]),
                "volume": float(r[5] or 0),
            })
        df = pd.DataFrame(out)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            code = normalize_forex(symbol)
            text = _get_text(f"https://qt.gtimg.cn/q=wh{code}", _TENCENT_HEADERS, "gbk", timeout=8)
            if '="' not in text:
                return None
            parts = text.split('="', 1)[1].split("~")
            if len(parts) < 14 or not parts[3]:
                return None
            return {
                "symbol": code,
                "name": parts[1],
                "price": round(float(parts[3]), 4),
                "change": round(float(parts[12]), 4) if len(parts) > 12 else 0.0,
                "change_pct": round(float(parts[13]), 2) if len(parts) > 13 else 0.0,
                "ts": parts[5] if len(parts) > 5 else time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except ValueError:
            return None
        except Exception:
            return None


class SinaForexProvider(DataSource):
    id = "sina_forex"
    label = "新浪外汇"
    provider_name = "新浪"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        raise ValueError("新浪通道暂无外汇日线，请使用腾讯通道（默认已自动切换）")

    def get_quote(self, symbol: str):
        try:
            code = normalize_forex(symbol)
            q = "DINIW" if code == "DINIW" else f"fx_s{code.lower()}"
            text = _get_text(f"https://hq.sinajs.cn/list={q}", _SINA_HEADERS, "gbk", timeout=8)
            if '="' not in text:
                return None
            parts = text.split('="', 1)[1].split(",")
            if len(parts) < 10 or not parts[1]:
                return None
            price = float(parts[1])
            if code == "DINIW":
                prev = float(parts[3]) or price
                name = parts[9]
                ts = f"{parts[10]} {parts[0]}"
            else:
                prev = float(parts[5]) or price
                name = parts[9]
                ts = f"{parts[17]} {parts[0]}" if len(parts) > 17 else parts[0]
            return {
                "symbol": code,
                "name": name,
                "price": round(price, 4),
                "change": round(price - prev, 4),
                "change_pct": round(float(parts[12]), 2) if len(parts) > 12 and parts[12] else
                round((price - prev) / prev * 100, 2) if prev else 0.0,
                "ts": ts,
            }
        except ValueError:
            return None
        except Exception:
            return None


class ForexSource(DataSource):
    id = "forex"
    label = "外汇（汇率，需联网，日线）"
    requires_network = True
    intervals = ("1d",)

    def __init__(self):
        self._tx = TencentForexProvider()
        self._sina = SinaForexProvider()

    def default_symbols(self):
        return ["USDCNY", "EURUSD", "USDJPY", "GBPUSD", "美元指数"]

    @staticmethod
    def resolve(symbol: str):
        return normalize_forex(symbol)

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        try:
            return self._tx.get_bars(symbol, interval, limit)
        except ValueError as e:
            raise ValueError(f"{e}。可用：EURUSD、USDJPY、GBPUSD、USDCNY、美元指数（USDCNH 离岸暂无免费源）") from e

    def get_quote(self, symbol: str):
        q = self._tx.get_quote(symbol)
        if q:
            return q
        return self._sina.get_quote(symbol)

    def get_name(self, symbol: str) -> str:
        code = normalize_forex(symbol)
        q = self.get_quote(symbol)
        if q and q.get("name"):
            return str(q["name"])
        return _NAMES.get(code, code)
