# Multi-Agent Quantitative Trading System

> 基于《AI Quantitative Trading: From Zero to One》多智能体架构的量化回测系统。
> 核心发现：加入风控 Agent（一票否决权）后，最大回撤降低 51%，Calmar 比率提升 34%。

---

## 项目动机

在阅读 AlphaForgeBench (KDD'26) 和 AMM 链上事件预测 (arXiv:2604.20374) 两篇论文后，我开始系统学习量化交易系统的工程设计。《AI Quant Trading》这本书提供了一个清晰的框架：**不做策略圣杯，而是构建可落地的系统架构**。

AlphaForgeBench 的核心洞察——"LLM 应作为量化研究员生成策略代码，而非直接下单的随机代理"——和本书第 14 课的结论高度一致：**LLM 是最强大的研究助理，但最差劲的交易员。** 本项目在 SignalAgent 的 LLM 模块中实践了这一点：LLM 只输出结构化 JSON（方向+置信度），由系统负责执行，而非让 LLM 直接决定买卖。

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
                          │  trending/mean_revert/ │
                          │  crisis/uncertain      │
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
                │  订单创建 · 市价模拟成交               │
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

## 设计原则

### 来自书中第 11 课：为什么需要多智能体

| 单 Agent 缺陷 | 多 Agent 解法 |
|---|---|
| 无法并行处理 | Signal/Risk/Execution 独立运行 |
| 单点故障 | RiskAgent 故障 → 系统自动熔断，不影响平仓 |
| 难以专精 | 每个 Agent 只做一件事：信号/风控/执行 |
| 调试困难 | 每个 Agent 独立日志，可精确定位问题 |

### 来自书中第 15 课：风控的四条铁律

1. **硬约束不可覆盖** — 即使其他 Agent 有"更好的理由"也不能绕过 RiskAgent
2. **独立数据源** — RiskAgent 自己计算回撤和仓位，防止被喂假数据
3. **审计日志完整** — 每笔拒绝都记录时间、信号、决策、理由
4. **降级策略** — RiskAgent 故障时系统进入安全模式，禁止开仓只能减仓

### LLM 的定位（参考 AlphaForgeBench）

本系统中 LLM 只输出结构化 JSON `{direction, confidence, reason}`，由系统负责执行。这和 AlphaForgeBench 的核心范式一致：**LLM 做推理，系统做执行，随机性被封印在生成阶段。** 从实验来看，关闭 LLM 模块（默认）时系统行为完全确定性，temperature 不影响回测结果。

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
│   ├── data_manager.py         # 数据加载 + SMA/RSI/ADX/ATR
│   ├── backtest_engine.py      # 事件驱动日频回测引擎
│   ├── portfolio.py            # 持仓管理 + 回撤追踪
│   └── order.py                # 订单模型
├── strategies/
│   ├── trend_follow.py         # SMA 趋势跟踪（每日信号）
│   ├── momentum.py             # 金叉/死叉（交叉点信号）
│   └── mean_revert.py          # RSI 超买超卖（极端点信号）
├── config.yaml                 # 集中配置
├── main.py                     # 命令行入口
├── compare_experiment.py       # 核心对比实验（有无风控）
└── README.md
```

---

## 快速开始

```bash
# 安装依赖
python3 -m venv lianghua && source lianghua/bin/activate
pip install -r requirements.txt

# 运行回测
python main.py --symbols TSLA                # 完整系统
python main.py --symbols TSLA --skip-risk    # 对照组（无风控）

# 核心对比实验（生成图表）
python compare_experiment.py
```

---

## 核心实验结果

### TSLA（高波动标的）2021-2026 日频回测

| 指标 | 有 RiskAgent | 无 RiskAgent | 效果 |
|---|---|---|---|
| 年化收益率 (ARR) | 14.6% | 22.1% | — |
| 夏普比率 (SR) | 0.74 | 0.89 | — |
| **最大回撤 (MDD)** | **14.9%** | 30.2% | **↓ 51%** |
| **Calmar 比率 (CR)** | **0.98** | 0.73 | **↑ 34%** |
| 年化波动率 (VOL) | 15.2% | 20.8% | ↓ 27% |
| Sortino 比率 (SoR) | 0.71 | 1.05 | — |
| 交易次数 | 74 | 87 | 风控拒绝 40 次 |
| 胜率 | 85.1% | 81.6% | — |

### 关键发现

1. **风控以收益换安全** — ARR 从 22.1% 降至 14.6%，但回撤从 30.2% 砍到 14.9%。这和 AlphaForgeBench 论文中观察到的"收益-风险排名负相关"（高收益模型必伴随高回撤）是同一现象
2. **Calmar 比率是最诚实的指标** — 单独看收益或夏普都会误导，Calmar（收益/回撤）提升 34% 才是风控价值的真实体现
3. **架构的模块化带来了实验的对称性** — 关掉一个 Agent（RiskAgent）就能做对照实验，这是单体系统做不到的

---

## 局限性与未来方向

- **模拟数据的局限**：因网络限制使用了几何布朗运动生成的模拟数据（种子固定，可复现），其中仍保留了趋势切换和波动率聚类特征。在有条件时替换为真实 OHLCV 数据即可无缝切换
- **单资产评估**：当前只做单资产二元信号（全仓/空仓），这和 AlphaForgeBench 的 Stage 1 设计一致——先隔离信号质量再做组合优化
- **日频限制**：不适用于日内策略。更细粒度的时间框架需要事件驱动的 Tick 级回测引擎
- **LLM 模块**：当前默认关闭。后续可研究如何将 LLM 输出的结构化信号与 AlphaForgeBench 的"策略代码生成"范式结合——即让 LLM 输出一个小型规则函数而非逐日信号，从而消除信号级别的不稳定性

---

## 技术栈与参考

| 类别 | 内容 |
|---|---|
| 语言 | Python 3.9+ |
| 核心库 | pandas, numpy, matplotlib, PyYAML |
| 可选 | OpenAI API（LLM 信号模块） |
| 设计参考 | 《AI Quant Trading》第 11/14/15/21 课 |
| 相关论文 | AlphaForgeBench (KDD'26), Event-Aware AMM (arXiv:2604.20374) |

---

## License

MIT
