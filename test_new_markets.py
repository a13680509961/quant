# -*- coding: utf-8 -*-
"""期货/基金/AI 策略生成 端到端测试（针对运行中的服务）。"""
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
sources = get("/api/sources")
print("数据源:", [(s["id"], s["intervals"]) for s in sources])

# 2) 期货日线回测：螺纹钢连续
_, res = post("/api/backtest", {"source": "futures", "symbol": "RB0", "interval": "1d",
                                "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                "limit": 500})
m = res["metrics"]
print(f"[OK] 螺纹钢RB0 日线: 总收益 {m['total_return_pct']}% | 交易 {m['num_trades']} 次 | "
      f"区间 {res['candles']['dates'][0]} ~ {res['candles']['dates'][-1]}")

# 3) 期货15分钟回测：沪深300股指连续
_, res2 = post("/api/backtest", {"source": "futures", "symbol": "IF0", "interval": "15m",
                                 "strategy": "breakout", "params": {"period": 20}, "limit": 800})
m2 = res2["metrics"]
print(f"[OK] 股指IF0 15m: 总收益 {m2['total_return_pct']}% | 交易 {m2['num_trades']} 次 | "
      f"K线 {len(res2['candles']['dates'])} 根")

# 4) 期货实时报价
q = get("/api/quote?source=futures&symbol=RB0")
print(f"[OK] RB0 实时: {q.get('name')} 价格 {q.get('price')} | 涨跌 {q.get('change_pct')}% | 持仓 {q.get('open_interest')}")

# 5) 基金净值回测：易方达消费 110022
_, res3 = post("/api/backtest", {"source": "fund", "symbol": "110022", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 20, "slow": 60},
                                 "limit": 800})
m3 = res3["metrics"]
print(f"[OK] 基金110022 净值日线: 总收益 {m3['total_return_pct']}% | 交易 {m3['num_trades']} 次 | "
      f"区间 {res3['candles']['dates'][0]} ~ {res3['candles']['dates'][-1]}")

# 6) 基金源 000001（华夏成长混合）
_, res4 = post("/api/backtest", {"source": "fund", "symbol": "000001", "interval": "1d",
                                 "strategy": "rsi_reversal", "params": {"period": 14, "oversold": 30, "overbought": 70},
                                 "limit": 500})
print(f"[OK] 基金000001: 总收益 {res4['metrics']['total_return_pct']}% | "
      f"区间 {res4['candles']['dates'][0]} ~ {res4['candles']['dates'][-1]}")

# 7) AI：无 Key 的友好报错
st, err = post("/api/generate_strategy", {"prompt": "双均线策略", "api_key": ""})
print(f"[OK] AI 无Key报错: {st} {err.get('error', '')[:80]}")

# 8) AI 代码校验（模拟大模型输出，纯本地）
from quant.ai_strategy import register_generated, validate_code  # noqa: E402

sample_code = '''import numpy as np

def strategy(df, fast=5, slow=20, stop_loss=0.05):
    f = df["close"].rolling(fast).mean()
    s = df["close"].rolling(slow).mean()
    pos = pd.Series(0, index=df.index, dtype=float)
    entry_price = 0.0
    for i in df.index:
        if i > 0 and pos.loc[i - 1] == 1:
            if df["close"].loc[i] < entry_price * (1 - stop_loss):
                pos.loc[i] = 0.0
                continue
        if f.loc[i] > s.loc[i]:
            if i == 0 or pos.loc[i - 1] == 0:
                entry_price = df["close"].loc[i]
            pos.loc[i] = 1.0
        else:
            pos.loc[i] = 0.0
    return pos

PARAMS = [
    {"key": "fast", "label": "快线周期", "type": "int", "default": 5, "min": 1, "max": 60, "step": 1},
    {"key": "slow", "label": "慢线周期", "type": "int", "default": 20, "min": 2, "max": 120, "step": 1},
    {"key": "stop_loss", "label": "止损比例", "type": "float", "default": 0.05, "min": 0.01, "max": 0.5, "step": 0.01},
]
'''
v = validate_code(sample_code)
assert v.get("ok"), f"校验失败: {v}"
print(f"[OK] AI 代码校验通过，参数 {len(v['params'])} 个")

# 9) 注册生成策略并用模拟数据回测（离线验证自定义策略全流程）
register_generated("ai_demo", "🤖 双均线+止损", sample_code, v["params"])
from quant.backtest import run_backtest  # noqa: E402
from quant.storage import MarketData  # noqa: E402
from quant.strategies import get_strategy  # noqa: E402

md = MarketData()
df = md.get_bars("synthetic", "SYN:测试股票", "1d", 500)
strat = get_strategy("ai_demo")
pos = strat["fn"](df)
res5 = run_backtest(df, pos, 100000, 0.0003, "1d")
print(f"[OK] AI自定义策略回测: 总收益 {res5['metrics']['total_return_pct']}% | "
      f"交易 {res5['metrics']['num_trades']} 次 | 最大回撤 {res5['metrics']['max_drawdown_pct']}%")

# 10) 校验恶意代码被拦截
bad = 'import os\ndef strategy(df):\n    os.system("dir")\n    return pd.Series(0, index=df.index)\nPARAMS = []\n'
vb = validate_code(bad)
assert not vb.get("ok"), "恶意代码应被拦截"
print(f"[OK] 恶意代码被拦截: {vb.get('error', '')[:60]}")
print("== 期货/基金/AI 测试全部通过 ==")
