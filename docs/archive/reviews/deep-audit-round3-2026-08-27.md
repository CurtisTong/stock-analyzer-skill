# screener / backtest / stock / chan / experts 逻辑层审查报告（2026-08-27）

> **审查时间**：2026-08-27
> **审查对象**：`scripts/screener.py` + `scripts/business/screening_*.py`、`scripts/strategies/`、`scripts/backtest/`、`scripts/strategy_performance.py`、`scripts/stock.py` + `scripts/business/stock_analysis.py`、`scripts/chan/`、`experts/vote_engine.py`、`scripts/classifier.py`
> **方法**：2 个并行 Explore agent + 合成数据实测（最小复现确认）
> **流程**：延续 2026-08-27 技术模块/market/sector/portfolio 审查模式

---

## 一、一句话结论

> 🚨 **本轮发现两类最严重问题：① walk-forward 是"假外样本"——窗口边界从未传给回测引擎，OOS 数据全部被 IS 见过，`--walk-forward` 输出的 OOS 指标无任何样本外意义（P0）；② 专家单组模式空输入会产出"强烈看多+满仓"**（all([]) 恒真，实测复现）。前者需引擎设计变更（已标注已知缺口），后者已修复。

## 二、已修复（d161369）

| # | 问题 | 证据 | 修复 |
|---|---|---|---|
| P1-1 | **aggregate_group_votes 空输入 → "强烈看多+满仓"**：`all(s >= 70 for s in [])` 恒真 → position_factor=1.2 | `experts/vote_engine.py:791`（实测复现） | 空输入守卫返回中性（已修） |
| P1-2 | **K 线 10-59 根技术面静默降级产出误导评分**：`_analyze_technical` 失败返回 `_technical_error` 但评分/渲染层无人消费 → 实测输出"36.4 中性(偏空)"看似真实 | `stock_analysis.py:195-213`（实测） | 评分走中性 + data_warnings 标注 |
| P1-4 | **缠论"一买(弱)"分支死代码**：`beichi is None` 分支生产链路不可达（`chan/__init__.py` 恒传 dict），无背驰下跌笔结束场景被静默 | `chan/maidian.py:69-73` | 记录（弱信号降级语义待产品确认） |
| P2-1 | **SKILL 短线单组模式误写"均分驱动"**（上轮改错：单组模式代码是 ≥2/3 投票计数，均分只用于双组冲突解决） | `SKILL.md:248,290,398` vs `vote_engine.py:785-823` | SKILL 改回组内投票 + 注明双组均分 |
| P2-2 | **"巴菲特否决权"残留表述**（代码已改否决警示：不改方向仅降信心） | `SKILL.md:358` | 措辞修正 |
| P2-4 | **盘整背驰不进评分/信号**（只识别 `startswith("检测到底背驰")`） | `scoring.py:352-353` + `signals.py:150-153` | 两处口径扩展（盘整背驰计入看涨） |
| P2-7 | **classifier 死赋值**：`confidence="高"` 被无条件覆盖为"低" | `classifier.py:65,102` | 记录（低风险） |

## 三、已知缺口（需设计变更，未修）

| # | 问题 | 证据 | 建议 |
|---|---|---|---|
| P0-1 | **walk-forward 是假外样本**：`walk_forward.py:160-212` 计算了窗口边界但 `SimContext` 无窗口偏移参数（实测 `train_start used: False`），IS/OOS 两次调用仅 total_days 不同，OOS 时间落在 IS 窗口内部 | `backtest/walk_forward.py` + `backtest/engine.py:91-109` | 引擎加窗口偏移参数（train/test 分段喂数据），补 walk_forward 测试 |
| P0-2 | **regime 修复死代码**：`_fetch_index_bars_for_backtest` / `_classify_regime_from_index`（engine.py:612-673）全库无调用方，主路径仍用个股 bars 判 regime | `backtest/engine.py:268` | 主路径接线到 index bars |
| P1-1 | **财务缺失时因子静默低分**：`quality_score({})`=12（负债率 0 被当最优），`check_finance_freshness({})` 不判定时效 | `factors/quality.py:64` | 缺失因子按"中性 50"语义统一 |
| P1-2 | **回测与筛选评分不一致**（回测的不是同一策略）：0.85 系数、自研 momentum、event 跳过、turnover=0 | `engine.py:242,494-534,52-62` | 评分同源化（回测复用 screener 因子） |
| P1-3 | **optimize_weights 静默丢 5 因子**：只取 4 键归一化，volatility/chip/dividend/event 34% 权重被置零 | `backtest/cli.py:100-125` | 全因子归一化 |
| P1-4 | **regime 策略混合恒不触发**：`blend_rule` keys 是策略 ID，`original_weights.get("label")` 是中文标签 | `regime/overlay.py:237-243` | 键名统一 |
| P1-5 | **watchdog 部分结果路径死代码**：`_on_timeout` 直接 `os._exit(2)`，从不抛 `ScreenerTimeoutError` | `common/screener_watchdog.py:69-85` | 抛异常或修文档 |

## 四、验证无问题项（防误报）

- 6 策略权重和 = 1.0（实测）；除零防护全覆盖（to_float/clamp/industry_thresholds 无退化阈值）
- 归一化全零/全等值不崩（MAD=0 兜底 1.0、quantile 全等值 → 50）
- `aggregate_votes` 单组 5/5 看多 → 强烈看多（dict 输入格式下正确，P1-2 部分推翻）
- 缠论最小阈值链路自洽（30 根 valid=False、34/240 根可跑、坐标映射有上界检查）
- 估值负值/缺失防护（pe≤0→50、PEG 有前置）
- stock.py 降级路径（data_warnings + footer 标注）正确

## 五、立场结论

**screener/backtest 的"回测与筛选评分不同源"和"walk-forward 假外推"是投资结论可信度的根基问题**——建议下轮优先 P0-1/P0-2（引擎窗口偏移 + regime 接线），其次 P1-2（评分同源）。本轮已修复专家系统空输入满仓、技术面降级误导、盘整背驰口径三类用户可见问题。