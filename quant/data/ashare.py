# -*- coding: utf-8 -*-
"""A股统一数据源：东方财富通道优先，失败自动切换腾讯行情通道。

代码规则：
    - 沪市：6xxxxx（主板）、688xxx（科创板）、9xxxxx（沪B）、5xxxxx（沪基金）
    - 深市：0xxxxx / 3xxxxx（含创业板）、2xxxxx（深B）、1xxxxx（深基金）
    - 北交所：4xxxxx / 8xxxxx / 43xxxx / 83xxxx / 87xxxx
    - 指数需显式加前缀：sh000001（上证指数）、sz399001（深证成指）、sz399006（创业板指）
      （不写前缀时 000001 指深市平安银行）
日线默认前复权，保证回测连续性。
"""
from __future__ import annotations

import pandas as pd

from .base import DataSource


def resolve_a_symbol(symbol: str):
    """解析A股代码 -> (market, code)，market 1=沪市，0=深市/北交所。"""
    s = symbol.strip().lower()
    if s[:2] in ("sh", "sz"):
        return (1 if s[:2] == "sh" else 0), s[2:]
    if not s.isdigit() or len(s) != 6:
        raise ValueError(
            f"A股代码应为 6 位数字（如 600519、300750），指数需加前缀（如 sh000001），当前输入：{symbol}"
        )
    if s[0] in "69" or s.startswith("5"):
        return 1, s
    return 0, s


class AShareSource(DataSource):
    id = "ashare"
    label = "A股（沪深/北交所，需联网，东财/腾讯/新浪自动切换）"
    requires_network = True
    hidden = True  # 已并入「股票」顶层源，仅作内部通道

    def __init__(self):
        self._providers = []

    def _providers_lazy(self):
        if not self._providers:
            from .eastmoney import EastmoneyProvider
            from .sina import SinaProvider
            from .tencent import TencentProvider
            # 通道顺序：东方财富 → 腾讯 → 新浪（任一成功即返回）
            self._providers = [EastmoneyProvider(), TencentProvider(), SinaProvider()]
        return self._providers

    def default_symbols(self):
        return ["600519", "000001", "300750", "sh000001", "588000"]

    @staticmethod
    def resolve(symbol: str):
        return resolve_a_symbol(symbol)

    def get_bars(self, symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
        # 先本地校验代码格式（所有通道共用）
        resolve_a_symbol(symbol)
        errors = []
        for provider in self._providers_lazy():
            try:
                df = provider.get_bars(symbol, interval, limit)
                if df is not None and len(df):
                    return df
                errors.append(f"{provider.provider_name}：未返回数据")
            except Exception as e:
                errors.append(f"{provider.provider_name}：{e}")
        detail = "；".join(errors) or "未知错误"
        raise ValueError(f"A股行情获取失败（{detail}）。请检查网络后重试，或改用「模拟数据」离线演示")

    def get_quote(self, symbol: str):
        resolve_a_symbol(symbol)
        for provider in self._providers_lazy():
            try:
                q = provider.get_quote(symbol)
                if q:
                    return q
            except Exception:
                continue
        return None
