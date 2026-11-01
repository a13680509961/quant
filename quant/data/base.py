# -*- coding: utf-8 -*-
"""数据源抽象接口与注册表。

所有数据源统一返回 pandas.DataFrame，字段固定为：
    date, open, high, low, close, volume
其中 date 为字符串（"YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM:SS"），按时间升序排列。
"""
from __future__ import annotations

import abc

import pandas as pd


class DataSource(abc.ABC):
    """数据源基类。子类需实现 get_bars；实时源可覆盖 get_quote。"""

    id: str = ""           # 唯一标识
    label: str = ""        # 界面显示名
    requires_network: bool = False  # 是否需要联网
    intervals: tuple = ("1d", "1h", "15m", "1m")  # 支持的周期
    hidden: bool = False   # True = 仅作内部通道，不在界面数据源下拉框显示

    @abc.abstractmethod
    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        """拉取最近 limit 根 K 线，返回升序 DataFrame。"""

    def default_symbols(self):
        """界面下拉框建议的示例标的。"""
        return []

    def get_quote(self, symbol: str):
        """返回最新报价 dict（price/change/change_pct/ts），不支持实时则返回 None。"""
        return None

    def get_name(self, symbol: str) -> str:
        """返回标的名称（如 600519 -> 贵州茅台）；取不到时返回代码本身。"""
        try:
            q = self.get_quote(symbol)
            if q and q.get("name"):
                return str(q["name"])
        except Exception:
            pass
        return symbol


# ---------------------------------------------------------------------------
# 注册表：新增数据源时，在此处 import 并加入 REGISTRY
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, DataSource] = {}

# 数据源英文名（多语言）
_LABELS_EN = {
    "synthetic": "Synthetic (offline)",
    "stocks": "Stocks (CN/HK/US)",
    "ashare": "A-Shares (CN)",
    "futures": "Futures (CN/Global)",
    "cn_futures": "CN Futures",
    "global_futures": "Global Futures",
    "fund": "Mutual Funds",
    "hk": "Hong Kong",
    "forex": "Forex (FX)",
    "indices": "Indices (Global)",
    "crypto": "Crypto (Blockchain)",
    "yahoo": "Yahoo Finance",
    "stooq": "Stooq",
}


def register_source(source: DataSource) -> None:
    _REGISTRY[source.id] = source


def get_source(source_id: str):
    return _REGISTRY.get(source_id)


def list_sources(include_hidden: bool = False):
    """返回数据源描述信息（默认只返回界面可见的顶层数据源）。"""
    out = []
    for s in _REGISTRY.values():
        if s.hidden and not include_hidden:
            continue
        out.append({
            "id": s.id,
            "label": s.label,
            "label_en": _LABELS_EN.get(s.id, s.label),
            "requires_network": s.requires_network,
            "intervals": list(s.intervals),
            "default_symbols": s.default_symbols(),
        })
    return out


def ensure_registered():
    """惰性注册内置数据源（避免循环 import）。"""
    if "synthetic" not in _REGISTRY:
        from .synthetic import SyntheticSource
        register_source(SyntheticSource())
    if "ashare" not in _REGISTRY:
        from .ashare import AShareSource
        register_source(AShareSource())
    if "stocks" not in _REGISTRY:
        from .stocks import StocksSource
        register_source(StocksSource())
    if "futures" not in _REGISTRY:
        from .futures import FuturesSource
        register_source(FuturesSource())
    if "global_futures" not in _REGISTRY:
        from .global_futures import GlobalFuturesSource
        register_source(GlobalFuturesSource())
    if "fund" not in _REGISTRY:
        from .fund import FundSource
        register_source(FundSource())
    if "hk" not in _REGISTRY:
        from .hk import HKSource
        register_source(HKSource())
    if "forex" not in _REGISTRY:
        from .forex import ForexSource
        register_source(ForexSource())
    if "indices" not in _REGISTRY:
        from .indices import IndicesSource
        register_source(IndicesSource())
    if "crypto" not in _REGISTRY:
        from .crypto import CryptoSource
        register_source(CryptoSource())
    if "yahoo" not in _REGISTRY:
        from .yahoo import YahooSource
        register_source(YahooSource())
    if "stooq" not in _REGISTRY:
        from .stooq import StooqSource
        register_source(StooqSource())
