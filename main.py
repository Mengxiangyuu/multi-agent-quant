#!/usr/bin/env python3
"""
Multi-Agent Quantitative Trading System
========================================

基于《AI Quantitative Trading: From Zero to One》的多智能体架构。

启动方式:
    python main.py                 # 默认标的 AAPL
    python main.py --symbol AAPL,TSLA,BTC-USD
"""

import argparse
import yaml
from pathlib import Path
from core.backtest_engine import BacktestEngine


def load_config(path: str = "config.yaml") -> dict:
    cfg_path = Path(__file__).parent / path
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="多智能体量化交易系统")
    parser.add_argument(
        "--symbols", type=str, default="AAPL",
        help="投资标的，逗号分隔 (default: AAPL)",
    )
    parser.add_argument(
        "--skip-risk", action="store_true",
        help="跳过风控 Agent（用于观察无风控时的表现）",
    )
    parser.add_argument(
        "--config", type=str, default="config.yaml",
        help="配置文件路径",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    config = load_config(args.config)

    print(f"\n{'='*60}")
    print(f"  多智能体量化交易系统")
    print(f"  标的: {symbols}")
    print(f"  风控: {'关闭' if args.skip_risk else '启用'}")
    print(f"{'='*60}")

    engine = BacktestEngine(config)
    result = engine.run(symbols, enable_risk=not args.skip_risk)
    engine.report(result)


if __name__ == "__main__":
    main()
