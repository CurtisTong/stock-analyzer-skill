# 策略验证方法论

本文档定义 stock-analyzer-skill 项目策略胜率与回测结果的**验证等级**、**升级条件**与**重新校准时机**。CLAIM 与证据分离是项目长期未明示的承诺问题（ma_volume_momentum 71.4% 胜率被当作 CLAIM 宣传，但实际上是 5 只股票样本内拟合，CLAUDE.md:93 已自爆），本文确立分层验证体系。

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

### 双池联合判定（v1.21.1）

> ⚠️ **单池 OOS 结论受池构成影响极大，禁止单池升级**。实测：
> 同一批策略在 55 只跨板块大票池 walk-forward OOS 全部为正（+25.7%~+29.2%），
> 在 210 只 sector 池上全部为负（-31.7%~-44.5%）。选一个"对自己有利的池"
> 即可刷出 oos_verified，单池验证无统计意义。

`scripts/strategies/oos_validation.py:evaluate_multi_pool` 要求**每个池**都满足
`evaluate_oos` 阈值才返回 `oos_verified`，任一池不达标即整体 `in_sample`，
note 点名未达标池。

```bash
# 每个池分别跑一次，结果按 pool_type 累积到 JSON 的 pools 嵌套结构
python3 scripts/multi_stock_backtest.py --update-validation --pool-type default   # 全量 sector 池
python3 scripts/multi_stock_backtest.py --update-validation --pool-type large     # 跨板块大票池
# 双池联合判定：全部池达标才升级
python3 scripts/multi_stock_backtest.py --update-validation --pool-type large --require-all-pools
```

JSON 结构：

```json
{"balanced": {
    "validation_status": "oos_verified",
    "pools": {
        "default": {"win_rate_pct": 58.5, "n_stocks": 210, "total_return_pct": 5.2},
        "large":   {"win_rate_pct": 55.0, "n_stocks": 55,  "total_return_pct": 3.1}
    }
}}
```

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
| 新策略注册到 registry | 必须 | 首次跑 `multi_stock_backtest --update-validation --pool-type default` + `--pool-type large` 建立双池基线 |
| 市场环境切换（牛市→熊市 / 震荡→趋势） | 建议 | 每季度跑一次，看 OOS 胜率是否跌破阈值 |
| 因子权重调整（改 scoring.yaml） | 必须 | 权重变了，验证结果必变 |
| 单一 fetcher 数据源失效但未触发全局回退 | 建议 | 数据质量变化可能让历史 OOS 数字失真 |
| 距上次校准 ≥ 90 日 | 建议 | 季度复盘节奏 |

## 自校准链最小池（v1.21.1）

`scripts/strategy_performance.py record` 强制 **MIN_POOL_SIZE = 30**：股票池小于
30 只直接拒绝记录（CLI 报错），不再产生小池记录。

> 背景：历史 442 条自校准记录中 441 条在 ≤3 只小池上运行，6 策略指标完全相同
> （胜率 26.6% / 收益 -9.79%），小池回测无区分度，自校准链从未真正工作。

## CLAIM 与证据分离

**规则**：README / CHANGELOG / SKILL.md 顶部 banner 等"对外宣传位置"只能写以下三类内容：

1. **机制类声明**："支持 6 策略 × 9 因子 × 35 fetcher"——可观察可验证
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

## 运行入口

### 第一次跑：建立 OOS 基线

```bash
# 1. 跑 50+ 只股票外样本回测（首次需联网拉 K 线；缓存后离线可用）
python3 scripts/multi_stock_backtest.py --update-validation

# 2. 查看哪些策略升级到 oos_verified
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from strategies import get_validation
for s in ['balanced', 'quality_value', 'growth_momentum', 'defensive', 'turning_point', 'ma_volume_momentum']:
    v = get_validation(s)
    print(f'  {s}: {v[\"validation_status\"]} ({v[\"validation_note\"][:50]})')"
```

### 季度复盘：重新跑升级

```bash
python3 scripts/multi_stock_backtest.py --update-validation  # 覆盖 JSON
git diff data/strategy_oos_validation.json                    # 复盘胜率漂移
```

### 单策略查验证状态

```python
from strategies import get_validation
print(get_validation("balanced"))
# {'validation_status': 'oos_verified', 'validation_note': '...',
#  'win_rate_pct': 58.5, 'n_stocks': 50, 'validated_at': '2026-08-20T10:59:40', ...}
```

### 回滚：清除 OOS 覆盖

```bash
rm data/strategy_oos_validation.json   # 所有策略回到 in_sample 默认
```

## 关联文档

- `scripts/strategies/registry.py:STRATEGY_VALIDATION` — 默认值（in_sample）
- `scripts/strategies/oos_validation.py` — 状态机 + JSON 读写
- `scripts/multi_stock_backtest.py` — 外样本回测入口
- `experts/ARCHITECTURE.md` — 专家投票的 5 长 + 3 短结构（与策略验证正交）
- `CONTRIBUTING.md §4.1` — CHANGELOG 粒度规则（CLAIM 修订走 CHANGELOG）

## 历史

- 2026-08-26：双池联合判定 + 自校准最小池，依据 `docs/archive/reviews/backtest-philosophy-review-2026-08-26.md`
- 2026-08-20：本文初稿
- 之前：`docs/archive/designs/methodology.md`（数据字段映射，已归档）