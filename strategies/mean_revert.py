"""
均值回归策略 — RSI 超买超卖。

逻辑：
  - RSI < oversold (30) → 超卖反弹，买入
  - RSI > overbought (70) → 超买回落，卖出
  - 信号强度由 RSI 极端程度决定
"""

from dataclasses import dataclass
from typing import List
import pandas as pd
from .momentum import Signal


class MeanRevertStrategy:
    """RSI 均值回归策略。"""

    name = "mean_revert"

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def generate(
        self,
        df: pd.DataFrame,
        symbol: str,
    ) -> List[Signal]:
        """返回 0-1 个信号。"""
        rsi = df["rsi"].dropna()
        if len(rsi) < 2:
            return []

        prev_rsi = float(rsi.iloc[-2])
        curr_rsi = float(rsi.iloc[-1])
        price = float(df["close"].iloc[-1])
        timestamp = df.index[-1]

        # 超卖区上穿 → 买入
        if prev_rsi < self.rsi_oversold and curr_rsi >= self.rsi_oversold:
            strength = min(1.0, (self.rsi_oversold - curr_rsi + 20) / 20)
            strength = max(0.3, strength)
            return [Signal(symbol, "long", strength, "mean_revert", price, timestamp)]

        # 超买区下穿 → 卖出
        if prev_rsi > self.rsi_overbought and curr_rsi <= self.rsi_overbought:
            return [Signal(symbol, "close", 0.8, "mean_revert", price, timestamp)]

        return []
