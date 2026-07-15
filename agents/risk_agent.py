"""
RiskAgent — 风控 + 资金管理，拥有一票否决权。

"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
import pandas as pd
import numpy as np


class Decision(Enum):
    APPROVE = "approve"
    REDUCE = "reduce"
    REJECT = "reject"


@dataclass
class RiskDecision:
    decision: Decision
    reason: str
    adjusted_size: Optional[float] = None   # REDUCE 时的新仓位


class RiskAgent:
    """风控 Agent —— 系统的最后一道防线。

    注意：本实现为「进程内单体」版本（对应书中阶段 1 架构）。
    未来可独立部署为微服务（阶段 2-3）。
    """

    def __init__(self, config: dict):
        cfg = config.get("risk", config)
        self.max_single = cfg.get("max_single_position", 0.15)
        self.max_symbol = cfg.get("max_symbol_exposure", 0.20)
        self.max_total = cfg.get("max_total_exposure", 0.80)
        self.kelly_fraction = cfg.get("kelly_fraction", 0.5)
        self.atr_stop_mult = cfg.get("atr_stop_multiplier", 2.0)
        self.dd_warning = cfg.get("drawdown_warning", 0.05)
        self.dd_stop = cfg.get("drawdown_stop", 0.10)
        self.dd_circuit = cfg.get("drawdown_circuit", 0.15)

        # 内部状态
        self.is_circuit_active = False
        self.peak_value: float = 0.0
        self.current_drawdown: float = 0.0

    # ------------------------------------------------------------------
    # 核心审核入口
    # ------------------------------------------------------------------
    def check(
        self,
        symbol: str,
        direction: str,
        proposed_size: float,
        current_price: float,
        portfolio: Dict[str, float],   # {symbol: position_value}
        portfolio_value: float,        # 总资产
    ) -> RiskDecision:
        """审核一笔交易请求。"""

        # ---- 0. 熔断 ----
        if self.is_circuit_active:
            return RiskDecision(Decision.REJECT, "熔断生效，禁止新开仓")

        # ---- 1. 回撤检查 ----
        if self.current_drawdown >= self.dd_stop:
            if direction == "long":
                return RiskDecision(
                    Decision.REJECT,
                    f"回撤 {self.current_drawdown:.1%} 超过控制线 {self.dd_stop:.1%}，停止开仓",
                )
            # 平仓信号在回撤期允许执行

        # ---- 2. 单笔上限 ----
        if proposed_size > self.max_single:
            return RiskDecision(
                Decision.REDUCE,
                f"仓位 {proposed_size:.1%} > 单笔上限 {self.max_single:.1%}",
                adjusted_size=self.max_single,
            )

        # ---- 3. 标的上限 ----
        current_symbol_val = portfolio.get(symbol, 0.0)
        current_pct = current_symbol_val / portfolio_value if portfolio_value > 0 else 0
        order_pct = proposed_size
        if current_pct + order_pct > self.max_symbol:
            allowed = max(0, self.max_symbol - current_pct)
            if allowed <= 0.01:
                return RiskDecision(
                    Decision.REJECT,
                    f"{symbol} 已超标的集中度上限 {self.max_symbol:.0%}",
                )
            return RiskDecision(
                Decision.REDUCE,
                f"{symbol} 接近集中度上限，缩小至 {allowed:.1%}",
                adjusted_size=allowed,
            )

        # ---- 4. 总仓位上限 ----
        total_pct = sum(portfolio.values()) / portfolio_value if portfolio_value > 0 else 0
        if total_pct + order_pct > self.max_total:
            return RiskDecision(
                Decision.REJECT,
                f"总仓位已接近上限 {self.max_total:.0%}",
            )

        return RiskDecision(Decision.APPROVE, "风控审核通过")

    # ------------------------------------------------------------------
    # 动态止损计算 (ATR-based)
    # ------------------------------------------------------------------
    def calc_stop_price(
        self,
        entry_price: float,
        atr_value: float,
        direction: str = "long",
    ) -> float:
        """基于 ATR 计算止损价。"""
        if direction == "long":
            return entry_price - self.atr_stop_mult * atr_value
        else:
            return entry_price + self.atr_stop_mult * atr_value

    # ------------------------------------------------------------------
    # Kelly 最优仓位
    # ------------------------------------------------------------------
    @staticmethod
    def kelly_position(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.5,
    ) -> float:
        """计算 Kelly 最优仓位比例（默认半 Kelly）。"""
        if avg_loss <= 0 or win_rate <= 0:
            return 0.0
        b = avg_win / avg_loss
        k = (win_rate * b - (1 - win_rate)) / b
        k = max(0.0, k) * fraction
        return round(k, 4)

    # ------------------------------------------------------------------
    # 回撤更新（每个交易日调用）
    # ------------------------------------------------------------------
    def update_drawdown(self, current_value: float):
        """更新峰值和当前回撤。"""
        self.peak_value = max(self.peak_value, current_value)
        if self.peak_value > 0:
            self.current_drawdown = (self.peak_value - current_value) / self.peak_value

        # 检查熔断触发
        if self.current_drawdown >= self.dd_circuit:
            self.is_circuit_active = True

        # 回撤恢复到控制线以下时解除熔断
        if self.is_circuit_active and self.current_drawdown < self.dd_warning:
            self.is_circuit_active = False

    def get_status(self) -> str:
        """返回当前风控状态。"""
        if self.is_circuit_active:
            return "circuit_breaker"
        if self.current_drawdown >= self.dd_stop:
            return "stop_new_positions"
        if self.current_drawdown >= self.dd_warning:
            return "reduce_risk"
        return "normal"
