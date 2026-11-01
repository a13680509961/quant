# -*- coding: utf-8 -*-
"""生成 PWA 图标（icon-192.png / icon-512.png）。"""
from PIL import Image, ImageDraw

BG = (13, 17, 23)
PANEL = (22, 27, 34)
UP = (239, 83, 80)
DOWN = (38, 166, 154)
GOLD = (255, 176, 32)


def make_icon(size, path):
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    pad = int(size * 0.05)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=int(size * 0.18), fill=PANEL)

    def candle(cx, top, bottom, color, body_w=None):
        body_w = body_w or max(3, size // 18)
        d.line([cx, top, cx, bottom], fill=color, width=max(2, size // 64))
        d.rectangle([cx - body_w // 2, top + (bottom - top) * 0.18,
                     cx + body_w // 2, bottom - (bottom - top) * 0.22], fill=color)

    base = int(size * 0.60)
    candle(int(size * 0.30), int(size * 0.34), int(size * 0.72), UP)
    candle(int(size * 0.50), int(size * 0.46), int(size * 0.80), DOWN)
    candle(int(size * 0.70), int(size * 0.28), int(size * 0.66), UP)
    # 金色均线
    d.line([int(size * 0.18), int(size * 0.50), int(size * 0.84), int(size * 0.40)],
           fill=GOLD, width=max(3, size // 48))
    img.save(path)
    print(f"已生成 {path} ({size}x{size})")


make_icon(192, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app\web\icon-192.png")
make_icon(512, r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-app\web\icon-512.png")
