# -*- coding: utf-8 -*-
"""数据源合并后的组织验证：股票/期货/指数路由 + 下拉框清爽。"""
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


# 1) 界面可见的数据源（应为 7 个大类）
sources = get("/api/sources")
ids = [s["id"] for s in sources]
print("界面数据源（", len(ids), "个）:", ids)
assert ids == ["synthetic", "stocks", "futures", "fund", "forex", "indices", "crypto"], ids

# 2) 股票源路由：A股/港股/美股
cases = [("600519", "贵州茅台"), ("sh000001", "上证指数"), ("00700", "腾讯控股"), ("AAPL", None)]
for sym, expect in cases:
    st, res = post("/api/backtest", {"source": "stocks", "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 300})
    if st == 200:
        name = res.get("name")
        if expect:
            assert name == expect, (sym, name)
        print(f"[OK] 股票源 {sym}: 回测正常 | {name} | "
              f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
    else:
        print(f"[提示] 股票源 {sym}: {res.get('error', '')[:70]}")

# 3) 期货源路由：国内/国际
for sym in ["RB0", "AG6666", "GC", "CL"]:
    st, res = post("/api/backtest", {"source": "futures", "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 400})
    if st == 200:
        print(f"[OK] 期货源 {sym}: 总收益 {res['metrics']['total_return_pct']}% | {res.get('name')}")
    else:
        print(f"[提示] 期货源 {sym}: {res.get('error', '')[:70]}")

# 4) 指数源路由：上证/恒指/美元指数/标普
for sym, expect in [("sh000001", "上证指数"), ("hkHSI", "恒生指数"), ("DINIW", "美元指数")]:
    st, res = post("/api/backtest", {"source": "indices", "symbol": sym, "interval": "1d",
                                     "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                     "limit": 400})
    if st == 200:
        assert res.get("name") == expect, (sym, res.get("name"))
        print(f"[OK] 指数源 {sym}: 总收益 {res['metrics']['total_return_pct']}% | {res.get('name')}")
    else:
        print(f"[提示] 指数源 {sym}: {res.get('error', '')[:70]}")

# 5) 旧源 ID 仍兼容（内部通道）
st, res = post("/api/backtest", {"source": "ashare", "symbol": "600519", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20}, "limit": 300})
assert st == 200, res
print(f"[OK] 旧源ID ashare 兼容: {res.get('name')}")
print("== 数据源合并验证通过 ==")
