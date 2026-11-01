# -*- coding: utf-8 -*-
"""指标图数据测试：回测响应携带全部 18 组技术指标序列。"""
import json
import sys
import urllib.request

sys.path.insert(0, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app")

BASE = "http://127.0.0.1:8000"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


for src, sym in [("synthetic", "SYN:测试股票"), ("ashare", "600519")]:
    res = post("/api/backtest", {"source": src, "symbol": sym, "interval": "1d",
                                 "strategy": "ma_cross", "params": {"fast": 5, "slow": 20},
                                 "limit": 300})
    inds = res.get("indicators") or {}
    n = len(res["candles"]["dates"])
    assert inds, "回测响应缺少 indicators 字段"
    # 长度一致性（18 组指标）
    groups = list(inds.keys())
    for grp in groups:
        for k, v in inds[grp].items():
            assert len(v) == n, f"{src}/{sym} 指标 {grp}.{k} 长度 {len(v)} != {n}"
    # 数值合理性
    assert inds["ma"]["ma20"][-1] is not None
    assert inds["boll"]["upper"][-1] >= inds["boll"]["lower"][-1]
    assert 0 <= inds["rsi"]["rsi12"][-1] <= 100
    assert 0 <= inds["kdj"]["d"][-1] <= 100
    assert -100 <= inds["wr"]["wr14"][-1] <= 0
    assert -400 <= inds["cci"]["cci14"][-1] <= 400
    assert inds["obv"]["obv"][-1] is not None
    assert inds["dmi"]["adx"][-1] is not None
    assert 0 <= inds["psy"]["psy12"][-1] <= 100
    assert inds["sar"]["sar"][-1] is not None
    assert inds["bbi"]["bbi"][-1] is not None
    assert inds["vr"]["vr26"][-1] is not None
    assert inds["trix"]["trix"][-1] is not None
    print(f"[OK] {src}/{sym}: 指标 {len(groups)} 组序列长度一致（{n} 根K线）")
    print(f"     WR={inds['wr']['wr14'][-1]} CCI={inds['cci']['cci14'][-1]} "
          f"+DI={inds['dmi']['pdi'][-1]} ADX={inds['dmi']['adx'][-1]} "
          f"TRIX={inds['trix']['trix'][-1]} SAR={inds['sar']['sar'][-1]}")
print("== 指标图数据测试通过（18 组指标） ==")
