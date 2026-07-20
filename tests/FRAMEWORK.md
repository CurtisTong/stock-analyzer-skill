# 测试框架规范（新规范）

本规范定义 stock-analyzer-skill 测试代码的全部约定，自 v1.16.0 起生效。
**所有新增测试必须遵守本规范**；历史测试正在按本规范迁移。

## 目录结构

```
tests/
├── FRAMEWORK.md                   # 本文档（规范）
├── README_TEST_NAMING.md          # 历史规范归档（不再适用，保留仅供查证）
├── conftest.py                    # 顶层 fixtures（跨所有层共享）
├── helpers/                       # 测试辅助代码（不参与 pytest 收集）
│   ├── __init__.py
│   ├── assertions.py              # 领域断言（assert_valid_quote / assert_kline_shape）
│   ├── http_fixtures.py           # respx 路由 + 真实字节样本
│   ├── cli_runner.py              # CLI 进程封装
│   ├── market_data.py             # K 线/行情合成（替代 conftest 内 _generate_*）
│   └── domain_types.py            # 测试侧 dataclass
├── unit/                          # 纯函数无 IO 测试
│   ├── conftest.py                # 自动给本目录测试打 `unit` marker
│   └── test_<module>.py
├── integration/                   # 跨模块/跨进程测试
│   ├── conftest.py
│   ├── test_<module>.py
│   └── test_install.sh            # install.sh 集成测试
├── e2e/                           # 端到端（CLI 进程边界）
│   ├── conftest.py
│   └── test_<flow>.py
└── contracts/                     # schema/yaml 合约（独立 CI job）
    ├── conftest.py
    └── test_<aspect>.py
```

### 为什么这样分层

| 层 | 触发 marker | 依赖 | 用途 | 示例 |
|---|---|---|---|---|
| `unit/` | `unit` | 无（仅被测模块） | 纯函数、算法、数据结构 | `validators`、`board_type`、`sort_stocks` |
| `integration/` | `integration` | 多模块协作、可 mock IO | 跨模块流程 | `ScreeningService` 跨 fetchers+strategies |
| `e2e/` | `e2e` | 真实子进程 | CLI 端到端 | `python3 scripts/stock.py sh600519` |
| `contracts/` | `contracts` | 文件系统（schema/yaml） | 数据契约 | `skills/_shared/contracts/*.schema.json` |

## 命名规范

### 文件

- `test_<被测模块>.py` -- 每个被测模块**唯一**对应一个测试文件
- **禁止** `_final / _extra / _coverage` 等覆盖补充后缀（互补测试应合并进主文件）
- **禁止** 文件名含版本号（`v2` / `final2` / `final3` 等）

### 测试类

格式：`Test<被测对象><场景>`（语义唯一，无撞名）

- ✅ `TestScreeningServiceHardFilter`、`TestChanFenxingDetection`
- ❌ `TestMain`、`TestMainCLI`、`TestMore`、`TestExtra`（撞名通用名禁用）
- ❌ 同一文件内多个 `TestMain`（按场景拆分）

### 测试方法

格式：`test_<行为>_<期望>`（短动词+结果）

- ✅ `test_invalid_code_raises`、`test_st_returns_false`
- ❌ `test_xxx_yyy_with_some_complex_scenario_that_is_too_long`

### 模块与函数

- 测试模块/函数禁止散落 `sys.path.insert`：统一依赖 `pyproject.toml::pythonpath`
- 测试模块顶部可以导入 `tests.helpers.*` 作为辅助

## pytest 配置（pyproject.toml）

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
addopts = "-ra --strict-markers --strict-config"
markers = [
    "unit: 纯函数/单类单元测试",
    "integration: 跨模块集成测试",
    "e2e: 端到端 CLI 测试",
    "contracts: schema/yaml 合约测试",
    "slow: 慢速测试",
    "network: 需要真实网络访问（默认 skip）",
]
```

- `--strict-markers`：未声明 marker 即报错，避免真空 marker
- `--strict-config`：pyproject.toml 配置冲突即报错

## fixtures（tests/conftest.py）

### 保留的旧 fixtures（按域重命名，原名作为别名）

K 线域：
- `kline_uptrend` / `kline_downtrend` / `kline_sideways`
- `kline_with_top_fenxing` / `kline_with_bottom_fenxing`
- `kline_macd_golden_cross` / `kline_macd_death_cross`
- `kline_limit_up`

行情域：
- `sample_quote` / `sample_finance` / `sample_finance_akshare` / `sample_finance_efinance`

Mock 域：
- `mock_http_get` / `mock_fetch_kline` / `mock_fetch_batch`

autouse：
- `_reload_config_loader`：每个测试前重置 ConfigLoader 缓存
- `_reset_expert_registry`：每个测试前重置专家注册表（修复顺序污染）

### 新增 fixtures

- `mock_external_network(respx_mock)`：对所有 fetchers 调用的统一 respx 路由
- `cli_runner`：CLI 子进程封装（替代散落的 `subprocess.run`）
- `freeze_time`：注入 `scripts.dev.clock` 的固定时间

## 网络替身（respx）

所有 fetchers 测试**必须**使用 respx 拦截网络请求，禁止依赖真实网络：

```python
def test_tencent_quote_returns_normalized(respx_mock):
    respx_mock.get("qt.gtimg.cn").respond(
        200, content=b'v_sh600519="1~贵州茅台~600519~1800.00~..."'
    )
    quote = quote.fetch("sh600519")
    assert_valid_quote(quote)
```

respx 真实字节样本维护在 `tests/helpers/http_fixtures.py`。

## CLI 测试

CLI 测试在 `tests/e2e/` 下，使用 `cli_runner` fixture 封装：

```python
def test_stock_cli_runs(cli_runner):
    result = cli_runner.run("stock.py", "sh600519")
    assert result.exit_code == 0
    assert "贵州茅台" in result.stdout
```

`cli_runner` 内部用 `subprocess.run`，捕获 stdout/stderr/exit_code/execution_time。

## 断言

简单断言用 `assert` 即可；领域对象（Quote/KLine/FinanceRecord）必须用 `helpers/assertions.py` 提供的断言函数：

```python
from helpers.assertions import assert_valid_quote, assert_kline_shape

def test_quote_normalized(sample_quote):
    assert_valid_quote(sample_quote, code="600519", price_positive=True)
```

禁止散落的 `assert isinstance(q, dict) and q["price"] > 0` 长链断言。

## 覆盖率门禁

CI 命令保持不变：

```
pytest tests/ -q -m "not network" --timeout=60 -n auto --cov=scripts --cov=experts --cov-fail-under=60
```

`fail_under=60` 是底线。当前 MUST PRESERVE 21 个核心文件覆盖约 25-35%，**门禁需调整到符合实际的水平**（Step 5 处理）。

## CI 编排

- `test` job：跑 `pytest tests/ -q -m "not network" --timeout=60 -n auto`
- `integration` job：跑 `tests/integration/test_install.sh` + `tests/integration/test_*.py`
- `e2e` job：跑 `pytest tests/e2e/ -q`
- `contracts` job：跑 `pytest tests/contracts/ -q`
- `smoke` job：跑 `tests/smoke_test.sh`（live network）
- `checks` job：black / ruff / mypy / 版本一致性

## 不允许的做法

- ❌ 在 `_final.py` / `_extra.py` / `_coverage.py` 等追加文件加新测试
- ❌ 散落的 `sys.path.insert(0, "scripts")`
- ❌ 测试中 `subprocess.run` 而不通过 `cli_runner`
- ❌ `unittest.mock.patch` 直接打 `common.http_get`，应走 `mock_external_network` + respx
- ❌ 通用类名 `TestMain` / `TestMainCLI` / `TestMore`
- ❌ 测试覆盖率低于产品代码覆盖率当借口不修测试

## 重构路径（已删除文件的处理）

删除的旧测试文件已 git 历史可查；不再放回测试目录。如果发现被删除文件中有价值测试，按本规范重新实现，存放在新结构对应位置。