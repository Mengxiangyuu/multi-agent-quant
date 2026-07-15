"""
Order — 订单模型。

来自书中第 21 课 core/order.py。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """订单数据模型。"""
    order_id: str
    symbol: str
    side: str            # "buy" | "sell"
    quantity: int
    order_type: str      # "market" | "limit"
    limit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: Optional[float] = None
    filled_time: Optional[str] = None
    fee: float = 0.0
