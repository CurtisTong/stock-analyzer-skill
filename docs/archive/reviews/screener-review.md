# /screener 策略实现 · 复盘改进文档

> 审查日期：2026-06-17
> 审查范围：`scripts/strategies/`（7 个因子模块）、`scripts/screener.py`、`scripts/business/screening_service.py`、`scripts/config/scoring.yaml`、`scripts/data/industry_thresholds.json`

---

## 一、权重体系复盘

### 问题 1：balanced 的波动率权重过高

`balanced` 的波动率权重为 0.18，与动量、估值相同。但波动率因子的评分范围是 5–95（`volatility.py:22-35`），远大于动量因子的有效评分范围（~0–85）。这导致 **balanced 隐式偏向低波股**，与"均衡"标签矛盾。

**改进方向**：对六因子评分做 cross-sectional z-score 标准化后再加权，消除各因子尺度差异。或压缩波动率分档间距。

### 问题 2：turning_point 与 balanced 区分度不足

```
balanced:      质量 0.23 估值 0.18 动量 0.18 波动 0.18 流动性 0.14 股息 0.09
turning_point: 质量 0.18 估值 0.18 动量 0.30 波动 0.16 流动性 0.14 股息 0.04
```

差异仅在于质量和股息向动量转移了 0.11。按当前评分机制，**turning_point 在实盘中大概率输出与 balanced 相似的结果**，无法真正区分"拐点修复"与"均衡精选"。

**改进方向**：turning_point 应改为两阶段评分——先检测"是否处于超跌区间"（硬条件），再对进入超跌区间的标的质量+估值打分。

### 问题 3：缺少市场状态依赖的动态权重

当前权重是固定的，不随市场状态变化。`scoring.yaml` 的 `market_weights` 节定义了牛市/熊市/震荡/冰点/亢奋的调节系数，但**未被 screener 管线使用**。

**改进方向**：将 `market_regime` 信号接入 `compute_weighted_score()`，通过调节系数做策略内子因子动态加权，而不是切换策略。

---

## 二、因子评分实现问题

### 问题 4：质量因子 ROE 趋势检测过于敏感

**文件**：`scripts/strategies/factors/quality.py:34-41`

用 `all(roe_trend[i] < roe_trend[i-1])` 判断连续下降。一个单期波动就会打破连续性导致趋势误判。同时 `roe_trend` 数据在大部分场景为 `[]`（无填充者），趋势惩罚形同虚设。

**改进方向**：

- `compute_factor_parts()` 内部从多期财务记录自动计算 `roe_trend`
- 改用"下降期占比"替代全序列严格单调（如 60% 以上期下降才触发）

### 问题 5：估值因子 PEG 用单期净利润增速

**文件**：`scripts/strategies/factors/valuation.py:14`

`growth = max(net_profit_yoy, 0)` —— 单期净利润增速极易受非经常性损益、基数效应扭曲。

**改进方向**：改用三年复合增速或中位数增速，覆盖周期性噪音。

### 问题 6：动量因子量化衰减阈值硬编码

**文件**：`scripts/strategies/factors/momentum.py:21-22`

`market_amount > 12000` 判断量化高活跃。12000 亿这个阈值在 A 股全市场成交额的分布中（2023-2026 介于 5000-20000 亿）过于粗糙。衰减系数 0.70 需回测验证。

**改进方向**：

- 改为百分位动态阈值（取过去 20 日成交额的 75% 分位数）
- 或从 `market_regime` 信号中获取量化活跃度状态

### 问题 7：动量因子趋势基础分线性和区分度不足

**文件**：`scripts/strategies/factors/momentum.py:55`

趋势方向 base 差异（上升 40 vs 下降 12）达 28 分，占比过高。MACD 金叉仅 ±10 分、量价信号 ±8 分，边际影响力被趋势 base 压制。

**改进方向**：收敛趋势 base（40→30, 20→18, 12→15），为量价确认信号腾出更多区分空间。

### 问题 8：波动率因子 K 线窗口过短

**文件**：`scripts/strategies/factors/volatility.py:49-51`

只取最近 20 根 K 线计算波动率，仅相当于 1 个月日线，噪声大。`compute_factor_parts` 传入的 `features["closes"]` 实际有 240 根，但 `volatility_from_closes()` 只取 `closes[-20:]`，前 220 根全部浪费。

**改进方向**：至少使用 60 根（一个季度）计算核心波动率。

### 问题 9：股息因子分红连续性数据不可靠

**文件**：`scripts/strategies/factors/dividend.py:86-94`

`_count_dividend_years()` 尝试从 `dividend_records` 列表判断。但当前财务数据 fetcher 不输出此字段。大部分场景回退到 `dps>0 → 2年` 或 `dps<=0 → 0年`，导致连续 10 年分红的工商银行得到 2 年（仅 18 分 vs 合理 24 分），从不分红的科技股也得到 0 或 2 年。

**改进方向**：

- 在财务 fetcher 中补充历史分红记录字段
- 对有分红历史的行业（银行/能源/公用事业）默认调高分红评分可靠性标签

### 问题 10：ESG 治理维度数据获取缺失

**文件**：`scripts/strategies/factors/quality.py:63-111`

`_esg_score()` 需要大股东减持、违规处罚等四个字段。审计意见有 fallback（`AUDIT_OPINION`），但**大股东减持和违规处罚数据在标准财务 fetcher 中未实现**。当前 ESG 评分几乎永远返回 0，12 分的振幅空间形同虚设。

**改进方向**：

- 在 fetcher 层新增违规处罚接口
- 新增股东增减持接口
- 在缺少 ESG 数据时给出清晰的 "ESG: N/A" 标记而非静默返回 0

---

## 三、数据流与性能问题

### 问题 11：全市场模式数据获取可并行优化

**文件**：`scripts/screener.py:306-325`

行情获取（`_fetch_batch_dicts`）在前，财务数据获取（`prefetch_finance_all`）在后，总耗时 ≈ max(行情, 财务) 而非并行。

**改进方向**：行情与财务获取并行发起，用 `concurrent.futures` 做结果合并。

### 问题 12：技术指标在筛选环节重复计算

**文件**：`scripts/screener.py:337`, `scripts/business/screening_service.py:75-144`

`compute_features()` 对每只候选股独立调用 `get_kline()`。全市场 5000 只股票意味着 5000 次 K 线 HTTP 请求。

**改进方向**：

- 实现批量 K 线缓存（按日期+scale+code 缓存到本地文件）
- 或仅在 Top N 候选股才计算技术指标，筛选阶段先用行情+财务数据排序

### 问题 13：行业分类依赖股票名称

分类器 `classifier.infer_industry()` 根据股票名称匹配行业。"中国平安"不含"金融/保险" → 回退 "默认" → 使用通用阈值。行业阈值匹配不到直接影响质量因子 ROE 基准、估值 PE 范围、波动率阈值。

**改进方向**：使用东方财富 API 返回的行业字段，或在 `_fetch_batch_dicts()` 中携带行业信息。

---

## 四、缺失的关键功能

### 问题 14：缺少因子分标准化

核心数学问题：六因子的均值、方差差异巨大：

| 因子       | 常见得分范围 | 标准差 |
| :--------- | :----------: | :----: |
| quality    |    30-85     |  ~12   |
| valuation  |    15-75     |  ~18   |
| momentum   |    20-70     |  ~15   |
| liquidity  |    20-60     |  ~10   |
| volatility |     5-95     |  ~22   |
| dividend   |     0-60     |  ~18   |

不加标准化意味着 volatility 因子（范围最宽）对总分的**实际影响力远大于权重显示的数值**。

**改进方向**：在 `compute_factor_parts()` 之上增加一层 z-score 标准化，或至少对每只股票的六因子做 min-max 归一化到 [0,100]。

### 问题 15：板块集中度约束与行业标签不匹配

**文件**：`scripts/screener.py:348-384`

`apply_portfolio_constraints()` 的 `max_per_sector` 计算在候选池较小时过度严格（`int(len * 0.30)` → 5 只池子只剩 1 只/行业）。行业标签使用 `infer_industry()` 的输出，与 `industry_thresholds.json` 的行业名称不一致。

### 问题 16：缺少选股快照机制

每次运行结果因数据源状态不同，无快照导致复盘时无法复现同一时刻的评分排序。

**改进方向**：输出结果同时保存 JSON 快照，含评分、数据源时间戳、API 版本。

### 问题 17：没有回测闭环

策略权重的设定没有回测数据支撑，均为经验值。

**改进方向**：

- 对五种策略做年化回测，输出夏普比率、最大回撤、胜率
- 根据回测调整权重（如 growth_momentum 动量 0.512 是否最优？用网格搜索验证）
- 定期（每月）校准策略表现，记入 `strategy_performance.json`

---

## 五、优先改进清单

| 优先级 | 问题                                 | 影响范围              | 预估工作量 |           收益            |
| :----: | :----------------------------------- | :-------------------- | :--------: | :-----------------------: |
|   P0   | 因子标准化（问题 14）                | 5 个策略全部          |     2d     | 分数可解释性 + 排序稳定性 |
|   P0   | ESG/分红数据填充（问题 10+9）        | quality/dividend 因子 |     3d     |    因子有效性提升 20%+    |
|   P1   | 动态权重接入 market_regime（问题 3） | 5 个策略              |     2d     |      策略市场适应性       |
|   P1   | 波动率窗口扩至 60 根（问题 8）       | defensive/balanced    |    0.5d    |     波动率评分稳定性      |
|   P1   | ROE 趋势自动填充（问题 4）           | quality 因子          |     1d     |      质量评分准确性       |
|   P2   | turning_point 区分度改进（问题 2）   | turning_point 策略    |    1.5d    |        策略差异化         |
|   P2   | 动量衰减阈值动态化（问题 6）         | growth_momentum       |     1d     |      动量信号可靠性       |
|   P2   | 行情+财务并行拉取（问题 11）         | 全市场模式            |     1d     |      性能提升 30-50%      |
|   P3   | 行业分类改进（问题 13）              | 全部                  |     2d     |        评分准确性         |
|   P3   | K 线分批获取（问题 12）              | 全市场模式            |     2d     |       性能大幅提升        |
|   P3   | 选股快照输出（问题 16）              | 复盘                  |    0.5d    |         可复现性          |
|   P3   | PEG 用复合增速（问题 5）             | valuation 因子        |    0.5d    |        估值准确性         |

---

## 六、架构建议（中期）

### 评分管线重构

当前 **单管线无状态架构**：

```
行情 → 财务 → K线 → 计算因子 → 加权 → 排序 → 输出
```

建议改为 **两阶段分层**：

```
Phase 1（轻量快速筛选）：
  行情 → 财务 → 质量+估值+流动性评分 → 排序取 Top N×3

Phase 2（精准评分）：
  Top N×3 → K线 → 动量+波动率+股息评分 → 加权 → 约束 → 输出
```

Phase 1 在 3-5 秒内完成，Phase 2 只在候选子集上运行。全市场模式耗时从 ~120 秒降到 ~20 秒。

### 权重数据化

从 `STRATEGIES` dict 硬编码 → 从 YAML/JSON 加载权重 + 支持 overlay：

```yaml
strategies:
  growth_momentum:
    weights:
      momentum: 0.512
      liquidity: 0.153
    overrides:
      quant_high: { momentum: 0.40 } # 量化高活跃时降动量
      bear_market: { momentum: 0.25 } # 熊市再加码降
```

---

## 涉及文件清单

| 文件                                       | 行数 | 关键问题编号 |
| :----------------------------------------- | :--: | :----------: |
| `scripts/strategies/registry.py`           |  97  |   1, 2, 3    |
| `scripts/strategies/factors/quality.py`    | 112  |    4, 10     |
| `scripts/strategies/factors/valuation.py`  |  77  |      5       |
| `scripts/strategies/factors/momentum.py`   |  93  |     6, 7     |
| `scripts/strategies/factors/volatility.py` |  71  |      8       |
| `scripts/strategies/factors/dividend.py`   | 148  |      9       |
| `scripts/strategies/factors/common.py`     |  40  |      14      |
| `scripts/screener.py`                      | 483  |  11, 12, 15  |
| `scripts/business/screening_service.py`    | 461  | 4, 8, 12, 14 |
| `scripts/config/scoring.yaml`              | 180  |      3       |
| `scripts/data/industry_thresholds.json`    | 347  |      13      |
