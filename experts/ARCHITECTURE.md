# Experts 子系统架构

本文档说明 `experts/` 的设计意图、与 skill / scripts 的边界关系，以及可独立运行点。experts 处于"既不属于 skills/ 也不属于 scripts/"的灰区，本文确立其作为**独立子系统的地位**与边界约束。

## 定位

experts/ 是**专家人设 + 决策引擎**的独立子系统，承载两件事：

1. **人设资产**：16 份专家哲学档案（`*.md`），是项目的内容资产而非代码资产，对应 README 中"16 份专家人设"的对外宣传。
2. **决策引擎**：注册表 + 评分矩阵 + 投票引擎，把人设转成可执行的 `score / vote / decide` 调用。

**与 skill 的关系**：`/stock debate` 模式调用 `experts.decide.run_debate` 直接产出结论，**绕过** `scripts/business/stock_analysis.py` 业务层。这意味着 experts 不是 skill 的实现细节，而是 skill 可以直接调用的对等子系统。

## 模块边界

```
experts/
├── *.md                 # 人设内容资产（哲学档案）——16 份
├── registry.py          # 注册表：16 人 active/legacy 标记 + 元数据
├── decide.py / decide.md # 对外主入口：run_debate(stock_data, mode)
├── vote_engine.py       # aggregate_votes(expert_results, ...)——5 长 + 3 短投票
├── scoring/             # 各专家独立 score() 函数 + weighted_merge 合并
├── calibration.py       # 专家历史准确率自校准（clibration_factor ± 0.1）
├── market_detector.py   # 市场环境指数（regime）→ 长短线权重
├── veto_evaluator.py    # 否决条件评估器
├── formatter.py         # 输出格式化（decide.md 文本模板）
├── yaml/                # expert 配置可 YAML 化（实验性）
├── types.py             # ExpertProfile dataclass
├── __init__.py          # 公开 API 入口（list_active_experts 等）
├── ARCHITECTURE.md      # 本文档
└── README.md            # 16 份人设内容档案索引
```

## 可独立运行点

experts/ **不依赖 skills/ 与 scripts/ 业务层**即可工作：

```bash
# 不启动 stock 分析，直接跑专家投票
python3 -c "from experts.decide import run_debate; print(run_debate({'code': 'sh600519'}, mode='quick'))"

# 校准自跑（不依赖业务层）
python3 scripts/calibration.py record   # 记录投票结果
python3 scripts/calibration.py verify   # 验证 30 日后准确率
python3 scripts/calibration.py report   # 输出 calibration_factor
```

**因此 experts/ 是独立可运行的子系统**，对外可作为 Python 包单独 import，不依赖 SKILL.md 加载流程。

## 与 skill 的边界（不可越界）

| skill 入口 | experts 调用点 | 边界约束 |
| --- | --- | --- |
| `/stock debate` | `experts.decide.run_debate` | 唯一允许的入口。skill 不应直接 import `vote_engine` 或 `scoring/*` |
| `/stock quick/full` | 不调用 experts | 5 层分析走 `scripts/business/stock_analysis.py`，不混用 experts 投票 |
| `/portfolio health` | 不调用 experts | 风险评分独立于专家投票 |
| `/screener` | 不调用 experts | 策略打分独立于专家投票 |
| `/market` | `experts.market_detector` | 市场环境指数复用 |

## 历史合并（合并型专家算 1 票）

v2.4.0 起，legacy 8 人（active=False）已合并入 active 8 人，**合并在 `score()` 阶段**（`weighted_merge` 0.5/0.5）已完成，到 `vote_engine._count_votes()` 时**算 1 票**。5 长 + 3 短 = 8 active 每人 1 票。详见 `experts/vote_engine.py:62-66` 与 `experts/scoring/_merge.py:23-84`。

## 校验

`experts/scoring/_merge.py:23` 的 `weighted_merge` 是合并型专家的核心算子，**不要轻动**——5 长 + 3 短票数对称依赖它。修改前必须跑 `tests/unit/test_vote_engine.py` 验证票数没破。