"""
RegimeAgent — 市场状态识别。

通过 ADX + 波动率 + 相关性识别四类市场状态：
  trending      → 趋势市 → 动量策略高权重
  mean_reverting → 震荡市 → 均值回归策略高权重
  crisis        → 危机市 → 防守模式
  uncertain     → 不确定 → 等权分配
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np
import pandas as pd


@dataclass
class RegimeState:
    regime: str             # "trending" | "mean_reverting" | "crisis" | "uncertain"
    confidence: float       # 0.0 - 1.0
    weights: Dict[str, float] = field(default_factory=dict)
    description: str = ""


class RegimeAgent:
    """市场状态识别 Agent —— 决定「现在是什么市」。

    设计原则（来自书中第 12-13 课）：
      - 危机检测优先级最高（先保命）
      - 趋势/震荡判断靠 ADX + 波动率
      - 输出策略权重而非硬切换（平滑过渡）
    """

    def __init__(self, config: dict):
        cfg = config.get("regime", config)
        self.adx_threshold = cfg.get("adx_threshold", 25)
        self.vol_low = cfg.get("volatility_low", 0.20)
        self.vol_crisis = cfg.get("volatility_crisis", 0.30)
        self.corr_crisis = cfg.get("correlation_crisis", 0.7)

    # ------------------------------------------------------------------
    def detect(self, df: pd.DataFrame) -> RegimeState:
        """从最新的行情数据中检测市场状态。"""
        adx_val = self._latest(df, "adx")
        vol_val = self._latest(df, "volatility")
        # 用近期收益率序列的自相关程度作为「趋势强度」的补充信号
        returns = df["returns"].dropna().tail(60)
        trend_strength = self._trend_strength(returns)

        # ---- 危机优先 ----
        if vol_val is not None and vol_val > self.vol_crisis:
            return RegimeState(
                regime="crisis",
                confidence=min(0.9, vol_val / 0.40),
                weights={"trend_follow": 0.1, "momentum": 0.05, "mean_revert": 0.05, "defensive": 0.8},
                description=f"高波动 ({vol_val:.1%})，启动防守",
            )

        # ---- 趋势市 ----
        if adx_val is not None and adx_val > self.adx_threshold and (
            vol_val is not None and vol_val < 0.25
        ):
            return RegimeState(
                regime="trending",
                confidence=min(0.8, adx_val / 40),
                weights={"trend_follow": 0.55, "momentum": 0.25, "mean_revert": 0.1, "defensive": 0.1},
                description=f"趋势市 ADX={adx_val:.0f} Vol={vol_val:.1%}",
            )

        # ---- 震荡市 ----
        if adx_val is not None and adx_val < 20 and (
            vol_val is not None and vol_val < self.vol_low
        ):
            return RegimeState(
                regime="mean_reverting",
                confidence=0.6,
                weights={"trend_follow": 0.15, "momentum": 0.2, "mean_revert": 0.55, "defensive": 0.1},
                description=f"震荡市 ADX={adx_val:.0f} Vol={vol_val:.1%}",
            )

        # ---- 不确定 ----
        return RegimeState(
            regime="uncertain",
            confidence=0.3,
            weights={"trend_follow": 0.3, "momentum": 0.25, "mean_revert": 0.25, "defensive": 0.2},
            description=f"不确定 ADX={adx_val} Vol={vol_val}",
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _latest(df: pd.DataFrame, col: str) -> Optional[float]:
        """取某列最后一个有效值。"""
        series = df[col].dropna()
        return float(series.iloc[-1]) if len(series) > 0 else None

    @staticmethod
    def _trend_strength(returns: pd.Series) -> float:
        """用自相关绝对值作为趋势强度的代理变量。"""
        if len(returns) < 20:
            return 0.0
        ac = returns.autocorr()
        return float(abs(ac)) if not np.isnan(ac) else 0.0
