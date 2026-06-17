# 基础设施层深度优化设计

**日期**: 2026-06-16
**范围**: `scripts/common/`、`scripts/fetchers/`、`scripts/config/loader.py`
**状态**: 待审批

---

## 1. 背景与动机

技术审查发现基础设施层存在 5 P0 + 7 P1 + 6 P2 = 18 个问题。核心风险：

- **连接池竞态**（http.py）：多线程同时创建连接导致泄漏
- **异常信息黑洞**（DataFetcherManager.fetch()）：调用方无法区分失败原因
- **barrel 全量加载**（common/**init**.py）：import 任一函数触发所有子模块执行
- **API 命名冲突**（cache.set）：覆盖 Python 内建 set 类型
- **线程安全缺失**（fetchers/**init**.py）：全局管理器无锁保护

---

## 2. 分阶段计划

### 阶段 A — P0 修复（5 项）

#### A1. http.py 连接池竞态修复

**文件**: `scripts/common/http.py`

将 `_get_connection` 中的连接创建移入 `_pool_lock` 临界区内。创建 `HTTP(S)Connection` 是毫秒级操作，持锁影响可忽略。

同时为连接池增加：

- 最大空闲连接数限制（`MAX_POOL_SIZE = 32`）
- `_return_connection` 中检查池大小，超限则 close 而非归还

**改动**:

- `_get_connection()`: 锁内创建连接
- `_return_connection()`: 增加池大小检查
- 新增 `MAX_POOL_SIZE` 常量

#### A2. DataFetcherManager.fetch() 异常信息暴露

**文件**: `scripts/common/__init__.py`

为 `DataFetcherManager` 增加 `last_error` 属性：

```python
class DataFetcherManager:
    def __init__(self, ...):
        ...
        self._last_error: Exception | None = None

    @property
    def last_error(self) -> Exception | None:
        return self._last_error

    def fetch(self, code, **kwargs):
        ...
        for fetcher in self.fetchers:
            ...
            except Exception as e:
                fetcher.on_failure()
                self._last_error = e  # 暴露而非吞掉
                continue
        return None
```

**兼容性**: 新增属性，不影响现有调用方。

#### A3. cache.set 重命名为 cache.put

**文件**: `scripts/common/cache.py`, `scripts/common/__init__.py`

- `cache.py`: `def set(...)` → `def put(...)`
- 保留 `set` 作为 deprecated 别名：`def set(...): warnings.warn(...); return put(...)`
- `cache.py`: `cache_set` 别名调用 `put` 而非 `set`
- `__init__.py`: `http_get_cached` 中 `cache.set(...)` → `cache.put(...)`
- `__init__.py`: re-export 中增加 `put`，保留 `set` 别名

**兼容性**: `cache.set()` 仍可用但会触发 DeprecationWarning。`cache_set()` 别名不变。

#### A4. RateLimitError.retry_after 传递

**文件**: `scripts/common/http.py`, `scripts/common/exceptions/__init__.py`

在 `_do_request` 中解析 `Retry-After` 响应头：

```python
if status == 429:
    retry_after_header = resp.getheader("Retry-After")
    try:
        resp.read()
    except Exception:
        pass
    raise RateLimitError(url, retry_after=int(retry_after_header) if retry_after_header else None)
```

**兼容性**: `RateLimitError.__init__` 签名不变，只是现在 `retry_after` 有值了。

#### A5. common/**init**.py barrel 模块懒加载

**文件**: `scripts/common/__init__.py`

采用 PEP 562 `__getattr__` 模式。顶层只保留：

- 异常类导入（零副作用）
- 向后兼容别名
- `__all__` 列表
- `__getattr__` 函数

其他符号通过 `_LAZY_IMPORTS` 映射按需加载。

`cache.cleanup_tmp_files()` 从模块顶层移除，改为在以下 CLI 入口脚本的 `main()` 开头显式调用：`stock.py`, `screener.py`, `technical.py`, `monitor.py`, `backtest.py`, `chan.py`, `kline.py`, `finance.py`, `quote.py`, `classifier.py`, `patterns_local.py`, `refresh_pool.py`（共 12 个导入 `common` 的入口脚本）。

**改动量**: `__init__.py` 从 ~375 行缩减到 ~150 行。

**兼容性**: 所有 `from common import X` 调用行为不变，只是加载时机从 import 时变为首次访问时。

---

### 阶段 B — P1 修复（7 项）

#### B6. fetchers/**init**.py 全局管理器加锁

**文件**: `scripts/fetchers/__init__.py`

引入通用工厂函数消除 7 个重复的 `get_*_manager()`：

```python
_manager_lock = threading.Lock()
_managers: dict[str, DataFetcherManager] = {}

def _get_or_create(domain: str, factory, source_section: str = None):
    mgr = _managers.get(domain)
    if mgr is not None:
        return mgr
    with _manager_lock:
        if domain not in _managers:
            cfg = _load_source_config(source_section) if source_section else {}
            _managers[domain] = DataFetcherManager(factory(), source_config=cfg)
        return _managers[domain]
```

7 个公开函数保留为一行包装：

```python
def get_quote_manager():
    return _get_or_create("quote", get_quote_fetchers, "quote_sources")
```

**兼容性**: 公开 API 不变。

#### B7. 消除 sys.path.insert hack

**文件**: `scripts/fetchers/__init__.py`

删除第 21 行 `sys.path.insert(0, ...)`. `pyproject.toml` 的 `pythonpath = ["scripts"]` 已覆盖此需求。

**验证**: 运行 `python3 -m pytest tests/ -x -q` 确认无导入错误。

#### B8. formatters.py 拆分

**文件**:

- `scripts/common/formatters.py` — 保留核心格式化
- `scripts/common/glossary.py` — 新建，移入术语库
- `scripts/common/exporters.py` — 新建，移入导出 + 风险提示

拆分后 `formatters.py` 从 467 行缩减到 ~200 行。

同时修复 `auto_detect_terms` 中 `import re` 移到模块顶层。

**兼容性**: `from common.formatters import X` 对于核心函数不变。术语库和导出函数移入新模块后，在 `formatters.py` 中保留 re-export 别名（`from common.glossary import format_glossary` 等），确保 `from common.formatters import format_glossary` 仍可用。同时在 `__init__.py` 的 `_LAZY_IMPORTS` 中为新模块的符号添加映射。

#### B9. cache.cleanup_by_size 修复双 stat()

**文件**: `scripts/common/cache.py`

一次性收集文件 stat 信息：

```python
file_stats = [(f, f.stat()) for f in files]
total_size = sum(s.st_size for _, s in file_stats)
...
file_stats.sort(key=lambda x: x[1].st_mtime, reverse=keep_newest)
```

#### B10. ConfigLoader.\_cache 加 mtime 检查

**文件**: `scripts/config/loader.py`

缓存条目存储 `(mtime, config)` 元组。`load()` 时比较文件 mtime：

```python
_cache: dict[str, tuple[float, dict]] = {}

@classmethod
def load(cls, filename, use_cache=True):
    config_path = cls._config_dir / filename
    if not config_path.exists():
        return {}
    current_mtime = config_path.stat().st_mtime
    if use_cache and filename in cls._cache:
        cached_mtime, cached_data = cls._cache[filename]
        if current_mtime <= cached_mtime:
            return cached_data
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    cls._cache[filename] = (current_mtime, config)
    return config
```

#### B11. **all** 与 re-export 一致性

**文件**: `scripts/common/__init__.py`

A5 将顶层 import 改为 `__getattr__` 懒加载后，需要在 `_LAZY_IMPORTS` 映射中补充缺失的符号：`compute_volume_ratio`, `compute_optimal_workers`, `board_limit_pct`。确保所有 `utils.__all__` 中的符号都在 `_LAZY_IMPORTS` 中有映射。

#### B12. get\_\*\_manager() 消除重复

已在 B6 中通过 `_get_or_create` 工厂解决。7 个全局变量 + 7 个函数 → 1 个 `_managers` 字典 + 1 个工厂函数 + 7 个一行包装。

---

### 阶段 C — P2 修复（6 项）

#### C13. MetricsCollector.\_latencies 无界增长

**文件**: `scripts/common/metrics.py`

```python
from collections import defaultdict, deque
self._latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1000))
```

#### C14. parallel_map 类型标注

**文件**: `scripts/common/utils.py`

```python
from typing import Callable, Any
def parallel_map(fn: Callable[[str], Any], items: list[str], ...) -> dict[str, Any]:
```

#### C15. cache_key_for_stock MD5 → SHA256

**文件**: `scripts/common/cache.py`

```python
param_hash = hashlib.sha256(param_str.encode()).hexdigest()[:12] if param_str else ""
```

#### C16. NOT_HANDLED 可序列化

**文件**: `scripts/common/__init__.py`

```python
class _NotHandled:
    """可序列化的 NOT_HANDLED 哨兵。"""
    def __repr__(self): return "NOT_HANDLED"
    def __reduce__(self):
        # 返回字符串：pickle 将其解释为模块级全局变量名
        # unpickling 时自动查找 common.NOT_HANDLED 恢复单例
        return "NOT_HANDLED"
    def __eq__(self, other): return isinstance(other, _NotHandled)
    def __hash__(self): return hash("_NOT_HANDLED_")

NOT_HANDLED = _NotHandled()
```

#### C17. BaseFetcher.provider 显式属性

**文件**: `scripts/common/__init__.py`

```python
class BaseFetcher(ABC):
    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.provider = name.split("_")[0]
        ...
```

`_apply_source_config` 中 `fetcher.provider` 替代 `fetcher.name.split("_")[0]`。

#### C18. formatters auto_detect_terms import re

已在 B8 中解决（`import re` 移到模块顶层）。

---

## 3. 受影响文件清单

| 文件                                    | 阶段                  | 改动类型 |
| --------------------------------------- | --------------------- | -------- |
| `scripts/common/__init__.py`            | A2, A5, B11, C16, C17 | 重构     |
| `scripts/common/http.py`                | A1, A4                | 修复     |
| `scripts/common/cache.py`               | A3, B9, C15           | 修复     |
| `scripts/common/formatters.py`          | B8                    | 拆分     |
| `scripts/common/glossary.py`            | B8                    | 新建     |
| `scripts/common/exporters.py`           | B8                    | 新建     |
| `scripts/common/metrics.py`             | C13                   | 修复     |
| `scripts/common/utils.py`               | C14                   | 修复     |
| `scripts/common/exceptions/__init__.py` | A4                    | 微调     |
| `scripts/fetchers/__init__.py`          | B6, B7                | 重构     |
| `scripts/config/loader.py`              | B10                   | 修复     |

---

## 4. 测试策略

1. **现有测试**: `python3 -m pytest tests/ -x -q` 全量通过作为基线
2. **回归验证**: 每阶段完成后运行全量测试
3. **新增测试**:
   - 连接池并发安全测试（多线程同时 `_get_connection`）
   - `DataFetcherManager.last_error` 传播测试
   - `cache.put` / `cache.set` 别名测试
   - `ConfigLoader` mtime 失效测试
   - `NOT_HANDLED` pickle 序列化测试
4. **冒烟测试**: `npm test` 确认端到端不回归

---

## 5. 不做的事情（明确排除）

- 不重构 `CircuitBreaker`（已线程安全，无已知问题）
- 不修改 `BaseFetcher` 的 `fetch()` 签名（影响所有 28 个 fetcher）
- 不引入第三方 HTTP 库（保持 stdlib only）
- 不改变 `ConfigLoader` 的公共 API
- 不删除向后兼容别名（`DataSourceUnavailableError`、`DataParseError`）

---

## 6. 风险评估

| 风险                        | 概率 | 影响 | 缓解措施                                       |
| --------------------------- | ---- | ---- | ---------------------------------------------- |
| 懒加载导致循环导入          | 低   | 高   | 保持异常类在顶层导入，其他符号走 `__getattr__` |
| 连接池改造引入新 bug        | 低   | 中   | 并发测试 + 现有测试覆盖                        |
| formatters 拆分破坏导入路径 | 中   | 低   | `__getattr__` 保持旧路径可用                   |
| cache.rename 改名破坏调用方 | 低   | 低   | 保留 deprecated 别名                           |

---

## 7. 成功标准

- [ ] `python3 -m pytest tests/ -x -q` 全量通过
- [ ] `npm test` 冒烟测试通过
- [ ] 连接池无竞态（并发测试 100 线程无泄漏）
- [ ] `DataFetcherManager.last_error` 可被调用方访问
- [ ] `from common import set` 不再覆盖内建 `set`
- [ ] `from common import to_float` 不触发 cache 模块加载
- [ ] `ConfigLoader` 对修改后的配置文件自动刷新
