# 项目改进路线图

> 基于深度分析，按优先级排序的系统性改进计划。
> 创建时间：2026-06-05

---

## 一、改进总览

| 优先级 | 改进项 | 影响范围 | 工作量 | 状态 |
| --- | --- | --- |
| P0 | 核心算法单元测试 | 全项目 | 大 | ✅ 已完成（253 个测试） |
| P0 | technical.py 拆分重构 | scripts/ | 大 | ✅ 已完成（14 个模块） |
| P1 | 数据源容错与降级 | scripts/common.py | 中 | 待启动 |
| P1 | 双平台 SKILL.md 同步机制 | .claude/ + .agents/ | 小 | ✅ 已同步（无需操作） |
| P1 | 缓存管理优化 | scripts/common.py | 小 | 待启动 |
| P2 | 回测框架 | 新增模块 | 大 | 待启动 |
| P2 | 缠论实现精度提升 | scripts/chan.py | 中 | 待启动 |
| P2 | 错误处理与日志体系 | 全项目 | 中 | 待启动 |
| P3 | CI/CD 集成 | .github/ | 中 | 待启动 |
| P3 | 股票池扩容与去重 | data/ | 小 | 待启动 |
| P3 | 请求限速与并发控制 | scripts/ | 小 | 待启动 |
| P3 | 类型注解 | scripts/ | 中 | 待启动 |

---

## 二、P0 — 必须修复（核心风险）

### 2.1 核心算法单元测试

**问题**：项目最大的技术风险。1682 行的 technical.py、552 行的 chan.py、547 行的 screener.py 均无任何单元测试。冒烟测试仅验证"能跑"，不验证"算对"。

**现状**：
- 测试文件仅 `tests/smoke_test.sh`（Bash 冒烟测试）
- 依赖真实网络请求，无法离线运行
- 核心算法（分型识别、笔构建、MACD 背驰、多因子评分）零覆盖

**改进方案**：

```
tests/
├── conftest.py              # pytest fixtures（mock 数据、K 线样本）
├── data/
│   ├── kline_sample.json    # 标准 K 线测试数据（含已知形态）
│   ├── fenxing_cases.json   # 分型识别边界用例
│   └── macd_diverge.json    # MACD 背驰测试用例
├── test_common.py           # common.py 单元测试
├── test_technical.py        # technical.py 单元测试（最高优先级）
├── test_chan.py             # chan.py 单元测试
├── test_screener.py         # screener.py 因子评分测试
├── test_classifier.py       # classifier.py 分类逻辑测试
├── test_patterns_local.py   # 本土战法形态测试
└── smoke_test.sh            # 保留原有冒烟测试
```

**关键测试用例**：

1. **缠论（test_chan.py）**：
   - K 线包含处理：涨势取高高、跌势取低低、最大合并 3 次
   - 分型识别：标准顶分型、底分型、连续同类型去重
   - 笔构建：>= 2 根独立 K 线、笔的方向、笔的破坏
   - 线段构建：>= 3 笔、前三笔重叠区间
   - 中枢识别：3 段线段重叠、扩展中枢合并
   - 背驰检测：趋势背驰（MACD 面积对比）、盘整背驰
   - 三类买卖点：一买（底背驰）、二买（不创新低）、三买（回踩不入中枢）

2. **技术分析（test_technical.py）**：
   - MACD 计算：DIF/DEA/柱值、金叉死叉判定
   - MACD 背离：顶背离（价格新高但 MACD 不新高）、底背离
   - KDJ 计算：K/D/J 值、超买超卖、A 股钝化检测
   - 均线系统：MA 计算、排列状态、粘合度
   - K 线形态：每种形态（十字星、锤子线、早晨之星等）的正向/反向用例
   - 综合评分：不同类型股票在不同市场环境下的权重验证

3. **选股器（test_screener.py）**：
   - 因子评分：各因子桶的分值计算
   - 硬过滤：ST 检测、成交额阈值、涨跌停过滤
   - 策略差异：5 种策略的权重配置验证

**实施步骤**：
1. 建立 `tests/conftest.py`，定义标准 K 线 fixture（含已知技术形态）
2. 编写 `test_chan.py`（缠论逻辑最复杂，优先覆盖）
3. 编写 `test_technical.py`（从 MACD/均线等基础指标开始）
4. 编写 `test_screener.py`（因子评分逻辑）
5. 编写 `test_classifier.py` + `test_patterns_local.py`
6. 添加 `pytest.ini` 或 `pyproject.toml` 中的 pytest 配置
7. 在 CONTRIBUTING.md 中补充测试规范

**预期收益**：重构有安全网、算法正确性可验证、回归风险大幅降低

---

### 2.2 technical.py 拆分重构

**问题**：1682 行单文件承担 9+ 个职责，是典型的"God Object"。

**当前职责**（全塞在一个文件里）：
- 均线系统（MA 计算、排列、粘合度）
- MACD（DIF/DEA/柱、金叉死叉、背离检测）
- KDJ（K/D/J、超买超卖、钝化检测）
- BOLL（布林带、带宽、价格位置）
- RSI（超买超卖信号）
- 成交量分析（量比、量价配合、OBV）
- K 线形态识别（单根/双根/三根、A 股特化）
- 趋势结构（支撑阻力、箱体、突破、波浪）
- A 股特化（涨跌停、连板、T+1）
- 自适应综合评分（类型×指标×市场环境矩阵）
- 买卖信号汇总

**重构方案**：

```
scripts/
├── technical/
│   ├── __init__.py          # 导出主入口 analyze()
│   ├── core.py              # 主分析流程编排（< 200 行）
│   ├── moving_average.py    # 均线系统（MA 计算、排列、粘合度、支撑阻力）
│   ├── macd.py              # MACD（DIF/DEA/柱、金叉死叉、背离检测）
│   ├── kdj.py               # KDJ（K/D/J、超买超卖、钝化检测）
│   ├── boll.py              # 布林带（上中下轨、带宽、价格位置）
│   ├── rsi.py               # RSI（超买超卖信号）
│   ├── volume.py            # 成交量分析（量比、量价配合、OBV 背离）
│   ├── candlestick.py       # K 线形态识别（所有形态）
│   ├── trend.py             # 趋势结构（支撑阻力、箱体、突破、波浪）
│   ├── astock.py            # A 股特化（涨跌停、连板、T+1）
│   ├── scoring.py           # 综合评分引擎（类型×指标×市场环境矩阵）
│   └── signals.py           # 买卖信号汇总
├── technical.py             # 保留为兼容入口（import technical，转发 CLI）
```

**重构原则**：
- 先写测试，再拆分（保证行为不变）
- 每个模块独立可测试，无循环依赖
- `technical.py` 保留为 CLI 入口，内部 import 拆分后的模块
- 评分矩阵（7 类型 × 9 维度）提取为配置文件，不硬编码

**实施步骤**：
1. **先完成 test_technical.py**（2.1 中已规划），确保现有行为有测试覆盖
2. 创建 `scripts/technical/` 目录，从最大最独立的模块开始拆分
3. 拆分顺序：`candlestick.py` → `macd.py` → `kdj.py` → `boll.py` → `rsi.py` → `volume.py` → `moving_average.py` → `trend.py` → `astock.py` → `scoring.py` → `signals.py`
4. 每拆一个模块，运行全部测试确认无回归
5. 最后将 `technical.py` 改为薄包装层

**预期收益**：可维护性大幅提升、每个模块可独立测试、后续扩展更容易

---

## 三、P1 — 重要改进（可靠性）

### 3.1 数据源容错与降级

**问题**：使用非官方 API，无降级策略，单点故障会导致整个系统不可用。

**改进方案**：

```python
# scripts/common.py 中增加数据源管理器

class DataSourceManager:
    """数据源容错管理"""

    def __init__(self):
        self.sources = {
            'quote': [
                ('tencent', fetch_tencent_quote),
                # 未来可加: ('sina', fetch_sina_quote),
            ],
            'finance': [
                ('eastmoney', fetch_eastmoney_finance),
            ],
            'kline': [
                ('sina', fetch_sina_kline),
                # 未来可加: ('eastmoney', fetch_eastmoney_kline),
            ],
        }

    def fetch(self, category, *args, **kwargs):
        """按优先级尝试数据源，失败自动降级"""
        for name, fetcher in self.sources[category]:
            try:
                return fetcher(*args, **kwargs)
            except Exception as e:
                log.warning(f"数据源 {name} 失败: {e}, 尝试下一个")
                continue
        raise DataSourceError(f"所有数据源均失败: {category}")
```

**具体改进**：
1. 为每个数据源添加健康检查函数
2. 实现请求超时配置（当前使用 urllib 默认超时）
3. 添加 429（限流）检测与退避重试（指数退避）
4. 数据源失败时记录日志并尝试备选源
5. 在 common.py 中增加 `--timeout` CLI 参数

---

### 3.2 双平台 SKILL.md 同步机制

**问题**：`.claude/skills/` 和 `.agents/skills/` 下的 SKILL.md 是独立副本，改一个忘改另一个会不一致。

**方案 A — Symlink（推荐）**：
```bash
# .agents/skills/ 中的文件 symlink 到 .claude/skills/
ln -s ../../.claude/skills/stock/SKILL.md .agents/skills/stock/SKILL.md
```

**方案 B — 安装脚本自动同步**：
在 `install.sh` 中增加同步步骤，每次安装时复制。

**方案 C — Pre-commit hook**：
添加 git pre-commit hook，检测两个目录下的 SKILL.md 是否一致。

**推荐方案 A**：最简单，零维护成本，消除同步问题。

---

### 3.3 缓存管理优化

**问题**：
- `.cache/` 目录无清理机制，会无限膨胀
- 全局 TTL 6 小时不适合所有数据（实时行情 vs 财务数据）

**改进方案**：

1. **差异化 TTL**：
```python
CACHE_TTL = {
    'quote':        300,      # 实时行情 5 分钟
    'kline':        1800,     # K 线 30 分钟
    'finance':      21600,    # 财务数据 6 小时
    'announcement': 3600,     # 公告 1 小时
    'screener':     1800,     # 选股结果 30 分钟
}
```

2. **缓存清理**：
```bash
# 添加 scripts/cache_clean.py
python scripts/cache_clean.py --max-age 7d    # 清理 7 天前的缓存
python scripts/cache_clean.py --max-size 100M  # 限制缓存总大小
```

3. **缓存统计**：
```bash
python scripts/cache_clean.py --stats  # 显示缓存命中率、大小、文件数
```

---

## 四、P2 — 重要增强（功能性）

### 4.1 回测框架

**问题**：选股策略、技术指标、形态识别都无法验证历史表现。权重配置无数据支撑。

**方案**：新增 `scripts/backtest.py`

```
scripts/backtest.py
├── 加载历史 K 线数据（从新浪或本地 CSV）
├── 按时间步进模拟交易
├── 记录每次信号触发后的收益
├── 统计胜率、盈亏比、最大回撤、夏普比率
└── 输出策略评估报告
```

**核心接口**：
```bash
# 回测某个技术指标的历史表现
python scripts/backtest.py --strategy macd_golden_cross \
    --stock 600519 --period 2023-01-01:2025-12-31 \
    --output report.json

# 回测选股策略
python scripts/backtest.py --strategy screener \
    --params '{"strategy": "quality_value", "sector": "白酒"}' \
    --period 2023-01-01:2025-12-31
```

**最小可用版本（MVP）**：
1. 支持单股票 MACD 金叉/死叉策略回测
2. 输出：交易次数、胜率、平均收益、最大回撤
3. 后续迭代：多股票、多策略、组合回测

---

### 4.2 缠论实现精度提升

**问题**：chan.py 是简化版实现，与完整缠论有差距。

**改进项**：

| 改进项 | 当前状态 | 目标状态 |
| --- |
| 笔构建 | >= 2 根独立 K 线 | 支持"笔破坏"动态修正 |
| 线段构建 | >= 3 笔，前 3 笔重叠 | 支持"线段破坏"和第一种/第二种情况 |
| 中枢级别 | 单一级别 | 支持多级别递归（1 分/5 分/30 分） |
| 背驰检测 | 仅 MACD 面积 | 增加成交量、力度等辅助判断 |
| 买卖点 | 三类基本买卖点 | 增加类二买、三买后的延伸判断 |

**实施建议**：
- 逐步改进，每改一个点补充对应测试用例
- 参考《缠中说禅：教你炒股票》原文中的精确定义
- 输出结果增加"级别"字段，支持多周期递归分析

---

### 4.3 错误处理与日志体系

**问题**：当前只有 `print` 输出，无日志级别、无结构化日志。

**改进方案**：

```python
# scripts/common.py 中增加日志配置

import logging

def setup_logger(name, level=logging.INFO):
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger
```

**改进项**：
1. 所有脚本替换 `print` 为 `logging`
2. 支持 `--verbose` / `--quiet` 参数控制日志级别
3. 数据源失败记录 warning，计算异常记录 error
4. 关键决策点（买卖信号、评分结果）记录 info

---

## 五、P3 — 长期优化（工程化）

### 5.1 CI/CD 集成

**方案**：GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install pytest
      - run: pytest tests/ -v --tb=short
      - run: bash tests/smoke_test.sh
```

---

### 5.2 股票池扩容与去重

**问题**：当前 14 板块 99 只股票覆盖面有限。

**改进**：
1. `refresh_pool.py` 增加去重逻辑（同一股票出现在多个板块时只保留一次）
2. 扩展板块覆盖：增加"半导体"、"人工智能"、"新能源车"等热门板块
3. `sector_stocks.json` 不提交到 git（加入 .gitignore），改为 CI 中动态生成

---

### 5.3 请求限速与并发控制

**问题**：screener.py 的 ThreadPoolExecutor 无速率限制，批量拉取可能触发 API 封禁。

**改进**：
```python
# scripts/common.py 中增加简单限速器

import time
import threading

class RateLimiter:
    def __init__(self, max_per_second=5):
        self.interval = 1.0 / max_per_second
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            wait_time = self.interval - (now - self.last)
            if wait_time > 0:
                time.sleep(wait_time)
            self.last = time.monotonic()
```

---

### 5.4 类型注解

**问题**：全部脚本无类型注解，IDE 无法提供智能提示。

**改进**：
- 逐步添加，从 `common.py` 的核心函数开始
- 使用 `from __future__ import annotations` 兼容 Python 3.9+
- 不引入 mypy 检查（保持零依赖原则），仅用于 IDE 辅助

---

## 六、已知限制（暂不修复）

以下问题已知但暂不纳入改进计划，记录在此供参考：

| 限制 | 原因 |
| --- | --- |
| 数据源为非官方 API | 无官方免费 API 可替代，接受此风险 |
| 选股池仅覆盖 A 股 | 项目定位为 A 股分析工具 |
| 专家评分权重无数据支撑 | 需要回测框架先就绪（见 4.1） |
| methodology.md 根目录和 docs/ 各一份 | 保持现状，docs/ 版本为文档站用 |
| .cache/ 目录已提交 98 个文件 | 下次 refresh_pool 运行后统一清理 |

---

## 七、实施建议

**推荐顺序**：

```
阶段一（基础保障）：2.1 测试 → 2.2 拆分 technical.py → 3.2 SKILL.md 同步
阶段二（可靠性）：  3.1 数据源容错 → 3.3 缓存优化 → 4.3 日志体系
阶段三（功能性）：  4.1 回测框架 → 4.2 缠论精度 → 5.3 请求限速
阶段四（工程化）：  5.1 CI/CD → 5.2 股票池扩容 → 5.4 类型注解
```

**核心原则**：
- **先写测试再重构**：每个 P0/P1 改进项都应先有测试覆盖
- **小步快跑**：每次改动聚焦一个模块，确保可回滚
- **保持零依赖**：新增功能继续使用 stdlib，除非有充分理由引入第三方库
