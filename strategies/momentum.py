"""
动量策略 — SMA 金叉/死叉 + 趋势过滤。

逻辑：
  - 快线 (SMA20) 上穿慢线 (SMA50) → 买入信号
  - 快线下穿慢线 → 卖出信号
  - 信号强度由价格偏离均线的幅度决定
"""

from dataclasses import dataclass
from typing import List, Optional
import pandas as pd


@dataclass
class Signal:
    symbol: str
    direction: str       # "long" | "close"
    strength: float      # 0.0 - 1.0
    source: str          # "momentum" | "mean_revert" | "llm"
    price: float
    timestamp: pd.Timestamp


class MomentumStrategy:
    """SMA 交叉动量策略。"""

    name = "momentum"

    def __init__(self, sma_fast: int = 20, sma_slow: int = 50):
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow

    def generate(
        self,
        df: pd.DataFrame,
        symbol: str,
    ) -> List[Signal]:
        """返回 0-1 个信号（动量策略低频交易）。"""
        if len(df) < self.sma_slow + 2:
            return []

        col_fast = f"sma_{self.sma_fast}"
        col_slow = f"sma_{self.sma_slow}"

        fast = df[col_fast].dropna()
        slow = df[col_slow].dropna()
        if len(fast) < 3 or len(slow) < 3:
            return []

        # 前一根 K 线和当前 K 线的交叉关系
        prev_fast, curr_fast = fast.iloc[-2], fast.iloc[-1]
        prev_slow, curr_slow = slow.iloc[-2], slow.iloc[-1]

        price = float(df["close"].iloc[-1])
        timestamp = df.index[-1]

        # 金叉
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            deviation = (curr_fast - curr_slow) / curr_slow
            strength = min(1.0, max(0.3, 0.5 + deviation * 20))
            return [Signal(symbol, "long", strength, "momentum", price, timestamp)]

        # 死叉
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return [Signal(symbol, "close", 0.8, "momentum", price, timestamp)]

        return []
