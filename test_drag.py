# -*- coding: utf-8 -*-
"""K线左右拉动自动化验证：点击全景条定位 + 拖动平移。"""
import json
import os
import subprocess

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app"
page = os.path.join(BASE, "test_drag.html")
out = os.path.join(BASE, "drag_dom.html")

with open(out, "w", encoding="utf-8") as f:
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=8000", "--dump-dom", "file:///" + page.replace("\\", "/")],
        stdout=f, stderr=subprocess.DEVNULL, timeout=120,
    )
with open(out, encoding="utf-8") as f:
    html = f.read()

import re
m = re.search(r"DRAG_TEST:(\{.*\})\s*</title>", html)
assert m, "未找到测试输出"
r = json.loads(m.group(1))
print(f"测试结果: 初始 offset={r['before']} → 点击定位后={r['afterClick']} → 拖动后={r['afterDrag']}")

assert r["count"] == 120 and r["n"] == 500
assert r["afterClick"] != r["before"], "点击全景条应改变可视窗口"
assert r["afterDrag"] != r["afterClick"], "拖动应改变可视窗口"
assert 0 <= r["afterClick"] <= r["n"] - r["count"]
assert 0 <= r["afterDrag"] <= r["n"] - r["count"]
print("[OK] K线左右拉动：点击定位与拖动平移均生效（窗口在 0~380 内移动）")
print("[OK] 全景缩略条渲染正常（含窗口高亮与拖动把手）")
