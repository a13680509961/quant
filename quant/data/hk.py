# -*- coding: utf-8 -*-
"""港股数据源：东方财富（116.xxxxx）+ 腾讯行情（hkXXXXX）双通道。

标的写法：
    00700 / 700 / 00700.HK / hk00700  腾讯控股（自动补零到 5 位）
    09988                             阿里巴巴
    00005                             汇丰控股
    hkHSI / HSI                       恒生指数（仅腾讯通道）
    hkHSCEI                           恒生国企指数（仅腾讯通道）
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
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://quote.eastmoney.com/",
}

_MIN_MAP = {"1h": "m60", "15m": "m15", "1m": "m1"}
_EM_KLT = {"1d": 101, "1h": 60, "15m": 15, "1m": 1}


def _get_text(url: str, headers: dict, encoding: str = "utf-8", timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"港股行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"港股行情网络不可用（{type(e).__name__}）") from e


def resolve_hk(symbol: str):
    """返回 (通道类型, 通道代码)：('stock', '00700') / ('index', 'hkHSI')。"""
    s = symbol.strip().upper().replace("^", "")
    if s in ("HKHSI", "HSI"):
        return "index", "hkHSI"
    if s in ("HKHSCEI", "HSCEI"):
        return "index", "hkHSCEI"
    code = re.sub(r"\.HK$", "", s).lstrip("HK")
    if not code.isdigit() or len(code) > 5:
        raise ValueError(f"港股代码格式错误：{symbol}（如 00700、09988、hkHSI）")
    return "stock", code.zfill(5)


class TencentHKProvider(DataSource):
    id = "tencent_hk"
    label = "腾讯港股"
    provider_name = "腾讯"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        kind, code = resolve_hk(symbol)
        qq = code if kind == "index" else f"hk{code}"
        if interval == "1d":
            url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                   f"?param={qq},day,,,{int(limit)},qfq")
            data = json.loads(_get_text(url, _TENCENT_HEADERS))
            node = (data.get("data") or {}).get(qq) or {}
            rows = node.get("qfqday") or node.get("day") or []
        elif interval in _MIN_MAP:
            period = _MIN_MAP[interval]
            url = (f"https://web.ifzq.gtimg.cn/appstock/app/kline/mkline"
                   f"?param={qq},{period},,,{int(limit)}")
            data = json.loads(_get_text(url, _TENCENT_HEADERS))
            node = (data.get("data") or {}).get(qq) or {}
            rows = node.get(period)
            if not rows:
                for v in node.values():
                    if isinstance(v, list) and v and isinstance(v[0], list):
                        rows = v
                        break
            rows = rows or []
        else:
            raise ValueError(f"腾讯港股不支持周期 {interval}")
        if not rows:
            raise ValueError(f"腾讯未返回「{symbol}」的港股行情")
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
            kind, code = resolve_hk(symbol)
            qq = code if kind == "index" else f"hk{code}"
            text = _get_text(f"https://qt.gtimg.cn/q={qq}", _TENCENT_HEADERS, "gbk", timeout=8)
            if '="' not in text:
                return None
            parts = text.split('="', 1)[1].split("~")
            if len(parts) < 33 or not parts[3]:
                return None
            price = float(parts[3])
            prev = float(parts[4])
            return {
                "symbol": symbol,
                "name": parts[1],
                "price": round(price, 3),
                "change": round(price - prev, 3),
                "change_pct": round(float(parts[32]), 2),
                "ts": parts[30],
            }
        except ValueError:
            return None
        except Exception:
            return None


class EastmoneyHKProvider(DataSource):
    id = "em_hk"
    label = "东方财富港股"
    provider_name = "东方财富"
    requires_network = True

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        kind, code = resolve_hk(symbol)
        if kind == "index":
            raise ValueError("东财通道暂不支持港股指数，请使用代码（如 00700）或腾讯通道")
        secid = f"116.{code}"
        klt = _EM_KLT.get(interval, 101)
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
               f"?secid={secid}&klt={klt}&fqt=1&lmt={int(limit)}&end=20500101"
               "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
        try:
            data = json.loads(_get_text(url, _EM_HEADERS, timeout=15))
        except ValueError as e:
            raise ValueError(str(e)) from e
        klines = ((data.get("data") or {}).get("klines")) or []
        if not klines:
            raise ValueError(f"东财未返回「{symbol}」的港股行情")
        out = []
        for line in klines:
            p = line.split(",")  # date, open, close, high, low, volume
            out.append({
                "date": p[0][:16],
                "open": float(p[1]),
                "high": float(p[3]),
                "low": float(p[4]),
                "close": float(p[2]),
                "volume": float(p[5]),
            })
        df = pd.DataFrame(out)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            kind, code = resolve_hk(symbol)
            if kind == "index":
                return None
            data = json.loads(_get_text(
                f"https://push2.eastmoney.com/api/qt/stock/get?secid=116.{code}"
                "&fields=f43,f58,f59,f86,f169,f170", _EM_HEADERS, timeout=8))
            d = data.get("data") or {}
            raw = d.get("f43")
            if raw in (None, "-"):
                return None
            price = float(raw) / (10 ** max(int(d.get("f59") or 3), 1))
            chg = float(d.get("f169") or 0) / (10 ** max(int(d.get("f59") or 3), 1))
            pct = float(d.get("f170") or 0) / 100.0
            ts_raw = d.get("f86")
            return {
                "symbol": symbol,
                "name": d.get("f58") or "",
                "price": round(price, 3),
                "change": round(chg, 3),
                "change_pct": round(pct, 2),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S",
                                    time.localtime(int(ts_raw)) if ts_raw else time.localtime()),
            }
        except ValueError:
            return None
        except Exception:
            return None


class HKSource(DataSource):
    id = "hk"
    label = "港股（腾讯+东财，需联网）"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")
    hidden = True  # 已并入「股票」顶层源，仅作内部通道

    def __init__(self):
        self._em = EastmoneyHKProvider()
        self._tx = TencentHKProvider()

    def default_symbols(self):
        return ["00700", "09988", "03690", "00005", "hkHSI"]

    @staticmethod
    def resolve(symbol: str):
        return resolve_hk(symbol)

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        kind, _code = resolve_hk(symbol)
        errors = []
        if kind == "stock":
            try:
                df = self._em.get_bars(symbol, interval, limit)
                if df is not None and len(df):
                    return df
                errors.append("东方财富：未返回数据")
            except Exception as e:
                errors.append(f"东方财富：{e}")
        try:
            return self._tx.get_bars(symbol, interval, limit)
        except Exception as e:
            errors.append(f"腾讯：{e}")
        raise ValueError(f"港股行情获取失败（{'；'.join(errors)}）。请检查网络或确认代码（如 00700、hkHSI）")

    def get_quote(self, symbol: str):
        kind, _code = resolve_hk(symbol)
        if kind == "stock":
            q = self._em.get_quote(symbol)
            if q:
                return q
        return self._tx.get_quote(symbol)
