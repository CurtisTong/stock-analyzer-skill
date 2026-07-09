# stock-analyzer-skill 改进实施计划

> 基于 daily_stock_analysis 深度分析，制定 Phase 3-6 完整实施方案

## 概览

| Phase | 主题 | 优先级 | 预估工时 | 风险 |
|-------|------|--------|----------|------|
| Phase 3 | 数据源容错增强 | P0 | 3h | 低 |
| Phase 4 | 熔断器与错误分类 | P1 | 4h | 中 |
| Phase 5 | 并发优化 | P1 | 2h | 低 |
| Phase 6 | 策略模式重构 | P2 | 6h | 中 |

**设计约束**:
- 零外部依赖（不引入 pandas/requests/akshare）
- 渐进式改进（每个 Phase 独立可交付）
- 向后兼容（保留原有接口）

---

## Phase 3: 数据源容错增强（P0 - 立即执行）

### 3.1 quote.py 添加新浪备用源

**问题**: quote.py 只用腾讯接口，被封后完全不可用

**方案**: 参照 kline.py 的故障切换模式，添加新浪行情接口

#### 步骤

1. 在 `common.py` 新增新浪行情解析函数
2. 在 `quote.py` 添加 `fetch_batch_sina()` 函数
3. 修改 `fetch_batch()` 添加故障切换逻辑

#### 代码示例

```python
# common.py 新增

def parse_sina_quote_line(line: str) -> dict:
    """解析新浪行情单行: var hq_str_sh600989="名称,今开,昨收,当前价,最高,最低,..."; """
    if '="' not in line:
        return {}
    var_part, data_part = line.split('="', 1)
    code = var_part.split("_")[-1]  # sh600989
    fields = data_part.rstrip('";\n').split(",")
    if len(fields) < 32:
        return {}
    return {
        "code": code,
        "name": fields[0],
        "open": fields[1],
        "prev_close": fields[2],
        "price": fields[3],
        "high": fields[4],
        "low": fields[5],
        "volume": fields[8],      # 成交量(股)
        "amount": fields[9],      # 成交额
        "date": fields[30],
        "time": fields[31],
    }

SINA_QUOTE_URL = "https://hq.sinajs.cn/list={codes}"
```

```python
# quote.py 新增

def fetch_batch_sina(codes: list) -> list:
    """从新浪获取行情（备用源）。"""
    from common import http_get, parse_sina_quote_line, SINA_QUOTE_URL
    url = SINA_QUOTE_URL.format(codes=",".join(codes))
    raw = http_get(url, timeout=8)
    text = raw.decode("gbk", errors="replace")
    results = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        rec = parse_sina_quote_line(line)
        if rec:
            results.append(rec)
    return results

def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """调用腾讯 API，失败时自动切换到新浪。"""
    # ... 原有缓存逻辑 ...

    # 主路径：腾讯
    try:
        url = URL.format(codes=",".join(codes_to_fetch))
        raw = http_get(url, timeout=8)
        text = decode_gbk(raw)
        results = []
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec:
                results.append(rec)
                if use_cache:
                    key = cache_key_for_stock("quote", rec["code"])
                    cache_set(key, json.dumps(rec, ensure_ascii=False).encode())
    except Exception:
        results = []

    # 备用路径：新浪
    if not results:
        try:
            results = fetch_batch_sina(codes_to_fetch)
            for rec in results:
                if use_cache:
                    key = cache_key_for_stock("quote", rec["code"])
                    cache_set(key, json.dumps(rec, ensure_ascii=False).encode())
        except Exception:
            pass

    return cached_results + results
```

#### 验收标准

- [ ] 单独禁用腾讯接口后，quote.py 仍能返回数据
- [ ] 新浪返回的字段映射正确（price/name/code 等）
- [ ] 缓存键一致，两种源的数据不会冲突

#### 风险

| 风险 | 可能性 | 影响 | 缓解 |
|------|--------|------|------|
| 新浪字段与腾讯不完全一致 | 高 | 中 | 统一输出格式，缺失字段填默认值 |
| 新浪也有反爬 | 中 | 高 | Phase 4 熔断器解决 |

#### 预估: 1h

---

### 3.2 announcements.py 添加缓存

**问题**: 每次调用都打 API，浪费资源且易被限流

**方案**: 使用 `cache_key_for_stock` 按股票代码缓存

#### 步骤

1. 修改 `fetch_announcements()` 添加缓存
2. 修改 `fetch_reports()` 添加缓存

#### 代码示例

```python
# announcements.py

from common import http_get, cache_key_for_stock, cache_get, cache_set

def fetch_announcements(code: str, use_cache: bool = True) -> list:
    key = cache_key_for_stock("ann", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=1800)  # 30 分钟
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(ANN_URL.format(code=code))
    try:
        data = json.loads(raw)
        result = data.get("data", {}).get("list", [])
        if use_cache and result:
            cache_set(key, json.dumps(result, ensure_ascii=False).encode())
        return result
    except json.JSONDecodeError:
        return []

def fetch_reports(code: str, use_cache: bool = True) -> list:
    key = cache_key_for_stock("report", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=3600)  # 1 小时
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(REPORT_URL.format(code=code))
    try:
        data = json.loads(raw)
        result = data if isinstance(data, list) else []
        if use_cache and result:
            cache_set(key, json.dumps(result, ensure_ascii=False).encode())
        return result
    except json.JSONDecodeError:
        return []
```

#### 验收标准

- [ ] 首次调用走 API，第二次命中缓存
- [ ] 缓存文件名为 `ann_{code}_{hash}.cache` 格式
- [ ] 可通过删除缓存文件强制刷新

#### 预估: 0.5h

---

### 3.3 finance.py 改用语义化缓存键

**问题**: 当前用 URL hash 做缓存键，无法按股票清除

**方案**: 改用 `cache_key_for_stock("finance", code)`

#### 步骤

1. 修改 `fetch()` 函数，使用语义化缓存键

#### 代码示例

```python
# finance.py

from common import http_get, cache_key_for_stock, cache_get, cache_set, EAST_MONEY_FIELDS, normalize_finance_code, err

def fetch(code: str, use_cache: bool = True) -> list:
    key = cache_key_for_stock("finance", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=21600)  # 6 小时
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    raw = http_get(URL.format(code=code))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not data or "data" not in data or not data["data"]:
        return []
    result = data["data"][:4]

    if use_cache and result:
        cache_set(key, json.dumps(result, ensure_ascii=False).encode())
    return result
```

#### 验收标准

- [ ] 缓存文件名为 `finance_{code}_{hash}.cache`
- [ ] 可通过 `rm .cache/finance_SH600989_*.cache` 清除单只股票缓存

#### 预估: 0.5h

---

## Phase 4: 熔断器与错误分类（P1 - Phase 3 后执行）

### 4.1 实现 CircuitBreaker 类

**问题**: 数据源被封后持续无效请求

**方案**: 三态熔断器（CLOSED → OPEN → HALF_OPEN）

#### 步骤

1. 在 `common.py` 新增 `CircuitBreaker` 类
2. 在各数据源调用处集成

#### 代码示例

```python
# common.py 新增

import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断
    HALF_OPEN = "half_open"  # 试探

class CircuitBreaker:
    """简单熔断器：连续失败 N 次后熔断，超时后半开试探。"""

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: int = 60, half_open_max: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_success = 0

    def can_execute(self) -> bool:
        """判断是否允许请求。"""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_success = 0
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def record_success(self):
        """记录成功。"""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_success += 1
            if self.half_open_success >= self.half_open_max:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """记录失败。"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def reset(self):
        """重置熔断器。"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0

# 全局熔断器实例
_circuit_breakers = {}

def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """获取或创建熔断器实例。"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
    return _circuit_breakers[name]
```

#### 验收标准

- [ ] 连续 5 次失败后，熔断器进入 OPEN 状态
- [ ] OPEN 状态下，`can_execute()` 返回 False
- [ ] 超过 recovery_timeout 后，进入 HALF_OPEN 状态
- [ ] HALF_OPEN 成功后，回到 CLOSED 状态

#### 预估: 1.5h

---

### 4.2 异常分类体系

**问题**: 所有异常都当作一般错误，无法精细处理

**方案**: 定义 3 种业务异常类型

#### 步骤

1. 在 `common.py` 新增异常类
2. 在 `http_get` 中识别并抛出对应异常

#### 代码示例

```python
# common.py 新增

class RateLimitError(Exception):
    """429 Too Many Requests"""
    pass

class DataSourceUnavailableError(Exception):
    """数据源不可用（连接失败、超时等）"""
    pass

class DataParseError(Exception):
    """数据解析失败"""
    pass

def http_get(url: str, timeout: int = 10, max_retries: int = 3) -> bytes:
    """GET 请求，指数退避重试，UA 随机轮换。"""
    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": random.choice(USER_AGENTS),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                raise RateLimitError(f"429 Too Many Requests: {url}")
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
    raise DataSourceUnavailableError(f"GET {url} 失败: {last_err}")
```

#### 验收标准

- [ ] 429 响应抛出 `RateLimitError`
- [ ] 超时/连接失败抛出 `DataSourceUnavailableError`
- [ ] JSON 解析失败抛出 `DataParseError`
- [ ] 现有代码的 try-except 仍能捕获（因为都继承 Exception）

#### 预估: 1h

---

### 4.3 http_get 增强 429 检测

**问题**: 被限流后仍继续重试，浪费时间

**方案**: 检测 429 立即抛出，不重试

#### 步骤

1. 修改 `http_get`，429 直接抛出不重试

#### 代码示例

```python
# 已包含在 4.2 的 http_get 实现中
# 关键点: 429 不进入重试循环，立即抛出 RateLimitError
```

#### 验收标准

- [ ] 收到 429 后立即抛出，不等待重试
- [ ] 调用方可捕获 RateLimitError 进行熔断

#### 预估: 0.5h

---

## Phase 5: 并发优化（P1 - 与 Phase 4 并行）

### 5.1 finance.py 批量并发

**问题**: 批量查询时串行执行，N 只股票需要 N 倍时间

**方案**: 使用 `parallel_map` 并发查询

#### 步骤

1. 修改 `main()` 函数，使用 `parallel_map`

#### 代码示例

```python
# finance.py

from common import parallel_map

def main():
    # ... 参数解析 ...

    if len(codes) > 1:
        # 批量模式：并发查询
        results = parallel_map(fetch, codes, max_workers=4, timeout=30)
        all_results = {k: v for k, v in results.items() if v}
    else:
        # 单只模式
        code = codes[0]
        normalized = normalize_finance_code(code)
        all_results = {normalized: fetch(normalized)}

    # ... 输出 ...
```

#### 验收标准

- [ ] 查询 10 只股票的时间 < 串行时间的 1/3
- [ ] 单只失败不影响其他查询
- [ ] 结果顺序与输入一致

#### 预估: 0.5h

---

### 5.2 quote.py 批量并发

**问题**: 超过 15 只股票时，批次间串行

**方案**: 并发执行各批次

#### 步骤

1. 修改 `main()` 函数，并发执行批次

#### 代码示例

```python
# quote.py

from common import parallel_map

def fetch_single_batch(batch: list) -> list:
    """单批次查询（供 parallel_map 调用）。"""
    return fetch_batch(batch, use_cache=True)

def main():
    # ... 参数解析 ...

    batches = list(batchify(codes, 15))
    if len(batches) > 1:
        # 多批次：并发执行
        results = parallel_map(fetch_single_batch, batches, max_workers=4, timeout=30)
        all_records = []
        for batch in batches:
            all_records.extend(results.get(batch, []))
    else:
        # 单批次
        all_records = fetch_batch(batches[0])

    # ... 输出 ...
```

#### 验收标准

- [ ] 查询 30 只股票的时间 < 串行时间的 1/2
- [ ] 单批次失败不影响其他批次

#### 预估: 0.5h

---

## Phase 6: 策略模式重构（P2 - 长期优化）

### 6.1 BaseFetcher 抽象基类

**问题**: 各数据源的接口不统一，难以维护

**方案**: 定义统一的抽象基类

#### 步骤

1. 在 `common.py` 新增 `BaseFetcher` 抽象基类

#### 代码示例

```python
# common.py 新增

from abc import ABC, abstractmethod

class BaseFetcher(ABC):
    """数据源抽象基类。"""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self.circuit_breaker = get_circuit_breaker(name)

    @abstractmethod
    def fetch(self, code: str, **kwargs) -> dict | list | None:
        """获取数据。返回 None 表示失败。"""
        pass

    def is_available(self) -> bool:
        """检查数据源是否可用（熔断器状态）。"""
        return self.circuit_breaker.can_execute()

    def on_success(self):
        """记录成功。"""
        self.circuit_breaker.record_success()

    def on_failure(self):
        """记录失败。"""
        self.circuit_breaker.record_failure()
```

#### 验收标准

- [ ] 所有数据源类继承 `BaseFetcher`
- [ ] 统一的 `fetch()` 接口
- [ ] 自动集成熔断器

#### 预估: 1h

---

### 6.2 DataFetcherManager 策略管理器

**问题**: 故障切换逻辑分散在各模块

**方案**: 统一的策略管理器

#### 步骤

1. 在 `common.py` 新增 `DataFetcherManager` 类

#### 代码示例

```python
# common.py 新增

class DataFetcherManager:
    """数据源策略管理器：按优先级尝试，自动故障切换。"""

    def __init__(self, fetchers: list[BaseFetcher]):
        self.fetchers = sorted(fetchers, key=lambda f: f.priority, reverse=True)

    def fetch(self, code: str, **kwargs) -> dict | list | None:
        """按优先级尝试各数据源。"""
        last_error = None
        for fetcher in self.fetchers:
            if not fetcher.is_available():
                continue
            try:
                result = fetcher.fetch(code, **kwargs)
                if result is not None:
                    fetcher.on_success()
                    return result
                fetcher.on_failure()
            except RateLimitError:
                fetcher.on_failure()
                raise  # 限流直接抛出
            except Exception as e:
                fetcher.on_failure()
                last_error = e
                continue
        return None

    def fetch_with_fallback(self, code: str, fallback=None, **kwargs):
        """带默认值的获取。"""
        result = self.fetch(code, **kwargs)
        return result if result is not None else fallback
```

#### 验收标准

- [ ] 按优先级尝试数据源
- [ ] 自动跳过熔断的数据源
- [ ] 所有源失败后返回 None 或 fallback

#### 预估: 1.5h

---

### 6.3 现有脚本适配

**问题**: 现有脚本需要适配新的策略模式

**方案**: 逐步迁移，保持向后兼容

#### 步骤

1. 为每个数据源创建 Fetcher 类
2. 保留原有函数作为兼容层
3. 新代码使用 Manager

#### 代码示例

```python
# quote.py

class TencentQuoteFetcher(BaseFetcher):
    """腾讯行情数据源。"""

    def __init__(self):
        super().__init__("tencent_quote", priority=10)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = URL.format(codes=code)
        raw = http_get(url, timeout=8)
        text = decode_gbk(raw)
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            rec = parse_tencent_line(line)
            if rec:
                return rec
        return None

class SinaQuoteFetcher(BaseFetcher):
    """新浪行情数据源。"""

    def __init__(self):
        super().__init__("sina_quote", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        url = SINA_QUOTE_URL.format(codes=code)
        raw = http_get(url, timeout=8)
        text = raw.decode("gbk", errors="replace")
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            rec = parse_sina_quote_line(line)
            if rec:
                return rec
        return None

# 策略管理器
quote_manager = DataFetcherManager([
    TencentQuoteFetcher(),
    SinaQuoteFetcher(),
])

# 兼容层
def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """兼容原有接口。"""
    results = []
    for code in codes:
        result = quote_manager.fetch(code)
        if result:
            results.append(result)
    return results
```

#### 验收标准

- [ ] 原有 `fetch_batch()` 接口不变
- [ ] 新代码可使用 `quote_manager.fetch()`
- [ ] 故障切换自动发生

#### 预估: 3.5h

---

## 任务依赖关系

```
Phase 3.1 (quote 备用源) ──┐
Phase 3.2 (ann 缓存)    ──┼── 可并行
Phase 3.3 (finance 缓存) ──┘
          │
          ▼
Phase 4.1 (熔断器) ──┐
Phase 4.2 (异常分类) ─┼── 4.1 先行，4.2/4.3 可并行
Phase 4.3 (429 检测) ─┘
          │
          ▼
Phase 5.1 (finance 并发) ──┐
Phase 5.2 (quote 并发)   ──┼── 可并行
                           ┘
          │
          ▼
Phase 6.1 (BaseFetcher) ──→ 6.2 (Manager) ──→ 6.3 (适配)
```

---

## 总体验收标准

### 功能验收

- [ ] quote.py 腾讯被封后自动切换新浪
- [ ] announcements.py 30 分钟内不重复请求
- [ ] finance.py 可按股票清除缓存
- [ ] 连续 5 次失败后自动熔断，60 秒后恢复
- [ ] 429 限流立即停止重试
- [ ] 批量查询时间缩短 50%+

### 代码质量

- [ ] 所有新代码有 docstring
- [ ] 无第三方依赖引入
- [ ] 原有接口向后兼容
- [ ] 无循环导入

### 测试方法

```bash
# Phase 3 测试
python scripts/quote.py sh600989           # 正常查询
# 手动断开腾讯域名后重试，验证新浪切换

# Phase 4 测试
python -c "
from common import CircuitBreaker, CircuitState
cb = CircuitBreaker('test', failure_threshold=3, recovery_timeout=5)
for i in range(4):
    cb.record_failure()
print(cb.state)  # 应为 OPEN
"

# Phase 5 测试
time python scripts/finance.py -c SH600989,SZ000807,SH601318  # 计时

# Phase 6 测试
python -c "
from scripts.quote import quote_manager
result = quote_manager.fetch('sh600989')
print(result)
"
```

---

## 风险评估总结

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 新浪接口也有反爬 | 中 | 高 | 熔断器 + UA 轮换 |
| 缓存文件过多 | 低 | 中 | 定期清理 + TTL 过期 |
| 并发导致被限流 | 中 | 高 | 控制并发数 + 熔断器 |
| 重构引入 bug | 中 | 中 | 保留兼容层 + 逐步迁移 |

---

## 时间估算总结

| Phase | 任务数 | 预估工时 | 建议安排 |
|-------|--------|----------|----------|
| Phase 3 | 3 | 2h | 第 1 天 |
| Phase 4 | 3 | 3h | 第 2 天 |
| Phase 5 | 2 | 1h | 第 2 天（与 Phase 4 并行） |
| Phase 6 | 3 | 6h | 第 3-4 天 |
| **总计** | **11** | **12h** | **4 天** |

---

## 2026-07-08 其余模块审查：未处理项（写入 roadmap）

本轮审查处理了 6 个 P0 + 3 个高影响 P1（已提交）。以下 P2/低影响项留待后续：

### 文件 IO 原子性（B2 未覆盖的低风险点）
- `scripts/strategy_performance.py:40` - strategy_performance.json 非原子写
- `scripts/snapshots.py:113` / `scripts/hot_rank.py:250` - 快照文件非原子写
- `scripts/common/metrics.py:77` - metrics.json 非原子写（小文件，可重建）
- `scripts/perf_bench.py:128` - perf_benchmarks.json 非原子写（低频 CLI）
- 建议：上述均可改用已新增的 `common.atomic_write_json`，但风险较低，按需处理。

### 缠论其他模块
- 笔/线段/背驰的深入审查未覆盖（本轮仅修 P0 中枢合并）。
- chan_beichi（背驰检测）的 MACD 区间判定可能有边界问题，待专项审查。

### 策略层低影响项
- 策略模式识别模块（patterns/）的其他形态检测可能有类似的死代码/参数未用问题。
