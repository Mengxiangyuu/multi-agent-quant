"""
趋势跟踪策略 — 在 SMA 快线上方时持续看多。

来自书中第 4-5 课经典策略范式。

逻辑：
  - SMA20 > SMA50 → 趋势向上 → 持有/买入
  - SMA20 < SMA50 → 趋势向下 → 平仓
  - 每天都可输出信号（不限于交叉点），让系统有持续持仓
"""

from typing import List
import pandas as pd
from .momentum import Signal


class TrendFollowStrategy:
    """SMA 趋势跟踪策略 —— 持续输出方向信号。"""

    name = "trend_follow"

    def __init__(self, sma_fast: int = 20, sma_slow: int = 50):
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow

    def generate(self, df: pd.DataFrame, symbol: str) -> List[Signal]:
        """每根 K 线都判断方向。"""
        if len(df) < self.sma_slow + 2:
            return []

        col_fast = f"sma_{self.sma_fast}"
        col_slow = f"sma_{self.sma_slow}"

        fast = df[col_fast].dropna()
        slow = df[col_slow].dropna()
        if len(fast) < 2 or len(slow) < 2:
            return []

        curr_fast = float(fast.iloc[-1])
        curr_slow = float(slow.iloc[-1])
        price = float(df["close"].iloc[-1])
        timestamp = df.index[-1]

        # 计算趋势强度（偏离幅度）
        deviation = abs(curr_fast - curr_slow) / curr_slow

        if curr_fast > curr_slow:
            strength = min(1.0, 0.3 + deviation * 10)
            return [Signal(symbol, "long", strength, "trend_follow", price, timestamp)]
        else:
            return [Signal(symbol, "close", 0.6, "trend_follow", price, timestamp)]
