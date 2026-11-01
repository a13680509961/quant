# -*- coding: utf-8 -*-
"""加密货币（区块链）数据源：Gate.io 主通道 + Binance/OKX 备用通道。

标的写法（大小写均可）：
    BTC / BTCUSDT / BTC/USDT / BTC-USDT   比特币（默认兑 USDT）
    ETH、SOL、DOGE、XRP、ADA、BNB、LTC、DOT、LINK、AVAX、SHIB、PEPE …
支持周期：日线 / 1小时 / 15分钟 / 1分钟（加密货币 7×24 交易）。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}

_NAMES = {
    "BTC": "比特币", "ETH": "以太坊", "SOL": "Solana", "XRP": "瑞波币",
    "DOGE": "狗狗币", "ADA": "艾达币", "BNB": "币安币", "LTC": "莱特币",
    "DOT": "波卡", "LINK": "Chainlink", "AVAX": "雪崩", "SHIB": "柴犬币",
    "PEPE": "佩佩蛙", "TRX": "波场", "TON": "Toncoin",
}


def normalize_crypto(symbol: str) -> str:
    """返回 (base, quote)，如 ('BTC', 'USDT')。"""
    s = symbol.strip().upper().replace("/", "_").replace("-", "_")
    if "_" in s:
        parts = s.split("_")
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        raise ValueError(f"加密货币代码格式错误：{symbol}（如 BTC、BTCUSDT、ETH/USDT）")
    if s.endswith("USDT"):
        return s[:-4], "USDT"
    if s.endswith("USDC"):
        return s[:-4], "USDC"
    if not re.match(r"^[A-Z0-9]{2,10}$", s):
        raise ValueError(f"加密货币代码格式错误：{symbol}（如 BTC、ETH、SOL）")
    return s, "USDT"


def _get_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"加密行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"加密行情网络不可用（{type(e).__name__}）") from e


def _bars_from_rows(rows, ts_div, cols, interval) -> pd.DataFrame:
    """cols: (date_ts, open, high, low, close, volume) 各字段在行内的索引。"""
    out = []
    for r in rows:
        ts = int(float(r[cols[0]])) / ts_div
        if interval == "1d":
            dt = time.strftime("%Y-%m-%d", time.localtime(ts))
        else:
            dt = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        out.append({
            "date": dt,
            "open": float(r[cols[1]]),
            "high": float(r[cols[2]]),
            "low": float(r[cols[3]]),
            "close": float(r[cols[4]]),
            "volume": float(r[cols[5]]),
        })
    df = pd.DataFrame(out)
    return df.sort_values("date").reset_index(drop=True)


class GateProvider(DataSource):
    id = "gate"
    label = "Gate.io"
    provider_name = "Gate.io"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        base, quote = normalize_crypto(symbol)
        pair = f"{base}_{quote}"
        iv = {"1d": "1d", "1h": "1h", "15m": "15m", "1m": "1m"}.get(interval)
        if iv is None:
            raise ValueError(f"Gate 不支持周期 {interval}，可选：1d / 1h / 15m / 1m")
        url = (f"https://api.gateio.ws/api/v4/spot/candlesticks"
               f"?currency_pair={pair}&interval={iv}&limit={min(int(limit), 1000)}")
        rows = json.loads(_get_text(url))
        if not rows:
            raise ValueError(f"Gate 未返回「{pair}」的K线，请确认币种代码（如 BTC、ETH、SOL）")
        # Gate 行格式：[时间戳秒, 计价成交量, 收盘, 最高, 最低, 开盘, 基础成交量, ...]
        return _bars_from_rows(rows, 1, (0, 5, 3, 4, 2, 6), interval)

    def get_quote(self, symbol: str):
        try:
            base, quote = normalize_crypto(symbol)
            pair = f"{base}_{quote}"
            rows = json.loads(_get_text(
                f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={pair}", timeout=10))
            if not rows:
                return None
            t = rows[0]
            return {
                "symbol": f"{base}/{quote}",
                "name": _NAMES.get(base, base) + "/" + quote,
                "price": round(float(t.get("last") or 0), 6),
                "change_pct": round(float(t.get("change_percentage") or 0), 2),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except ValueError:
            return None
        except Exception:
            return None


class BinanceProvider(DataSource):
    id = "binance"
    label = "Binance"
    provider_name = "Binance"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        base, quote = normalize_crypto(symbol)
        pair = f"{base}{quote}"
        iv = {"1d": "1d", "1h": "1h", "15m": "15m", "1m": "1m"}.get(interval, "1d")
        url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={iv}&limit={min(int(limit), 1000)}"
        rows = json.loads(_get_text(url))
        if not rows:
            raise ValueError(f"Binance 未返回「{pair}」的K线")
        # Binance 行格式：[开时ms, 开, 高, 低, 收, 量, 收时ms, ...]
        return _bars_from_rows(rows, 1000, (0, 1, 2, 3, 4, 5), interval)

    def get_quote(self, symbol: str):
        try:
            base, quote = normalize_crypto(symbol)
            pair = f"{base}{quote}"
            t = json.loads(_get_text(f"https://api.binance.com/api/v3/ticker/24hr?symbol={pair}", timeout=10))
            return {
                "symbol": f"{base}/{quote}",
                "name": _NAMES.get(base, base) + "/" + quote,
                "price": round(float(t.get("lastPrice") or 0), 6),
                "change_pct": round(float(t.get("priceChangePercent") or 0), 2),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except ValueError:
            return None
        except Exception:
            return None


class OkxProvider(DataSource):
    id = "okx"
    label = "OKX"
    provider_name = "OKX"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        base, quote = normalize_crypto(symbol)
        inst = f"{base}-{quote}"
        bar = {"1d": "1D", "1h": "1H", "15m": "15m", "1m": "1m"}.get(interval, "1D")
        url = (f"https://www.okx.com/api/v5/market/candles"
               f"?instId={inst}&bar={bar}&limit={min(int(limit), 300)}")
        rows = json.loads(_get_text(url)).get("data") or []
        if not rows:
            raise ValueError(f"OKX 未返回「{inst}」的K线")
        rows = list(reversed(rows))  # OKX 最新在前，翻转为升序
        # OKX 行格式：[时间戳ms, 开, 高, 低, 收, 量, ...]
        return _bars_from_rows(rows, 1000, (0, 1, 2, 3, 4, 5), interval)

    def get_quote(self, symbol: str):
        try:
            base, quote = normalize_crypto(symbol)
            inst = f"{base}-{quote}"
            data = json.loads(_get_text(
                f"https://www.okx.com/api/v5/market/ticker?instId={inst}", timeout=10)).get("data") or []
            if not data:
                return None
            t = data[0]
            last = float(t.get("last") or 0)
            open24 = float(t.get("open24h") or last)
            return {
                "symbol": f"{base}/{quote}",
                "name": _NAMES.get(base, base) + "/" + quote,
                "price": round(last, 6),
                "change_pct": round((last - open24) / open24 * 100, 2) if open24 else 0.0,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except ValueError:
            return None
        except Exception:
            return None


class CryptoSource(DataSource):
    id = "crypto"
    label = "加密货币（Gate/Binance/OKX，需联网）"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")

    def __init__(self):
        # Gate 国内网络通常可达，放第一位
        self._providers = [GateProvider(), BinanceProvider(), OkxProvider()]

    def default_symbols(self):
        return ["BTC", "ETH", "SOL", "DOGE", "XRP"]

    @staticmethod
    def resolve(symbol: str):
        base, quote = normalize_crypto(symbol)
        return f"{base}/{quote}"

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        normalize_crypto(symbol)  # 先校验格式
        errors = []
        for p in self._providers:
            try:
                df = p.get_bars(symbol, interval, limit)
                if df is not None and len(df):
                    return df
                errors.append(f"{p.provider_name}：未返回数据")
            except Exception as e:
                errors.append(f"{p.provider_name}：{e}")
        raise ValueError(f"加密货币行情获取失败（{'；'.join(errors)}）。请检查网络后重试")

    def get_quote(self, symbol: str):
        normalize_crypto(symbol)
        for p in self._providers:
            try:
                q = p.get_quote(symbol)
                if q:
                    return q
            except Exception:
                continue
        return None

    def get_name(self, symbol: str) -> str:
        base, quote = normalize_crypto(symbol)
        return f"{_NAMES.get(base, base)}/{quote}"
