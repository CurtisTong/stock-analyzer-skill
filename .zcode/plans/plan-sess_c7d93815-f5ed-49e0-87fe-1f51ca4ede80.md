# 三条工作线推进计划

基于三路并行深度审查,以下是完整实现方案。按工作线组织,每项标注影响与风险。

---

## 工作线 1:样本外验证闭环(Calibration Closed-Loop)

**问题**:`record_prediction`/`verify_predictions` API 已存在但从未自动调用;`get_price_fn` 无真实实现;校准因子从不回灌 debate;重验证 bug(`get_price_fn=None` 时仍标 `verified=True` 永久跳过);doc/code ±10 vs ±1 矛盾。

### 1.1 新增 `experts/calibration.py:get_kline_return()`(价格回调)
- 实现 `get_kline_return(stock_code, start_date, end_date) -> float`,基于 `data.get_kline(scale=240, datalen=N)` 取足够日线,按 `bar.day` 匹配起止日,返回 `(end_close/start_close - 1)*100`。匹配不到精确日时取最近交易日。复用 `data/a_share_holidays.json`。
- 签名严格匹配 `verify_predictions` 期望的 `get_price_fn(stock_code, start_date, end_date) -> float`。

### 1.2 修复重验证 bug(`verify_predictions`)
- 当 `get_price_fn is None` 时,**不再**将 `verified=True`。改为跳过该条预测并记录到返回值的 `skipped` 列表。只有拿到 `actual_direction` 才置 `verified=True`。这避免"空验证永久锁死预测"。

### 1.3 新增编排器 `experts/decide.py:run_debate()`
- 新函数 `run_debate(stock_code, expert_results, market_state=None, horizon="medium") -> dict`,内部:调 `compute_calibration_factor()` 取因子 → 调 `aggregate_votes(..., calibration_factor=factor)` → 调 `record_prediction(stock_code, {r["name"]: r["score"]}, result["direction"], result["composite_score"])` → 在返回 dict 上挂 `_pred_id` 与 `_calibration_factor`。
- 兼容 `aggregate_group_votes` 的返回结构(用 `avg_score` 作 composite)。
- 这是"debate 后自动落库 + 因子自动回灌"的单一入口,SKILL.md 改为调用它。

### 1.4 改造 `scripts/calibration.py` CLI
- `cmd_verify` 改为默认传入真实 `get_kline_return`;新增 `--no-price` 标志保留旧的"仅标记"行为(用于无网络环境)。
- 新增 `factor` 子命令:打印当前 `compute_calibration_factor()` 与各专家准确率表。

### 1.5 新增 `scripts/calibration_backfill.py`
- 结构仿 `scripts/calibration.py`(`sys.path` 引导 + argparse)。子命令:
  - `status`:打印 pending/verified/expert 准确率表。
  - `verify`:批量运行 `verify_predictions(get_price_fn=get_kline_return)`。
  - `import`:从 JSON 文件导入历史预测记录(`--file`),用于把过去手工记录的 debate 结果灌入。**不做合成回填**(历史财务/市场特征无法还原,合成预测不可信——诚实起见从今天起累积)。
- 不直接写 JSON 文件,一律走 `record_prediction`/`verify_predictions` API,复用迁移+去重逻辑。

### 1.6 修复 doc/code ±10 vs ±1 矛盾(跨工作线,关键)
- `experts/scoring/__init__.py:319`:`cal_adjustment * 0.1` → `cal_adjustment`(使校准贡献为 `calibration_factor * 10` = ±10,符合 decide.md 设计意图与§6.3 文字"贡献不超过 ±10 分")。
- 同步更新 `decide.md §6.3` 公式文字使其与代码一致。
- **这条同时服务工作线 3**:短线组 20% 准确率经由校准因子对信心的压制力从 ±1 提升到 ±10。

### 1.7 文档与杂项
- `skills/stock/SKILL.md` Step 5:改为调用 `run_debate`,修正过时的 `buffett` 示例为 active 名,补 `--composite`。
- `experts/formatter.py`:debate 输出页脚追加校准因子显示(调 `compute_calibration_factor()`)。
- `scripts/config/scoring.yaml:187-188`:删除/修正"当前未被代码读取"的过时注释。
- `CLAUDE.md` 辅助脚本列表:登记 `calibration_backfill.py`。
- `.claude/settings.json` 权限:加 `Bash(python3 scripts/calibration_backfill.py *)`。

---

## 工作线 2:专家评分矩阵逻辑修复

**问题**:9 处高影响逻辑缺陷(情绪反转、死分支、伪多样性、指标错配、阈值矛盾)。

按影响排序,全部修复并补测试:

### P0(哲学性错误,必修)
1. **buffett.py:57 情绪维度反转** — 当前 `adv>0.5→70`(亢奋反而高分),违背"别人恐惧我贪婪"。改为 `adv<0.3→100(恐慌), adv<0.5→60, adv>0.7→20(亢奋), else 50`。同步 `score_with_reasoning` 文案。
2. **risk_manager.py:57-68 情绪维度反转** — 当前恐慌→30、亢奋→30(两端都低),违背 Howard Marks 逆向。改为恐慌→100、亢奋→0、中段→50。
3. **soros.py:13 流动性阈值** — `_SOROS_LIQUIDITY_FLOOR_DEFAULT` 5000 → 7000,对齐 `soros.md:84` 与 `decide.md`。

### P1(死代码/不可达,必修)
4. **_utils.py:253-256 与 262-265 死分支** — `<0.2` 在 `<0.3`/`<0.5` 之后永不触发。重排为 `<0.2` 先于 `<0.3`、`<0.2` 先于 `<0.5`。影响 sector_specialist + risk_manager。
5. **sector_specialist.py:114 情绪封顶 60** — `*0.6` 使 100 不可达。改为 `min(100, _score_sentiment)`(去掉 0.6 缩放,或改为权重明确化)。

### P1(伪多样性,必修)
6. **institution.py:75-76 两个硬编码常量** — 技术面/情绪恒 50。技术面:用 `kline.trend` 映射(上升→60/下降→0,对齐 institution.md:135);情绪:用机构持仓环比字段若有,否则 50(对齐 md:136,缺数据回退中性而非永远中性)。
7. **zhao_laoge.py:22 基本面恒 50** — 读 `market_features.topic_tier` 或 `sector_prosperity`(若有),否则按涨停基因回退;无数据时 50(标注"缺题材数据")。
8. **chaogu_yangjia.py:19 基本面恒 50** — 同理读题材新鲜度字段,缺数据回退中性并标注。

### P2(阈值/指标修正)
9. **lynch.py:62-84 内部人净卖出落入中性** — 增加 `insider is not None and insider <= 0 → 30`(看空),补齐 md 缺失桶。
10. **xu_xiang.py:44 涨停阈值 0.085 → 0.095**(主板)并按板块区分(创业板/科创板 0.195),对齐 xu_xiang.md:132。

### P2(指标错配——标注而非重写)
11. **lynch 风险(负债率 vs 负债/权益)、soros 估值(绝对PE vs 历史分位)、duan 技术面(PE vs 内在价值)、zhao_laoge 风险(回撤 vs 龙头地位)**:这些是"代码用可得数据近似 persona 理想指标"。**不改逻辑**(重写需新增数据源/DCF,超本次范围),但在各 `.py` 顶部 docstring 与对应 `.md` 加 `# 已知近似` 注释,明确记录"代码用 X 近似 persona 的 Y,因为 Z 数据不可得"。诚实标注 > 隐性偏差。

### 测试
- 每项 P0/P1 修复配套单测(构造输入验证新映射,尤其边界值)。`tests/test_scoring_*.py` 已有模式,新增/扩展用例。
- P0 反转修复:新增"恐慌输入应高分"用例,防止回归。

---

## 工作线 3:短线专家市场状态门控

**问题**:短线评分函数完全市场状态盲;冰点判定混淆真冰点(100)与主升初期(80);校准因子对称全局倾斜无法定向惩罚短线组;权重钳制 [0.3,0.7];缺市场数据默认震荡(不安全)。

### 3.1 注入 market_state 到 stock_data(基础设施)
- 在 `run_debate`(工作线1.3)与 SKILL.md 流程中,debate 前把 `detect_market_state()` 结果写入 `stock_data["market_state"]`,使评分函数可读。
- 不强制改 `score()` 签名(保持向后兼容),通过 dict 传递。

### 3.2 防御市短线组分数乘子(vote_engine 聚合层)
- 在 `aggregate_votes` 计算 `short_avg` 前,若 `market_state["state"]` ∈ {防御型, 熊市},对短线组分数施加配置驱动乘子(默认 0.7,`scoring.yaml: experts.short_term.defensive_score_factor`)。乘子作用于 `short_avg` 与 `short_votes` 重算(与现有养家 0.7 降权同模式,保持一致)。
- **这是定向惩罚**:只压短线组,不动长线组,绕过 [0.3,0.7] 权重钳制。
- 冰点期不施加该乘子(冰点是机会起爆点,短线可能有效)。

### 3.3 修复冰点判定混淆
- `vote_engine.py:519` `is_yangjia_ice = emotion_score >= 80` → 改为 `emotion_score >= 100`(真冰点=100),或新增养家显式 `phase` 字段。优先用 `>= 100`(最小改动,精确匹配 chaogu_yangjia.py 的冰点桶)。`emotion_score==80`(主升初期)不再被误判为冰点。

### 3.4 分组校准惩罚(定向,跨工作线1.6)
- `compute_calibration_factor` 拆出 `compute_group_calibration(group: str)`:分别算长线组/短线组准确率因子。
- vote_engine 信心计算:短线组信心贡献用短线组校准因子单独缩放(短线组 20% 准确率 → 短线信心贡献 ×0.4 左右),而非全局对称倾斜。
- 配合 1.6 的 ±10 修正,短线组低准确率现在能实质压低信心指数。

### 3.5 缺数据安全默认
- `market_detector.py:71`:无 index/kline 数据时默认 **防御型**(long 0.65/short 0.35)而非震荡。fail-safe:宁可在防御市误判,不可在防御市放任短线。

### 3.6 配置外置
- `scoring.yaml` 新增 `experts.short_term.defensive_score_factor: 0.7`、`experts.short_term.bearish_states: [防御型, 熊市]`、`experts.short_term.ice_states: [冰点]`。
- decide.md §二/§三 文档化新门控规则。

### 3.7 `prefer_horizon` 覆盖市场状态的 footgun
- vote_engine.py:479-481 当 `prefer_horizon=True` 时市场状态权重被完全丢弃。改为:**仍记录市场状态并施加 3.2 的防御市分数乘子**(分数级门控不应被期限覆盖),仅权重blend 用 horizon。这样用户选"短线"模式时,防御市短线分数仍被压。

### 测试
- 新增 `test_vote_engine_gating.py`:防御市短线乘子生效、冰点期豁免、缺数据默认防御型、分组校准惩罚。
- 回归:确保牛市/震荡行为不变。

---

## 实施顺序与验证

1. **工作线 2**(评分矩阵修复)— 最独立,先做,每修一项跑该专家单测。
2. **工作线 3**(短线门控)— 依赖 3.1 的 market_state 注入,与工作线1.3 的 run_debate 协同。
3. **工作线 1**(闭环)— 最后,串联 run_debate + 落库 + 回灌。
4. 1.6(±10 修正)作为跨线节点,在工作线3之前完成。

**验证**:每条线完成后 `pytest -m "not network"` 全量跑;关键路径 `pytest tests/test_calibration.py tests/test_scoring_*.py tests/test_decide.py tests/test_vote_engine.py`;最后 `ruff check scripts/ experts/` + `mypy`。提供测试结果摘要。

## 不做的事(明确边界)
- 不做合成历史回填(数据不可信)。
- 不重写指标错配项(需新数据源/DCF,超范围),仅加"已知近似"注释。
- 不碰 chan/technical/portfolio 模块。
- 不改 expert 人设 .md 的评分矩阵定义(仅同步代码与加注释)。

## 涉及文件清单
- 新增:`scripts/calibration_backfill.py`
- 改:`experts/calibration.py`、`experts/decide.py`、`experts/vote_engine.py`、`experts/market_detector.py`、`experts/scoring/__init__.py`、`experts/scoring/_utils.py`、`experts/scoring/{buffett,soros,risk_manager,institution,zhao_laoge,chaogu_yangjia,sector_specialist,lynch,xu_xiang}.py`、`experts/formatter.py`、`scripts/calibration.py`、`scripts/config/scoring.yaml`、`skills/stock/SKILL.md`、`experts/decide.md`、`CLAUDE.md`、`.claude/settings.json`、相关 `tests/test_*.py`
