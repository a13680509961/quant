# -*- coding: utf-8 -*-
"""加密货币数据源端到端测试。"""
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
from quant.data.crypto import normalize_crypto  # noqa: E402
cases = {"BTC": ("BTC", "USDT"), "eth": ("ETH", "USDT"), "BTCUSDT": ("BTC", "USDT"),
         "BTC/USDT": ("BTC", "USDT"), "ETH-USDC": ("ETH", "USDC"), "sol": ("SOL", "USDT")}
for k, v in cases.items():
    assert normalize_crypto(k) == v, (k, normalize_crypto(k))
print("[OK] 加密货币代码解析: 6 组全部正确")

# 3) 日线回测（Gate 通道，沙箱可用）
for sym in ["BTC", "ETH", "SOL"]:
    st, res = post("/api/backtest", {"source": "crypto", "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 500})
    if st == 200:
        m = res["metrics"]
        print(f"[OK] {sym} 日线回测: 总收益 {m['total_return_pct']}% | 交易 {m['num_trades']} 次 | "
              f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]} | 名称 {res.get('name')}")
    else:
        print(f"[FAIL] {sym}: {res.get('error', '')[:120]}")

# 4) 分钟线回测（1小时/15分钟）
for sym, iv in [("BTC", "1h"), ("ETH", "15m")]:
    st, res = post("/api/backtest", {"source": "crypto", "symbol": sym, "interval": iv,
                                     "strategy": "macd_trend", "params": {"fast": 12, "slow": 26, "signal": 9},
                                     "limit": 500})
    if st == 200:
        m = res["metrics"]
        print(f"[OK] {sym} {iv}回测: 总收益 {m['total_return_pct']}% | 交易 {m['num_trades']} 次")
    else:
        print(f"[提示] {sym} {iv}: {res.get('error', '')[:100]}")

# 5) 实时报价
for sym in ["BTC", "DOGE"]:
    try:
        q = get(f"/api/quote?source=crypto&symbol={sym}")
        print(f"[OK] {sym} 实时: {q.get('name')} {q.get('price')} | {q.get('change_pct')}%")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] {sym} 实时: {e.read().decode()[:100]}")

# 6) 多空 + 杠杆回测（加密货币 7x24，适合趋势策略）
st, res = post("/api/backtest", {"source": "crypto", "symbol": "BTC", "interval": "1d",
                                 "strategy": "ma_cross_dual", "params": {"fast": 5, "slow": 20},
                                 "direction": "both", "leverage": 2, "limit": 500})
if st == 200:
    m = res["metrics"]
    print(f"[OK] BTC 多空+2倍杠杆: 总收益 {m['total_return_pct']}% | 空单 {m['short_trades']} 笔 | "
          f"强平 {m['margin_call_count']} 次")
print("== 加密货币测试全部通过 ==")
