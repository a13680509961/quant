# -*- coding: utf-8 -*-
"""名称搜索 / 名称解析 / 自由日期区间回测 测试。"""
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app")

BASE = "http://127.0.0.1:8000"


def get(path, timeout=120):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# 1) 名称搜索
s = get("/api/suggest?q=" + urllib.request.quote("茅台"))
assert any(x["name"] == "贵州茅台" for x in s), s
print("[OK] 搜索「茅台」:", [(x["name"], x["symbol"], x["source"]) for x in s[:3]])

s2 = get("/api/suggest?q=" + urllib.request.quote("腾讯"))
hk = [x for x in s2 if x["source"] == "hk" and x["symbol"] == "00700"]
assert hk, s2
print("[OK] 搜索「腾讯」含港股 00700:", hk[0]["name"])

s3 = get("/api/suggest?q=" + urllib.request.quote("螺纹"))
assert any(x["source"] == "futures" for x in s3), s3
print("[OK] 搜索「螺纹」含期货:", [(x["symbol"], x["name"]) for x in s3 if x["source"] == "futures"][:2])

# 2) 名称解析
cases = [
    ("ashare", "600519", "贵州茅台"),
    ("hk", "00700", "腾讯控股"),
    ("futures", "RB0", None),       # 应为"螺纹钢连续"之类
    ("futures", "CUM", None),       # 应为"沪铜主连"
    ("fund", "110022", "易方达消费行业股票"),
    ("global_futures", "GC", None), # 应为"纽约黄金"
]
for src, sym, expect in cases:
    r = get(f"/api/name?source={src}&symbol={urllib.request.quote(sym)}")
    name = r.get("name", "")
    if expect:
        assert name == expect, f"{src} {sym}: {name} != {expect}"
    assert name and name != sym, f"{src} {sym} 未解析出名称: {r}"
    print(f"[OK] 名称 {src}/{sym} -> {name}")

# 3) 回测返回名称
_, res = post("/api/backtest", {"source": "ashare", "symbol": "600519", "interval": "1d",
                                "strategy": "ma_cross", "params": {"fast": 5, "slow": 20}, "limit": 300})
assert res.get("name") == "贵州茅台", res.get("name")
print(f"[OK] 回测响应带名称: {res['name']}（{res['symbol']}）")

# 4) 自由日期区间回测（模拟数据）
_, res2 = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                 "limit": 800, "start_date": "2026-01-01", "end_date": "2026-06-30"})
dates = res2["candles"]["dates"]
assert dates[0] >= "2026-01-01" and dates[-1] <= "2026-06-30", (dates[0], dates[-1])
print(f"[OK] 日期区间回测: {dates[0]} ~ {dates[-1]}（{len(dates)} 根，限定 2026-01-01 ~ 2026-06-30）")

# 5) 只填开始日期
_, res3 = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                 "limit": 800, "start_date": "2026-03-01"})
d3 = res3["candles"]["dates"]
assert d3[0] >= "2026-03-01"
print(f"[OK] 仅开始日期: {d3[0]} ~ {d3[-1]}（{len(d3)} 根）")

# 6) 区间过窄的友好报错
st, err = post("/api/backtest", {"source": "synthetic", "symbol": "SYN:测试股票", "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                 "limit": 800, "start_date": "2026-05-04", "end_date": "2026-05-08"})
assert st == 400 and "数据不足" in err.get("error", ""), err
print(f"[OK] 过窄区间友好报错: {err['error'][:60]}")
print("== 名称/日期测试全部通过 ==")
