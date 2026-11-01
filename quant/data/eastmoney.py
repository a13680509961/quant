# -*- coding: utf-8 -*-
"""东方财富行情通道：A股K线与实时报价（需联网）。

作为 AShareSource 的首选通道；本类不直接注册，由 quant/data/ashare.py 统一调度，
连接失败时自动切换到腾讯行情通道。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

_KLINES = {"1d": 101, "1h": 60, "15m": 15, "1m": 1}


def _get_json(url: str, timeout: int = 12, retries: int = 3) -> dict:
    """带自动重试的 GET+JSON（东财接口偶发断开连接，重试后一般可恢复）。"""
    req = urllib.request.Request(url, headers=_HEADERS)
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raise ValueError(
                f"无法访问东方财富行情（HTTP {e.code}）：可能网络不通或被限制，"
                "可改用「模拟数据」离线演示"
            ) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    raise ValueError(
        f"无法访问东方财富行情：网络不可用（{type(last_err).__name__}），请检查联网后重试"
    ) from last_err


class EastmoneyProvider(DataSource):
    id = "eastmoney"
    label = "东方财富"
    provider_name = "东方财富"
    requires_network = True

    def default_symbols(self):
        return ["600519", "000001", "300750", "sh000001", "588000"]

    # ------------------------------------------------------------------ 代码解析
    @staticmethod
    def resolve(symbol: str):
        """返回 (market, code)：market 1=沪市，0=深市/北交所。"""
        from .ashare import resolve_a_symbol
        return resolve_a_symbol(symbol)

    # ------------------------------------------------------------------ 历史K线
    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        market, code = self.resolve(symbol)
        klt = _KLINES.get(interval)
        if klt is None:
            raise ValueError(f"东方财富不支持周期 {interval}，可选：1d / 1h / 15m / 1m")
        fqt = 1 if interval == "1d" else 0  # 日线前复权
        secid = f"{market}.{code}"
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}&klt={klt}&fqt={fqt}&lmt={int(limit)}&end=20500101"
            "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
        )
        data = _get_json(url)
        d = data.get("data") or {}
        klines = d.get("klines") or []
        if not klines:
            name = d.get("name") or symbol
            raise ValueError(f"未获取到「{name}」的K线数据，请确认代码是否正确（如 600519、sh000001）")

        rows = []
        for line in klines:
            p = line.split(",")  # date, open, close, high, low, volume, amount
            rows.append({
                "date": p[0][:16],
                "open": float(p[1]),
                "high": float(p[3]),
                "low": float(p[4]),
                "close": float(p[2]),
                "volume": float(p[5]),
            })
        df = pd.DataFrame(rows)
        df = df[df["close"].notna()]
        return df.tail(int(limit)).reset_index(drop=True)

    # ------------------------------------------------------------------ 实时报价
    def get_quote(self, symbol: str):
        try:
            market, code = self.resolve(symbol)
            secid = f"{market}.{code}"
            data = _get_json(
                f"https://push2.eastmoney.com/api/qt/stock/get"
                f"?secid={secid}&fields=f43,f57,f58,f59,f86,f169,f170",
                timeout=8,
            )
            d = data.get("data") or {}
            raw = d.get("f43")
            if raw in (None, "-"):
                return None
            price = float(raw)
            decimals = int(d.get("f59") or 2)
            divisor = 10 ** max(decimals, 1)
            price /= divisor
            chg = float(d.get("f169") or 0) / divisor
            pct = float(d.get("f170") or 0) / 100.0
            ts_raw = d.get("f86")
            ts = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.localtime(int(ts_raw)) if ts_raw else time.localtime())
            return {
                "symbol": symbol,
                "name": d.get("f58") or "",
                "price": round(price, 3),
                "change": round(chg, 3),
                "change_pct": round(pct, 2),
                "ts": ts,
            }
        except ValueError:
            return None
        except Exception:
            return None
