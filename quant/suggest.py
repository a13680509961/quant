# -*- coding: utf-8 -*-
"""标的名称搜索（腾讯 smartbox）与名称解析。"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
    "Referer": "https://gu.qq.com/",
}

# 建议类型白名单（过滤权证等衍生品）
_TYPE_OK = {"GP", "ZS", "ETF", "GP-A", "GP-A-KCB", "GP-B", "FUND", ""}


def _get(text: str):
    req = urllib.request.Request(text, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("gbk", "replace")


def _decode_name(raw: str) -> str:
    """smartbox 返回的 unicode 转义（反斜杠uXXXX）还原为中文。"""
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw


def _map_item(market: str, code: str, name: str, typ: str):
    if market in ("sh", "sz"):
        return {"source": "ashare", "symbol": f"{market}{code}",
                "name": name, "market": market, "type": typ}
    if market == "bj":
        return {"source": "ashare", "symbol": code,
                "name": name, "market": "bj", "type": typ}
    if market == "hk":
        return {"source": "hk", "symbol": code,
                "name": name, "market": "hk", "type": typ}
    if market == "us":
        base = code.split(".")[0].upper()  # 去掉 .oq/.n/.ps/.am 交易所后缀
        return {"source": "yahoo", "symbol": base,
                "name": name, "market": "us", "type": typ}
    return None


def suggest(q: str, limit: int = 10) -> list:
    """按名称/代码/拼音搜索标的，返回 [{source, symbol, name, market, type}]。"""
    q = (q or "").strip()
    if not q:
        return []
    try:
        text = _get(f"https://smartbox.gtimg.cn/s3/?v=2&q={urllib.parse.quote(q)}&t=all&c=1")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return []  # 搜索失败静默返回空

    out = []
    m = re.search(r'v_hint="([^"]*)"', text)
    for it in (m.group(1).split("^") if m else []):
        p = it.split("~")
        if len(p) < 3:
            continue
        market, code, name = p[0], p[1], _decode_name(p[2])
        typ = p[4] if len(p) > 4 else ""
        if typ and typ not in _TYPE_OK:
            continue
        item = _map_item(market, code, name, typ)
        if item:
            out.append(item)

    # 类别提示（期货品种等）
    cm = re.search(r'v_cate_hint="([^"]*)"', text)
    for it in (cm.group(1).split("^") if cm else []):
        p = it.split("~")
        if len(p) >= 2 and p[0].startswith("qh_"):
            letters = p[0][3:]
            out.insert(0, {
                "source": "futures",
                "symbol": letters.upper() + "0",
                "name": _decode_name(p[1]),
                "market": p[0],
                "type": "期货",
            })
    return out[:limit]
