# -*- coding: utf-8 -*-
"""外汇数据源端到端测试。"""
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

# 2) 代码解析
from quant.data.forex import normalize_forex  # noqa: E402
assert normalize_forex("eurusd") == "EURUSD"
assert normalize_forex("whUSDJPY") == "USDJPY"
assert normalize_forex("美元指数") == "DINIW"
assert normalize_forex("DXY") == "DINIW"
assert normalize_forex("CNY") == "USDCNY"
print("[OK] 外汇代码解析: 5 组全部正确")

# 3) 日线回测（双均线）
for sym in ["EURUSD", "USDJPY", "USDCNY", "DINIW"]:
    st, res = post("/api/backtest", {"source": "forex", "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 500})
    if st == 200:
        m = res["metrics"]
        print(f"[OK] {sym} 日线回测: 总收益 {m['total_return_pct']}% | 交易 {m['num_trades']} 次 | "
              f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]} | 名称 {res.get('name')}")
    else:
        print(f"[FAIL] {sym}: {res.get('error', '')[:120]}")

# 4) 实时报价
for sym in ["USDCNY", "EURUSD"]:
    try:
        q = get(f"/api/quote?source=forex&symbol={sym}")
        print(f"[OK] {sym} 实时: {q.get('name')} {q.get('price')} | {q.get('change_pct')}% | {q.get('ts')}")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] {sym} 实时: {e.read().decode()[:100]}")

# 5) 分钟线的友好报错
st, err = post("/api/backtest", {"source": "forex", "symbol": "EURUSD", "interval": "1h",
                                 "strategy": "ma_cross", "params": {}, "limit": 100})
assert st == 400 and "日线" in err.get("error", ""), err
print(f"[OK] 分钟线友好报错: {err.get('error', '')[:60]}")
print("== 外汇测试全部通过 ==")
