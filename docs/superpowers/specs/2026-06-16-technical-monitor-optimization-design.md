# 技术分析+监控层深度优化设计

**日期**: 2026-06-16
**范围**: `scripts/technical/`、`scripts/monitor/`、`scripts/technical.py`
**状态**: 待审批

---

## 1. 背景与动机

技术审查发现 3 P0 + 5 P1 + 6 P2 = 14 个问题。核心风险：

- **God Function**: `technical.py:_compute_all`（145 行）和 `scoring.py:composite_score`（240 行）
- **并发安全缺失**: `monitor/manager.py` 的共享可变状态无锁保护
- **硬编码止损**: `alert_engine.py` 中 -8%/+20% 无法配置

---

## 2. 分阶段计划

### 阶段 A — P0（3 项）

#### A1. \_compute_all God Function 拆分

**文件**: `scripts/technical.py`

将估值分位计算提取到 `technical/valuation.py`，将指标编排复用 `technical/pipeline.py`。`_compute_all` 从 145 行缩减到 ~50 行的编排代码。

#### A2. 监控模块并发保护

**文件**: `scripts/monitor/manager.py`

为 `_throttle_log`、`_daily_count`、`_daily_date` 的读写加 `threading.Lock`。

#### A3. 止损线外部化

**文件**: `scripts/monitor/alert_engine.py`

`-8%` 和 `+20%` 改为从 `limits.yaml` 的 `stop_loss_pct` / `take_profit_pct` 读取，无配置时回退默认值。

---

### 阶段 B — P1（5 项）

#### B4. composite_score 拆分为独立评分函数

**文件**: `scripts/technical/scoring.py`

240 行的 `composite_score` 中 10 个评分维度拆分为独立函数：`_score_ma`、`_score_macd`、`_score_kdj`、`_score_boll`、`_score_rsi`、`_score_volume`、`_score_patterns`、`_score_chan`、`_score_local`、`_score_chip`。`composite_score` 变为 ~50 行的编排函数。

#### B5. 告警类型映射统一

**文件**: `scripts/monitor/alert_engine.py`

将 `check_and_push` 中的 `type_map` 合并到 `ALERT_LEVELS` 字典中，每种 type 增加 `push_type` 字段。

#### B6. sys.path hack 消除

**文件**: `scripts/technical/long_term.py`, `scripts/technical/sentiment.py`

删除 `sys.path.insert`，改用相对导入。

#### B7. BOLL 评分逻辑死角修复

**文件**: `scripts/technical/scoring.py`

L148-160 的 `if pos < 0.3 and "收窄" in bw` 应改为：`pos < 0.3` 时根据是否有"收窄"给不同分值。

#### B8. long_term.py 拼写错误修复

**文件**: `scripts/technical/long_term.py`

L244 `" dividend_yield"` → `"dividend_yield"`

---

### 阶段 C — P2（6 项）

#### C9. **init**.py 私有符号导出清理

**文件**: `scripts/technical/__init__.py`

`__all__` 中的 `_` 前缀函数去掉下划线或从 `__all__` 移除。

#### C10. sentiment.py API token 外部化

**文件**: `scripts/technical/sentiment.py`

`ut` token 从硬编码改为 `ConfigLoader` 或环境变量。

#### C11. scan_all 批量优化

**文件**: `scripts/monitor/alert_engine.py`

行情数据用 `fetch_batch` 批量获取，K 线用 `ThreadPoolExecutor` 并发。

#### C12. scoring.py YAML 回退简化

**文件**: `scripts/technical/scoring.py`

删除 `_USE_CONFIG` 分支，统一使用 `get_scoring_config` + 硬编码默认值。

#### C13. \_compute_all MA 性能优化

**文件**: `scripts/technical.py`

MA 序列计算从 O(N²) 切片改为增量滑动窗口。

#### C14. check_and_push type_map 合并

**文件**: `scripts/monitor/alert_engine.py`

与 B5 合并处理。

---

## 3. 受影响文件清单

| 文件                              | 阶段             | 改动类型 |
| --------------------------------- | ---------------- | -------- |
| `scripts/technical.py`            | A1, C13          | 重构     |
| `scripts/technical/valuation.py`  | A1               | 新建     |
| `scripts/technical/scoring.py`    | B4, B7, C12      | 重构     |
| `scripts/monitor/manager.py`      | A2               | 修复     |
| `scripts/monitor/alert_engine.py` | A3, B5, C11, C14 | 重构     |
| `scripts/technical/long_term.py`  | B6, B8           | 修复     |
| `scripts/technical/sentiment.py`  | B6, C10          | 修复     |
| `scripts/technical/__init__.py`   | C9               | 修复     |

---

## 4. 测试策略

1. 现有测试全量通过作为基线
2. 新增测试：
   - `NotificationManager` 并发安全测试
   - 止损线配置化测试
   - 各评分维度独立函数测试
   - BOLL pos < 0.3 且无"收窄"的评分测试
3. 回归：`npm test`

---

## 5. 不做的事情

- 不修改指标计算算法本身（MACD/KDJ/BOLL/RSI）
- 不重构 `signals.py` 的信号生成逻辑
- 不改变 `composite_score` 的评分规则和权重
- 不引入新的第三方依赖

---

## 6. 成功标准

- [ ] `python3 -m pytest tests/ -x -q` 全量通过
- [ ] `_compute_all` < 60 行
- [ ] `composite_score` < 60 行
- [ ] `NotificationManager` 共享状态有锁保护
- [ ] 止损线可配置
- [ ] 无 `sys.path.insert` hack
- [ ] `long_term.py` 无拼写错误
