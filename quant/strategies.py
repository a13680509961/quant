# -*- coding: utf-8 -*-
"""策略库：每只策略输出 0/1 持仓序列（1=持有，0=空仓，长仓单边）。

新增策略步骤：
1. 写一个函数 func(df, **params) -> pd.Series（值 0/1，与 df 等长）；
2. 调用 register() 注册名称、中文名与参数表。
"""
from __future__ import annotations

import pandas as pd

from . import indicators as ta

_STRATEGIES: dict = {}

# 策略与参数的英文名（多语言）
_STRATEGY_LABELS_EN = {
    "ma_cross": "Dual MA Trend",
    "rsi_reversal": "RSI Mean Reversion",
    "bollinger_revert": "Bollinger Mean Reversion",
    "macd_trend": "MACD Trend",
    "breakout": "N-day Breakout",
    "ma_cross_dual": "Dual MA Long/Short",
    "rsi_dual": "RSI Long/Short",
    "bollinger_dual": "Bollinger Long/Short",
    "macd_dual": "MACD Long/Short",
    "breakout_dual": "Breakout Long/Short",
}
_PARAM_LABELS_EN = {
    "快线周期": "Fast period", "慢线周期": "Slow period",
    "RSI 周期": "RSI period", "超卖阈值": "Oversold level", "超买阈值": "Overbought level",
    "布林周期": "Bollinger period", "标准差倍数": "Std multiplier",
    "快线 EMA": "Fast EMA", "慢线 EMA": "Slow EMA", "信号线": "Signal line",
    "突破周期": "Breakout period", "止损比例": "Stop loss",
}


def register(name: str, label: str, params: list, fn, long_only: bool = True):
    for p in params:
        p.setdefault("label_en", _PARAM_LABELS_EN.get(p.get("label", ""), p.get("label", "")))
    _STRATEGIES[name] = {
        "name": name,
        "label": label,
        "label_en": _STRATEGY_LABELS_EN.get(name, label),
        "params": params,
        "fn": fn,
        "long_only": long_only,
    }


def get_strategy(name: str):
    return _STRATEGIES.get(name)


def list_strategies():
    return [
        {"name": s["name"], "label": s["label"], "label_en": s.get("label_en", s["label"]),
         "params": s["params"], "long_only": s["long_only"]}
        for s in _STRATEGIES.values()
    ]


def _param(key, label, type_, default, min_, max_, step=1):
    return {"key": key, "label": label, "type": type_,
            "default": default, "min": min_, "max": max_, "step": step}


def _stateful_position(enter: pd.Series, exit_: pd.Series) -> pd.Series:
    """由入场/出场布尔序列生成持仓序列。"""
    pos = pd.Series(0, index=enter.index, dtype=float)
    holding = False
    for i in enter.index:
        if not holding and bool(enter.loc[i]):
            holding = True
        elif holding and bool(exit_.loc[i]):
            holding = False
        pos.loc[i] = 1.0 if holding else 0.0
    return pos


def _stateful_dual(enter_long, exit_long, enter_short, exit_short) -> pd.Series:
    """多空状态机：生成 -1/0/1 持仓序列。"""
    pos = pd.Series(0, index=enter_long.index, dtype=float)
    holding = 0
    for i in enter_long.index:
        if holding <= 0 and bool(enter_long.loc[i]):
            holding = 1
        elif holding >= 0 and bool(enter_short.loc[i]):
            holding = -1
        elif holding == 1 and bool(exit_long.loc[i]):
            holding = 0
        elif holding == -1 and bool(exit_short.loc[i]):
            holding = 0
        pos.loc[i] = float(holding)
    return pos


# ---------------------------------------------------------------------------
# 1. 双均线
# ---------------------------------------------------------------------------
def ma_cross(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    f = ta.sma(df["close"], fast)
    s = ta.sma(df["close"], slow)
    pos = (f > s).astype(float)
    pos[s.isna()] = 0.0
    return pos


register("ma_cross", "双均线趋势（金叉/死叉）", [
    _param("fast", "快线周期", "int", 5, 1, 60),
    _param("slow", "慢线周期", "int", 20, 5, 120),
], ma_cross)


# ---------------------------------------------------------------------------
# 2. RSI 超跌反弹
# ---------------------------------------------------------------------------
def rsi_reversal(df: pd.DataFrame, period: int = 14,
                 oversold: int = 30, overbought: int = 70) -> pd.Series:
    r = ta.rsi(df["close"], period)
    enter = r < oversold
    exit_ = r > overbought
    return _stateful_position(enter, exit_)


register("rsi_reversal", "RSI 超跌反弹", [
    _param("period", "RSI 周期", "int", 14, 2, 60),
    _param("oversold", "超卖阈值", "int", 30, 5, 45),
    _param("overbought", "超买阈值", "int", 70, 55, 95),
], rsi_reversal)


# ---------------------------------------------------------------------------
# 3. 布林带均值回归
# ---------------------------------------------------------------------------
def bollinger_revert(df: pd.DataFrame, period: int = 20,
                     k: float = 2.0) -> pd.Series:
    mid, upper, lower = ta.bollinger(df["close"], period, k)
    enter = df["close"] < lower        # 跌破下轨买入
    exit_ = df["close"] > mid          # 回到中轨上方卖出
    return _stateful_position(enter, exit_)


register("bollinger_revert", "布林带均值回归", [
    _param("period", "布林周期", "int", 20, 5, 100),
    _param("k", "标准差倍数", "float", 2.0, 1.0, 4.0, 0.1),
], bollinger_revert)


# ---------------------------------------------------------------------------
# 4. MACD 趋势
# ---------------------------------------------------------------------------
def macd_trend(df: pd.DataFrame, fast: int = 12, slow: int = 26,
               signal: int = 9) -> pd.Series:
    dif, dea, _ = ta.macd(df["close"], fast, slow, signal)
    pos = (dif > dea).astype(float)
    pos[dea.isna()] = 0.0
    return pos


register("macd_trend", "MACD 趋势（金叉/死叉）", [
    _param("fast", "快线 EMA", "int", 12, 2, 50),
    _param("slow", "慢线 EMA", "int", 26, 5, 100),
    _param("signal", "信号线", "int", 9, 2, 50),
], macd_trend)


# ---------------------------------------------------------------------------
# 5. 突破 N 日新高
# ---------------------------------------------------------------------------
def breakout(df: pd.DataFrame, period: int = 20) -> pd.Series:
    highest = df["close"].rolling(period).max().shift(1)
    lowest = df["close"].rolling(period).min().shift(1)
    enter = df["close"] > highest
    exit_ = df["close"] < lowest
    pos = _stateful_position(enter, exit_)
    pos[highest.isna()] = 0.0
    return pos


register("breakout", "N 日高低点突破", [
    _param("period", "突破周期", "int", 20, 5, 120),
], breakout)


# ---------------------------------------------------------------------------
# 6~10. 多空策略（输出 -1/0/1，配合"允许做空"开关使用）
# ---------------------------------------------------------------------------
def ma_cross_dual(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    f = ta.sma(df["close"], fast)
    s = ta.sma(df["close"], slow)
    pos = pd.Series(0.0, index=df.index)
    pos[(f > s)] = 1.0
    pos[(f <= s) & s.notna()] = -1.0
    pos[s.isna()] = 0.0
    return pos


register("ma_cross_dual", "双均线多空（金叉做多/死叉做空）", [
    _param("fast", "快线周期", "int", 5, 1, 60),
    _param("slow", "慢线周期", "int", 20, 5, 120),
], ma_cross_dual, long_only=False)


def rsi_dual(df: pd.DataFrame, period: int = 14,
             oversold: int = 30, overbought: int = 70) -> pd.Series:
    r = ta.rsi(df["close"], period)
    return _stateful_dual(r < oversold, r > overbought, r > overbought, r < oversold)


register("rsi_dual", "RSI 多空（超卖做多/超买做空）", [
    _param("period", "RSI 周期", "int", 14, 2, 60),
    _param("oversold", "超卖阈值", "int", 30, 5, 45),
    _param("overbought", "超买阈值", "int", 70, 55, 95),
], rsi_dual, long_only=False)


def bollinger_dual(df: pd.DataFrame, period: int = 20, k: float = 2.0) -> pd.Series:
    mid, upper, lower = ta.bollinger(df["close"], period, k)
    return _stateful_dual(df["close"] < lower, df["close"] > mid,
                          df["close"] > upper, df["close"] < mid)


register("bollinger_dual", "布林带多空（下轨做多/上轨做空）", [
    _param("period", "布林周期", "int", 20, 5, 100),
    _param("k", "标准差倍数", "float", 2.0, 1.0, 4.0, 0.1),
], bollinger_dual, long_only=False)


def macd_dual(df: pd.DataFrame, fast: int = 12, slow: int = 26,
              signal: int = 9) -> pd.Series:
    dif, dea, _ = ta.macd(df["close"], fast, slow, signal)
    pos = pd.Series(0.0, index=df.index)
    pos[(dif > dea)] = 1.0
    pos[(dif <= dea) & dea.notna()] = -1.0
    pos[dea.isna()] = 0.0
    return pos


register("macd_dual", "MACD 多空（金叉做多/死叉做空）", [
    _param("fast", "快线 EMA", "int", 12, 2, 50),
    _param("slow", "慢线 EMA", "int", 26, 5, 100),
    _param("signal", "信号线", "int", 9, 2, 50),
], macd_dual, long_only=False)


def breakout_dual(df: pd.DataFrame, period: int = 20) -> pd.Series:
    highest = df["close"].rolling(period).max().shift(1)
    lowest = df["close"].rolling(period).min().shift(1)
    pos = _stateful_dual(df["close"] > highest, df["close"] < lowest,
                         df["close"] < lowest, df["close"] > highest)
    pos[highest.isna()] = 0.0
    return pos


register("breakout_dual", "突破多空（创新高做多/创新低做空）", [
    _param("period", "突破周期", "int", 20, 5, 120),
], breakout_dual, long_only=False)
