# -*- coding: utf-8 -*-
"""SQLite 本地行情缓存（仅标准库 sqlite3）。"""
from __future__ import annotations

import os
import sqlite3
import threading
import time

import pandas as pd


class Storage:
    def __init__(self, path: str = None):
        if path is None:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "market.db")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bars (
                source   TEXT NOT NULL,
                symbol   TEXT NOT NULL,
                interval TEXT NOT NULL,
                dt       TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY (source, symbol, interval, dt)
            )
            """
        )
        self._conn.commit()

    def save(self, source: str, symbol: str, interval: str, df: pd.DataFrame) -> None:
        rows = []
        now = time.time()
        for _, r in df.iterrows():
            rows.append((source, symbol, interval, str(r["date"]),
                         float(r["open"]), float(r["high"]), float(r["low"]),
                         float(r["close"]), float(r["volume"]), now))
        with self._lock:
            self._conn.executemany(
                """INSERT OR REPLACE INTO bars
                   (source, symbol, interval, dt, open, high, low, close, volume, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self._conn.commit()

    def load(self, source: str, symbol: str, interval: str,
             ttl_seconds: float = None, limit: int = 500) -> pd.DataFrame:
        """读取缓存；ttl 为 None 表示永不过期。数据不足或过期返回 None。"""
        with self._lock:
            cur = self._conn.execute(
                """SELECT dt, open, high, low, close, volume, MAX(fetched_at) AS fa
                   FROM bars WHERE source=? AND symbol=? AND interval=?
                   GROUP BY dt ORDER BY dt DESC LIMIT ?""",
                (source, symbol, interval, int(limit)),
            )
            rows = cur.fetchall()
        if not rows:
            return None
        if ttl_seconds is not None and (time.time() - rows[0][6]) > ttl_seconds:
            return None
        df = pd.DataFrame(
            [{"date": r[0], "open": r[1], "high": r[2], "low": r[3],
              "close": r[4], "volume": r[5]} for r in reversed(rows)]
        )
        if len(df) < min(limit, 50):
            return None
        return df


class MarketData:
    """统一行情入口：模拟源直接生成；联网源走"先查缓存、后拉取、再入库"。"""

    def __init__(self):
        self.storage = Storage()

    def get_bars(self, source_id: str, symbol: str, interval: str = "1d",
                 limit: int = 500, force_refresh: bool = False) -> pd.DataFrame:
        from .data.base import ensure_registered, get_source
        ensure_registered()
        src = get_source(source_id)
        if src is None:
            raise ValueError(f"未知数据源：{source_id}")
        if not symbol or not symbol.strip():
            raise ValueError("请填写标的代码")
        symbol = symbol.strip()
        limit = max(50, min(int(limit), 5000))

        if src.id == "synthetic":
            return src.get_bars(symbol, interval, limit)

        ttl = 86400 if interval == "1d" else 300  # 日线缓存1天，分钟/小时缓存5分钟
        if not force_refresh:
            cached = self.storage.load(src.id, symbol, interval, ttl_seconds=ttl, limit=limit)
            if cached is not None:
                return cached.tail(limit).reset_index(drop=True)
        df = src.get_bars(symbol, interval, limit)
        if df is None or df.empty:
            raise ValueError("未获取到行情数据")
        self.storage.save(src.id, symbol, interval, df)
        return df

    def get_quote(self, source_id: str, symbol: str):
        from .data.base import ensure_registered, get_source
        ensure_registered()
        src = get_source(source_id)
        if src is None:
            raise ValueError(f"未知数据源：{source_id}")
        return src.get_quote(symbol.strip())
