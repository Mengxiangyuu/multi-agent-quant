"""
SignalAgent — 多策略信号生成 + LLM 辅助增强。

架构（来自书中第 11/14/21 课）：
  1. 各子策略（动量、均值回归）独立生成原始信号
  2. Regime Agent 输出的市场状态权重用于融合多策略信号
  3. （可选）LLM 输入最近行情描述，输出方向判断 + 置信度，
     作为额外的一路信号参与融合

重要设计决策：
  - LLM 不直接下单，只输出「方向 + 置信度」
  - 这和 AlphaForgeBench 的结论一致：LLM 做推理而非执行
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
import json
import pandas as pd
from strategies.momentum import MomentumStrategy, Signal
from strategies.mean_revert import MeanRevertStrategy
from strategies.trend_follow import TrendFollowStrategy


class SignalAgent:
    """信号生成 Agent —— 汇总各策略信号，按 Regime 权重融合。"""

    def __init__(self, config: dict):
        cfg = config.get("signal", config)

        # 初始化子策略
        mom_cfg = cfg.get("momentum", {})
        mr_cfg = cfg.get("mean_revert", {})
        self.momentum = MomentumStrategy(
            sma_fast=mom_cfg.get("sma_fast", 20),
            sma_slow=mom_cfg.get("sma_slow", 50),
        )
        self.mean_revert = MeanRevertStrategy(
            rsi_period=mr_cfg.get("rsi_period", 14),
            rsi_oversold=mr_cfg.get("rsi_oversold", 30),
            rsi_overbought=mr_cfg.get("rsi_overbought", 70),
        )
        self.trend_follow = TrendFollowStrategy(
            sma_fast=mom_cfg.get("sma_fast", 20),
            sma_slow=mom_cfg.get("sma_slow", 50),
        )

        # LLM 配置
        llm_cfg = cfg.get("llm", {})
        self.llm_enabled = llm_cfg.get("enabled", False)
        self.llm_model = llm_cfg.get("model", "gpt-4o-mini")
        self.llm_temp = llm_cfg.get("temperature", 0.7)
        self.llm_max_tokens = llm_cfg.get("max_tokens", 200)

    # ------------------------------------------------------------------
    def generate_signals(
        self,
        df: pd.DataFrame,
        symbol: str,
        regime_weights: Dict[str, float],
    ) -> List[Signal]:
        """汇总各策略信号，按 Regime 权重融合。"""
        raw: List[Signal] = []

        # 1) 趋势跟踪（每日信号）
        raw += self.trend_follow.generate(df, symbol)
        # 2) 动量策略（只在交叉点）
        raw += self.momentum.generate(df, symbol)
        # 3) 均值回归
        raw += self.mean_revert.generate(df, symbol)
        # 3) LLM 增强（可选）
        if self.llm_enabled:
            llm_sig = self._llm_signal(df, symbol)
            if llm_sig:
                raw.append(llm_sig)

        if not raw:
            return []

        # ---- 按 regime 权重调整信号强度 ----
        merged: Dict[tuple, Signal] = {}
        for sig in raw:
            weight = regime_weights.get(sig.source, 0.33)
            key = (sig.symbol, sig.direction)
            adj_strength = sig.strength * weight

            if key in merged:
                merged[key].strength += adj_strength
            else:
                sig.strength = adj_strength
                merged[key] = sig

        # 过滤弱信号（阈值降低，趋势跟踪的持续性信号需要低门槛）
        result = [s for s in merged.values() if s.strength > 0.10]
        return result

    # ------------------------------------------------------------------
    # LLM 辅助信号
    # ------------------------------------------------------------------
    def _llm_signal(self, df: pd.DataFrame, symbol: str) -> Optional[Signal]:
        """调用 LLM 对最近行情做方向判断。

        提示词设计借鉴了 AlphaForgeBench 的思路：
        LLM 输出结构化 JSON（方向 + 置信度），由系统执行，而非 LLM 直接下单。
        """
        try:
            from openai import OpenAI
        except ImportError:
            return None

        recent = self._describe_market(df)
        prompt = (
            f"You are a quantitative analyst. Given the recent market data for {symbol}, "
            f"output a JSON object with:\n"
            f'  - "direction": "long" | "close" | "none"\n'
            f'  - "confidence": 0.0 to 1.0\n'
            f'  - "reason": one short sentence\n\n'
            f"Recent market data:\n{recent}\n\n"
            f"Output ONLY the JSON, no extra text."
        )

        try:
            client = OpenAI()
            resp = client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_temp,
                max_tokens=self.llm_max_tokens,
            )
            raw = resp.choices[0].message.content.strip()
            # 清理可能的 markdown code block
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
        except Exception:
            return None

        direction = data.get("direction", "none")
        if direction == "none":
            return None

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.1, min(1.0, confidence))

        return Signal(
            symbol=symbol,
            direction=direction,
            strength=confidence * 0.5,  # LLM 信号打折，作为辅助
            source="llm",
            price=float(df["close"].iloc[-1]),
            timestamp=df.index[-1],
        )

    @staticmethod
    def _describe_market(df: pd.DataFrame) -> str:
        """将最近行情压缩为一段文字描述供 LLM 阅读。"""
        tail = df.dropna().tail(20)
        if len(tail) < 5:
            return "Insufficient data."

        start_price = float(tail["close"].iloc[0])
        end_price = float(tail["close"].iloc[-1])
        ret_5d = (end_price / float(tail["close"].iloc[-5]) - 1) * 100
        ret_20d = (end_price / start_price - 1) * 100
        high_20d = float(tail["high"].max())
        low_20d = float(tail["low"].min())
        last_rsi = float(tail["rsi"].iloc[-1]) if "rsi" in tail.columns else None
        last_vol = float(tail["volatility"].iloc[-1]) if "volatility" in tail.columns else None

        lines = [
            f"Symbol price over last 20 days: {start_price:.2f} → {end_price:.2f}",
            f"20-day return: {ret_20d:+.1f}%",
            f"5-day return: {ret_5d:+.1f}%",
            f"20-day high/low: {high_20d:.2f} / {low_20d:.2f}",
        ]
        if last_rsi is not None:
            lines.append(f"RSI(14): {last_rsi:.0f}")
        if last_vol is not None:
            lines.append(f"Annualized Volatility (20d): {last_vol:.1%}")

        return "\n".join(lines)
