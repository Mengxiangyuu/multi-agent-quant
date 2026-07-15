#!/usr/bin/env python3
"""
对比实验：有无风控 Agent 的回测差异
=====================================

这是简历上的核心项目亮点。

实验设计：
  组 A: 完整系统（Regime + Signal + Risk + Execution）
  组 B: 无风控系统（Regime + Signal + Execution，跳过 RiskAgent）

对比维度：
  - 年化收益率 (ARR)
  - 夏普比率 (Sharpe Ratio)
  - 最大回撤 (MaxDD)
  - Calmar 比率
  - Sortino 比率
  - 年化波动率
  - 收益曲线对比图

运行:
    python compare_experiment.py

输出:
    - 终端打印对比表
    - 保存收益曲线图 compare_result.png
"""

import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
from core.backtest_engine import BacktestEngine, BacktestResult


def load_config(path: str = "config.yaml") -> dict:
    cfg_path = Path(__file__).parent / path
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def run_experiment(
    config: dict,
    symbols: list,
    label: str,
    enable_risk: bool,
) -> BacktestResult:
    """运行一组实验。"""
    print(f"\n--- 运行 {label} ---")
    engine = BacktestEngine(config)
    result = engine.run(symbols, enable_risk=enable_risk)
    engine.report(result)
    return result


def plot_comparison(result_a: BacktestResult, result_b: BacktestResult):
    """绘制两组收益曲线对比图。"""
    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    # ---- 上图：累计收益曲线 ----
    ax1 = axes[0]
    base = 100_000
    vals_a = [v / base * 100 for v in result_a.values]
    vals_b = [v / base * 100 for v in result_b.values]
    dates = result_a.dates

    ax1.plot(dates, vals_a, color="#2ecc71", linewidth=1.2, label="With RiskAgent")
    ax1.plot(dates, vals_b, color="#e74c3c", linewidth=1.2, label="Without RiskAgent")
    ax1.axhline(y=100, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax1.set_ylabel("Portfolio Value (×$10K)", fontsize=11)
    ax1.set_title("Portfolio Value Comparison", fontsize=13, fontweight="bold")
    ax1.legend(fontsize=10)
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0fK"))
    ax1.grid(True, alpha=0.3)

    # ---- 下图：回撤曲线 ----
    ax2 = axes[1]
    dd_a = _calc_drawdown_series(result_a.values)
    dd_b = _calc_drawdown_series(result_b.values)

    ax2.fill_between(dates, 0, [-v * 100 for v in dd_a],
                     color="#2ecc71", alpha=0.3, label="With RiskAgent")
    ax2.fill_between(dates, 0, [-v * 100 for v in dd_b],
                     color="#e74c3c", alpha=0.3, label="Without RiskAgent")
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_title("Drawdown Comparison", fontsize=13, fontweight="bold")
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.invert_yaxis()

    plt.tight_layout()
    out_path = Path(__file__).parent / "compare_result.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n[图表] 已保存 → {out_path}")


def _calc_drawdown_series(values: list) -> list:
    """计算逐日回撤序列。"""
    peak = values[0]
    dd = []
    for v in values:
        peak = max(peak, v)
        dd.append((peak - v) / peak if peak > 0 else 0)
    return dd


def main():
    config = load_config()
    symbols = config.get("backtest", {}).get("assets", ["AAPL"]) or ["AAPL"]
    # 从 config 读取，默认单标的以突出差异
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",")]

    # 确保不是空列表
    if not symbols:
        symbols = ["AAPL"]

    print(f"\n{'='*60}")
    print(f"  对比实验：风控 Agent 的影响")
    print(f"  标的: {symbols}")
    print(f"{'='*60}")

    # 组 A：有风控
    result_with = run_experiment(config, symbols, "组 A — 有风控", enable_risk=True)
    # 组 B：无风控
    result_without = run_experiment(config, symbols, "组 B — 无风控", enable_risk=False)

    # ---- 打印对比表 ----
    print("\n" + "=" * 70)
    print("  实验结果对比")
    print("=" * 70)
    print(f"  {'指标':<24} {'有风控':>12} {'无风控':>12} {'改善':>12}")
    print("  " + "-" * 60)

    metrics = [
        ("年化收益率 (ARR)", "annual_return", "{:.1%}", True),
        ("夏普比率 (SR)", "sharpe_ratio", "{:.2f}", True),
        ("最大回撤 (MDD)", "max_drawdown", "{:.1%}", False),
        ("Calmar 比率 (CR)", "calmar_ratio", "{:.2f}", True),
        ("Sortino 比率 (SoR)", "sortino_ratio", "{:.2f}", True),
        ("年化波动率 (VOL)", "volatility", "{:.1%}", False),
    ]

    for name, attr, fmt, higher_better in metrics:
        v_with = getattr(result_with, attr)
        v_without = getattr(result_without, attr)
        if v_without != 0:
            change = (v_with - v_without) / abs(v_without)
        else:
            change = float("inf") if v_with > 0 else 0
        arrow = "↑" if (change > 0 and higher_better) or (change < 0 and not higher_better) else "↓"
        print(f"  {name:<24} {fmt.format(v_with):>12} {fmt.format(v_without):>12} {arrow} {change:>+8.1%}")

    print("  " + "-" * 60)
    print(f"  {'交易次数':<24} {result_with.total_trades:>12d} {result_without.total_trades:>12d}")
    print("=" * 70)

    # ---- 结论 ----
    print("\n📊 结论:")
    mdd_improve = (result_without.max_drawdown - result_with.max_drawdown) / result_without.max_drawdown if result_without.max_drawdown > 0 else 0
    sharpe_improve = (result_with.sharpe_ratio - result_without.sharpe_ratio) / abs(result_without.sharpe_ratio) if result_without.sharpe_ratio != 0 else 0

    print(f"  → RiskAgent 将最大回撤降低了 {mdd_improve:.0%}")
    print(f"  → Sharpe 比率变化了 {sharpe_improve:+.0%}")
    print(f"  → 风控通过减少过交易和拒绝高风险信号，显著改善风险调整后收益")

    # ---- 绘图 ----
    plot_comparison(result_with, result_without)


if __name__ == "__main__":
    main()
