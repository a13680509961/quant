# -*- coding: utf-8 -*-
"""全球主要股票指数数据源：东财 → 腾讯 → Yahoo 三通道自动切换。

标的写法（大小写均可，也支持中文别名）：
    SPX / 标普500    标普500指数        IXIC / 纳斯达克    纳斯达克综合
    DJI / 道琼斯     道琼斯工业平均      N225 / 日经        日经225
    GDAXI / DAX      德国DAX            FTSE / 富时100     英国富时100
    FCHI / CAC       法国CAC40          KS11 / KOSPI       韩国综合
    TWII / 台湾加权  台湾加权指数
注：上证指数（sh000001）在 A股源、恒生指数（hkHSI）在港股源、美元指数（DINIW）在外汇源。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://quote.eastmoney.com/",
}
_TX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://gu.qq.com/",
}

_INDEXES = {
    "DJI":   {"name": "道琼斯",   "name_en": "Dow Jones",  "em": "100.DJIA",  "tx": "usDJI",  "yh": "^DJI"},
    "IXIC":  {"name": "纳斯达克", "name_en": "Nasdaq",     "em": "100.NDX",   "tx": "usIXIC", "yh": "^IXIC"},
    "SPX":   {"name": "标普500",  "name_en": "S&P 500",    "em": "100.SPX",   "tx": "usINX",  "yh": "^GSPC"},
    "N225":  {"name": "日经225",  "name_en": "Nikkei 225", "em": "100.N225",  "tx": None,     "yh": "^N225"},
    "GDAXI": {"name": "德国DAX",  "name_en": "DAX",        "em": "100.GDAXI", "tx": None,     "yh": "^GDAXI"},
    "FTSE":  {"name": "富时100",  "name_en": "FTSE 100",   "em": "100.FTSE",  "tx": None,     "yh": "^FTSE"},
    "FCHI":  {"name": "法国CAC40", "name_en": "CAC 40",    "em": "100.FCHI",  "tx": None,     "yh": "^FCHI"},
    "KS11":  {"name": "韩国KOSPI", "name_en": "KOSPI",     "em": "100.KS11",  "tx": None,     "yh": "^KS11"},
    "TWII":  {"name": "台湾加权", "name_en": "Taiwan TWII", "em": "100.TWII", "tx": None,     "yh": "^TWII"},
}
_ALIASES = {
    "道琼斯": "DJI", "道指": "DJI",
    "纳斯达克": "IXIC", "NDX": "IXIC",
    "标普500": "SPX", "标普": "SPX", "INX": "SPX",
    "日经": "N225", "日经225": "N225",
    "DAX": "GDAXI", "德国DAX": "GDAXI", "德国": "GDAXI",
    "富时": "FTSE", "富时100": "FTSE", "UKX": "FTSE", "英国": "FTSE",
    "CAC": "FCHI", "CAC40": "FCHI", "法国": "FCHI",
    "KOSPI": "KS11", "韩国": "KS11",
    "台湾": "TWII", "台湾加权": "TWII", "台指": "TWII",
}
_EM_KLT = {"1d": 101, "1h": 60, "15m": 15, "1m": 1}


def resolve_index(symbol: str) -> str:
    s = symbol.strip().upper().lstrip("^")
    if s in _ALIASES:
        return _ALIASES[s]
    if s in _INDEXES:
        return s
    raise ValueError(
        f"无法识别指数「{symbol}」。可用：SPX（标普500）、IXIC（纳斯达克）、DJI（道琼斯）、"
        "N225（日经）、GDAXI（德国DAX）、FTSE（富时100）、FCHI（法国CAC）、KS11（韩国）、TWII（台湾）；"
        "上证指数请用 A股源 sh000001，恒生指数请用港股源 hkHSI"
    )


def _get_text(url: str, headers: dict, encoding: str = "utf-8", timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"指数行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"指数行情网络不可用（{type(e).__name__}）") from e


def _em_bars(secid: str, interval: str, limit: int) -> pd.DataFrame:
    klt = _EM_KLT.get(interval, 101)
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&klt={klt}&fqt=0&lmt={int(limit)}&end=20500101"
           "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
    data = json.loads(_get_text(url, _HEADERS))
    klines = ((data.get("data") or {}).get("klines")) or []
    if not klines:
        raise ValueError("东财未返回数据")
    rows = []
    for line in klines:
        p = line.split(",")  # date, open, close, high, low, volume
        rows.append({"date": p[0][:16], "open": float(p[1]), "high": float(p[3]),
                     "low": float(p[4]), "close": float(p[2]), "volume": float(p[5])})
    return pd.DataFrame(rows).tail(int(limit)).reset_index(drop=True)


def _tx_bars(code: str, limit: int) -> pd.DataFrame:
    data = json.loads(_get_text(
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{int(limit)},",
        _TX_HEADERS))
    node = (data.get("data") or {}).get(code) or {}
    rows = node.get("day") or node.get("qfqday") or []
    if len(rows) < 20:  # 腾讯对美股指数只给最近 1 根快照，视作无历史数据
        raise ValueError(f"腾讯仅返回 {len(rows)} 根K线（无历史数据）")
    out = [{"date": str(r[0])[:10], "open": float(r[1]), "high": float(r[3]),
            "low": float(r[4]), "close": float(r[2]), "volume": float(r[5] or 0)}
           for r in rows]
    return pd.DataFrame(out).tail(int(limit)).reset_index(drop=True)


class IndicesSource(DataSource):
    id = "indices"
    label = "指数（A股/港股/美元指数/全球，需联网）"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")

    def default_symbols(self):
        return ["SPX", "sh000001", "hkHSI", "DINIW", "N225"]

    @staticmethod
    def resolve(symbol: str):
        s = symbol.strip().upper()
        # 上证/深证指数 → A股通道
        if re.match(r"^(SH|SZ)\d{6}$", s):
            return s
        # 恒生指数 → 港股通道
        if s in ("HKHSI", "HSI", "HKHSCEI", "HSCEI"):
            return "hk" + s.removeprefix("HK")
        # 美元指数 → 外汇通道
        if s in ("DINIW", "DXY") or "美元" in symbol:
            return "DINIW"
        return resolve_index(s)

    def _routed(self, symbol: str):
        """非本源的指数路由到其他数据源。返回 (source_id, symbol) 或 None。"""
        s = symbol.strip().upper()
        if re.match(r"^(SH|SZ)\d{6}$", s):
            return "ashare", s
        if s in ("HKHSI", "HSI", "HKHSCEI", "HSCEI"):
            return "hk", "hk" + s.removeprefix("HK")
        if s in ("DINIW", "DXY") or "美元" in symbol:
            return "forex", "DINIW"
        return None

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        route = self._routed(symbol)
        if route:
            from .base import get_source, ensure_registered
            ensure_registered()
            src = get_source(route[0])
            if src is not None:
                return src.get_bars(route[1], interval, limit)
        code = resolve_index(symbol)
        info = _INDEXES[code]
        errors = []
        # 1) 东财（日线到分钟线）
        if info["em"]:
            try:
                return _em_bars(info["em"], interval, limit)
            except Exception as e:
                errors.append(f"东方财富：{e}")
        # 2) 腾讯（仅日线；美股三大指数）
        if info["tx"] and interval == "1d":
            try:
                return _tx_bars(info["tx"], limit)
            except Exception as e:
                errors.append(f"腾讯：{e}")
        # 3) Yahoo（日线到分钟线）
        if info["yh"]:
            try:
                from .yahoo import YahooSource
                return YahooSource().get_bars(info["yh"], interval, limit)
            except Exception as e:
                errors.append(f"Yahoo：{e}")
        raise ValueError(
            f"「{info['name']}」历史行情获取失败（{'；'.join(errors)}）。"
            "当前网络下该指数无可用免费数据源（东财/Yahoo 需正常网络，换台联网机器即可）；"
            "沙箱演示可用指数：上证 sh000001（A股源）、恒指 hkHSI（港股源）、美元指数 DINIW（外汇源）"
        )

    def get_quote(self, symbol: str):
        try:
            route = self._routed(symbol)
            if route:
                from .base import get_source, ensure_registered
                ensure_registered()
                src = get_source(route[0])
                if src is not None:
                    q = src.get_quote(route[1])
                    if q:
                        return q
            code = resolve_index(symbol)
            info = _INDEXES[code]
            # 腾讯实时（美股三大指数）
            if info["tx"]:
                text = _get_text(f"https://qt.gtimg.cn/q={info['tx']}", _TX_HEADERS, "gbk", timeout=8)
                if '="' in text:
                    parts = text.split('="', 1)[1].split("~")
                    if len(parts) >= 14 and parts[3]:
                        return {"symbol": code, "name": parts[1],
                                "price": round(float(parts[3]), 2),
                                "change_pct": round(float(parts[13]), 2) if len(parts) > 13 else 0.0,
                                "ts": parts[5] if len(parts) > 5 else time.strftime("%Y-%m-%d %H:%M:%S")}
            # 东财实时
            if info["em"]:
                data = json.loads(_get_text(
                    f"https://push2.eastmoney.com/api/qt/stock/get?secid={info['em']}"
                    "&fields=f43,f58,f86,f170", _HEADERS, timeout=8))
                d = data.get("data") or {}
                if d.get("f43") not in (None, "-"):
                    return {"symbol": code, "name": d.get("f58") or info["name"],
                            "price": round(float(d["f43"]) / 100.0, 2),
                            "change_pct": round(float(d.get("f170") or 0) / 100.0, 2),
                            "ts": time.strftime("%Y-%m-%d %H:%M:%S",
                                                time.localtime(int(d["f86"])) if d.get("f86") else time.localtime())}
        except ValueError:
            return None
        except Exception:
            return None
        return None

    def get_name(self, symbol: str) -> str:
        route = self._routed(symbol)
        if route:
            try:
                from .base import get_source, ensure_registered
                ensure_registered()
                src = get_source(route[0])
                if src is not None:
                    name = src.get_name(route[1])
                    if name and name != symbol:
                        return str(name)
            except Exception:
                pass
        code = resolve_index(symbol)
        return _INDEXES[code]["name"]
