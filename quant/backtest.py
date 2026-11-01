# -*- coding: utf-8 -*-
"""回测引擎：支持杠杆（两融融资）、做空（融券）、融资利息与强平模拟。

持仓序列约定：
    1  = 持有多仓（买入/融资买入）
    -1 = 持有空仓（融券卖出）
    0  = 空仓
引擎逐周期模拟净值：
    名义市值 = 持仓 × 杠杆 × 净值
    借入资金 = |名义市值| × (杠杆-1)/杠杆        （杠杆>1 时才借贷）
    融资/融券利息按借入额 × 年利率 / 年化周期数 逐期计提
    维持担保比例 = 净值 / 借入额；低于 maintenance_ratio（默认 1.3）触发强平
    爆仓（净值≤0）后强制归零，后续不再交易
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import indicators as _ta

# 各周期对应的年化周期数（用于年化收益/波动/夏普/利息折算）
PERIODS_PER_YEAR = {
    "1d": 252,
    "1h": 252 * 6.5,
    "15m": 252 * 6.5 * 4,
    "1m": 252 * 6.5 * 60,
}


def _safe_round(x, n=4):
    try:
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return 0.0
        return round(v, n)
    except (TypeError, ValueError):
        return 0.0


def _series_list(series: pd.Series, n: int = 3):
    """Series -> JSON 友好列表（NaN -> null）。"""
    out = []
    for v in series:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        else:
            out.append(round(float(v), n))
    return out


def compute_indicators(df: pd.DataFrame) -> dict:
    """计算标准技术指标序列（图表用）。

    主图叠加：MA / BOLL / EXPMA / BBI / SAR
    副图窗格：MACD / KDJ / RSI / WR / CCI / OBV / DMI / BIAS / ROC / PSY / MTM / VR / TRIX
    """
    close = df["close"]
    ma5, ma10, ma20, ma60 = (_ta.sma(close, n) for n in (5, 10, 20, 60))
    mid, upper, lower = _ta.bollinger(close, 20, 2.0)
    dif, dea, hist = _ta.macd(close, 12, 26, 9)
    k, d, j = _ta.kdj(df, 9, 3, 3)
    pdi, mdi, adx = _ta.dmi(df, 14, 6)
    trix_line, matrix = _ta.trix(close, 12, 9)
    return {
        "ma": {
            "ma5": _series_list(ma5), "ma10": _series_list(ma10),
            "ma20": _series_list(ma20), "ma60": _series_list(ma60),
        },
        "boll": {
            "mid": _series_list(mid), "upper": _series_list(upper), "lower": _series_list(lower),
        },
        "expma": {
            "expma12": _series_list(_ta.ema(close, 12)),
            "expma50": _series_list(_ta.ema(close, 50)),
        },
        "bbi": {"bbi": _series_list(_ta.bbi(close))},
        "sar": {"sar": _series_list(_ta.sar(df))},
        "macd": {
            "dif": _series_list(dif), "dea": _series_list(dea), "hist": _series_list(hist),
        },
        "kdj": {"k": _series_list(k), "d": _series_list(d), "j": _series_list(j)},
        "rsi": {
            "rsi6": _series_list(_ta.rsi(close, 6)),
            "rsi12": _series_list(_ta.rsi(close, 12)),
            "rsi24": _series_list(_ta.rsi(close, 24)),
        },
        "wr": {"wr14": _series_list(_ta.wr(df, 14), 2)},
        "cci": {"cci14": _series_list(_ta.cci(df, 14), 2)},
        "obv": {"obv": _series_list(_ta.obv(df), 0)},
        "dmi": {
            "pdi": _series_list(pdi, 2), "mdi": _series_list(mdi, 2),
            "adx": _series_list(adx, 2),
        },
        "bias": {
            "bias6": _series_list(_ta.bias(close, 6), 2),
            "bias12": _series_list(_ta.bias(close, 12), 2),
            "bias24": _series_list(_ta.bias(close, 24), 2),
        },
        "roc": {"roc12": _series_list(_ta.roc(close, 12), 2)},
        "psy": {"psy12": _series_list(_ta.psy(df, 12), 2)},
        "mtm": {"mtm12": _series_list(_ta.mtm(close, 12), 2)},
        "vr": {"vr26": _series_list(_ta.vr(df, 26), 2)},
        "trix": {
            "trix": _series_list(trix_line, 2), "matrix": _series_list(matrix, 2),
        },
    }


def run_backtest(df: pd.DataFrame, position: pd.Series,
                 initial_capital: float = 100_000.0,
                 fee_rate: float = 0.0003,
                 interval: str = "1d",
                 leverage: float = 1.0,
                 direction: str = "long",
                 margin_interest: float = 0.0,
                 margin_ratio: float = 0.1,
                 maintenance_ratio: float = 1.3) -> dict:
    """执行回测。

    参数:
        df: K线 DataFrame（date/open/high/low/close/volume，升序）
        position: 与 df 等长的持仓序列（做多策略 0/1，多空策略 -1/0/1）
        leverage: 杠杆倍数（≥1，两融融资模式；实际借贷 = (L-1)/L × 名义市值）
        direction: 交易方向 "long" 只做多 / "short" 只做空 / "both" 多空双向
        margin_interest: 借贷年利率（小数，如 0.0835 = 8.35%）
        margin_ratio: 初始保证金比例（默认 0.1，即 10 倍杠杆上限，期货风格）
        maintenance_ratio: 维持担保比例（默认 1.3，低于触发强平）
    """
    close = df["close"].astype(float).reset_index(drop=True)
    pos_raw = position.astype(float).reset_index(drop=True).reindex(close.index).fillna(0.0)
    pos_raw = pos_raw.clip(-1.0, 1.0)
    if direction == "long":
        pos_raw = pos_raw.clip(lower=0.0)   # 只做多：忽略做空信号
    elif direction == "short":
        pos_raw = pos_raw.clip(upper=0.0)   # 只做空：忽略做多信号

    lev = max(1.0, min(float(leverage), 1.0 / max(margin_ratio, 0.05)))
    dates = list(df["date"])
    ret = close.pct_change().fillna(0.0)
    ppy = PERIODS_PER_YEAR.get(interval, 252)
    daily_interest = float(margin_interest) / ppy
    n = len(close)
    if n == 0:
        raise ValueError("K线数据为空")

    # ---- 逐周期模拟净值（统一处理杠杆/利息/强平，无杠杆时结果与向量化一致）----
    equity = float(initial_capital)
    eq_series = np.empty(n)
    pos_eff = np.zeros(n)          # 实际生效持仓（可能被强平打断）
    interest_total = 0.0
    fee_total = 0.0
    liq_events = []

    for i in range(n):
        prev_pos = pos_eff[i - 1] if i > 0 else 0.0
        if i > 0:
            # 上一持仓的本期盈亏 + 利息
            notional = prev_pos * lev * equity
            pnl = notional * ret.iloc[i]
            borrowed = abs(notional) * (lev - 1.0) / lev if lev > 1.0 else 0.0
            interest = borrowed * daily_interest
            interest_total += interest
            equity = equity + pnl - interest
            # 维持担保比例检查 → 强平
            # 担保比例 = (净资产 + 负债) / 负债 ≥ maintenance_ratio，等价于 净资产/负债 ≥ maintenance_ratio - 1
            if prev_pos != 0 and lev > 1.0 and borrowed > 0:
                if equity / borrowed < (maintenance_ratio - 1.0):
                    liq_events.append({"date": dates[i], "price": _safe_round(close.iloc[i])})
                    if equity <= 0:
                        equity = 0.0
        # 目标仓位与换仓手续费
        target = float(pos_raw.iloc[i])
        if liq_events and i > 0 and liq_events and dates[i] == liq_events[-1]["date"]:
            target = 0.0  # 当日已强平
        if prev_pos != target and equity > 0:
            fee = abs(target - prev_pos) * lev * equity * float(fee_rate)
            equity -= fee
            fee_total += fee
        pos_eff[i] = target
        eq_series[i] = max(equity, 0.0)
        if equity <= 0:  # 爆仓：账户归零，后续不再交易
            pos_eff[i:] = 0.0
            eq_series[i:] = 0.0
            break

    equity_series = pd.Series(eq_series)
    bench_series = float(initial_capital) * (1.0 + ret).cumprod()

    # ---- 指标 ----
    final_eq = float(equity_series.iloc[-1])
    strat_ret = equity_series.pct_change().fillna(0.0)
    total_return = final_eq / initial_capital - 1.0
    years = max(n / ppy, 1e-9)
    cagr = (final_eq / initial_capital) ** (1.0 / years) - 1.0 if final_eq > 0 else -1.0
    vol = float(strat_ret.std(ddof=0) * np.sqrt(ppy))
    sharpe = float(strat_ret.mean() / strat_ret.std(ddof=0) * np.sqrt(ppy)) \
        if strat_ret.std(ddof=0) > 1e-12 else 0.0

    dd = equity_series / equity_series.cummax() - 1.0
    max_dd = float(dd.min())
    calmar = cagr / abs(max_dd) if max_dd < -1e-12 else 0.0

    # ---- 交易配对（支持做空）----
    trades = []
    markers = []
    sig = pd.Series(pos_eff)

    def close_trade(entry_i, entry_sign, entry_price, exit_i):
        exit_p = float(close.iloc[exit_i])
        if entry_sign > 0:
            r = exit_p / entry_price - 1.0 - 2.0 * float(fee_rate)
            side = "做多"
        else:
            r = entry_price / exit_p - 1.0 - 2.0 * float(fee_rate)
            side = "做空"
        trades.append({
            "side": side,
            "side_code": "long" if entry_sign > 0 else "short",
            "entry_date": dates[entry_i], "exit_date": dates[exit_i],
            "entry_price": _safe_round(entry_price), "exit_price": _safe_round(exit_p),
            "return_pct": _safe_round(r * 100),
            "bars": int(exit_i - entry_i + 1),
            "win": bool(r > 0),
        })

    entry = None  # (idx, sign, price)
    for i in range(n):
        p = float(sig.iloc[i])
        if entry is None:
            if p != 0:
                entry = (i, 1 if p > 0 else -1, float(close.iloc[i]))
                markers.append({"i": i, "type": "buy" if p > 0 else "short",
                                "price": _safe_round(close.iloc[i]), "date": dates[i]})
        else:
            if p == 0:
                close_trade(entry[0], entry[1], entry[2], i)
                markers.append({"i": i, "type": "sell" if entry[1] > 0 else "cover",
                                "price": _safe_round(close.iloc[i]), "date": dates[i]})
                entry = None
            elif (p > 0) != (entry[1] > 0):
                # 反手：先平仓再反向开仓（同根K线两笔事件）
                close_trade(entry[0], entry[1], entry[2], i)
                markers.append({"i": i, "type": "sell" if entry[1] > 0 else "cover",
                                "price": _safe_round(close.iloc[i]), "date": dates[i]})
                entry = (i, 1 if p > 0 else -1, float(close.iloc[i]))
                markers.append({"i": i, "type": "buy" if p > 0 else "short",
                                "price": _safe_round(close.iloc[i]), "date": dates[i]})
    if entry is not None:
        close_trade(entry[0], entry[1], entry[2], n - 1)
        markers.append({"i": n - 1, "type": "sell" if entry[1] > 0 else "cover",
                        "price": _safe_round(close.iloc[n - 1]), "date": dates[n - 1]})

    num_trades = len(trades)
    wins = sum(1 for t in trades if t["win"])
    short_trades = sum(1 for t in trades if t["side"] == "做空")
    gross_profit = sum(t["return_pct"] for t in trades if t["win"]) / 100.0
    gross_loss = sum(-t["return_pct"] for t in trades if not t["win"]) / 100.0
    win_rate = wins / num_trades if num_trades else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 1e-12 else \
        (999.0 if gross_profit > 0 else 0.0)
    avg_trade = (gross_profit - gross_loss) / num_trades * 100 if num_trades else 0.0

    metrics = {
        "total_return_pct": _safe_round(total_return * 100, 2),
        "cagr_pct": _safe_round(cagr * 100, 2),
        "annual_vol_pct": _safe_round(vol * 100, 2),
        "sharpe": _safe_round(sharpe, 2),
        "max_drawdown_pct": _safe_round(max_dd * 100, 2),
        "calmar": _safe_round(calmar, 2),
        "num_trades": num_trades,
        "win_rate_pct": _safe_round(win_rate * 100, 2),
        "profit_factor": _safe_round(profit_factor, 2),
        "avg_trade_pct": _safe_round(avg_trade, 2),
        "benchmark_return_pct": _safe_round((float(bench_series.iloc[-1]) / initial_capital - 1) * 100, 2),
        "leverage_used": _safe_round(lev, 2),
        "short_trades": short_trades,
        "margin_call_count": len(liq_events),
        "interest_total": _safe_round(interest_total, 2),
        "fee_total": _safe_round(fee_total, 2),
    }

    step = max(1, n // 500)  # 净值曲线抽样，控制 JSON 体积
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)

    return {
        "metrics": metrics,
        "candles": {
            "dates": dates,
            "open": [_safe_round(v) for v in df["open"]],
            "high": [_safe_round(v) for v in df["high"]],
            "low": [_safe_round(v) for v in df["low"]],
            "close": [_safe_round(v) for v in df["close"]],
            "volume": [_safe_round(v, 0) for v in df["volume"]],
        },
        "equity": {"dates": [dates[i] for i in idx],
                   "values": [_safe_round(equity_series.iloc[i], 2) for i in idx]},
        "benchmark": {"dates": [dates[i] for i in idx],
                      "values": [_safe_round(bench_series.iloc[i], 2) for i in idx]},
        "trades": trades,
        "markers": markers,
        "margin_events": liq_events,
        "indicators": compute_indicators(df),
    }


def last_signal(df: pd.DataFrame, position: pd.Series) -> dict:
    """由持仓序列判断最新信号（支持做空）。"""
    pos = position.reset_index(drop=True).fillna(0.0)
    last = int(pos.iloc[-1])
    prev = int(pos.iloc[-2]) if len(pos) > 1 else 0
    if last == 1 and prev <= 0:
        action = "买入"
    elif last == 0 and prev == 1:
        action = "卖出"
    elif last == -1 and prev >= 0:
        action = "融券卖出"
    elif last == 0 and prev == -1:
        action = "买券还券"
    elif last == 1:
        action = "持有"
    elif last == -1:
        action = "做空持有"
    else:
        action = "空仓"
    return {
        "position": last,
        "action": action,
        "action_code": {
            "买入": "buy", "卖出": "sell", "持有": "hold", "空仓": "flat",
            "融券卖出": "short_open", "买券还券": "short_cover", "做空持有": "short_hold",
        }.get(action, "flat"),
        "last_close": _safe_round(df["close"].iloc[-1]),
        "bar_time": str(df["date"].iloc[-1]),
    }
