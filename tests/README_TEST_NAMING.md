# 测试文件命名约定（已知技术债）

## 背景

历史 sprint 在提升覆盖率时，未将新测试合并回 `<module>.py` 主文件，而是
追加为 `<module>_final.py` / `<module>_final2.py` / `<module>_final3.py` /
`<module>_coverage.py` / `<module>_extra.py`。这种模式**内容互补而不重复**，
合并需要按类逐一迁移并跑回归测试，是 sprint 级重构。

## 当前分布（截至 v1.15.0）

| 模块 | 文件数 | 文件清单 |
| --- | --- | --- |
| announcements | 4 | `test_announcements.py` + `_final{,2,3}.py` |
| data_pool | 6 | `test_data_pool.py` + `_coverage.py` + `_extra.py` + `_final{2,3,4}.py` |
| quality | 4 | `test_quality_factor.py` + `_coverage.py` + `test_quality_final{,2}.py` |
| finance | 5 | `test_finance_field_mapping.py` + `_normalize.py` + `_quote.py` + `_final{,2}.py` |
| dibu_shouban | 3 | `test_dibu_shouban_coverage.py` + `_final{,2}.py` |
| dispatch | 3 | `test_dispatch_coverage.py` + `_final{,2}.py` |
| market_breadth | 3 | `test_market_breadth.py` + `_coverage.py` + `_final2.py` |

共 **42 个** `*_final*.py` 文件。

## 文件命名含义

- `<module>.py`：主测试文件（含基础类与场景）
- `<module>_coverage.py`：覆盖补充（针对未命中分支）
- `<module>_extra.py`：边界/特殊场景
- `<module>_final{N}.py`：后续 sprint 增量补测（`More` / `Main` 等类名表示补充）
- 测试**互补而非重复**——移除任一文件都会丢覆盖率

## 重构路径（不在 P3 范围内）

1. 选取一个模块（如 `dispatch`）作为试点
2. 合并 `_coverage.py` + `_final{,2}.py` → 单个 `test_dispatch.py`
3. 跑回归（`pytest tests/test_dispatch* -x -q -m "not network"`）
4. 通过后推广到其他模块

## 不推荐的做法

- ❌ 直接删除 `_final2.py` 等文件——会丢覆盖率
- ❌ 批量重命名——引入大量回归风险
- ❌ 在 `_final.py` 加新测试——继续恶化蔓延
