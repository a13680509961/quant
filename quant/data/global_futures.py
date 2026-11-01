# -*- coding: utf-8 -*-
"""国际期货（外盘）数据源（新浪，需联网）：COMEX / NYMEX / CBOT / ICE 等。

标的：交易所英文代码（大写），如：
    GC  COMEX黄金     CL  NYMEX原油     SI  COMEX白银
    HG  COMEX铜       NG  NYMEX天然气    OIL 布伦特原油
支持周期：日线（外盘分钟线免费接口暂不可用）。
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request

import pandas as pd

from .base import DataSource

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://finance.sina.com.cn/",
}


def _get_text(url: str, encoding: str = "utf-8", timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"新浪外盘行情请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"新浪外盘行情网络不可用（{type(e).__name__}）") from e


class GlobalFuturesSource(DataSource):
    id = "global_futures"
    label = "国际期货（新浪外盘，需联网，日线）"
    requires_network = True
    intervals = ("1d",)
    hidden = True  # 已并入「期货」顶层源，仅作内部通道

    def default_symbols(self):
        return ["GC", "CL", "SI", "HG", "NG"]

    @staticmethod
    def resolve(symbol: str):
        s = symbol.strip().upper()
        if not re.match(r"^[A-Z]{1,6}$", s):
            raise ValueError(f"国际期货代码应为英文代码（如 GC、CL、SI），当前输入：{symbol}")
        return s

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        sym = self.resolve(symbol)
        if interval != "1d":
            raise ValueError("国际期货免费接口仅支持日线，请选择周期 1d")
        url = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_=/"
               f"GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={sym}")
        text = _get_text(url)
        s = text.find("(")
        e = text.rfind(")")
        if s < 0 or e <= s:
            raise ValueError(f"未获取到「{sym}」的外盘行情")
        import json
        arr = json.loads(text[s + 1:e])
        if not isinstance(arr, list) or not arr:
            raise ValueError(f"未获取到「{sym}」的外盘行情，请确认品种代码（如 GC、CL、SI、HG、NG）")
        rows = []
        for r in arr:
            rows.append({
                "date": str(r.get("date", ""))[:16],
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume") or 0),
            })
        df = pd.DataFrame(rows)
        return df.tail(int(limit)).reset_index(drop=True)

    def get_quote(self, symbol: str):
        try:
            sym = self.resolve(symbol)
            text = _get_text(f"https://hq.sinajs.cn/list=hf_{sym}", "gbk", timeout=8)
            if '="' not in text:
                return None
            parts = text.split('="', 1)[1].split(",")
            if len(parts) < 14 or not parts[0]:
                return None
            price = float(parts[0])
            prev = float(parts[4]) or price
            date = parts[12]
            tm = parts[6]
            ts = f"{date} {tm}" if len(date) == 10 else time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "symbol": symbol,
                "name": parts[13] if len(parts) > 13 else sym,
                "price": round(price, 3),
                "change": round(price - prev, 3),
                "change_pct": round((price - prev) / prev * 100, 2) if prev else 0.0,
                "ts": ts,
            }
        except ValueError:
            return None
        except Exception:
            return None
