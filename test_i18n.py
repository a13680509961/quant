# -*- coding: utf-8 -*-
"""多语言后端元数据 + 前端双语渲染验证。"""
import json
import os
import subprocess
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


# 1) 数据源带 label_en
sources = get("/api/sources")
assert all("label_en" in s and s["label_en"] for s in sources), sources
print("[OK] 数据源 label_en:", {s["id"]: s["label_en"] for s in sources[:4]})

# 2) 策略带 label_en 与参数 label_en
strats = get("/api/strategies")
assert all("label_en" in s for s in strats), strats
assert all("label_en" in p for s in strats for p in s["params"])
print("[OK] 策略 label_en:", {s["name"]: s["label_en"] for s in strats[:3]})

# 3) 回测响应带 label_en / action_code / side_code
res = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                             "strategy": "ma_cross_dual", "params": {"fast": 5, "slow": 20},
                             "direction": "both", "limit": 300})
assert "label_en" in res["strategy"], res["strategy"]
assert "action_code" in res["signal"], res["signal"]
assert res["trades"] and all("side_code" in td for td in res["trades"]), res["trades"][:1]
print(f"[OK] 回测元数据: 策略EN={res['strategy']['label_en']} | "
      f"信号 action_code={res['signal']['action_code']} | 首笔 side_code={res['trades'][0]['side_code']}")

# 4) 前端双语渲染（headless dump-dom）
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def dump(lang):
    out = os.path.join(r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app",
                       f"dom_{lang}.html")
    with open(out, "w", encoding="utf-8") as f:
        subprocess.run(
            [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=12000", "--dump-dom",
             f"http://127.0.0.1:8000/?lang={lang}"],
            stdout=f, stderr=subprocess.DEVNULL, timeout=120,
        )
    with open(out, encoding="utf-8") as f:
        return f.read()


zh = dump("zh")
en = dump("en")

assert ">总收益<" in zh and "量化分析工作台" in zh, "中文渲染缺失"
assert ">Total Return<" in en, "英文渲染缺失：Total Return"
assert "▶ Run Backtest" in en and ">Strategy<" in en, "英文按钮/策略缺失"
assert ">总收益<" not in en, "英文页指标名仍是中文"
print("[OK] 中文渲染: 总收益/量化分析工作台 正常")
print("[OK] 英文渲染: Total Return / Run Backtest / Strategy 正常，指标名已翻译")

# 5) 指标数据与图例不受影响
m = json.dumps(res.get("indicators", {}))
assert "kdj" in m and "macd" in m
print("[OK] 指标序列仍完整")
print("== 多语言验证全部通过 ==")
