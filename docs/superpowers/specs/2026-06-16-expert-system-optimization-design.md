# 专家系统深度优化设计

**日期**: 2026-06-16
**范围**: `experts/` 目录
**状态**: 待审批

---

## 1. 背景与动机

技术审查发现 3 P0 + 5 P1 + 6 P2 = 14 个问题。核心风险：

- **YAML 死代码**: `experts/yaml/` 下 8 个 YAML 文件无人读取
- **calibration 遗漏**: 只追踪 8 位 legacy 专家，6 位 active 专家无校准
- **循环依赖**: `__init__` ↔ `registry` 互相导入
- **decide.py God Object**: 892 行，6 个职责混杂

---

## 2. 分阶段计划

### 阶段 A — P0（3 项）

#### A1. YAML 死代码清理

**文件**: `experts/yaml/` 目录

删除 8 个 YAML 文件。这些文件从未被任何 Python 代码读取，是"未来可配置化"的占位符但从未实现。保留会造成维护误导（改 YAML 无效）。

#### A2. calibration.py 专家名列表修复

**文件**: `experts/calibration.py`

将 `_EXPERT_NAMES` 从硬编码 8 个改为从 `registry` 动态获取全部 14 个：

```python
def _get_all_expert_names() -> list:
    from experts.registry import EXPERT_REGISTRY
    return list(EXPERT_REGISTRY.keys())
```

#### A3. 循环依赖消除

**文件**: `experts/types.py`（新建）, `experts/__init__.py`, `experts/registry.py`

将 `ExpertProfile` dataclass 和 `DIRECTION_THRESHOLDS`、`direction_from_score` 移到 `experts/types.py`。`__init__.py` 和 `registry.py` 都从 `types.py` 导入，消除 `__init__ ↔ registry` 循环。

---

### 阶段 B — P1（5 项）

#### B4. decide.py 拆分

**文件**: `experts/decide.py` → `experts/market_detector.py`, `experts/vote_engine.py`, `experts/formatter.py`

| 新模块               | 职责                                                                        | 原 decide.py 行 |
| -------------------- | --------------------------------------------------------------------------- | --------------- |
| `market_detector.py` | `detect_market_state`                                                       | ~85 行          |
| `vote_engine.py`     | `_count_votes`, `_resolve_conflict`, `aggregate_votes`, `_compute_position` | ~285 行         |
| `formatter.py`       | `format_debate_output`, `format_debate_card`, `format_group_output`         | ~210 行         |
| `decide.py`          | 编排层，导入并协调以上模块                                                  | ~100 行         |

#### B5. score/score_with_reasoning 去重

**文件**: `experts/scoring/*.py`（14 个专家评分文件）

让 `score_with_reasoning()` 内部调用 `score()` 获取数值，再附加推理文本。消除阈值逻辑的双重实现。

#### B6. 三源数据一致性校验

**文件**: `experts/registry.py` 的 `_ensure_loaded()`

增加权重校验：检查 `registry.py` 中定义的权重与 `scoring/*.py` 中实际使用的阈值是否一致。不一致时发出警告。

#### B7. \_resolve_conflict 去硬编码

**文件**: `experts/vote_engine.py`（拆分后）

将巴菲特否决权和养家情绪退潮的特殊处理逻辑参数化，通过 `ExpertProfile` 的 `veto_priority` 属性控制。

#### B8. 新专家 .md 完善

**文件**: `experts/value_anchor.md`, `experts/topic_leader.md`, `experts/emotion_tech.md`, `experts/sector_specialist.md`, `experts/institution.md`, `experts/risk_manager.md`

为 6 个新专家补充完整的哲学、案例、引用来源。

---

### 阶段 C — P2（6 项）

#### C9. scoring/**init**.py 别名清理

移除 8 个 `_score_xxx` 向后兼容别名。测试改用 `score_expert_precise()`。

#### C10. 信心指数公式一致性

确认 `decide.md` 和代码中的权重一致（当前文档 0.35/0.55/0.1 vs 代码 0.45/0.45/0.1）。

#### C11. apply_veto 改进

当 `veto_results is None` 时，尝试自动判断条件而非返回全部条件列表。

#### C12. sector_specialist 导入修复

`from . import _score_fundamentals` 改为从 `_utils.py` 导入。

#### C13. 格式化函数分离业务逻辑

`format_debate_output` 中的校准卡片拼接移到 `aggregate_votes` 返回值中。

#### C14. 合并型专家模式文档化

`weighted_merge` 模式记录为最佳实践。

---

## 3. 受影响文件清单

| 文件                         | 阶段        | 改动类型 |
| ---------------------------- | ----------- | -------- |
| `experts/yaml/` (8 个文件)   | A1          | 删除     |
| `experts/calibration.py`     | A2          | 修复     |
| `experts/types.py`           | A3          | 新建     |
| `experts/__init__.py`        | A3          | 重构     |
| `experts/registry.py`        | A3, B6      | 重构     |
| `experts/decide.py`          | B4          | 拆分     |
| `experts/market_detector.py` | B4          | 新建     |
| `experts/vote_engine.py`     | B4, B7      | 新建     |
| `experts/formatter.py`       | B4, C13     | 新建     |
| `experts/scoring/*.py`       | B5, C9, C12 | 修复     |
| `experts/*.md` (6 个新专家)  | B8          | 扩展     |

---

## 4. 测试策略

1. 现有测试全量通过作为基线
2. 新增测试：
   - calibration 14 个专家名完整性
   - types.py 循环导入验证
   - decide.py 拆分后 API 兼容性
   - score/score_with_reasoning 一致性
3. 回归：`npm test`

---

## 5. 不做的事情

- 不修改专家评分算法本身
- 不改变 `ExpertProfile` 的字段定义
- 不删除 legacy 专家（保留 A/B 对比）
- 不重构 `scoring/` 的通用评分函数

---

## 6. 成功标准

- [ ] `python3 -m pytest tests/ -x -q` 全量通过
- [ ] `experts/yaml/` 目录为空或已删除
- [ ] calibration 追踪全部 14 位专家
- [ ] 无循环导入
- [ ] decide.py < 150 行
- [ ] score/score_with_reasoning 阈值逻辑单一来源
