# -*- coding: utf-8 -*-
"""两融（融资融券）数据：个股每日融资余额 / 融券余额 / 买卖额（东方财富数据中心）。"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://data.eastmoney.com/",
}

_cache: dict = {}  # (symbol, limit) -> (ts, result)


def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise ValueError(f"两融数据请求失败（HTTP {e.code}）") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ValueError(f"两融数据网络不可用（{type(e).__name__}）") from e


def get_margin_history(symbol: str, limit: int = 250) -> dict:
    """返回个股两融历史（升序）。

    返回字段：
        name 股票名称
        dates           日期列表
        rzye / rqye     融资余额 / 融券余额（元）
        rzrqye          两融余额合计
        rzmre / rzche   融资买入额 / 融资偿还额
        rzjme           融资净买入额
        rzyezb          融资余额占流通市值比（%）
        rqmcl           融券卖出量
    """
    s = (symbol or "").strip()
    if not (s.isdigit() and len(s) == 6):
        raise ValueError("两融数据仅支持 6 位 A股代码，如 600519")
    limit = max(30, min(int(limit), 500))
    key = (s, limit)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 300:
        return hit[1]

    f = urllib.parse.quote(f'(scode="{s}")')
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get"
           f"?reportName=RPTA_WEB_RZRQ_GGMX&columns=ALL&source=WEB&client=WEB"
           f"&filter={f}&pageNumber=1&pageSize={limit}"
           "&sortColumns=date&sortTypes=-1")
    data = _get_json(url)
    result = data.get("result") or {}
    rows = result.get("data") or []
    if not rows:
        raise ValueError(f"未获取到「{s}」的两融数据（可能该股不在融资融券标的范围内）")

    def col(r, *names):
        for nm in names:
            v = r.get(nm)
            if v is not None and str(v) not in ("-", ""):
                return float(v)
        return 0.0

    out = {
        "name": rows[0].get("SECNAME") or s,
        "dates": [],
        "rzye": [], "rqye": [], "rzrqye": [],
        "rzmre": [], "rzche": [], "rzjme": [], "rzyezb": [], "rqmcl": [],
    }
    for r in reversed(rows):  # 接口返回倒序，翻转为升序
        d = str(r.get("DATE") or "")[:10]
        out["dates"].append(d)
        out["rzye"].append(round(col(r, "RZYE") / 1e8, 3))       # 亿元
        out["rqye"].append(round(col(r, "RQYE") / 1e8, 3))
        out["rzrqye"].append(round(col(r, "RZRQYE") / 1e8, 3))
        out["rzmre"].append(round(col(r, "RZMRE") / 1e8, 3))
        out["rzche"].append(round(col(r, "RZCHE") / 1e8, 3))
        out["rzjme"].append(round(col(r, "RZJME") / 1e8, 3))
        out["rzyezb"].append(round(col(r, "RZYEZB"), 2))
        out["rqmcl"].append(round(col(r, "RQMCL") / 1e4, 2))     # 万股
    _cache[key] = (time.time(), out)
    return out
