"""
DataManager — 数据获取、清洗、技术指标计算。

职责：
  - 优先读取本地 CSV 缓存（避免限流）
  - 本地无缓存时尝试 yfinance 下载
  - 数据质量检查（缺失值、异常价格）
  - 计算技术指标：SMA, RSI, ADX, ATR, 波动率

来自书中第 21 课 core/data_manager.py。
"""

import time
from pathlib import Path
import numpy as np
import pandas as pd
from typing import List, Tuple, Optional


class DataManager:
    """数据管理器 —— 获取行情并计算技术指标。"""

    def __init__(self, cache_dir: str = "./data_cache"):
        self.cache_dir = Path(cache_dir)

    # ------------------------------------------------------------------
    # 数据获取
    # ------------------------------------------------------------------
    def get_history(
        self,
        symbol: str,
        start_date: str = "2021-01-01",
        end_date: str = "2026-01-01",
    ) -> pd.DataFrame:
        """获取历史 OHLCV 数据（优先本地缓存 → yfinance 兜底）。"""
        # ---- 1) 尝试本地缓存 ----
        cache_path = self.cache_dir / f"{symbol}.csv"
        if cache_path.exists():
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        else:
            # ---- 2) yfinance 兜底 ----
            df = self._download_yf(symbol, start_date, end_date)
            if df is None:
                raise RuntimeError(f"无法获取 {symbol} 数据：本地无缓存且 yfinance 被限流。"
                                   f"请先运行 download_data.py 下载数据。")

        # ---- 3) 统一列名 ----
        col_map = {
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
        df = df.rename(columns=col_map)

        required = ["open", "high", "low", "close", "volume"]
        # 如果缺少 volume 列（某些 CSV），补一列
        for c in required:
            if c not in df.columns:
                df[c] = 0.0
        df = df[[c for c in required]]

        # ---- 4) 裁切日期范围 ----
        df = df.loc[start_date:end_date]
        df = df[~df.index.duplicated()]

        if df.empty:
            raise ValueError(f"{symbol}: 日期范围内无数据")

        return df

    @staticmethod
    def _download_yf(symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """尝试从 yfinance 下载数据。"""
        try:
            import yfinance as yf
        except ImportError:
            return None

        for attempt in range(3):
            try:
                df = yf.download(symbol, start=start, end=end, progress=False)
                if not df.empty:
                    return df
            except Exception:
                pass
            time.sleep(2 ** attempt)
        return None

    # ------------------------------------------------------------------
    # 技术指标
    # ------------------------------------------------------------------
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算全部技术指标，直接附加到 df 上返回。"""
        df = df.copy()

        # ---- 收益率 ----
        df["returns"] = df["close"].pct_change()

        # ---- 移动平均 ----
        df["sma_20"] = df["close"].rolling(20).mean()
        df["sma_50"] = df["close"].rolling(50).mean()
        df["sma_200"] = df["close"].rolling(200).mean()

        # ---- 波动率（年化）- 20 日滚动 ----
        df["volatility"] = (
            df["returns"].rolling(20).std() * np.sqrt(252)
        )

        # ---- RSI (14) ----
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

        # ---- ATR (14) ----
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()

        # ---- ADX (14) ----
        df["adx"] = self._calc_adx(df, period=14)

        return df

    @staticmethod
    def _calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算 ADX (Average Directional Index)。"""
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)

        up_move = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm = pd.Series(0.0, index=df.index)
        minus_dm = pd.Series(0.0, index=df.index)

        plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
        minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

        # True Range (简化版)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100.0 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
        minus_di = 100.0 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))

        dx = (
            (plus_di - minus_di).abs()
            / (plus_di + minus_di).replace(0, np.nan)
            * 100.0
        )
        adx = dx.rolling(period).mean()
        return adx

    # ------------------------------------------------------------------
    # 数据验证
    # ------------------------------------------------------------------
    def validate(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """检查数据质量，返回 (是否通过, 错误列表)。"""
        errors = []

        if df.empty:
            errors.append("DataFrame is empty")
            return False, errors

        if df["close"].isnull().any():
            n_missing = df["close"].isnull().sum()
            errors.append(f"Missing close prices: {n_missing} rows")

        if (df["close"] <= 0).any():
            errors.append("Invalid prices (<= 0) found")

        if df["high"].lt(df["low"]).any():
            errors.append("high < low detected (data error)")

        return len(errors) == 0, errors
