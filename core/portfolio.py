"""
Portfolio — 组合管理。

来自书中第 21 课 core/portfolio.py。

职责：
  - 维护持仓（标的 → 股数）
  - 维护现金余额
  - 计算总资产净值
  - 更新回撤
  - 记录交易历史
"""

from dataclasses import dataclass, field
from typing import Dict, List
import pandas as pd


@dataclass
class Portfolio:
    """组合管理器。"""

    initial_capital: float
    cash: float = 0.0
    positions: Dict[str, int] = field(default_factory=dict)   # {symbol: shares}
    trades: List[dict] = field(default_factory=list)           # 交易历史
    value_history: List[float] = field(default_factory=list)   # 每日净值
    peak_value: float = 0.0
    current_drawdown: float = 0.0

    def __post_init__(self):
        self.cash = self.initial_capital
        self.peak_value = self.initial_capital

    # ------------------------------------------------------------------
    @property
    def total_value(self) -> float:
        """总资产 = 现金 + 持仓市值。"""
        return self.cash  # 持仓市值由外部传入价格后计算

    def compute_total_value(self, prices: Dict[str, float]) -> float:
        """按当日价格计算总资产。"""
        holdings = sum(
            self.positions.get(sym, 0) * price
            for sym, price in prices.items()
        )
        return self.cash + holdings

    def get_position_value(self, symbol: str, price: float) -> float:
        """某标的的持仓市值。"""
        return self.positions.get(symbol, 0) * price

    # ------------------------------------------------------------------
    def apply_trade(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        fee: float,
        timestamp: pd.Timestamp,
    ):
        """执行一笔成交，更新现金、持仓、交易记录。"""
        if side == "buy":
            cost = quantity * price + fee
            self.cash -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
        else:  # sell
            proceeds = quantity * price - fee
            self.cash += proceeds
            self.positions[symbol] = self.positions.get(symbol, 0) - quantity
            if self.positions[symbol] <= 0:
                del self.positions[symbol]

        self.trades.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "fee": fee,
        })

    # ------------------------------------------------------------------
    def update_drawdown(self, current_value: float):
        """更新回撤状态。"""
        self.peak_value = max(self.peak_value, current_value)
        self.value_history.append(current_value)
        if self.peak_value > 0:
            self.current_drawdown = (self.peak_value - current_value) / self.peak_value

    # ------------------------------------------------------------------
    def get_position_pct(self, symbol: str, price: float, total_value: float) -> float:
        """返回某标的占总资产的比例。"""
        if total_value <= 0:
            return 0.0
        return self.get_position_value(symbol, price) / total_value

    def get_position_map(self, prices: Dict[str, float], total_value: float) -> Dict[str, float]:
        """返回 {symbol: 持仓占比}。"""
        return {
            sym: self.get_position_pct(sym, prices.get(sym, 0), total_value)
            for sym in self.positions
        }

    # ------------------------------------------------------------------
    def summary(self, prices: Dict[str, float]) -> str:
        """每日摘要。"""
        tv = self.compute_total_value(prices)
        pos_str = ", ".join(
            f"{s}: {q}股" for s, q in self.positions.items()
        ) or "空仓"
        return (
            f"总资产=${tv:,.0f} | 现金=${self.cash:,.0f} | "
            f"回撤={self.current_drawdown:.1%} | 持仓: {pos_str}"
        )
