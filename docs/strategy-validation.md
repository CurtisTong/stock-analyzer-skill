# 策略验证方法论

本文档定义 stock-analyzer-skill 项目策略胜率与回测结果的**验证等级**、**升级条件**与**重新校准时机**。grill-me 审查识别出"CLAIM 与证据分离"是项目长期未明示的承诺问题（ma_volume_momentum 71.4% 胜率被当作 CLAIM 宣传，但实际上是 5 只股票样本内拟合），本文确立分层验证体系。

> 数据字段映射类（旧 `docs/archive/designs/methodology.md`）已归档——v2.0.0 重构后字段定义不再适用，本文件专注验证逻辑。

## 验证等级（status 状态机）

`scripts/strategies/registry.py` 的 `STRATEGY_VALIDATION` 定义三类状态：

| 状态 | 含义 | 适用场景 |
| --- | --- | --- |
| `in_sample` | 仅在样本内拟合过，未做外样本验证 | 默认状态——立场默认怀疑 |
| `oos_verified` | 已通过 `multi_stock_backtest.py` 外样本验证 | 满足升级阈值（见下） |
| `unknown` | 未在 registry 注册的策略 | `get_validation()` 返回占位 |

### 升级阈值（`scripts/strategies/oos_validation.py:evaluate_oos`）

```python
n_stocks >= 30            # 股票池至少 30 只
win_rate_pct >= 50.0      # 胜率至少 ≥ 50%
total_return_pct > 0      # 累计收益为正
```

三条**同时满足**才能从 `in_sample` 升级到 `oos_verified`。任一条不满足即保持 `in_sample`，note 加"未达阈值，保持 in_sample"提示。

### 默认值与运行时覆盖

```
registry.STRATEGY_VALIDATION（git tracked）
    ↓ get_validation() 函数内合并
data/strategy_oos_validation.json（git ignored, 运行时）
```

- 删 JSON 文件 → 所有策略回落到 `in_sample`
- 不写 JSON → `get_validation()` 永远返回 registry 默认值
- 升级须显式 opt-in：`multi_stock_backtest.py --update-validation`

## 重新校准时机

策略权重与因子阈值会随市场环境漂移。下列情况**必须**重跑 `--update-validation`：

| 触发 | 必要性 | 操作 |
| --- | --- | --- |
| 新策略注册到 registry | 必须 | 首次跑 `multi_stock_backtest --update-validation` 建立基线 |
| 市场环境切换（牛市→熊市 / 震荡→趋势） | 建议 | 每季度跑一次，看 OOS 胜率是否跌破阈值 |
| 因子权重调整（改 scoring.yaml） | 必须 | 权重变了，验证结果必变 |
| 单一 fetcher 数据源失效但未触发全局回退 | 建议 | 数据质量变化可能让历史 OOS 数字失真 |
| 距上次校准 ≥ 90 日 | 建议 | 季度复盘节奏 |

## CLAIM 与证据分离

**规则**：README / CHANGELOG / SKILL.md 顶部 banner 等"对外宣传位置"只能写以下三类内容：

1. **机制类声明**："支持 6 策略 × 6 因子 × 27 fetcher"——可观察可验证
2. **OOS 数字**：当且仅当 `validation_status == oos_verified` 时才允许写胜率/收益数字
3. **结构类声明**："8 位活跃专家圆桌"——结构性事实（已合并底料来源链路见 experts/ARCHITECTURE.md）

**禁止**：

- ❌ 写"71.4% 胜率"等 in_sample 数字（CLAIM 已修复，见 commit `57844b2`）
- ❌ 写"3 分钟拿到 5 层分析"等 SLA 时长（CLAIM 已修复，见 commit `57844b2`）
- ❌ 写"16 份专家"等营销虚高（CLAIM 已修复，见 commit `dd96bf8`）

## 校验链路

```
scripts/multi_stock_backtest.py --update-validation
    ↓ 写
data/strategy_oos_validation.json
    ↓ 读
scripts/strategies/registry.py:get_validation()
    ↓ 透传
screener / backtest JSON 输出 _validation_status / _validation_note
    ↓ 消费方
LLM caller / 用户 → 看到 in_sample 警告
```

消费方只需读 JSON 输出的 `_validation_status` 字段，**不要**只看顶部数字就下结论。

## 关联文档

- `scripts/strategies/registry.py:STRATEGY_VALIDATION` — 默认值（in_sample）
- `scripts/strategies/oos_validation.py` — 状态机 + JSON 读写
- `scripts/multi_stock_backtest.py` — 外样本回测入口
- `experts/ARCHITECTURE.md` — 专家投票的 5 长 + 3 短结构（与策略验证正交）
- `CONTRIBUTING.md §4.1` — CHANGELOG 粒度规则（CLAIM 修订走 CHANGELOG）

## 历史

- 2026-08-20：本文初稿（grill-me 报告 P2 第 3 条落地）
- 之前：`docs/archive/designs/methodology.md`（数据字段映射，已归档）