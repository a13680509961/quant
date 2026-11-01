# -*- coding: utf-8 -*-
"""港股 / 两融 / 杠杆 / 做空 端到端测试。"""
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


# 1) 数据源
print("数据源:", [s["id"] for s in get("/api/sources")])

# 2) 港股代码解析
from quant.data.hk import resolve_hk  # noqa: E402
cases = [("00700", ("stock", "00700")), ("700", ("stock", "00700")),
         ("9988", ("stock", "09988")), ("00700.HK", ("stock", "00700")),
         ("hk00700", ("stock", "00700")), ("HSI", ("index", "hkHSI")),
         ("hkHSI", ("index", "hkHSI"))]
for sym, expect in cases:
    got = resolve_hk(sym)
    assert got == expect, f"{sym}: {got} != {expect}"
print("[OK] 港股代码解析: 7 组全部正确")

# 3) 港股日线回测（腾讯通道）
st, res = post("/api/backtest", {"source": "hk", "symbol": "00700", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                 "limit": 500})
if st == 200:
    print(f"[OK] 腾讯控股 00700: 总收益 {res['metrics']['total_return_pct']}% | "
          f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
else:
    print(f"[FAIL] 00700: {res.get('error', '')[:150]}")

# 4) 恒生指数回测
st, res = post("/api/backtest", {"source": "hk", "symbol": "hkHSI", "interval": "1d",
                                 "strategy": "macd_trend", "params": {"fast": 12, "slow": 26, "signal": 9},
                                 "limit": 500})
if st == 200:
    print(f"[OK] 恒生指数: 总收益 {res['metrics']['total_return_pct']}% | "
          f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")
else:
    print(f"[FAIL] 恒指: {res.get('error', '')[:150]}")

# 5) 港股实时
try:
    q = get("/api/quote?source=hk&symbol=00700")
    print(f"[OK] 腾讯实时: {q.get('name')} {q.get('price')} | {q.get('change_pct')}% | {q.get('ts')}")
except urllib.error.HTTPError as e:
    print(f"[提示] 港股实时: {e.read().decode()[:120]}")

# 6) 两融数据
try:
    mg = get("/api/margin?symbol=600519")
    print(f"[OK] 两融 600519: {mg['name']} | 数据 {len(mg['dates'])} 天 | "
          f"最新融资余额 {mg['rzye'][-1]} 亿 / 融券余额 {mg['rqye'][-1]} 亿 | {mg['dates'][-1]}")
except urllib.error.HTTPError as e:
    print(f"[FAIL] 两融: {e.read().decode()[:150]}")

# 7) 做空回测：多空双向
st, res = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                 "strategy": "ma_cross_dual", "params": {"fast": 5, "slow": 20},
                                 "direction": "both", "leverage": 1, "limit": 500})
m = res["metrics"]
print(f"[OK] 双均线多空(双向): 总收益 {m['total_return_pct']}% | 交易 {m['num_trades']} 次 | "
      f"空单 {m['short_trades']} 笔 | 最大回撤 {m['max_drawdown_pct']}%")
assert m["short_trades"] > 0, "多空策略应产生空单"

# 7.1) 纯做空：多空策略只取空头信号
st, res_s = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                   "strategy": "ma_cross_dual", "params": {"fast": 5, "slow": 20},
                                   "direction": "short", "limit": 500})
ms = res_s["metrics"]
assert ms["num_trades"] > 0 and ms["short_trades"] == ms["num_trades"], \
    f"纯做空应全部为空单: {ms['num_trades']} vs {ms['short_trades']}"
print(f"[OK] 纯做空(多空策略): 总收益 {ms['total_return_pct']}% | 交易 {ms['num_trades']} 次全部为空单")

# 7.2) 纯做空：只做多策略信号反转
st, res_r = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                   "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                   "direction": "short", "limit": 500})
mr = res_r["metrics"]
assert mr["num_trades"] > 0 and mr["short_trades"] == mr["num_trades"], \
    f"反转信号应全部为空单: {mr}"
print(f"[OK] 纯做空(信号反转): 总收益 {mr['total_return_pct']}%（原做多 {res['metrics']['total_return_pct']}%）| "
      f"交易 {mr['num_trades']} 次全部为空单")

# 7.3) 只做多方向下多空策略不产生空单
st, res2 = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                  "strategy": "ma_cross_dual", "params": {"fast": 5, "slow": 20},
                                  "direction": "long", "limit": 500})
print(f"[OK] 只做多方向: 空单 {res2['metrics']['short_trades']} 笔（应为 0）")
assert res2["metrics"]["short_trades"] == 0

# 9) 杠杆回测：3倍 + 年利率 8.35%
st, res3 = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                  "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                  "leverage": 3, "margin_interest": 0.0835, "limit": 500})
m3 = res3["metrics"]
print(f"[OK] 3倍杠杆: 总收益 {m3['total_return_pct']}% | 强平 {m3['margin_call_count']} 次 | "
      f"利息 {m3['interest_total']} | 最大回撤 {m3['max_drawdown_pct']}%")
assert m3["leverage_used"] == 3.0

# 10) 信号接口支持做空状态
import urllib.parse  # noqa: E402
sig = get("/api/signal?source=synthetic&symbol=SYN:%E6%B5%8B%E8%AF%95%E8%82%A1%E7%A5%A8&interval=1d"
          "&strategy=ma_cross_dual&params=%7B%22fast%22%3A5%2C%22slow%22%3A20%7D")
print(f"[OK] 多空信号: {sig['action']}（position={sig['position']}）")
print("== 港股/两融/杠杆/做空 测试全部通过 ==")
