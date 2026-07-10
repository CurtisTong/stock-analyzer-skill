# 数据源架构改进计划

> 基于 daily_stock_analysis 深度分析，结合 stock-analyzer-skill 现状制定

## 一、现状差距分析

### 1.1 架构对比

| 维度 | stock-analyzer-skill | daily_stock_analysis | 差距 |
| --- | --- |
| **数据源数量** | 3个 (腾讯/新浪/东财) | 7+个 (efinance/akshare/tushare/pytdx等) | 需扩充 |
| **设计模式** | 各脚本独立实现 | 策略模式 (BaseFetcher + Manager) | 需重构 |
| **故障切换** | 仅kline.py有手动切换 | Manager自动遍历所有数据源 | 需系统化 |
| **缓存** | 文件缓存，单层 | 双层缓存 (内存+文件) | 需增强 |
| **熔断器** | 无 | CircuitBreaker三态状态机 | 需新增 |
| **错误分类** | 无 | 5类异常精细处理 | 需新增 |

### 1.2 当前数据源问题清单

| 数据源 | 备用方案 | 缓存 | 风险等级 | 优先级 |
| --- | --- | --- |
| `quote.py` (腾讯行情) | **无** | 15分钟 | **高** - 单点故障 | P0 |
| `kline.py` (新浪K线) | 腾讯备用 | 6小时 | 低 | 已完成 |
| `finance.py` (东财财务) | **无** | 6小时(URL hash) | 中 | P1 |
| `announcements.py` (东财公告) | **无** | **无** | 中 | P1 |
| `refresh_pool.py` (东财板块) | **无** | 1小时 | 低 | P2 |

---

## 二、借鉴的核心设计模式

### 2.1 策略模式 (Strategy Pattern)

**daily_stock_analysis 实现**:
```python
class BaseFetcher(ABC):
    name: str
    priority: int  # 数字越小越优先

    @abstractmethod
    def _fetch_raw_data(self, code, start, end) -> DataFrame

    @abstractmethod
    def _normalize_data(self, df, code) -> DataFrame

class DataFetcherManager:
    def get_daily_data(self, code):
        for fetcher in sorted(self._fetchers, key=lambda f: f.priority):
            try:
                return fetcher.get_daily_data(code)
            except Exception:
                continue
        raise DataFetchError("所有数据源失败")
```

**应用到 stock-analyzer-skill**:
- 保持零外部依赖，不引入 pandas
- 简化为 dict 列表而非 DataFrame
- 保留现有接口 (`fetch_batch`, `fetch`) 向后兼容

### 2.2 熔断器 (Circuit Breaker)

**daily_stock_analysis 实现**:
```
CLOSED (正常) --连续失败N次--> OPEN (熔断)
OPEN --冷却时间到--> HALF_OPEN (半开)
HALF_OPEN --成功--> CLOSED
HALF_OPEN --失败--> OPEN
```

**关键参数**:
- 实时行情: 3次失败触发，冷却5分钟
- 筹码接口: 2次失败触发，冷却10分钟

**应用到 stock-analyzer-skill**:
- 为每个数据源添加独立熔断器
- 实时行情熔断后自动切换备用源
- K线/财务数据熔断后使用缓存兜底

### 2.3 全量缓存 + 按需过滤

**daily_stock_analysis 实现**:
- efinance/akshare 全量拉取5000+股票数据
- 缓存为 DataFrame，按代码过滤
- TTL 10-20分钟

**应用到 stock-analyzer-skill**:
- quote.py 已实现按股票代码缓存
- 可增加内存缓存层减少磁盘I/O

### 2.4 字段补充合并 (Quote Supplement)

**daily_stock_analysis 实现**:
```
主源返回基础字段 → 检查缺失字段 → 尝试补充源 → 合并非None字段
```

**应用到 stock-analyzer-skill**:
- quote.py 可从新浪补充量比字段
- finance.py 可从多个东财接口合并更完整数据

---

## 三、分阶段改进计划

### Phase 3: 数据源容错增强 (1-2天)

#### 3.1 为 quote.py 添加新浪备用源

**目标**: 消除单点故障风险

**实现方案**:
```python
# scripts/quote.py 新增
SINA_URL = "https://hq.sinajs.cn/list={codes}"

def fetch_sina(codes: list) -> list:
    """从新浪获取实时行情（备用）"""
    # 解析格式: var hq_str_sh600519="贵州茅台,1866.000,..."

def fetch_batch(codes: list, use_cache: bool = True) -> list:
    # 主路径: 腾讯
    try:
        results = fetch_tencent(codes)
        if results:
            return results
    except Exception:
        pass

    # 备用路径: 新浪
    return fetch_sina(codes)
```

**验收标准**:
- 腾讯API不可用时，自动切换新浪
- 切换时间 < 3秒
- 两个源返回的数据格式统一

#### 3.2 为 announcements.py 添加缓存

**目标**: 减少不必要的API调用

**实现方案**:
```python
def fetch_announcements(code: str, use_cache: bool = True) -> list:
    key = cache_key_for_stock("ann", code)
    if use_cache:
        cached = cache_get(key, ttl_seconds=3600)  # 1小时
        if cached:
            return json.loads(cached)

    # ... 原有逻辑 ...

    if use_cache and results:
        cache_set(key, json.dumps(results).encode())
    return results
```

**验收标准**:
- 重复调用同一股票公告，第二次命中缓存
- 缓存TTL: 公告1小时，研报2小时

#### 3.3 为 finance.py 改用语义化缓存键

**目标**: 支持按股票精确清除缓存

**实现方案**:
```python
# 修改前
raw = http_get_cached(URL.format(code=code))

# 修改后
key = cache_key_for_stock("finance", code)
raw = http_get_cached_keyed(URL.format(code=code), key, ttl=21600)
```

**验收标准**:
- `cache_clear_by_code("sh600989")` 能清除该股票所有缓存
- 缓存文件名格式: `finance_sh600989.cache`

---

### Phase 4: 熔断器与错误分类 (2-3天)

#### 4.1 实现 CircuitBreaker

**目标**: 防止对已封禁接口的无效请求

**核心实现** (参考 daily_stock_analysis):
```python
class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold=3, cooldown_seconds=300):
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0

    def can_execute(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.cooldown_seconds:
                self.state = self.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN

    def record_success(self):
        self.state = self.CLOSED
        self.failure_count = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
```

**集成位置**:
- `common.py` 添加 CircuitBreaker 类
- 每个数据源维护独立熔断器实例
- `http_get` 中检查熔断状态

#### 4.2 异常分类体系

**目标**: 精细化错误处理

**异常类型**:
```python
class DataFetchError(Exception): pass
class RateLimitError(DataFetchError): pass  # HTTP 429
class DataSourceUnavailableError(DataFetchError): pass  # 5xx
class DataParseError(DataFetchError): pass  # JSON解析失败
```

**http_get 增强**:
```python
def http_get(url, timeout=10, max_retries=3):
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        if resp.status == 429:
            raise RateLimitError(f"限流: {url}")
        return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitError(f"限流: {url}")
        if e.code >= 500:
            raise DataSourceUnavailableError(f"服务不可用: {url}")
        raise
```

---

### Phase 5: 并发优化与批量增强 (1-2天)

#### 5.1 finance.py 批量并发

**目标**: 50只股票财务查询从串行~50秒降到并发~8秒

**实现方案**:
```python
def fetch_batch(codes: list) -> dict:
    """批量获取财务数据（并发）"""
    def _fetch_one(code):
        return code, fetch(normalize_finance_code(code))

    results = parallel_map(_fetch_one, codes, max_workers=8)
    return {code: data for code, data in results.items() if data}
```

#### 5.2 quote.py 批量并发

**目标**: 消除批次间串行等待

**当前问题**: 50只股票分4批串行，每批等待前一批完成

**优化方案**:
```python
def fetch_batch_parallel(codes: list) -> list:
    """并发分批获取行情"""
    batches = list(batchify(codes, 15))
    results = parallel_map(fetch_batch, batches, max_workers=4)
    return [item for batch_results in results.values() if batch_results for item in batch_results]
```

---

### Phase 6: 策略模式重构 (3-5天)

#### 6.1 BaseFetcher 抽象基类

**设计原则**:
- 保持零依赖 (不引入 pandas)
- 返回 dict/list 而非 DataFrame
- 保留现有接口向后兼容

**核心接口**:
```python
class BaseFetcher(ABC):
    name: str
    priority: int

    @abstractmethod
    def fetch_quote(self, codes: list) -> list:
        """获取实时行情"""

    @abstractmethod
    def fetch_kline(self, code: str, scale: int, datalen: int) -> list:
        """获取K线数据"""

    @abstractmethod
    def fetch_finance(self, code: str) -> list:
        """获取财务数据"""

    def is_available(self) -> bool:
        return True
```

#### 6.2 DataFetcherManager

**核心职责**:
- 管理多个 Fetcher 实例
- 按优先级排序
- 自动故障切换
- 熔断器集成

**使用方式**:
```python
manager = DataFetcherManager([
    TencentFetcher(priority=0),
    SinaFetcher(priority=1),
    EastMoneyFetcher(priority=2),
])

# 自动故障切换
quotes = manager.fetch_quote(["sh600989", "sz000807"])
```

#### 6.3 现有脚本适配

**向后兼容策略**:
```python
# scripts/quote.py 保留原有接口
_manager = DataFetcherManager()

def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """保持原有签名，内部委托给 Manager"""
    return _manager.fetch_quote(codes)
```

---

## 四、实施优先级与时间估算

| Phase | 改进项 | 优先级 | 时间 | 风险 |
| --- | --- | --- |
| 3.1 | quote.py 新浪备用源 | **P0** | 0.5天 | 低 |
| 3.2 | announcements.py 缓存 | **P1** | 0.5天 | 低 |
| 3.3 | finance.py 语义化缓存键 | **P1** | 0.5天 | 低 |
| 4.1 | CircuitBreaker | P2 | 1天 | 中 |
| 4.2 | 异常分类体系 | P2 | 1天 | 中 |
| 5.1 | finance.py 并发 | P2 | 0.5天 | 低 |
| 5.2 | quote.py 并发 | P2 | 0.5天 | 低 |
| 6.1 | BaseFetcher 基类 | P3 | 1天 | 中 |
| 6.2 | DataFetcherManager | P3 | 2天 | 中 |
| 6.3 | 现有脚本适配 | P3 | 2天 | 高 |

**总计**: 约 9-10 天

---

## 五、验收标准

### Phase 3 验收
- [ ] quote.py: 腾讯API不可用时，自动切换新浪，延迟 < 3秒
- [ ] announcements.py: 重复调用命中缓存，API调用减少 80%+
- [ ] finance.py: `cache_clear_by_code()` 能精确清除指定股票缓存

### Phase 4 验收
- [ ] CircuitBreaker: 连续3次失败后熔断，冷却5分钟后恢复
- [ ] 异常分类: 429限流自动识别，退避时间加倍
- [ ] 日志输出: 显示熔断状态变化和故障切换链路

### Phase 5 验收
- [ ] finance.py: 50只股票批量查询 < 10秒 (当前~50秒)
- [ ] quote.py: 50只股票批量查询 < 3秒 (当前~8秒)

### Phase 6 验收
- [ ] Manager 自动故障切换: 模拟主源故障，自动切换备用源
- [ ] 向后兼容: 所有现有脚本无需修改即可运行
- [ ] 日志追踪: 显示完整的数据源选择和切换链路

---

## 六、风险缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
| --- | --- |
| 新浪/腾讯接口变更 | 中 | 高 | 保持代码解耦，变更只需修改单个 Fetcher |
| 熔断器误判 | 低 | 中 | 设置合理的阈值和冷却时间，支持手动重置 |
| 缓存一致性 | 低 | 低 | 使用 TTL 过期策略，关键操作跳过缓存 |
| Phase 6 重构影响范围大 | 中 | 高 | 保持向后兼容，分步迁移，充分测试 |

---

## 七、关键文件路径

| 文件 | 用途 | Phase |
| --- |
| `scripts/common.py` | 基础设施 (CircuitBreaker/缓存/HTTP) | 4, 5 |
| `scripts/quote.py` | 实时行情 (添加新浪备用) | 3.1 |
| `scripts/kline.py` | K线数据 (已完成) | - |
| `scripts/finance.py` | 财务数据 (语义化缓存+并发) | 3.3, 5.1 |
| `scripts/announcements.py` | 公告/研报 (添加缓存) | 3.2 |
| `scripts/fetcher_base.py` | 新增: BaseFetcher 抽象基类 | 6.1 |
| `scripts/fetcher_manager.py` | 新增: DataFetcherManager | 6.2 |
| `scripts/fetchers/tencent.py` | 新增: 腾讯数据源 | 6.3 |
| `scripts/fetchers/sina.py` | 新增: 新浪数据源 | 6.3 |
| `scripts/fetchers/eastmoney.py` | 新增: 东财数据源 | 6.3 |

---

## 八、参考资源

- daily_stock_analysis 策略模式: `data_provider/base.py`
- daily_stock_analysis 熔断器: `data_provider/realtime_types.py`
- daily_stock_analysis efinance: `data_provider/efinance_fetcher.py`
- daily_stock_analysis akshare: `data_provider/akshare_fetcher.py`
- stock-analyzer-skill 设计文档: `docs/superpowers/specs/2026-06-05-data-provider-refactor-design.md`
