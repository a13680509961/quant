# -*- coding: utf-8 -*-
"""国内期货数据源：东方财富（主连/次主连/具体合约）+ 新浪（连续/具体合约）双通道。

标的写法：
    RB0            连续合约（新浪，成交量加权拼接，最常用的回测序列）
    RBM / 沪铜主连   主力连续（东财，跟随成交/持仓最大的合约自动换月）
    CUS / 沪铜次主连 次主力连续（东财）
    CU2506 / RB2601 具体合约（东财优先，失败自动走新浪）
    IF0            中金所股指连续

说明：免费行情源不提供现成的"加权指数"（那是文华/博易等付费终端的品种指数），
研究时通常用主连或连续替代；如需加权指数可后续基于交易所原始合约数据自行计算。
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://finance.sina.com.cn/",
}
_EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://quote.eastmoney.com/",
}

_FEW_MIN = {"1h": 60, "15m": 15, "1m": 1}
_EM_KLT = {"1d": 101, "1h": 60, "15m": 15, "1m": 1}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")


def _get_text(url: str, headers: dict, encoding: str = "utf-8", timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"网络不可用（{type(e).__name__}）") from e


def _get_json(url: str, headers: dict, timeout: int = 15, retries: int = 3) -> dict:
    last_err = None
    for attempt in range(retries):
        try:
            return json.loads(_get_text(url, headers, "utf-8", timeout))
        except ValueError as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    raise last_err


def _parse_jsonp(text: str):
    s = text.find("(")
    e = text.rfind(")")
    if s < 0 or e <= s:
        raise ValueError("行情返回格式异常")
    obj = json.loads(text[s + 1:e])
    if isinstance(obj, dict) and obj.get("__ERROR") is not None:
        raise ValueError("接口未返回数据，请确认品种代码")
    return obj


# ===========================================================================
# 东财期货合约表（主连/次主连/具体合约 -> secid）
# ===========================================================================
class _EmTable:
    """惰性加载东财期货合约表（futsse-static 接口），带磁盘缓存（1 天）。"""

    CACHE = os.path.join(DATA_DIR, "futures_em.json")

    def __init__(self):
        self._name2sec: dict = {}
        self._code2sec: dict = {}
        self._code2name: dict = {}
        self._variety2mkt: dict = {}
        self._variety2name: dict = {}
        self._loaded = False
        self._lock = threading.Lock()

    def load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self._load_cache():
                self._loaded = True
                return
            try:
                markets = _get_json("https://futsse-static.eastmoney.com/redis?msgid=gnweb", _EM_HEADERS)
                mktids = [str(m.get("mktid")) for m in markets]

                def fetch_market(mktid):
                    items = []
                    for num in range(1, 80):
                        try:
                            page = _get_json(
                                f"https://futsse-static.eastmoney.com/redis?msgid={mktid}_{num}",
                                _EM_HEADERS, timeout=10, retries=1,
                            )
                        except Exception:
                            break
                        if not page:
                            break
                        items.extend(page)
                    return items

                all_items = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                    for items in ex.map(fetch_market, mktids):
                        all_items.extend(items)
                for it in all_items:
                    name = it.get("name") or ""
                    code = (it.get("code") or "").lower()
                    mktid = str(it.get("mktid"))
                    vcode = (it.get("vcode") or "").lower()
                    vname = it.get("vname") or ""
                    if name and code:
                        self._name2sec[name] = f"{mktid}.{code}"
                        self._code2sec[code] = f"{mktid}.{code}"
                        self._code2name[code] = name
                    if vcode and mktid:
                        self._variety2mkt.setdefault(vcode, mktid)
                    if vcode and vname:
                        self._variety2name.setdefault(vcode, vname)
                self._save_cache()
            except Exception:
                pass
            self._loaded = True

    def _load_cache(self) -> bool:
        try:
            with open(self.CACHE, encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - data.get("ts", 0) < 86400:
                self._name2sec = data.get("name2sec", {})
                self._code2sec = data.get("code2sec", {})
                self._code2name = data.get("code2name", {})
                self._variety2mkt = data.get("variety2mkt", {})
                self._variety2name = data.get("variety2name", {})
                # 旧版缓存缺少名称映射时视为失效，强制重新拉取
                return bool(self._name2sec) and bool(self._code2name)
        except Exception:
            pass
        return False

    def _save_cache(self) -> None:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(self.CACHE, "w", encoding="utf-8") as f:
                json.dump({
                    "ts": time.time(),
                    "name2sec": self._name2sec,
                    "code2sec": self._code2sec,
                    "code2name": self._code2name,
                    "variety2mkt": self._variety2mkt,
                    "variety2name": self._variety2name,
                }, f, ensure_ascii=False)
        except Exception:
            pass

    def resolve(self, symbol: str):
        """返回 secid 或 None（None 表示不是东财代码，走新浪通道）。

        支持别名：XX6666 / XX0000 -> 主连（variety+"m"），XX7777 -> 次主连（variety+"s"），
        XX0 -> 新浪连续；XX8888/XX9999（加权指数）无免费源，由上层给出提示。
        """
        s = symbol.strip()
        low = s.lower()
        if s in self._name2sec:
            return self._name2sec[s]
        if low in self._code2sec:
            return self._code2sec[low]
        m = re.match(r"^([A-Za-z]{1,4})(\d{3,4})$", s)
        if m:
            variety, digits = m.group(1).lower(), m.group(2)
            if digits == "0":
                return None  # "0" 是新浪连续约定，无需加载合约表
            if digits in ("6666", "0000"):  # 主连别名（文华/同花顺风格）
                self.load()
                mkt = self._variety2mkt.get(variety)
                if mkt:
                    return f"{mkt}.{variety}m"
                return None
            if digits == "7777":  # 次主力连续（TickDB/同花顺风格）
                self.load()
                mkt = self._variety2mkt.get(variety)
                if mkt:
                    return f"{mkt}.{variety}s"
                return None
            self.load()
            mkt = self._variety2mkt.get(variety)
            if mkt:
                return f"{mkt}.{variety}{digits}"
            return None
        # 中文名（沪铜主连）或纯字母代码（CUM）
        if s.isalpha() or any("\u4e00" <= ch <= "\u9fff" for ch in s):
            self.load()
            if s in self._name2sec:
                return self._name2sec[s]
            if low in self._code2sec:
                return self._code2sec[low]
        return None

    def get_name(self, symbol: str) -> str:
        """东财合约表反向查名称（CUM -> 沪铜主连，AG6666 -> 沪银主连，AG7777 -> 沪银次主连）。"""
        self.load()
        s = symbol.strip()
        if s in self._name2sec:
            return s
        low = s.lower()
        if low in self._code2name:
            return self._code2name[low]
        m = re.match(r"^([A-Za-z]{1,4})(\d{3,4})$", s)
        if m:
            variety, digits = m.group(1).lower(), m.group(2)
            vn = self._variety2name.get(variety)
            if vn:
                if digits in ("6666", "0000"):
                    return f"{vn}主连"
                if digits == "7777":
                    return f"{vn}次主连"
                return f"{vn}{digits}"
        return s


_EM_TABLE = _EmTable()


# ===========================================================================
# 通道：东方财富（主连/次主连/具体合约）
# ===========================================================================
class EastmoneyFuturesProvider(DataSource):
    id = "em_futures"
    label = "东方财富期货"
    provider_name = "东方财富"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        secid = _EM_TABLE.resolve(symbol)
        if not secid:
            raise ValueError(f"东方财富无法识别期货代码 {symbol}")
        klt = _EM_KLT.get(interval, 101)
        url = (
            "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={secid}&klt={klt}&fqt=1&lmt={int(limit)}&end=20500101"
            "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
        )
        data = _get_json(url, _EM_HEADERS, retries=2)
        d = data.get("data") or {}
        klines = d.get("klines") or []
        if not klines:
            raise ValueError(f"东财未返回「{symbol}」行情（请确认合约存在）")
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
        return df.tail(int(limit)).reset_index(drop=True)

    def get_name(self, symbol: str) -> str:
        return _EM_TABLE.get_name(symbol)

    def get_quote(self, symbol: str):
        try:
            secid = _EM_TABLE.resolve(symbol)
            if not secid:
                return None
            data = _get_json(
                f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}"
                "&fields=f43,f58,f59,f86,f169,f170",
                _EM_HEADERS, timeout=8, retries=1,
            )
            d = data.get("data") or {}
            raw = d.get("f43")
            if raw in (None, "-"):
                return None
            price = float(raw)
            divisor = 10 ** max(int(d.get("f59") or 2), 1)
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
        except Exception:
            return None


# ===========================================================================
# 通道：新浪（连续 / 具体合约）
# ===========================================================================
class SinaFuturesProvider(DataSource):
    id = "sina_futures"
    label = "新浪期货"
    provider_name = "新浪"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")

    @staticmethod
    def resolve(symbol: str):
        s = symbol.strip().upper()
        if not re.match(r"^[A-Z]{1,4}\d{1,4}$", s):
            raise ValueError(f"期货代码格式错误：{symbol}（连续合约如 RB0，具体合约如 RB2601）")
        return s

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        sym = self.resolve(symbol)
        base = "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_=/"
        if interval == "1d":
            url = base + f"InnerFuturesNewService.getDailyKLine?symbol={sym}"
        elif interval in _FEW_MIN:
            url = base + f"InnerFuturesNewService.getFewMinLine?symbol={sym}&type={_FEW_MIN[interval]}"
        else:
            raise ValueError(f"新浪期货不支持周期 {interval}")
        arr = _parse_jsonp(_get_text(url, _HEADERS))
        if not arr:
            raise ValueError(f"新浪未返回「{sym}」行情")
        rows = []
        for r in arr:
            rows.append({
                "date": str(r.get("d", ""))[:16],
                "open": float(r["o"]),
                "high": float(r["h"]),
                "low": float(r["l"]),
                "close": float(r["c"]),
                "volume": float(r.get("v") or 0),
            })
        df = pd.DataFrame(rows)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            sym = self.resolve(symbol)
            text = _get_text(f"https://hq.sinajs.cn/list=nf_{sym}", _HEADERS, "gbk", timeout=8)
            if '="' not in text:
                return None
            parts = text.split('="', 1)[1].split(",")
            if len(parts) < 18 or not parts[8]:
                return None
            price = float(parts[8])
            prev = float(parts[10]) or float(parts[5]) or price
            tm = parts[1]
            ts = f"{parts[17]} {tm[:2]}:{tm[2:4]}:{tm[4:6]}" if len(tm) >= 6 else time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "symbol": symbol,
                "name": parts[0],
                "price": round(price, 3),
                "change": round(price - prev, 3),
                "change_pct": round((price - prev) / prev * 100, 2) if prev else 0.0,
                "open_interest": parts[13],
                "ts": ts,
            }
        except ValueError:
            return None
        except Exception:
            return None


# ===========================================================================
# 国内期货统一入口（东财优先，新浪兜底）
# ===========================================================================
class CnFuturesSource(DataSource):
    id = "cn_futures"
    label = "国内期货（主连/连续/合约，需联网）"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")
    hidden = True  # 已并入「期货」顶层源，仅作内部通道

    def __init__(self):
        self._em = EastmoneyFuturesProvider()
        self._sina = SinaFuturesProvider()

    def default_symbols(self):
        return ["RB0", "AG6666", "AG7777", "沪铜主连", "IF0"]

    @staticmethod
    def resolve(symbol: str):
        return symbol.strip()

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        s = symbol.strip()
        m = re.match(r"^([A-Za-z]{1,4})(\d{1,4})$", s)
        letters = m.group(1).upper() if m else ""
        digits = m.group(2) if m else ""

        if m and digits in ("8888", "9999"):
            raise ValueError(
                "免费行情源暂无「加权指数/加权连续」（8888/9999 是文华、同花顺等终端的指数约定）；"
                "研究请用主连（如 AG6666）、次主连（如 AG7777）或连续（如 AG0）替代"
            )

        # 主连/次主连别名（XX6666 / XX0000 / XX7777）：东财优先，新浪连续兜底
        if m and digits in ("6666", "0000", "7777"):
            errors = []
            if _EM_TABLE.resolve(s):
                try:
                    df = self._em.get_bars(s, interval, limit)
                    if df is not None and len(df):
                        return df
                    errors.append("东方财富：未返回数据")
                except Exception as e:
                    errors.append(f"东方财富：{e}")
            try:
                return self._sina.get_bars(letters + "0", interval, limit)
            except Exception as e:
                errors.append(f"新浪：{e}")
            raise ValueError(f"「{s}」行情获取失败（{'；'.join(errors)}）。请检查网络后重试")

        em_secid = _EM_TABLE.resolve(s)
        sina_ok = bool(m)
        errors = []
        if em_secid:
            try:
                df = self._em.get_bars(s, interval, limit)
                if df is not None and len(df):
                    return df
                errors.append("东方财富：未返回数据")
            except Exception as e:
                errors.append(f"东方财富：{e}")
        if sina_ok:
            try:
                return self._sina.get_bars(s, interval, limit)
            except Exception as e:
                errors.append(f"新浪：{e}")
        if not em_secid and not sina_ok:
            raise ValueError(
                f"无法识别期货代码「{symbol}」。可用写法：主连 RBM / 沪铜主连 / AG6666，连续 RB0，"
                "具体合约 CU2506；注意：免费行情源暂无「加权指数」"
            )
        raise ValueError(f"期货行情获取失败（{'；'.join(errors)}）。请检查网络或换代码（主连如 AG6666，连续如 RB0）")

    def get_quote(self, symbol: str):
        s = symbol.strip()
        m = re.match(r"^([A-Za-z]{1,4})(\d{1,4})$", s)
        if m and m.group(2) in ("6666", "0000", "7777"):  # 主连/次主连别名
            if _EM_TABLE.resolve(s):
                q = self._em.get_quote(s)
                if q:
                    return q
            return self._sina.get_quote(m.group(1) + "0")
        if _EM_TABLE.resolve(s):
            q = self._em.get_quote(s)
            if q:
                return q
        if m:
            return self._sina.get_quote(s)
        return None

    def get_name(self, symbol: str) -> str:
        s = symbol.strip()
        m = re.match(r"^([A-Za-z]{1,4})(\d{1,4})$", s)
        if m:
            letters, digits = m.group(1).upper(), m.group(2)
            if digits == "0":  # 连续合约（XX0）直接走新浪，无需加载东财合约表
                q = self._sina.get_quote(s)
                if q and q.get("name"):
                    return str(q["name"])
                return s
            if digits in ("6666", "0000", "7777"):  # 主连/次主连别名
                if _EM_TABLE.resolve(s):
                    n = _EM_TABLE.get_name(s)
                    if n and n != s:
                        return n
                q = self._sina.get_quote(letters + "0")
                if q and q.get("name"):
                    return str(q["name"])
                return s
        # 东财代码优先用合约表名称（CUM -> 沪铜主连）
        if _EM_TABLE.resolve(s):
            n = _EM_TABLE.get_name(s)
            if n and n != s:
                return n
        # 新浪通道（RB2601 等具体合约）
        if m:
            q = self._sina.get_quote(s)
            if q and q.get("name"):
                return str(q["name"])
        return s


# ===========================================================================
# 期货顶层源（国内 + 国际自动路由）
# ===========================================================================
class FuturesSource(DataSource):
    id = "futures"
    label = "期货（国内/国际，需联网）"
    requires_network = True
    intervals = ("1d", "1h", "15m", "1m")

    def __init__(self):
        self._cn = CnFuturesSource()
        self._global = None  # 惰性加载

    def default_symbols(self):
        return ["RB0", "AG6666", "GC", "CL", "IF0"]

    @staticmethod
    def resolve(symbol: str):
        return symbol.strip()

    def _cn_like(self, symbol: str) -> bool:
        s = symbol.strip()
        return bool(re.match(r"^[A-Za-z]{1,4}\d{1,4}$", s)) or \
            any("\u4e00" <= ch <= "\u9fff" for ch in s) or s.isalpha()

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        s = symbol.strip()
        errors = []
        # 国内优先（带数字/中文/纯字母主连代码）
        if self._cn_like(s):
            try:
                return self._cn.get_bars(s, interval, limit)
            except Exception as e:
                errors.append(f"国内期货：{e}")
        # 国际（GC/CL/SI/HG/NG/OIL 等纯字母外盘品种）
        try:
            from .global_futures import GlobalFuturesSource
            if self._global is None:
                self._global = GlobalFuturesSource()
            return self._global.get_bars(s, interval, limit)
        except Exception as e:
            errors.append(f"国际期货：{e}")
        raise ValueError(
            f"期货行情获取失败（{'；'.join(errors)}）。国内写法 RB0/AG6666/CU2506，国际写法 GC/CL/SI/HG/NG"
        )

    def get_quote(self, symbol: str):
        s = symbol.strip()
        if self._cn_like(s):
            q = self._cn.get_quote(s)
            if q:
                return q
        try:
            from .global_futures import GlobalFuturesSource
            if self._global is None:
                self._global = GlobalFuturesSource()
            return self._global.get_quote(s)
        except Exception:
            return None

    def get_name(self, symbol: str) -> str:
        s = symbol.strip()
        if self._cn_like(s):
            n = self._cn.get_name(s)
            if n and n != s:
                return n
        try:
            from .global_futures import GlobalFuturesSource
            if self._global is None:
                self._global = GlobalFuturesSource()
            return self._global.get_name(s)
        except Exception:
            return s
