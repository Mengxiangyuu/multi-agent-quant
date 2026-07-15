# Multi-Agent Quantitative Trading System

> 基于《AI Quantitative Trading: From Zero to One》，从零实现了一个多智能体量化回测系统。核心发现：加入 RiskAgent（一票否决权）后，最大回撤降低 51%，Calmar 比率提升 34%。

---

## 项目背景

市面上大多数量化教程停留在回测框架 API 翻译和技术指标堆砌，这本书的不同之处在于教的是**系统架构**——怎么设计一个能真正跑起来的交易系统，而不是过拟合一个"神奇策略"。

读完书后我按照第 21 课的项目实战框架，从零搭建了这个系统。过程中最大的收获是理解了"单 Agent 为什么不够"：信号、风控、执行这三件事混在一个超级大脑里，既无法并行、也难调试、单点故障就全崩。多智能体的核心不是"智能"，而是**分工**——每个 Agent 只做一件事并做到极致。

---

## 架构概览

```
                          ┌──────────────────────┐
                          │    DataManager         │
                          │  CSV 缓存 + 技术指标    │
                          └──────────┬───────────┘
                                     │ OHLCV + SMA/RSI/ADX/ATR
                                     ▼
                          ┌──────────────────────┐
                          │    RegimeAgent         │
                          │  市场状态识别           │
                          │  ADX + 波动率 →        │
                          │  trending / mean_revert│
                          │  / crisis / uncertain  │
                          └──────────┬───────────┘
                                     │ 策略权重向量
                                     ▼
                          ┌──────────────────────┐
                          │    SignalAgent         │
                          │  多策略信号融合         │
                          │  · 趋势跟踪 (SMA)       │
                          │  · 动量 (金叉死叉)      │
                          │  · 均值回归 (RSI)       │
                          │  · LLM 辅助 (可选)      │
                          └──────────┬───────────┘
                                     │ 交易信号
                                     ▼
                ┌────────────────────────────────────┐
                │          RiskAgent                   │
                │       ★ 一票否决权 ★                 │
                │  · 单笔仓位上限 (15%)                 │
                │  · Kelly 最优仓位                    │
                │  · ATR 动态止损 (2×)                  │
                │  · 三级回撤熔断 (5%/10%/15%)           │
                │  · 硬约束不可覆盖                      │
                └──────────────┬─────────────────────┘
                               │ APPROVE / REDUCE / REJECT
                               ▼
                ┌────────────────────────────────────┐
                │        ExecutionAgent                │
                │  订单创建 · 模拟成交                  │
                │  含滑点 (0.05%) + 手续费 (0.1%)       │
                └──────────────┬─────────────────────┘
                               │
                               ▼
                ┌────────────────────────────────────┐
                │      Portfolio + MonitorAgent       │
                │  组合管理 · 回撤追踪 · 审计日志        │
                └────────────────────────────────────┘
```

---

## 设计决策

### 为什么需要多个 Agent（书第 11 课）

| 单 Agent 的问题 | 多 Agent 怎么解决 |
|---|---|
| 串行处理，错过时效 | Signal/Risk/Execution 独立运行 |
| 一个模块崩，全挂 | RiskAgent 故障 → 自动熔断，不影响平仓 |
| 什么都做，什么都不精 | 每个 Agent 只聚焦自己的职责 |
| 亏了不知道谁的锅 | 独立日志，可精确定位问题 |

### RiskAgent 的规范

1. **硬约束不可覆盖** — 即使其他 Agent 有"更好的理由"也不能绕过风控
2. **独立数据源** — RiskAgent 自己算回撤和仓位，不依赖其他 Agent 的数据
3. **审计日志完整** — 每笔拒绝都记录时间、信号、决策、理由
4. **降级策略** — RiskAgent 故障时系统进入安全模式，只能减仓不能开仓

### LLM 在量化中的定位

实验数据很清楚：LLM 直接做交易决策会跑输随机策略。所以本系统中 LLM 只输出结构化 JSON `{direction, confidence, reason}`，由系统负责执行——LLM 做推理，系统做执行，随机性被控制在生成阶段。

---

## 项目结构

```
multi-agent-quant/
├── agents/
│   ├── regime_agent.py         # 市场状态识别（ADX + Vol）
│   ├── signal_agent.py         # 多策略信号融合 + LLM 辅助
│   ├── risk_agent.py           # 一票否决 + Kelly + ATR + 熔断
│   ├── execution_agent.py      # 订单创建与模拟成交
│   └── monitor_agent.py        # 审计日志
├── core/
│   ├── data_manager.py         # 数据加载 + SMA/RSI/ADX/ATR 计算
│   ├── backtest_engine.py      # 事件驱动日频回测引擎
│   ├── portfolio.py            # 持仓管理 + 回撤追踪
│   └── order.py                # 订单模型
├── strategies/
│   ├── trend_follow.py         # SMA 趋势跟踪（每日信号）
│   ├── momentum.py             # 金叉/死叉（交叉点信号）
│   └── mean_revert.py          # RSI 超买超卖（极端点信号）
├── config.yaml                 # 集中配置文件
├── main.py                     # 命令行入口
├── compare_experiment.py       # 有无风控对比实验
└── README.md
```

---

## 快速开始

```bash
# 1. 安装依赖
python3 -m venv lianghua && source lianghua/bin/activate
pip install -r requirements.txt

# 2. 运行回测
python main.py --symbols TSLA                # 完整系统（默认有风控）
python main.py --symbols TSLA --skip-risk    # 对照组（关闭风控）

# 3. 核心对比实验
python compare_experiment.py
```

---

## 实验结果

### TSLA 2021-2026 日频回测

| 指标 | 有 RiskAgent | 无 RiskAgent | 效果 |
|---|---|---|---|
| 年化收益率 (ARR) | 14.6% | 22.1% | — |
| 夏普比率 (SR) | 0.74 | 0.89 | — |
| **最大回撤 (MDD)** | **14.9%** | 30.2% | **↓ 51%** |
| **Calmar 比率 (CR)** | **0.98** | 0.73 | **↑ 34%** |
| 年化波动率 (VOL) | 15.2% | 20.8% | ↓ 27% |
| 交易次数 | 74 | 87 | 风控拒绝 40 次 |
| 胜率 | 85.1% | 81.6% | — |

### 分析

RiskAgent 以牺牲部分收益为代价，将回撤减半，Calmar（收益/回撤比）提升 34%。这验证了书中第 15 课的核心观点：**"活下来"比"赚得多"更重要。** 单独看收益或夏普都会误导决策，Calmar 才是衡量风控价值的核心指标。

---

## 数据说明

项目使用几何布朗运动生成的模拟数据（种子固定，结果可复现），根据每只标的的真实特征分别设参：

| 标的 | 年化漂移 μ | 年化波动 σ | 特征 |
|---|---|---|---|
| AAPL | 18% | 26% | 趋势型大盘科技 |
| TSLA | 8% | 35% | 高波动成长股 |
| BTC-USD | 28% | 72% | 加密货币 |

数据保存在 `data_cache/` 目录的 CSV 文件中。DataManager 的加载逻辑是：优先读本地 CSV → 如果本地没有则尝试 yfinance 下载。在有网络条件时，替换为真实数据的 CSV 文件即可无缝切换。

---

## 当前局限

- 使用模拟数据，无法完全复现真实市场的 microstructure 效应（但策略逻辑和 Agent 协作机制与数据来源无关）
- 只做单资产二元信号（全仓/空仓），多资产组合管理后续扩展
- 日频回测，不适用于 Tick/分钟级策略

---

## 参考

- [AI Quantitative Trading: From Zero to One](https://github.com/waylandzhang/ai-quant-book) — Wayland Zhang

