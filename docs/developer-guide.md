# 开发者指南

理解项目结构并能扩展开发。

## 项目结构详解

```
stock-analyzer-skill/
├── README.md                       # 项目说明
├── CONTRIBUTING.md                 # 贡献规范
├── CLAUDE.md                       # Claude Code 上下文
├── workflow.md                     # 8 个 skill 的协作流程
├── methodology.md                  # 完整投资方法论
├── install.sh                      # 一键注册到 ~/.claude/skills/
├── package.json                    # npm 发布配置
├── pyproject.toml                  # Python 项目配置
├── experts/                        # 8 位专家深度档案
│   ├── buffett.md / lynch.md / soros.md / duan_yongping.md
│   ├── xu_xiang.md / zhao_laoge.md / chaogu_yangjia.md / zuoshou_xinyi.md
│   └── decide.md                   # 决策整合规则
├── .claude/skills/                 # Claude Code skill 源（11 个 skill）
│   ├── stock/SKILL.md
│   ├── market/SKILL.md
│   ├── sector/SKILL.md
│   ├── portfolio/SKILL.md
│   ├── screener/SKILL.md
│   ├── technical/SKILL.md
│   ├── stock-init/SKILL.md
│   ├── monitor/SKILL.md
│   ├── backtest/SKILL.md
│   ├── financial-analyst/SKILL.md
│   ├── investment-researcher/SKILL.md
│   └── help/SKILL.md
├── .agents/skills/                 # Codex workspace skill 源
├── skills/                         # Claude Code skill 源（与 .claude/skills/ 一致）
├── scripts/                        # 工具脚本（三层架构）
│   ├── business/                   # 业务逻辑层
│   │   ├── stock_analysis.py
│   │   └── screening_service.py
│   ├── common/                     # 基础设施层
│   │   ├── __init__.py            # BaseFetcher, CircuitBreaker, DataFetcherManager
│   │   ├── http.py                # HTTP 请求封装
│   │   ├── cache.py               # 磁盘缓存（v1.3.2 从 data/cache.py 迁入）
│   │   ├── validators.py          # 输入验证器
│   │   ├── utils.py               # 工具函数
│   │   ├── parsers.py             # 数据解析器
│   │   ├── metrics.py             # 指标计算
│   │   └── exceptions/            # 异常类体系
│   ├── config/                     # 配置外部化
│   │   ├── loader.py              # YAML 配置加载器
│   │   ├── data_source.yaml       # 数据源端点
│   │   ├── scoring.yaml           # 评分权重（含资金面因子，v1.3.1）
│   │   ├── limits.yaml            # 限流配置
│   │   ├── industry_thresholds.yaml # 行业差异化阈值（v1.3.2 从 data/industry_thresholds.json 迁入）
│   │   └── notification.yaml      # 通知通道配置
│   ├── data/                       # 数据层
│   │   ├── types.py               # 数据类型（含 goodwill/pledge_ratio，v1.3.1）
│   │   ├── cache.py               # 兼容 shim（实际在 common/cache.py，v1.3.2）
│   │   ├── chip.py                # 资金面数据汇总（v1.3.1）
│   │   ├── config.py              # 数据配置
│   │   └── *.json / *.csv         # 静态参考数据
│   ├── fetchers/                   # 数据获取层（25+ 模块）
│   │   ├── tencent_quote.py       # 腾讯行情
│   │   ├── eastmoney_quote.py     # 东财行情
│   │   ├── eastmoney_finance.py   # 东财财务
│   │   ├── eastmoney_kline.py     # 东财 K 线
│   │   ├── eastmoney_chip.py      # 东财资金面（v1.3.1）
│   │   ├── eastmoney_flow.py      # 东财资金流向
│   │   ├── eastmoney_lhb.py       # 东财龙虎榜
│   │   ├── eastmoney_event.py     # 东财事件日历
│   │   ├── sina_quote.py          # 新浪行情
│   │   ├── sina_kline.py          # 新浪 K 线
│   │   ├── xueqiu_quote.py        # 雪球行情（v1.3.1）
│   │   ├── ths_quote.py           # 同花顺行情（v1.3.1）
│   │   ├── efinance_quote.py      # efinance 行情
│   │   ├── akshare_quote.py       # AkShare 行情
│   │   ├── tushare_quote.py       # Tushare 行情
│   │   ├── pytdx_quote.py         # pytdx 行情
│   │   ├── baostock_kline.py      # baostock K 线
│   │   └── ...                    # 更多数据源
│   ├── *.py                        # 顶层 CLI 脚本（SKILL.md 直接调用的入口）
│   ├── fetchers/                   # 数据获取层（25+ 模块）
│   │   ├── tencent_quote.py       # 腾讯行情
│   │   ├── eastmoney_quote.py     # 东财行情
│   │   ├── eastmoney_finance.py   # 东财财务
│   │   ├── eastmoney_kline.py     # 东财 K 线
│   │   ├── eastmoney_chip.py      # 东财资金面（v1.3.1）
│   │   ├── eastmoney_flow.py      # 东财资金流向
│   │   ├── eastmoney_lhb.py       # 东财龙虎榜
│   │   ├── eastmoney_event.py     # 东财事件日历
│   │   ├── sina_quote.py          # 新浪行情
│   │   ├── sina_kline.py          # 新浪 K 线
│   │   ├── xueqiu_quote.py        # 雪球行情（v1.3.1）
│   │   ├── ths_quote.py           # 同花顺行情（v1.3.1）
│   │   ├── efinance_quote.py      # efinance 行情
│   │   ├── akshare_quote.py       # AkShare 行情
│   │   ├── tushare_quote.py       # Tushare 行情
│   │   ├── pytdx_quote.py         # pytdx 行情
│   │   ├── baostock_kline.py      # baostock K 线
│   │   └── ...                    # 更多数据源
│   ├── strategies/                 # 选股策略系统
│   │   ├── registry.py            # 策略注册中心
│   │   ├── thresholds.py          # 行业阈值管理
│   │   └── factors/               # 因子实现
│   │       ├── quality.py         # 质量因子
│   │       ├── valuation.py       # 估值因子
│   │       ├── momentum.py        # 动量因子
│   │       ├── liquidity.py       # 流动性因子
│   │       └── volatility.py      # 波动率因子
│   ├── technical/                  # 技术分析模块
│   │   ├── macd.py / kdj.py / boll.py / rsi.py
│   │   ├── moving_average.py      # 均线系统
│   │   ├── volume.py              # 量价分析
│   │   ├── trend.py               # 趋势判断
│   │   ├── candlestick.py         # K 线形态
│   │   ├── astock.py              # A 股特色指标
│   │   ├── signals.py             # 信号生成
│   │   ├── scoring.py             # 综合评分（含资金面因子，v1.3.1）
│   │   └── report.py              # 报告生成
│   ├── chan/                       # 缠论模块（v1.3.1 重构）
│   │   ├── merge.py / fenxing.py / bi.py
│   │   ├── xianduan.py / zhongshu.py / macd.py
│   │   ├── beichi.py / maidian.py
│   │   └── __init__.py
│   ├── monitor/                    # 实时监控
│   │   ├── health.py              # 健康检查（v1.3.1 支持 --cleanup）
│   │   ├── manager.py             # 监控管理器
│   │   └── channels/              # 通知渠道
│   │       ├── base.py / bark.py
│   │       ├── wechat.py          # 企业微信（v1.3.1）
│   │       └── dingtalk.py        # 钉钉（v1.3.1）
│   ├── portfolio/                  # 持仓管理
│   ├── quote.py                   # 腾讯实时行情
│   ├── finance.py                 # 东财财务数据
│   ├── kline.py                   # 新浪 K线
│   ├── chip.py                    # 资金面分析 CLI（v1.3.1）
│   ├── announcements.py           # 东财公告/研报
│   ├── screener.py                # A股多因子选股器
│   ├── technical.py               # 纯技术分析
│   ├── classifier.py              # 个股类型分类
│   ├── chan.py                    # 缠论结构（兼容层，已迁移至 chan/）
│   ├── backtest.py                # 回测引擎（v1.3.1 改为 8 线程并发）
│   └── patterns_local.py          # A股本土战法形态
├── data/                           # 静态参考数据
│   ├── industry_thresholds.json   # 行业阈值配置
│   ├── sector_etf.csv              # 板块 ETF 清单
│   ├── sector_stocks.json          # 板块核心标的库
│   └── portfolio_example.json      # 持仓配置示例
└── tests/
    ├── conftest.py                # pytest 配置
    ├── smoke_test.sh              # 端到端冒烟测试
    └── test_*.py                  # 单元测试（含 test_chip.py，v1.3.1）
```

## 脚本模块说明

### common.py - 编码转换、字段映射、HTTP 工具

提供通用工具函数：

- GBK 编码转换与腾讯行情字段解析
- HTTP 请求封装（含磁盘缓存，TTL 6 小时）
- 代码标准化（sh/sz 前缀推断、交易所识别、板块类型判断）
- 批量分组工具（batchify，每批 ≤15 只）
- 字段映射配置（腾讯/东财/新浪）

### quote.py - 腾讯实时行情

从 `qt.gtimg.cn` 获取实时行情数据。

用法：

```bash
python3 scripts/quote.py sh600989
```

### finance.py - 东财财务数据

从 `emweb.securities.eastmoney.com` 获取财务摘要。

用法：

```bash
python3 scripts/finance.py SH600989
```

### kline.py - 新浪 K 线

从 `money.finance.sina.com.cn` 获取 K 线数据。

用法：

```bash
python3 scripts/kline.py sh600989 240 30
```

### screener.py - 多因子选股器

A 股多因子选股系统。

用法：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

### technical.py - 技术分析引擎

纯技术分析，包含均线、MACD、KDJ、BOLL、缠论、本土战法。

用法：

```bash
python3 scripts/technical.py sh600989 full
```

### chan.py - 缠论结构

缠论分析：笔-线段-中枢-买卖点-背驰。

### patterns_local.py - A 股本土战法形态

本土战法形态识别：三阴一阳、老鸭头、美人肩等。

### classifier.py - 个股类型分类

A 股个股类型分类器。

## 核心技术组件

### BaseFetcher - 数据源抽象基类

```python
# scripts/common/__init__.py
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
        """检查数据源是否可用。"""
        return self.circuit_breaker.can_execute()
```

### CircuitBreaker - 线程安全熔断器

```python
# scripts/common/__init__.py
class CircuitBreaker:
    """三态熔断器：CLOSED → OPEN → HALF_OPEN"""

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: int = 60):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self._lock = threading.Lock()  # 线程安全
```

### DataFetcherManager - 多源故障转移

```python
# scripts/common/__init__.py
class DataFetcherManager:
    """按优先级尝试各数据源，自动故障切换。"""

    def fetch(self, code: str, **kwargs):
        for fetcher in self.fetchers:  # 已按 priority 排序
            if not fetcher.is_available():
                continue
            result = fetcher.fetch(code, **kwargs)
            if result is not None:
                return result
        return None  # 所有源失败
```

## 数据源架构

### 行情数据源（9 个）

| 数据源 | 用途 | 编码 | 优先级 |
|--------|------|------|--------|
| 腾讯 qt.gtimg.cn | 实时行情、PE/PB/市值 | GBK | 10 |
| 东财 emweb.securities.eastmoney.com | 实时行情 | UTF-8 | 9 |
| 雪球 stock.xueqiu.com | 实时行情（v1.3.1） | UTF-8 | 8 |
| 同花顺 quote.ths123.com | 实时行情（v1.3.1） | UTF-8 | 7 |
| 新浪 hq.sinajs.cn | 实时行情 | GBK | 6 |
| efinance | 实时行情 | UTF-8 | 4 |
| akshare | 实时行情 | UTF-8 | 3 |
| tushare | 实时行情 | UTF-8 | 2 |
| pytdx | 实时行情 | UTF-8 | 1 |

### K线数据源（8 个）

| 数据源 | 用途 | 周期 |
|--------|------|------|
| 新浪 money.finance.sina.com.cn | 5/15/30/240 分钟 | ✅ |
| 东财 | 5/15/30/60/240 分钟 | ✅ |
| efinance | 5/15/30/60/日 | ✅ |
| akshare | 全周期 | ✅ |
| baostock | 日/周/月 | ✅ |
| pytdx | 日/分时 | ✅ |
| tushare | 全周期 | ✅ |
| yfinance | 港股/美股 | ✅ |

### 财务数据源（3 个）

| 数据源 | 用途 |
|--------|------|
| 东财 emweb.securities.eastmoney.com | 财务摘要 |
| efinance | 财务数据 |
| akshare | 财务数据 |

### 资金面数据源（1 个，v1.3.1 新增）

| 数据源 | 用途 |
|--------|------|
| 东财 data.eastmoney.com | 融资融券、股东户数、十大流通股东 |

### 辅助数据源

- 资金流向：`eastmoney_flow.py`
- 龙虎榜：`eastmoney_lhb.py`
- 事件日历：`eastmoney_event.py`
- 公告/研报：`announcements.py`

## Skill 注册机制

### .claude/skills/ vs .agents/skills/

- `.claude/skills/`：Claude Code 读取的 skill 源
- `.agents/skills/`：Codex workspace 读取的 skill 源
- 两者内容需保持一致

### symlink 机制

`install.sh` 创建扁平 symlink 到 `~/.claude/skills/`：

```bash
ln -sf ~/Documents/curtis/stock-analyzer-skill/.claude/skills/stock ~/.claude/skills/stock
ln -sf ~/Documents/curtis/stock-analyzer-skill/.claude/skills/market ~/.claude/skills/market
# ... 共 8 个
```

### SKILL.md 格式

每个 skill 的 `SKILL.md` 包含：

- name：技能名称
- description：触发条件和用途
- 指令：详细的使用说明

## 扩展开发指南

### 添加新数据源

1. 在 `scripts/fetchers/` 下创建新模块，继承 `BaseFetcher`
2. 实现 `fetch()` 方法，返回 dict/list 或 None
3. 设置合适的 `priority`（越高越优先）
4. 在 `scripts/fetchers/__init__.py` 中注册

```python
# scripts/fetchers/my_custom_quote.py
from scripts.common import BaseFetcher, http_get, get_circuit_breaker

class MyCustomQuoteFetcher(BaseFetcher):
    def __init__(self):
        super().__init__("my_custom_quote", priority=5)

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not self.is_available():
            return None
        try:
            url = f"https://api.example.com/quote/{code}"
            data = http_get(url, timeout=8)
            # 解析数据...
            self.on_success()
            return parsed_data
        except Exception as e:
            self.on_failure()
            return None
```

### 添加新因子

1. 在 `scripts/strategies/factors/` 下创建新因子模块
2. 实现因子计算逻辑
3. 在 `scripts/strategies/registry.py` 中注册
4. 更新权重配置 `scripts/config/scoring.yaml`

### 添加新技能

1. 创建 `.claude/skills/<name>/SKILL.md`
2. 添加 YAML frontmatter（name、description）
3. 更新 `install.sh` 添加新的 symlink
4. 同步到 `.agents/skills/`

```yaml
---
name: my-new-skill
description: 我的新技能 /my-new-skill
---

# 技能说明
...
```

### 行业差异化配置

1. 编辑 `data/industry_thresholds.json`
2. 添加新行业的阈值配置
3. 重启服务生效

```json
{
  "新行业": {
    "roe": { "min": 12 },
    "pe": { "max": 25 },
    "gross_margin": { "min": 30 },
    "debt_ratio": { "max": 65 }
  }
}
```

## 测试与验证

### 单元测试

```bash
python3 -m pytest tests/ -x -q
```

### 包含网络请求的测试

```bash
python3 -m pytest tests/ -x -q --run-network
```

### 端到端冒烟测试

```bash
./tests/smoke_test.sh
```

预期输出：`N 通过, 0 失败`

### 手动测试流程

1. 运行单个脚本验证数据获取
2. 运行 skill 命令验证功能
3. 检查输出格式和内容

### 健康检查

```bash
python3 scripts/monitor/health.py
python3 scripts/monitor/health.py --json
```

### 回测验证

```bash
python3 scripts/backtest.py --strategy balanced --top 5 --days 60
python3 scripts/backtest.py --optimize --strategy balanced
```

## 贡献流程

### Git 规范

- 提交信息：Conventional Commits（`feat` / `fix` / `docs` / `refactor` / `chore`）
- 标题与正文使用中文
- 分支命名：`<type>/<短描述>`

### 示例

```bash
git commit -m "feat: 添加新数据源"
git commit -m "fix: 修复编码问题"
git commit -m "docs: 更新 API 文档"
```

### 提交前检查

```bash
# 运行测试
python3 -m pytest tests/ -x -q

# 端到端测试
./tests/smoke_test.sh
```
