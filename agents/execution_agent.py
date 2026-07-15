"""
ExecutionAgent — 订单创建与模拟成交。

来自书中第 21 课 agents/execution_agent.py。

职责：
  - 将信号转换为订单（引用 core/order 模型）
  - 模拟市价成交（含滑点 + 手续费）
  - 管理订单状态

当前为「纸上交易」模式（对应书中阶段 2）。
"""

from typing import Optional, Dict
import uuid
from datetime import datetime

from core.order import Order, OrderStatus


class ExecutionAgent:
    """订单执行 Agent —— 信号 → 订单 → 成交记录。"""

    def __init__(self, config: dict):
        cfg = config.get("execution", config)
        self.slippage = cfg.get("slippage", 0.0005)
        self.transaction_cost = config.get("backtest", {}).get("transaction_cost", 0.001)
        self.orders: Dict[str, Order] = {}

    # ------------------------------------------------------------------
    def create_order(
        self,
        symbol: str,
        direction: str,
        size_pct: float,
        portfolio_value: float,
        current_price: float,
    ) -> Optional[Order]:
        """将信号转为订单。"""
        target_dollar = portfolio_value * size_pct
        quantity = int(target_dollar / current_price)

        if quantity <= 0:
            return None

        side = "buy" if direction == "long" else "sell"
        order = Order(
            order_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type="market",
        )
        self.orders[order.order_id] = order
        return order

    # ------------------------------------------------------------------
    def fill_order(self, order: Order, current_price: float):
        """模拟市价成交（含滑点 + 手续费）。"""
        slip_dir = 1 if order.side == "buy" else -1
        fill_price = current_price * (1 + slip_dir * self.slippage)

        order.status = OrderStatus.FILLED
        order.filled_price = fill_price
        order.filled_time = datetime.now().isoformat()
        order.fee = order.quantity * fill_price * self.transaction_cost
