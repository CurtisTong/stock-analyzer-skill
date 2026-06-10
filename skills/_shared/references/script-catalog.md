# 脚本目录

> 12 个 skill 共用，按需加载。Claude Code 运行时工作目录即为项目根目录。

## 数据获取脚本

| 脚本                       | 用途                             | 常用参数                  |
| -------------------------- | -------------------------------- | ------------------------- |
| `python3 scripts/quote.py`        | 实时行情/估值                  | `<sh/sz代码>`、`-j` JSON |
| `python3 scripts/finance.py`      | 财务数据（最近 4 季）           | `SH/SZ代码`、`-c` 批量   |
| `python3 scripts/kline.py`        | K 线                          | `<代码> <周期> <根数>`    |
| `python3 scripts/announcements.py`| 公告/研报                      | `<代码> [reports]`        |
| `python3 scripts/chip.py`         | 筹码分布                       | `<sh/sz代码>`             |

## 分析脚本

| 脚本                         | 用途                              |
| ---------------------------- | --------------------------------- |
| `python3 scripts/technical.py`     | 纯技术分析报告                    |
| `python3 scripts/chan.py`          | 缠论（笔-线段-中枢-买卖点-背驰） |
| `python3 scripts/classifier.py`    | 个股类型自适应分类                |
| `python3 scripts/patterns_local.py`| A 股本土战法形态                  |
| `python3 scripts/screener.py`      | 多因子选股                        |
| `python3 scripts/backtest.py`      | 策略回测                          |

## 业务/系统脚本

| 脚本                          | 用途                       |
| ----------------------------- | -------------------------- |
| `python3 scripts/init_pool.py`     | 初始化股票池（首次使用）   |
| `python3 scripts/refresh_pool.py`  | 刷新股票池                 |
| `python3 scripts/monitor.py`       | 盘中监控与告警             |

## JSON 输出

所有数据获取脚本支持 `-j` 输出 JSON，便于二次计算（排序、过滤、聚合）。

## 数据源

- **行情**：腾讯 `qt.gtimg.cn`
- **财务**：东方财富 `emweb.securities.eastmoney.com`
- **K 线**：新浪 `money.finance.sina.com.cn`
- **公告/研报**：东方财富 `np-anotice-stock.eastmoney.com`

国内直连无代理。脚本不可用时，参考 `methodology.md` 中数据源说明直接 curl。
