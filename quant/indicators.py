# -*- coding: utf-8 -*-
"""常用技术指标（纯 pandas/numpy 实现）。"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(int(n)).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=int(n), adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False).mean()
    denom = (avg_gain + avg_loss).replace(0.0, np.nan)
    rs = avg_gain / denom
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(denom.notna(), 50.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """返回 (DIF, DEA, 柱)。"""
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """返回 (中轨, 上轨, 下轨)。"""
    mid = sma(close, n)
    std = close.rolling(int(n)).std(ddof=0)
    return mid, mid + k * std, mid - k * std


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3):
    """随机指标，返回 (K, D, J) 三个 Series。"""
    low_n = df["low"].rolling(int(n), min_periods=1).min()
    high_n = df["high"].rolling(int(n), min_periods=1).max()
    rng = (high_n - low_n).replace(0.0, np.nan)
    rsv = (df["close"] - low_n) / rng * 100.0
    rsv = rsv.fillna(50.0)
    k = rsv.ewm(alpha=1.0 / m1, adjust=False).mean()
    d = k.ewm(alpha=1.0 / m2, adjust=False).mean()
    j = 3.0 * k - 2.0 * d
    return k, d, j


def wr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """威廉指标（0 ~ -100）。"""
    hh = df["high"].rolling(int(n), min_periods=1).max()
    ll = df["low"].rolling(int(n), min_periods=1).min()
    rng = (hh - ll).replace(0.0, np.nan)
    return ((hh - df["close"]) / rng * -100.0).fillna(-50.0)


def cci(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """顺势指标。"""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    ma_tp = tp.rolling(int(n), min_periods=1).mean()
    md = tp.rolling(int(n), min_periods=1).apply(
        lambda x: float(np.abs(x - x.mean()).mean()), raw=True)
    md = md.replace(0.0, np.nan)
    return (tp - ma_tp) / (0.015 * md)


def obv(df: pd.DataFrame) -> pd.Series:
    """能量潮。"""
    sign = np.sign(df["close"].diff()).fillna(0.0)
    return (sign * df["volume"]).cumsum()


def bias(close: pd.Series, n: int = 6) -> pd.Series:
    """乖离率（%）。"""
    ma = close.rolling(int(n), min_periods=1).mean()
    return (close - ma) / ma * 100.0


def dmi(df: pd.DataFrame, n: int = 14, m: int = 6):
    """动向指标，返回 (+DI, -DI, ADX)。"""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
         (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    atr_n = tr.ewm(alpha=1.0 / n, adjust=False).mean().replace(0.0, np.nan)
    pdi = plus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_n * 100.0
    mdi = minus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_n * 100.0
    dx = (pdi - mdi).abs() / (pdi + mdi).replace(0.0, np.nan) * 100.0
    adx = dx.ewm(alpha=1.0 / m, adjust=False).mean()
    return pdi, mdi, adx


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    """变动率（%）。"""
    return close.pct_change(int(n)) * 100.0


def psy(df: pd.DataFrame, n: int = 12) -> pd.Series:
    """心理线（%）。"""
    up = (df["close"].diff() > 0).astype(float)
    return up.rolling(int(n), min_periods=1).mean() * 100.0


def mtm(close: pd.Series, n: int = 12) -> pd.Series:
    """动量指标。"""
    return close - close.shift(int(n))


def vr(df: pd.DataFrame, n: int = 26) -> pd.Series:
    """成交量变异率。"""
    up = df["volume"].where(df["close"].diff() > 0, 0.0)
    down = df["volume"].where(df["close"].diff() < 0, 0.0)
    flat = df["volume"].where(df["close"].diff() == 0, 0.0)
    u = up.rolling(int(n), min_periods=1).sum()
    d = down.rolling(int(n), min_periods=1).sum()
    f = flat.rolling(int(n), min_periods=1).sum()
    denom = (d + f / 2.0).replace(0.0, np.nan)
    return ((u + f / 2.0) / denom * 100.0).fillna(100.0)


def trix(close: pd.Series, n: int = 12, m: int = 9):
    """三重指数平滑，返回 (TRIX, MATRIX)。"""
    e1 = close.ewm(span=int(n), adjust=False).mean()
    e2 = e1.ewm(span=int(n), adjust=False).mean()
    e3 = e2.ewm(span=int(n), adjust=False).mean()
    trix_line = e3.pct_change() * 100.0
    matrix = trix_line.ewm(span=int(m), adjust=False).mean()
    return trix_line, matrix


def sar(df: pd.DataFrame, step: float = 0.02, maximum: float = 0.2) -> pd.Series:
    """抛物线转向（主图叠加点）。"""
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    n = len(df)
    out = np.full(n, np.nan)
    if n == 0:
        return pd.Series(out, index=df.index)
    bull = True
    ep = high[0]
    af = step
    sar_val = low[0]
    for i in range(1, n):
        sar_val = sar_val + af * (ep - sar_val)
        if bull:
            out[i] = min(sar_val, low[i - 1], low[i])
            if high[i] > ep:
                ep = high[i]
                af = min(af + step, maximum)
            if low[i] < out[i]:
                bull = False
                sar_val = ep
                ep = low[i]
                af = step
        else:
            out[i] = max(sar_val, high[i - 1], high[i])
            if low[i] < ep:
                ep = low[i]
                af = min(af + step, maximum)
            if high[i] > out[i]:
                bull = True
                sar_val = ep
                ep = high[i]
                af = step
    return pd.Series(out, index=df.index)


def bbi(close: pd.Series) -> pd.Series:
    """多空指标（3/6/12/24 日均线均值，主图叠加）。"""
    return (sma(close, 3) + sma(close, 6) + sma(close, 12) + sma(close, 24)) / 4.0
