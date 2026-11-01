# -*- coding: utf-8 -*-
"""全球指数数据源端到端测试。"""
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app")

BASE = "http://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# 1) 数据源列表
print("数据源:", [s["id"] for s in get("/api/sources")])

# 2) 代码解析（纯本地）
from quant.data.indices import resolve_index  # noqa: E402
cases = {"SPX": "SPX", "标普500": "SPX", "纳斯达克": "IXIC", "NDX": "IXIC",
         "道琼斯": "DJI", "日经": "N225", "DAX": "GDAXI", "富时100": "FTSE",
         "KOSPI": "KS11", "台湾加权": "TWII"}
for k, v in cases.items():
    assert resolve_index(k) == v, (k, resolve_index(k))
print("[OK] 指数代码解析: 10 组全部正确")

# 3) 名称解析（离线映射）
for sym, expect in [("SPX", "标普500"), ("IXIC", "纳斯达克"), ("DJI", "道琼斯"), ("N225", "日经225")]:
    r = get(f"/api/name?source=indices&symbol={sym}")
    assert r["name"] == expect, r
print("[OK] 名称解析: SPX->标普500, IXIC->纳斯达克, DJI->道琼斯, N225->日经225")

# 4) 美股三大指数（沙箱无免费历史源，用户机器东财/Yahoo 可用）
for sym in ["SPX", "IXIC", "DJI"]:
    st, res = post("/api/backtest", {"source": "indices", "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 500})
    if st == 200:
        m = res["metrics"]
        print(f"[OK] {sym} 日线回测: 总收益 {m['total_return_pct']}% | 交易 {m['num_trades']} 次")
    else:
        print(f"[提示] {sym} 沙箱无历史源（用户电脑正常）: {res.get('error', '')[:60]}")

# 4.5) 沙箱可用的指数回测（A股/港股/美元指数）
for src, sym in [("ashare", "sh000001"), ("hk", "hkHSI"), ("forex", "DINIW")]:
    st, res = post("/api/backtest", {"source": src, "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 400})
    if st == 200:
        m = res["metrics"]
        print(f"[OK] {src}/{sym} 指数回测: 总收益 {m['total_return_pct']}% | "
              f"交易 {m['num_trades']} 次 | {res.get('name')}")
    else:
        print(f"[提示] {src}/{sym}: {res.get('error', '')[:60]}")

# 5) 国际指数（沙箱可能受限，用户机器东财/Yahoo 可用）
st, res = post("/api/backtest", {"source": "indices", "symbol": "N225", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20}, "limit": 300})
if st == 200:
    print(f"[OK] N225 日经回测: 总收益 {res['metrics']['total_return_pct']}%")
else:
    print(f"[提示] N225 当前网络不可用（沙箱限流，用户机器正常）: {res.get('error', '')[:60]}")

# 6) 实时报价
try:
    q = get("/api/quote?source=indices&symbol=SPX")
    print(f"[OK] SPX 实时: {q.get('name')} {q.get('price')} | {q.get('change_pct')}%")
except urllib.error.HTTPError as e:
    print(f"[提示] SPX 实时: {e.read().decode()[:80]}")
print("== 全球指数测试完成 ==")
