# 数据获取层重构设计规格

**日期**: 2026-06-05
**状态**: 已批准
**作者**: Claude Code

## 1. 概述

### 1.1 背景

当前 stock-analyzer-skill 项目的数据获取层存在以下问题：
- 使用原生 urllib 同步请求，效率低
- 简单文件缓存，批量分析时缓存命中率低
- 没有防封禁策略，容易被 API 封禁
- 没有熔断器机制，连续失败时仍继续请求

### 1.2 目标

参考 daily_stock_analysis 项目的架构，重构数据获取层，实现：
- 多数据源支持（efinance、akshare、tushare、baostock、yfinance、longbridge）
- 防封禁策略（随机 UA、随机休眠、指数退避重试）
- 双层缓存（内存缓存 + 文件缓存）
- 熔断器机制
- 动态优先级管理

### 1.3 约束

- 命令行接口完全兼容现有脚本
- 依赖按需安装，核心必须，其他可选
- 使用线程池并发请求

## 2. 架构设计

### 2.1 目录结构

```
scripts/
├── data_provider/           # 新增：数据源管理模块
│   ├── __init__.py
│   ├── base.py             # 抽象基类、异常类、工具函数
│   ├── manager.py          # DataFetcherManager 管理器
│   ├── cache.py            # 双层缓存实现
│   ├── circuit_breaker.py  # 熔断器实现
│   ├── realtime_types.py   # 统一的实时行情数据类型
│   ├── efinance_fetcher.py # efinance 数据源
│   ├── akshare_fetcher.py  # akshare 数据源
│   ├── tushare_fetcher.py  # tushare 数据源
│   ├── baostock_fetcher.py # baostock 数据源
│   ├── yfinance_fetcher.py # yfinance 数据源（美股）
│   └── longbridge_fetcher.py # longbridge 数据源（港股）
├── common.py               # 重构：保留工具函数，移除数据获取逻辑
├── quote.py                # 重构：使用 DataFetcherManager
├── kline.py                # 重构：使用 DataFetcherManager
├── finance.py              # 重构：使用 DataFetcherManager
└── ...                     # 其他脚本
```

### 2.2 核心组件

| 组件 | 职责 |
|------|------|
| `BaseFetcher` | 抽象基类，定义统一接口 |
| `DataFetcherManager` | 策略管理器，实现数据源切换、优先级管理 |
| `CacheManager` | 双层缓存管理（内存 + 文件） |
| `CircuitBreaker` | 熔断器，防止无效请求 |
| 各 Fetcher 实现 | 具体数据源的实现 |

### 2.3 数据流

```
用户调用 → DataFetcherManager
                ↓
            检查缓存 → 命中则返回
                ↓
            获取排序后的数据源列表（动态优先级）
                ↓
            遍历数据源：
                ├── 检查熔断器 → 跳过不可用数据源
                ├── 调用 Fetcher
                │   ├── 成功 → 更新优先级和缓存，返回结果
                │   └── 失败 → 记录失败，尝试下一个数据源
                └── 所有数据源失败 → 返回 None
```

## 3. 详细设计

### 3.1 BaseFetcher 抽象基类

#### 3.1.1 统一数据类型

```python
@dataclass
class UnifiedRealtimeQuote:
    code: str
    name: str
    price: float
    change_pct: float
    change_amount: float
    volume: int
    amount: float
    turnover_rate: float = 0.0
    amplitude: float = 0.0
    high: float = 0.0
    low: float = 0.0
    open_price: float = 0.0
    pre_close: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    total_mv: float = 0.0  # 总市值（元）
    circ_mv: float = 0.0   # 流通市值（元）
    volume_ratio: float = 0.0  # 量比
    source: str = ""  # 数据源名称
```

#### 3.1.2 标准列名

```python
STANDARD_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
```

#### 3.1.3 抽象接口

```python
class BaseFetcher(ABC):
    name: str = "BaseFetcher"
    priority: int = 99  # 优先级，数字越小越优先

    @abstractmethod
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """获取实时行情

        Args:
            stock_code: 股票代码，如 'sh600989', 'sz000807'

        Returns:
            UnifiedRealtimeQuote 对象，获取失败返回 None
        """
        pass

    @abstractmethod
    def get_kline(self, stock_code: str, scale: int, datalen: int) -> list:
        """获取 K 线数据

        Args:
            stock_code: 股票代码，如 'sh600989'
            scale: K线周期，5=5分钟, 15=15分钟, 30=30分钟, 240=日线
            datalen: 获取的K线数量

        Returns:
            K线数据列表，每个元素为字典：
            [
                {
                    'day': '2024-01-01',  # 日期
                    'open': 100.0,        # 开盘价
                    'high': 105.0,        # 最高价
                    'low': 99.0,          # 最低价
                    'close': 103.0,       # 收盘价
                    'volume': 1000000     # 成交量
                },
                ...
            ]
            获取失败返回空列表 []
        """
        pass

    @abstractmethod
    def get_finance(self, stock_code: str) -> list:
        """获取财务数据

        Args:
            stock_code: 股票代码，如 'SH600989'

        Returns:
            财务数据列表，每个元素为字典，包含以下字段：
            [
                {
                    'REPORT_DATE': '2024-03-31',      # 报告期
                    'EPSJB': 0.5,                     # 每股收益
                    'ROEJQ': 5.0,                     # ROE(加权)%
                    'TOTALOPERATEREVETZ': 10.0,       # 营收同比%
                    'PARENTNETPROFITTZ': 15.0,        # 净利同比%
                    'XSMLL': 30.0,                    # 毛利率%
                    'XSJLL': 10.0,                    # 净利率%
                    'ZCFZL': 50.0,                    # 负债率%
                    'BPS': 10.0,                      # 每股净资产
                    'MGJYXJJE': 2.0,                  # 每股经营现金流
                    ...
                },
                ...
            ]
            获取失败返回空列表 []
        """
        pass

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """获取主要指数行情（可选）

        Args:
            region: 市场区域，cn=A股

        Returns:
            指数列表，每个元素为字典：
            [
                {
                    'code': 'sh000001',  # 指数代码
                    'name': '上证指数',  # 指数名称
                    'current': 3000.0,   # 当前点位
                    'change': 30.0,      # 涨跌点数
                    'change_pct': 1.0,   # 涨跌幅(%)
                    ...
                },
                ...
            ]
            获取失败返回 None
        """
        return None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """获取市场统计（可选）

        Returns:
            市场统计字典：
            {
                'up_count': 2000,        # 上涨家数
                'down_count': 1000,      # 下跌家数
                'flat_count': 500,       # 平盘家数
                'limit_up_count': 50,    # 涨停家数
                'limit_down_count': 10,  # 跌停家数
                'total_amount': 10000.0  # 总成交额（亿）
            }
            获取失败返回 None
        """
        return None
```

#### 3.1.4 异常类

```python
class DataFetchError(Exception):
    """数据获取异常基类"""
    pass

class RateLimitError(DataFetchError):
    """API 速率限制异常"""
    pass

class DataSourceUnavailableError(DataFetchError):
    """数据源不可用异常"""
    pass
```

### 3.2 DataFetcherManager 管理器

#### 3.2.1 核心职责

1. **数据源注册与发现**：自动发现并注册可用的数据源
2. **动态优先级管理**：根据响应时间和成功率自动调整优先级
3. **故障转移**：当主数据源失败时，自动切换到备用数据源
4. **缓存集成**：与 CacheManager 集成，减少重复请求
5. **熔断器集成**：与 CircuitBreaker 集成，跳过不可用数据源

#### 3.2.2 动态优先级算法

```
综合得分 = 基础优先级 + (平均延迟 × 0.6) + ((1 - 成功率) × 0.4)
```

- **基础优先级**：配置的静态优先级（efinance=0, akshare=1, ...）
- **平均延迟**：历史请求的平均响应时间（秒）
- **成功率**：历史请求的成功率（0-1）

得分越低，优先级越高。

#### 3.2.3 核心方法

```python
class DataFetcherManager:
    def __init__(self, max_workers: int = 4):
        self._fetchers: Dict[str, BaseFetcher] = {}
        self._stats: Dict[str, DataSourceStats] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._cache = CacheManager()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # 动态优先级权重
        self._latency_weight = 0.6
        self._success_rate_weight = 0.4

    def register(self, fetcher: BaseFetcher):
        """注册数据源"""
        pass

    def _get_sorted_fetchers(self, capability: str) -> List[BaseFetcher]:
        """根据动态优先级获取排序后的数据源列表"""
        pass

    def _record_success(self, name: str, latency: float):
        """记录成功"""
        pass

    def _record_failure(self, name: str):
        """记录失败"""
        pass

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """获取实时行情（带故障转移）"""
        pass

    def get_kline(self, stock_code: str, scale: int, datalen: int) -> list:
        """获取 K 线数据（带故障转移）"""
        pass

    def get_finance(self, stock_code: str) -> list:
        """获取财务数据（带故障转移）"""
        pass
```

### 3.3 CacheManager 双层缓存

#### 3.3.1 设计目标

- **内存缓存**：快速访问，TTL 10 分钟，适合批量分析场景
- **文件缓存**：持久化存储，TTL 6 小时，适合跨会话复用
- **自动降级**：内存缓存未命中时查询文件缓存

#### 3.3.2 缓存键设计

| 数据类型 | 缓存键格式 | TTL |
|----------|------------|-----|
| 实时行情 | `realtime:{code}` | 10分钟 |
| K线数据 | `kline:{code}:{scale}:{datalen}` | 6小时 |
| 财务数据 | `finance:{code}` | 6小时 |
| 指数行情 | `indices:{region}` | 10分钟 |
| 市场统计 | `market_stats` | 10分钟 |

#### 3.3.3 核心方法

```python
class CacheManager:
    def __init__(self,
                 memory_ttl: int = 600,      # 内存缓存 TTL：10 分钟
                 file_ttl: int = 21600,      # 文件缓存 TTL：6 小时
                 cache_dir: str = ".cache"): # 文件缓存目录
        pass

    def get(self, key: str) -> Optional[Any]:
        """获取缓存数据"""
        pass

    def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """设置缓存数据"""
        pass

    def delete(self, key: str):
        """删除缓存"""
        pass

    def clear(self):
        """清空所有缓存"""
        pass
```

### 3.4 CircuitBreaker 熔断器

#### 3.4.1 设计目标

- **基本熔断**：连续 N 次失败后，冷却 M 秒
- **状态管理**：关闭 → 打开 → 半开 → 关闭
- **自动恢复**：冷却期后自动尝试恢复

#### 3.4.2 状态转换图

```
          连续失败 >= 阈值
    ┌─────────────────────────┐
    │                         ▼
┌───┴───┐  冷却期结束   ┌─────┐  成功 >= 阈值   ┌───────┐
│ CLOSED │ ────────────→ │ OPEN │ ──────────────→ │ CLOSED │
└───┬───┘               └──┬──┘                  └───────┘
    │                      │
    │                      │ 冷却期结束
    │                      ▼
    │               ┌──────────┐
    └───────────────│ HALF_OPEN │
      成功 >= 阈值   └────┬─────┘
                         │
                         │ 失败
                         ▼
                    ┌─────┐
                    │ OPEN │
                    └─────┘
```

#### 3.4.3 默认配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| failure_threshold | 5 | 连续失败 5 次后熔断 |
| recovery_timeout | 60 | 熔断后冷却 60 秒 |
| success_threshold | 2 | 半开状态成功 2 次后恢复 |

#### 3.4.4 核心方法

```python
class CircuitBreaker:
    def __init__(self,
                 failure_threshold: int = 5,
                 recovery_timeout: int = 60,
                 success_threshold: int = 2):
        pass

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        pass

    def is_available(self) -> bool:
        """检查是否可用"""
        pass

    def record_success(self):
        """记录成功"""
        pass

    def record_failure(self):
        """记录失败"""
        pass

    def reset(self):
        """重置熔断器"""
        pass
```

### 3.5 __init__.py 导出

```python
# data_provider/__init__.py
from .manager import DataFetcherManager
from .cache import CacheManager
from .circuit_breaker import CircuitBreaker
from .realtime_types import UnifiedRealtimeQuote
from .base import DataFetchError, RateLimitError, DataSourceUnavailableError

# 各 Fetcher 实现（按需导入）
from .efinance_fetcher import EfinanceFetcher
from .akshare_fetcher import AkshareFetcher
# ... 其他 fetcher


def create_default_manager() -> DataFetcherManager:
    """创建默认的数据源管理器"""
    manager = DataFetcherManager()

    # 按优先级注册数据源
    fetchers = [
        EfinanceFetcher,    # priority=0
        AkshareFetcher,     # priority=1
        TushareFetcher,     # priority=2
        BaostockFetcher,    # priority=3
        YfinanceFetcher,    # priority=4
        LongbridgeFetcher,  # priority=5
    ]

    for fetcher_class in fetchers:
        try:
            fetcher = fetcher_class()
            manager.register(fetcher)
        except ImportError:
            pass  # 依赖未安装，跳过
        except Exception as e:
            logger.warning(f"[数据源] 注册失败 {fetcher_class.__name__}: {e}")

    return manager


__all__ = [
    'DataFetcherManager',
    'CacheManager',
    'CircuitBreaker',
    'UnifiedRealtimeQuote',
    'DataFetchError',
    'RateLimitError',
    'DataSourceUnavailableError',
    'create_default_manager',
]
```

### 3.6 各 Fetcher 实现

#### 3.5.1 数据源依赖

| 数据源 | 依赖库 | 安装方式 |
|--------|--------|----------|
| efinance | `efinance` | `pip install efinance` |
| akshare | `akshare` | `pip install akshare` |
| tushare | `tushare` | `pip install tushare` |
| baostock | `baostock` | `pip install baostock` |
| yfinance | `yfinance` | `pip install yfinance` |
| longbridge | `longbridge-openapi` | `pip install longbridge-openapi` |

#### 3.6.2 按需导入机制

```python
def try_import(module_name: str, package_name: str = None):
    """尝试导入模块，失败返回 None"""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        pkg = package_name or module_name
        logger.debug(f"[依赖] {pkg} 未安装，跳过相关数据源")
        return None
```

#### 3.6.3 数据源能力矩阵

| 数据源 | 实时行情 | K线数据 | 财务数据 | 指数行情 | 市场统计 |
|--------|----------|---------|----------|----------|----------|
| efinance | ✅ | ✅ | ✅ | ✅ | ✅ |
| akshare | ✅ | ✅ | ✅ | ✅ | ✅ |
| tushare | ✅ | ✅ | ✅ | ❌ | ❌ |
| baostock | ❌ | ✅ | ✅ | ❌ | ❌ |
| yfinance | ✅ | ✅ | ❌ | ❌ | ❌ |
| longbridge | ✅ | ❌ | ❌ | ❌ | ❌ |

#### 3.6.4 数据源注册

```python
def create_default_manager() -> DataFetcherManager:
    """创建默认的数据源管理器"""
    manager = DataFetcherManager()

    # 按优先级注册数据源
    fetchers = [
        EfinanceFetcher,    # priority=0
        AkshareFetcher,     # priority=1
        TushareFetcher,     # priority=2
        BaostockFetcher,    # priority=3
        YfinanceFetcher,    # priority=4
        LongbridgeFetcher,  # priority=5
    ]

    for fetcher_class in fetchers:
        try:
            fetcher = fetcher_class()
            manager.register(fetcher)
            logger.info(f"[数据源] 注册成功: {fetcher.name}")
        except ImportError as e:
            logger.debug(f"[数据源] 跳过: {e}")
        except Exception as e:
            logger.warning(f"[数据源] 注册失败 {fetcher_class.__name__}: {e}")

    return manager
```

### 3.7 现有脚本重构

#### 3.7.1 重构原则

1. **保持命令行接口完全兼容**
2. **内部实现替换为 DataFetcherManager**
3. **最小化代码改动**

#### 3.7.2 quote.py 重构

```python
#!/usr/bin/env python3
"""
腾讯实时行情查询。
用法:
  quote.py sh600989                       # 单只，表格输出
  quote.py sh600989,sz000807,sh518880     # 批量（≤15/批）
  quote.py @codes.txt                     # 从文件读代码
  quote.py -j sh600989                    # JSON 输出
"""
import sys
import json
from data_provider import create_default_manager
from common import split_codes, normalize_quote_code, err

# 创建数据源管理器（全局单例）
_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = create_default_manager()
    return _manager

def fetch_batch(codes: list) -> list:
    """批量获取实时行情"""
    manager = get_manager()
    results = []

    for code in codes:
        quote = manager.get_realtime_quote(code)
        if quote:
            results.append({
                'code': quote.code,
                'name': quote.name,
                'price': quote.price,
                'change_pct': quote.change_pct,
                'pe': quote.pe_ratio,
                'turnover': quote.turnover_rate,
                'total_cap': quote.total_mv / 1e8,  # 转换为亿
            })

    return results

def main():
    if len(sys.argv) < 2:
        err("用法: quote.py <代码|@文件> [-j]")
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]

    codes = [normalize_quote_code(c) for c in split_codes(args[0])]
    if not codes:
        err("未提供代码")

    all_records = fetch_batch(codes)

    if json_mode:
        print(json.dumps(all_records, ensure_ascii=False, indent=2))
        return

    # 表格输出（保持原有格式）
    if not all_records:
        print("(无数据)")
        return
    print(f"{'代码':<10} {'名称':<10} {'现价':>8} {'涨跌%':>7} {'PE':>7} {'换手%':>6} {'市值亿':>8}")
    print("-" * 60)
    for r in all_records:
        print(f"{r['code']:<10} {r['name']:<10} {r['price']:>8} {r['change_pct']:>7} {r['pe']:>7} {r['turnover']:>6} {r['total_cap']:>8}")

if __name__ == "__main__":
    main()
```

#### 3.7.3 kline.py 重构

```python
#!/usr/bin/env python3
"""
新浪 K线数据。
用法:
  kline.py sh600989                       # 日 K，30 根
  kline.py sh600989 5 48                  # 5 分钟 K，48 根
  kline.py sh600989 240 30 -j             # JSON
"""
import sys
import json
from data_provider import create_default_manager
from common import normalize_quote_code, err

_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = create_default_manager()
    return _manager

def fetch(symbol: str, scale: int, datalen: int) -> list:
    """获取 K 线数据"""
    manager = get_manager()
    return manager.get_kline(symbol, scale, datalen)

def render_table(records: list) -> str:
    """渲染表格（保持原有格式）"""
    if not records:
        return "(无数据)"
    lines = []
    for d in records:
        lines.append(f"{d['day']} | O:{d['open']:>7} H:{d['high']:>7} L:{d['low']:>7} C:{d['close']:>7} V:{d['volume']:>12}")
    return "\n".join(lines)

def main():
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]
    if not args:
        err("用法: kline.py <symbol> [scale=240] [datalen=30] [-j]")
    symbol = normalize_quote_code(args[0])
    scale = int(args[1]) if len(args) > 1 else 240
    datalen = int(args[2]) if len(args) > 2 else 30

    records = fetch(symbol, scale, datalen)
    if json_mode:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(render_table(records))

if __name__ == "__main__":
    main()
```

#### 3.7.4 finance.py 重构

```python
#!/usr/bin/env python3
"""
东方财富财务数据。
用法:
  finance.py SH600989                  # 单只，最近 4 季
  finance.py -c SH600989,SZ000807      # 批量
  finance.py -j SH600989               # JSON 输出
"""
import sys
import json
from data_provider import create_default_manager
from common import normalize_finance_code, err

_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = create_default_manager()
    return _manager

def fetch(code: str) -> list:
    """获取财务数据"""
    manager = get_manager()
    return manager.get_finance(code)

def render_table(records: list) -> str:
    """渲染表格（保持原有格式）"""
    if not records:
        return "(无数据)"
    keys = list(EAST_MONEY_FIELDS.keys())
    lines = []
    header = " | ".join(["报告期"] + [EAST_MONEY_FIELDS[k] for k in keys])
    lines.append(header)
    lines.append("-" * len(header))
    for r in records:
        period = r.get("REPORT_DATE") or r.get("NOTICE_DATE") or r.get("SECURITYCODE") or "?"
        for dk in ["REPORT_DATE", "REPORTDATETIME", "NOTICE_DATE", "DECLARE_DATE"]:
            if dk in r and r[dk]:
                period = str(r[dk])[:10]
                break
        values = [r.get(k, "-") for k in keys]
        lines.append(" | ".join([period] + [str(v)[:8] for v in values]))
    return "\n".join(lines)

def main():
    if len(sys.argv) < 2:
        err("用法: finance.py <代码> [-c codes] [-j]")
    args = sys.argv[1:]
    json_mode = "-j" in args
    args = [a for a in args if a != "-j"]
    if not args:
        err("缺少代码")

    if args[0] == "-c":
        codes = args[1].split(",")
    else:
        codes = [args[0]]

    all_results = {}
    for code in codes:
        normalized = normalize_finance_code(code)
        records = fetch(normalized)
        all_results[normalized] = records

    if json_mode:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))
        return

    for code, records in all_results.items():
        print(f"\n=== {code} ===")
        print(render_table(records))
```

#### 3.7.5 common.py 变更

**保留**：
- `split_codes()` - 代码解析
- `normalize_quote_code()` - 代码标准化
- `normalize_finance_code()` - 财务代码标准化
- `err()` - 错误输出
- `to_float()` - 类型转换工具

**移除**：
- `http_get()` - HTTP 请求（移至各 Fetcher）
- `http_get_cached()` - 带缓存的 HTTP 请求（移至 CacheManager）
- `cache_get()` / `cache_set()` / `cache_key()` - 缓存函数（移至 CacheManager）
- `parse_tencent_line()` - 腾讯数据解析（移至 EfinanceFetcher）

## 4. 测试策略

### 4.1 单元测试

- 测试 BaseFetcher 抽象接口
- 测试 CacheManager 缓存逻辑
- 测试 CircuitBreaker 状态转换
- 测试 DataFetcherManager 优先级排序

### 4.2 集成测试

- 测试各 Fetcher 实现的数据获取
- 测试故障转移机制
- 测试缓存命中率

### 4.3 端到端测试

- 测试命令行接口兼容性
- 测试批量数据获取性能

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 依赖安装失败 | 数据源不可用 | 按需导入，优雅降级 |
| API 封禁 | 数据获取失败 | 防封禁策略 + 熔断器 |
| 数据格式不一致 | 解析错误 | 统一数据类型 + 标准化 |
| 性能下降 | 用户体验差 | 双层缓存 + 并发请求 |

## 6. 实施计划

### 6.1 阶段 1：基础设施（2天）

- 实现 BaseFetcher 抽象基类
- 实现 CacheManager 双层缓存
- 实现 CircuitBreaker 熔断器
- 实现 DataFetcherManager 管理器

### 6.2 阶段 2：数据源实现（3天）

- 实现 EfinanceFetcher
- 实现 AkshareFetcher
- 实现 TushareFetcher
- 实现 BaostockFetcher
- 实现 YfinanceFetcher
- 实现 LongbridgeFetcher

### 6.3 阶段 3：脚本重构（2天）

- 重构 quote.py
- 重构 kline.py
- 重构 finance.py
- 重构 common.py

### 6.4 阶段 4：测试与优化（2天）

- 单元测试
- 集成测试
- 性能优化

## 7. 验收标准

1. **功能完整性**：所有现有功能正常工作
2. **命令行兼容性**：现有命令行用法完全不变
3. **性能提升**：批量数据获取速度提升 50% 以上
4. **稳定性提升**：单数据源故障不影响整体功能
5. **代码质量**：符合项目编码规范，有适当的文档和注释

## 8. 参考资料

- daily_stock_analysis/data_provider/ 模块
- efinance 官方文档：https://github.com/Micro-sheep/efinance
- akshare 官方文档：https://github.com/akfamily/akshare
- tushare 官方文档：https://tushare.pro/
- baostock 官方文档：http://baostock.com/
- yfinance 官方文档：https://github.com/ranaroussi/yfinance
- longbridge 官方文档：https://open.longbridge.com/
