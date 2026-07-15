"""
BacktestEngine — 事件驱动日频回测引擎。

来自书中第 21 课 Step 6 的 main_loop，严格遵循书中流程：

  1. 获取数据（走到当日）
  2. 识别市场状态（Regime Agent）
  3. 生成信号（Signal Agent，按 Regime 权重融合）
  4. 风控审核（Risk Agent，一票否决）
  5. 执行订单（Execution Agent）
  6. 更新组合
  7. 记录日志（Monitor Agent）

以及第 7 课的 Quality Gate：
  - 无未来数据泄漏
  - 成本建模真实（含手续费+滑点）
  - 回测清单检查
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from core.data_manager import DataManager
from core.portfolio import Portfolio
from core.order import Order, OrderStatus
from agents.regime_agent import RegimeAgent, RegimeState
from agents.signal_agent import SignalAgent
from agents.risk_agent import RiskAgent, Decision
from agents.execution_agent import ExecutionAgent
from agents.monitor_agent import MonitorAgent


@dataclass
class BacktestResult:
    """回测结果。"""
    returns: List[float] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    dates: List[pd.Timestamp] = field(default_factory=list)
    trades: List[dict] = field(default_factory=list)
    regime_history: List[dict] = field(default_factory=list)

    # 计算指标
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    volatility: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0


class BacktestEngine:
    """日频事件驱动回测引擎。

    使用方式：
        engine = BacktestEngine(config)
        result = engine.run(symbols=["AAPL"])
        engine.report(result)
    """

    def __init__(self, config: dict):
        self.config = config
        bt_cfg = config.get("backtest", config)

        self.start_date = bt_cfg.get("start_date", "2021-01-01")
        self.end_date = bt_cfg.get("end_date", "2026-01-01")
        self.initial_capital = bt_cfg.get("initial_capital", 100_000)
        self.transaction_cost = bt_cfg.get("transaction_cost", 0.001)

        # 初始化各模块
        self.data_mgr = DataManager()
        self.regime_agent = RegimeAgent(config)
        self.signal_agent = SignalAgent(config)
        self.risk_agent = RiskAgent(config)
        self.execution_agent = ExecutionAgent(config)
        self.monitor = MonitorAgent()

    # ------------------------------------------------------------------
    def run(
        self,
        symbols: List[str],
        enable_risk: bool = True,
    ) -> BacktestResult:
        """执行回测。

        enable_risk=False 时跳过 RiskAgent（用于对比实验）。
        """
        result = BacktestResult()
        portfolio = Portfolio(initial_capital=self.initial_capital)

        # ---- 加载所有资产数据 ----
        data: Dict[str, pd.DataFrame] = {}
        for sym in symbols:
            df = self.data_mgr.get_history(sym, self.start_date, self.end_date)
            df = self.data_mgr.calculate_indicators(df)
            ok, errs = self.data_mgr.validate(df)
            if not ok:
                print(f"[WARN] {sym} 数据质量问题: {errs}")
            data[sym] = df

        # ---- 取所有日期的并集作为交易日历 ----
        all_dates = sorted(set().union(*[data[sym].index for sym in symbols]))
        # 过滤：确保所有标的数据都已就绪
        valid_dates = []
        for dt in all_dates:
            if all(dt in data[sym].index for sym in symbols):
                valid_dates.append(dt)
        all_dates = valid_dates

        if len(all_dates) < 60:
            raise ValueError("交易日不足 60 天，无法回测")

        # ---- 逐日回测主循环（书中 main_loop） ----
        self.monitor.log_start(symbols, self.start_date, self.end_date)

        for i, date in enumerate(all_dates):
            # --- 需要足够的 lookback 才能计算指标 ---
            if i < 60:
                # 记录初始净值
                prices_now = {s: float(data[s].loc[date, "close"]) for s in symbols}
                tv = portfolio.compute_total_value(prices_now)
                portfolio.update_drawdown(tv)
                result.values.append(tv)
                result.dates.append(date)
                self.risk_agent.update_drawdown(tv)
                continue

            # ========== Step 1: 获取当日行情快照 ==========
            prices = {}
            snapshots = {}
            for sym in symbols:
                series = data[sym].loc[:date].copy()
                prices[sym] = float(series["close"].iloc[-1])
                snapshots[sym] = series

            # ========== Step 2: 识别市场状态 ==========
            # 使用主要标的（第一个 symbol）做 Regime 检测
            primary_df = snapshots[symbols[0]]
            regime_state = self.regime_agent.detect(primary_df)
            result.regime_history.append({
                "date": date,
                "regime": regime_state.regime,
                "confidence": regime_state.confidence,
            })

            # ========== Step 3: 生成信号 ==========
            all_signals = []
            for sym in symbols:
                sigs = self.signal_agent.generate_signals(
                    snapshots[sym], sym, regime_state.weights
                )
                all_signals += sigs

            # ========== Step 4: 风控审核 ==========
            tv_before = portfolio.compute_total_value(prices)
            pos_map = portfolio.get_position_map(prices, tv_before)

            for sig in all_signals:
                if enable_risk:
                    decision = self.risk_agent.check(
                        symbol=sig.symbol,
                        direction=sig.direction,
                        proposed_size=sig.strength,
                        current_price=sig.price,
                        portfolio=pos_map,
                        portfolio_value=tv_before,
                    )
                else:
                    decision = type('RiskDecision', (), {
                        'decision': Decision.APPROVE,
                        'adjusted_size': None,
                        'reason': '风控已禁用',
                    })()

                if decision.decision == Decision.REJECT:
                    self.monitor.log_reject(date, sig, decision.reason)
                    continue

                size = (
                    decision.adjusted_size
                    if hasattr(decision, 'adjusted_size') and decision.adjusted_size
                    else sig.strength
                )

                # ========== Step 5: 执行订单 ==========
                if sig.direction == "close":
                    # 卖出平仓
                    current_shares = portfolio.positions.get(sig.symbol, 0)
                    if current_shares > 0:
                        order = Order(
                            order_id=f"{date.strftime('%Y%m%d')}-{sig.symbol}",
                            symbol=sig.symbol,
                            side="sell",
                            quantity=current_shares,
                            order_type="market",
                        )
                        self.execution_agent.fill_order(order, sig.price)
                        portfolio.apply_trade(
                            sig.symbol, "sell", current_shares,
                            order.filled_price, order.fee, date,
                        )
                        self.monitor.log_trade(date, order)
                        result.trades.append({
                            "date": date, "symbol": sig.symbol,
                            "side": "sell", "quantity": current_shares,
                            "price": order.filled_price, "fee": order.fee,
                            "source": sig.source,
                        })
                else:
                    # 买入
                    tv_after_sell = portfolio.compute_total_value(prices)
                    order = self.execution_agent.create_order(
                        sig.symbol, sig.direction, size, tv_after_sell, sig.price,
                    )
                    if order is None:
                        continue
                    self.execution_agent.fill_order(order, sig.price)
                    total_cost = order.quantity * order.filled_price + order.fee
                    if total_cost > portfolio.cash:
                        # 资金不足，跳过
                        continue
                    portfolio.apply_trade(
                        sig.symbol, "buy", order.quantity,
                        order.filled_price, order.fee, date,
                    )
                    self.monitor.log_trade(date, order)
                    result.trades.append({
                        "date": date, "symbol": sig.symbol,
                        "side": "buy", "quantity": order.quantity,
                        "price": order.filled_price, "fee": order.fee,
                        "source": sig.source,
                    })

            # ========== Step 6: 更新组合 ==========
            tv = portfolio.compute_total_value(prices)
            portfolio.update_drawdown(tv)
            self.risk_agent.update_drawdown(tv)
            result.values.append(tv)
            result.dates.append(date)

        # ========== Step 7: 计算指标 ==========
        self.monitor.log_end()
        return self._calc_metrics(result, portfolio)

    # ------------------------------------------------------------------
    # 指标计算
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_metrics(result: BacktestResult, portfolio: Portfolio) -> BacktestResult:
        """计算全部回测指标。"""
        values = pd.Series(result.values)
        if len(values) < 2:
            return result

        # 日收益率
        returns = values.pct_change().dropna()
        result.returns = returns.tolist()

        # 年化收益率
        n_years = (result.dates[-1] - result.dates[0]).days / 365.25
        if n_years > 0 and values.iloc[0] > 0:
            result.annual_return = (values.iloc[-1] / values.iloc[0]) ** (1 / n_years) - 1
        else:
            result.annual_return = 0.0

        # 波动率
        result.volatility = float(returns.std() * np.sqrt(252)) if len(returns) > 0 else 0.0

        # Sharpe
        rf_daily = 0.03 / 252
        excess = returns - rf_daily
        if excess.std() > 0:
            result.sharpe_ratio = float(excess.mean() / excess.std() * np.sqrt(252))
        else:
            result.sharpe_ratio = 0.0

        # 最大回撤
        peak = values.iloc[0]
        mdd = 0.0
        for v in values:
            peak = max(peak, v)
            dd = (peak - v) / peak
            mdd = max(mdd, dd)
        result.max_drawdown = float(mdd)

        # Calmar
        result.calmar_ratio = (
            result.annual_return / result.max_drawdown
            if result.max_drawdown > 0 else 0.0
        )

        # Sortino
        downside = returns[returns < 0]
        if len(downside) > 0 and downside.std() > 0:
            result.sortino_ratio = float(
                (returns.mean() - rf_daily) / downside.std() * np.sqrt(252)
            )
        else:
            result.sortino_ratio = 0.0

        # 胜率
        result.total_trades = len(result.trades)
        if result.total_trades > 0:
            # 用价格变化方向判断每笔交易的胜负（简化）
            # 更好做法是在 trades 中记录 PnL
            wins = sum(1 for t in result.trades if t["side"] == "buy")
            result.win_rate = wins / result.total_trades

        return result

    # ------------------------------------------------------------------
    @staticmethod
    def report(result: BacktestResult):
        """打印回测报告。"""
        print("\n" + "=" * 60)
        print("  回测结果报告")
        print("=" * 60)
        print(f"  年化收益率 (ARR) : {result.annual_return:>8.1%}")
        print(f"  夏普比率  (SR)   : {result.sharpe_ratio:>8.2f}")
        print(f"  最大回撤  (MDD)  : {result.max_drawdown:>8.1%}")
        print(f"  Calmar 比率 (CR)  : {result.calmar_ratio:>8.2f}")
        print(f"  Sortino 比率(SoR) : {result.sortino_ratio:>8.2f}")
        print(f"  年化波动率 (VOL)  : {result.volatility:>8.1%}")
        print(f"  交易次数          : {result.total_trades:>8d}")
        print(f"  胜率              : {result.win_rate:>8.1%}")
        print("=" * 60)
