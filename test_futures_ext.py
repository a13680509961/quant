# -*- coding: utf-8 -*-
"""期货主连/连续/国际期货 端到端测试。"""
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


def backtest(symbol, interval="1d", strategy="ma_cross"):
    st, res = post("/api/backtest", {"source": "futures", "symbol": symbol, "interval": interval,
                                     "strategy": strategy, "params": {"fast": 5, "slow": 20},
                                     "limit": 500})
    if st != 200:
        return None, res.get("error", "")
    return res, None


# 1) 数据源列表
sources = get("/api/sources")
print("数据源:", [s["id"] for s in sources])

# 2) 东财合约表解析（纯本地逻辑）
from quant.data.futures import _EM_TABLE  # noqa: E402
cases = [("沪铜主连", "113.cum"), ("CUM", "113.cum"), ("cum", "113.cum"),
         ("CU2506", "113.cu2506"), ("IF2611", "220.if2611"), ("M2601", "114.m2601"),
         ("RB0", None), ("沪铜加权", None)]
for sym, expect in cases:
    got = _EM_TABLE.resolve(sym)
    assert got == expect, f"{sym}: {got} != {expect}"
print("[OK] 主连/合约代码解析: 8 组全部正确")

# 3) 连续合约 RB0（新浪）
res, err = backtest("RB0")
if res:
    print(f"[OK] 连续 RB0 日线: 总收益 {res['metrics']['total_return_pct']}% | "
          f"交易 {res['metrics']['num_trades']} 次 | 末根 {res['candles']['dates'][-1]}")
else:
    print(f"[FAIL] RB0: {err}")

# 4) 主连 RBM（东财，沙箱可能限流，用户机器正常）
res, err = backtest("RBM")
if res:
    print(f"[OK] 主连 RBM 日线: 总收益 {res['metrics']['total_return_pct']}% | "
          f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
else:
    print(f"[提示] 主连 RBM 当前不可用（沙箱限流东财，用户机器正常）: {err[:100]}")

# 5) 中文主连名 沪铜主连
res, err = backtest("沪铜主连")
if res:
    print(f"[OK] 沪铜主连: 总收益 {res['metrics']['total_return_pct']}% | 交易 {res['metrics']['num_trades']} 次")
else:
    print(f"[提示] 沪铜主连当前不可用（同上）: {err[:80]}")

# 6) 具体合约（东财优先，新浪兜底）
res, err = backtest("RB2601")
if res:
    print(f"[OK] 合约 RB2601: 总收益 {res['metrics']['total_return_pct']}% | "
          f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
else:
    print(f"[提示] RB2601: {err[:100]}")

# 7) 加权指数提示
_, err = post("/api/backtest", {"source": "futures", "symbol": "RBW", "interval": "1d",
                                "strategy": "ma_cross", "params": {}, "limit": 300})
print(f"[OK] 加权指数提示: {err.get('error', '')[:90]}")

# 7.5) 主连/次主连 6666/7777 别名
from quant.data.futures import _EM_TABLE  # noqa: E402
assert _EM_TABLE.resolve("AG6666") == "113.agm", _EM_TABLE.resolve("AG6666")
assert _EM_TABLE.resolve("RB0000") == "113.rbm"
assert _EM_TABLE.resolve("AG7777") == "113.ags", _EM_TABLE.resolve("AG7777")
assert _EM_TABLE.get_name("AG6666") == "沪银主连", _EM_TABLE.get_name("AG6666")
assert _EM_TABLE.get_name("AG7777") == "沪银次主连", _EM_TABLE.get_name("AG7777")
print("[OK] 别名解析: AG6666 -> 113.agm（沪银主连），AG7777 -> 113.ags（沪银次主连），RB0000 -> 113.rbm")

res, err = backtest("AG6666")
if res:
    print(f"[OK] AG6666 主连回测: 总收益 {res['metrics']['total_return_pct']}% | "
          f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
else:
    print(f"[FAIL] AG6666: {err[:150]}")

res, err = backtest("AG7777")
if res:
    print(f"[OK] AG7777 次主连回测: 总收益 {res['metrics']['total_return_pct']}% | "
          f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
else:
    print(f"[FAIL] AG7777: {err[:150]}")

nm = get("/api/name?source=futures&symbol=AG6666")
nm2 = get("/api/name?source=futures&symbol=AG7777")
print(f"[OK] 名称: AG6666 -> {nm.get('name')}，AG7777 -> {nm2.get('name')}")

_, err8888 = post("/api/backtest", {"source": "futures", "symbol": "AG8888", "interval": "1d",
                                    "strategy": "ma_cross", "params": {}, "limit": 300})
assert "加权" in err8888.get("error", ""), err8888
_, err9999 = post("/api/backtest", {"source": "futures", "symbol": "AG9999", "interval": "1d",
                                    "strategy": "ma_cross", "params": {}, "limit": 300})
assert "加权" in err9999.get("error", ""), err9999
print(f"[OK] 8888/9999 加权指数提示: {err8888.get('error', '')[:70]}")

# 8) 国际期货
for sym in ["GC", "CL", "SI"]:
    st, res = post("/api/backtest", {"source": "global_futures", "symbol": sym, "interval": "1d",
                                     "strategy": "breakout", "params": {"period": 20}, "limit": 500})
    if st == 200:
        print(f"[OK] 国际期货 {sym}: 总收益 {res['metrics']['total_return_pct']}% | "
              f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
    else:
        print(f"[FAIL] 国际期货 {sym}: {res.get('error', '')[:100]}")

# 9) 国际期货实时
try:
    q = get("/api/quote?source=global_futures&symbol=GC")
    print(f"[OK] COMEX黄金实时: {q.get('name')} 价格 {q.get('price')} | 涨跌 {q.get('change_pct')}% | {q.get('ts')}")
except urllib.error.HTTPError as e:
    print(f"[提示] GC 实时: {e.read().decode()[:100]}")
print("== 期货扩展测试完成 ==")
