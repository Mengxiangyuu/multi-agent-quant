"""
MonitorAgent — 系统监控与日志。

来自书中第 21 课 agents/monitor_agent.py。

职责：
  - 记录每日摘要日志
  - 记录交易执行日志
  - 记录风控拒绝日志
  - 追踪关键指标趋势
"""

from typing import List
import pandas as pd
from core.order import Order


class MonitorAgent:
    """系统监控 Agent。"""

    def __init__(self):
        self.trades_log: List[dict] = []
        self.rejects_log: List[dict] = []
        self.start_date: str = ""
        self.end_date: str = ""

    # ------------------------------------------------------------------
    def log_start(self, symbols: List[str], start: str, end: str):
        self.start_date = start
        self.end_date = end
        print(f"[Monitor] 回测开始 | 标的: {symbols} | {start} → {end}")

    def log_end(self):
        print(f"[Monitor] 回测结束 | 共 {len(self.trades_log)} 笔成交, "
              f"{len(self.rejects_log)} 次风控拒绝")

    # ------------------------------------------------------------------
    def log_trade(self, date: pd.Timestamp, order: Order):
        """记录一笔成交。"""
        entry = {
            "date": date,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": order.filled_price,
            "fee": order.fee,
        }
        self.trades_log.append(entry)

    def log_reject(self, date: pd.Timestamp, signal, reason: str):
        """记录一次风控拒绝。"""
        self.rejects_log.append({
            "date": date,
            "symbol": signal.symbol,
            "direction": signal.direction,
            "strength": signal.strength,
            "reason": reason,
        })

    # ------------------------------------------------------------------
    def daily_summary(self, date, portfolio, prices) -> str:
        """每日摘要（书中 main_loop Step 7）。"""
        tv = portfolio.compute_total_value(prices)
        return (
            f"{date.strftime('%Y-%m-%d')} | "
            f"净值=${tv:,.0f} | "
            f"现金=${portfolio.cash:,.0f} | "
            f"回撤={portfolio.current_drawdown:.1%}"
        )
