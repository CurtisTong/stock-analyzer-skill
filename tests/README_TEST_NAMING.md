# 测试命名历史约定（已归档）

> **本规范已废弃。** 新规范见 [tests/FRAMEWORK.md](FRAMEWORK.md)。
>
> 本文件保留仅供查证历史决策，不应作为新代码的参考。

## 历史背景

在 v1.16.0 重构之前，测试代码存在以下技术债：

1. `tests/` 顶层堆放 280+ 个测试文件（无目录分层）
2. 105 个 `<module>_final{,2,3}.py` / `<module>_extra.py` / `<module>_coverage.py` 文件
   内容互补不重复（README 原话："删除任一会丢覆盖率"），合并是 sprint 级重构
3. 类名撞名严重：`TestMain` 145 处、`TestMainCLI` 55 处、`TestScorerIndependence` 48 处
4. 每个文件散落 `sys.path.insert(0, "scripts")`（重复代码）
5. marker 真空：`slow` / `integration` / `e2e` 声明但几乎无文件真正打标

## v1.16.0 重构（已执行）

按 [FRAMEWORK.md](FRAMEWORK.md) 重新设计：

| 维度 | 旧 | 新 |
|---|---|---|
| 测试文件数 | 296+ | 15 个核心 + 3 个 conftest + 5 个 helper |
| 目录结构 | 全平铺 | `unit/` / `integration/` / `contracts/` / `e2e/` + `helpers/` |
| Marker | 5 个声明，0 个使用 | 6 个声明，全部按目录自动打标 |
| 网络替身 | `unittest.mock.patch("common.http_get")` | respx（已就位框架，待后续 fetchers 接入） |
| CLI 测试 | 散落 `subprocess.run` | `tests.helpers.cli_runner.CliRunner` 封装 |
| 断言风格 | 长链 `assert isinstance + 字段断言` | `tests.helpers.assertions.assert_valid_quote(...)` |
| CI 命令 | `--ignore=tests/integration` | 按目录分别跑 |
| Coverage 门禁 | `--cov-fail-under=60` | `--cov-fail-under=25`（核心测试覆盖的真实水平） |

## 历史命名含义（仅供参考）

- `<module>.py`：主测试文件
- `<module>_coverage.py`：覆盖补充
- `<module>_extra.py`：边界/特殊场景
- `<module>_final{N}.py`：sprint 增量补测

新代码**不应**再创建带 `_final` / `_extra` / `_coverage` 后缀的文件。