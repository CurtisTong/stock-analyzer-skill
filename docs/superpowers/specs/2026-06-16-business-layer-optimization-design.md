# 业务层深度优化设计

**日期**: 2026-06-16
**范围**: `scripts/business/`、`scripts/strategies/`、`scripts/data/types.py`
**状态**: 待审批

---

## 1. 背景与动机

技术审查发现业务层存在 4 P0 + 7 P1 + 10 P2 = 21 个问题。核心风险：

- **PE 估值逻辑 3 处重复**：stock_analysis.py、momentum.py、valuation.py 各自实现，fallback 不一致
- **涨跌停过滤重复执行**：\_hard_filter 和 \_analyze_stock 都检查，浪费计算+格式不一致
- **filters.py 阈值冲突**：与 screening_service.py / limits.yaml 对创业板/科创板/北交所的阈值不同
- **因子接口不统一**：6 个因子函数签名各异，新增因子需改 6+ 文件

---

## 2. 分阶段计划

### 阶段 A — P0 修复（4 项）

#### A1. PE 估值逻辑统一

**文件**: `scripts/strategies/factors/common.py`（新建）

提取 `pe_percentile(pe, industry)` 函数。三个调用方改为导入此函数：

- `scripts/business/stock_analysis.py:196-215`
- `scripts/strategies/factors/momentum.py:60-80`
- `scripts/strategies/factors/valuation.py:34-61`（已使用 `get_industry_threshold`，只需改为调用 `pe_percentile`）

**兼容性**: 新增函数，不影响现有 API。

#### A2. 涨跌停过滤去重

**文件**: `scripts/business/screening_service.py`

从 `_analyze_stock` 方法（L299-307）删除涨跌停检查。`_hard_filter`（L438-441）已覆盖此逻辑。

#### A3. filters.py 阈值统一

**文件**: `scripts/strategies/filters.py`

改为使用 `ConfigLoader` 读取 `limits.yaml`，消除独立的 `PRE_SCREEN_FILTER` 硬编码。保留 `get_min_amount`/`get_min_cap` 公开函数签名不变。

#### A4. compute_optimal_workers 去重

**文件**: `scripts/business/screening_service.py`

删除 `_compute_optimal_workers` 静态方法，改为 `from common.utils import compute_optimal_workers`。

---

### 阶段 B — P1 修复（7 项）

#### B5. 引入 ScoringContext 统一因子接口

**文件**: `scripts/strategies/factors/common.py`（扩展）

```python
@dataclass
class ScoringContext:
    quote: dict
    fin: dict
    features: dict
    industry: str = "默认"
    code: str = ""
```

6 个因子函数增加 `ctx: ScoringContext` 参数。保留旧签名 wrapper（deprecated）。`screening_service.py` 构造 `ScoringContext` 传入。

#### B6. 技术指标计算去重

**文件**: `scripts/technical/pipeline.py`（新建）

提取 `compute_indicators(kline_bars, indicators=None) -> dict`。`StockAnalysisService._analyze_technical` 和 `ScreeningService.compute_features` 共用。

#### B7. eps 计算去重

**文件**: `scripts/business/screening_service.py`

`_hard_filter` 开头提取一次 `eps`，后续复用。

#### B8. to_dict 改用 dataclasses.asdict

**文件**: `scripts/data/types.py`

`Quote`、`KlineBar`、`FinanceRecord`、`ChipDistribution` 等的 `to_dict` 改用 `dataclasses.asdict(self)`。

#### B9. register_strategy 不修改传入 dict

**文件**: `scripts/strategies/registry.py`

函数开头 `weights = {**weights}` 创建副本。

#### B10. 行业阈值 fallback 统一

**文件**: `scripts/strategies/factors/dividend.py`

将 `industry_yield_thresholds` 迁移到 `industry_thresholds.json`，函数改为 `get_industry_threshold`。

#### B11. 移除未使用的 volatility_score 导出

**文件**: `scripts/strategies/__init__.py`

移除 `volatility_score` 导出。`volatility_from_closes` 保留。

---

### 阶段 C — P2 修复（10 项）

#### C12. K线数据直接传对象

**文件**: `scripts/business/stock_analysis.py`

`_analyze_technical` 接收 `KlineBar` 对象列表，删除 dict 转换。

#### C13. volatility 两个函数合并

**文件**: `scripts/strategies/factors/volatility.py`

提取 `_compute_vol_score(returns, industry)` 公共函数。

#### C14. \_hard_filter 板块阈值简化

**文件**: `scripts/business/screening_service.py`

删除 `_USE_CONFIG` 分支，统一使用 `_limit()`。

#### C15-16. FinanceRecord 补充字段

**文件**: `scripts/data/types.py`

添加：`goodwill_ratio`、`consecutive_dividend_years`、`major_shareholder_reduction`、`violation_penalty`、`audit_opinion`、`dividend_yield`。

#### C17. \_count_dividend_years 去掉 ROE 启发式

**文件**: `scripts/strategies/factors/dividend.py`

无实际分红数据时返回 0。

#### C18. \_detect_quant_activity 改进

**文件**: `scripts/strategies/factors/momentum.py`

移除个股换手率推断逻辑，只保留 `market_amount` 判断。无数据时返回 `"quant_normal"`。

#### C19. \_analyze_chan 异常处理收窄

**文件**: `scripts/business/stock_analysis.py`

`except Exception` → `except (ValueError, KeyError, RuntimeError, TypeError)`。

#### C20. dividend 阈值迁移到 industry_thresholds.json

**文件**: `scripts/data/industry_thresholds.json`、`scripts/strategies/factors/dividend.py`

#### C21. board_limit_pct 跨层依赖修复

**文件**: `scripts/common/utils.py`

`board_limit_pct` 去掉 `from config.loader import ConfigLoader`，只用硬编码默认值。

---

## 3. 受影响文件清单

| 文件                                       | 阶段                | 改动类型 |
| ------------------------------------------ | ------------------- | -------- |
| `scripts/strategies/factors/common.py`     | A1, B5              | 新建     |
| `scripts/business/screening_service.py`    | A2, A4, B5, B7, C14 | 重构     |
| `scripts/strategies/filters.py`            | A3                  | 修复     |
| `scripts/business/stock_analysis.py`       | A1, B6, C12, C19    | 重构     |
| `scripts/strategies/factors/momentum.py`   | A1, C18             | 修复     |
| `scripts/strategies/factors/valuation.py`  | A1                  | 修复     |
| `scripts/strategies/registry.py`           | B9                  | 修复     |
| `scripts/strategies/__init__.py`           | B11                 | 修复     |
| `scripts/strategies/factors/volatility.py` | C13                 | 重构     |
| `scripts/strategies/factors/dividend.py`   | B10, C17, C20       | 重构     |
| `scripts/data/types.py`                    | B8, C15-16          | 修复     |
| `scripts/data/industry_thresholds.json`    | C20                 | 扩展     |
| `scripts/common/utils.py`                  | C21                 | 修复     |
| `scripts/technical/pipeline.py`            | B6                  | 新建     |

---

## 4. 测试策略

1. 现有测试全量通过作为基线
2. 新增测试：
   - `pe_percentile()` 边界测试（pe<0, pe=0, 边界值, 极端值）
   - `ScoringContext` 构造和因子调用测试
   - `compute_indicators()` 管道测试
   - `to_dict()` 深拷贝验证（修改返回值不影响原对象）
   - `_count_dividend_years` 无数据返回 0
3. 回归：`npm test` 端到端

---

## 5. 不做的事情

- 不修改因子评分算法本身（只统一接口和去重）
- 不引入新的第三方依赖
- 不改变 `STRATEGIES` 字典的 5 种策略定义
- 不重构 `classifier.py` 的行业分类逻辑
- 不修改 `technical/scoring.py` 的复合评分函数

---

## 6. 成功标准

- [ ] `python3 -m pytest tests/ -x -q` 全量通过
- [ ] `npm test` 冒烟测试通过
- [ ] PE 估值只在 `strategies/factors/common.py` 中实现
- [ ] 涨跌停检查只在 `_hard_filter` 中出现
- [ ] `filters.py` 的阈值与 `screening_service.py` 一致
- [ ] 6 个因子函数都接受 `ScoringContext`
- [ ] `FinanceRecord.to_dict()` 修改返回值不影响原对象
