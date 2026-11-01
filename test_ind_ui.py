# -*- coding: utf-8 -*-
"""前端指标开关渲染验证。"""
import os
import subprocess

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app"
out = os.path.join(BASE, "ind_dom.html")

with open(out, "w", encoding="utf-8") as f:
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=12000", "--dump-dom",
         "http://127.0.0.1:8000/"],
        stdout=f, stderr=subprocess.DEVNULL, timeout=120,
    )
with open(out, encoding="utf-8") as f:
    html = f.read()

import re
chips = re.findall(r'data-ind="(ma|boll|expma|bbi|sar|macd|kdj|rsi|wr|cci|obv|dmi|bias|roc|psy|mtm|vr|trix)"', html)
print(f"指标开关: {len(chips)} 个（应 18）-> {sorted(set(chips))}")
assert len(set(chips)) == 18, chips
assert ">主图<" in html and ">副图<" in html, "分组标签缺失"
assert "SAR" in html and "TRIX" in html and "EXPMA" in html and "BBI" in html
print("[OK] 主图/副图分组与 18 个指标开关全部渲染")
os.remove(out)
