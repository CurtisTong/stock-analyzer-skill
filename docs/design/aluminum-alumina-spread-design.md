# 铝价 / 氧化铝价差数据获取项目设计

> 版本：v1.2｜日期：2026-11-22｜状态：**P0–P3 全部实现并验证**
> 目标：补齐云铝股份（sz000807）等电解铝周期股分析中「铝价/氧化铝价差数据缺失」的缺口

---

## 一、背景与缺口

在 2026-11-22 的云铝股份 full debate 报告中，周期股框架的关键输入被标记为缺失：

> 🔴 高级 | 周期定位缺失 | 铝价/氧化铝价格分位、行业历史 ROE/PE 分位、股息率均无数据 → 周期阈值判定为暂定

这直接导致一个**反直觉但关键的判断分歧**无法验证：
- 价值视角（林奇 87.5、价值锚 94.5）：ROE 31.33% + PE 5.49× → 看多
- 周期视角：ROE 31.33% = 周期顶部特征 → 需降权

两者谁对，取决于**铝价与氧化铝价差处于历史什么位置**——这正是本项目要解决的问题。

---

## 二、现状分析（探索代码库后的三个关键发现）

### 发现 1：基础设施已存在，但主流程未接入

`scripts/macro_indicators.py` 已经具备：

| 已有能力 | 位置 | 状态 |
| --- | --- | --- |
| `fetch_aluminum()`（沪铝 AL0） | L706-708 | ✅ 已定义 |
| `fetch_commodity_akshare()` 三段式泛化函数 | L626-678 | ✅ 已定义 |
| 历史序列 + 近 1 年分位计算 `_calc_percentile()` | L336-368 | ✅ 已定义 |
| `cyclical.py` 成本维度消费原料分位 | L217-239 | ✅ 已定义 |

**但 `fetch_all()` 的 macro 段（L859-868）只调用了 `fetch_lithium()`，未调用 `fetch_aluminum()`**。这就是为什么宏观桥输出里没有铝价——不是"取不到"，而是"没接线"。

### 发现 2：akshare 未安装 → 整条 akshare 链路失效

```
$ python3 -c "import akshare"
ModuleNotFoundError: No module named 'akshare'
```

`fetch_commodity_akshare()` 依赖 akshare，在当前环境**全部走 fixture(stale) 兜底**，而 `macro_snapshot.json` 中 `aluminum_cny_t` 为空 → 实际返回 `None`。

**结论：方案必须走零依赖（stdlib urllib）路线，或把 akshare 设为可选增强项。**

### 发现 3：东财期货接口不可用，新浪可用

| 接口 | 结果 |
| --- | --- |
| 东财 push2 `113.AL0` / `113.AO0` | `data: null`（不支持连续合约符号） |
| 东财 push2his kline | `Remote end closed connection` |
| 新浪 `nf_AL0` / `nf_AO0` | ✅ 实时快照可用（2026-11-21） |
| 新浪 `getDailyKLine?symbol=AL0/AO0` | ✅ 完整历史（AL0 5322 条 / AO0 830 条） |

---

## 三、数据源实测验证（2026-11-22 实拉结果）

### 3.1 实时价（新浪 `hq.sinajs.cn`，零依赖）

```
https://hq.sinajs.cn/list=nf_AL0,nf_AO0
Header: Referer: https://finance.sina.com.cn
```

返回解析：

| 合约 | 名称 | 字段8 最新价 | 字段10 昨结算 | 字段17 日期 |
| --- | --- | --- | --- | --- |
| nf_AL0 | 铝连续 | **21585** 元/吨 | 21425 | 2026-11-21 |
| nf_AO0 | 氧化铝连续 | **2609** 元/吨 | 2619 | 2026-11-21 |

⚠️ **致命坑**：必须用 `nf_` 前缀。不带前缀的 `AL0` 返回的是 **2024-07-17 的过期数据**（19800 元/吨），静默错 8%。`AO0` 不带前缀返回空串。

### 3.2 历史序列（新浪 `stock2.finance.sina.com.cn`，零依赖）

```
https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_{sym}=/InnerFuturesNewService.getDailyKLine?symbol={sym}
```

⚠️ **历史接口反而要用无 `nf_` 前缀**（`AL0` / `AO0`）。返回 JSONP，需正则 `=\((\[.*\])\);` 提取。

| 品种 | 起始日期 | bars | 最新收盘 |
| --- | --- | --- | --- |
| AL0（沪铝连续） | 2005-01-04 | 5322 | 21535（2026-11-20） |
| AO0（氧化铝连续） | 2023-06-19（上市日） | 830 | 2618（2026-11-20） |

### 3.3 反直觉发现：价差处于近 1 年**低位**

用实时价 vs 近 250 日历史序列计算分位：

| 指标 | 当前值 | 近 250 日分位 | 区间 |
| --- | --- | --- | --- |
| 铝价 | 21585 元/吨 | **4.4%** | — |
| 氧化铝 | 2609 元/吨 | **9.6%** | — |
| 冶炼价差（AL − 1.92×AO） | 16576 元/吨 | **6.4%** | 16127 – 20294 |

**这与上一轮报告"铝价高位 + 氧化铝低位剪刀差"的假设不符**——铝价本身也在近 1 年低位（4.4%）。说明云铝毛利率从 16.79% → 32.04% 的跃升更可能是**去年低基数 + 氧化铝跌幅更大**所致，而非"铝价高位"。

**这正是本项目的价值**：没有价差分位数据，周期定位会系统性误判。同时也说明——**数据取到后，上一轮的结论需要复核**。

---

## 四、价差计算口径（三档设计）

| 档位 | 公式 | 含义 | 本项目采用 |
| --- | --- | --- | --- |
| L1 简单价差 | `AL − AO` | 直观，但忽略吨铝耗 1.92 吨氧化铝 | ❌ 不采用 |
| **L2 冶炼价差** | `AL − 1.92 × AO` | 电解铝核心价差，行业通用口径 | ✅ **主口径** |
| L3 完全成本毛利 | `AL − 1.92×AO − 电力 − 预焙阳极 − 其他` | 真实利润，需额外数据 | ⚠️ 二期扩展 |

> **1.92 系数**：电解 1 吨铝理论耗氧化铝约 1.92 吨（氧化铝 Al₂O₃ 含铝 53%，考虑损耗）。这是行业通用简化系数，需在输出中标注"简化口径"。

**L3 所需额外数据（二期）**：
- 电力成本：云南水电电价（云铝特有，枯水期/丰水期差异大）
- 预焙阳极：可复用 `fetch_commodity_akshare` 或新增石油焦/煤沥青
- 其他：氟化铝、冰晶石等（占比小，可忽略）

---

## 五、架构设计（契合现有代码，最小侵入）

### 5.1 分层与接入点

```
数据源层  scripts/macro_indicators.py
  ├─ _sina_futures_get(symbol)        [新增] 实时快照，nf_ 前缀，解析字段8/10/17
  ├─ _sina_futures_get_history(sym)   [新增] 历史 JSONP，无前缀，返回 close 序列
  ├─ fetch_commodity_sina(mat, key)   [新增] 三段式泛化（对齐 L626 的 akshare 版）
  │    ├─ 1. 新鲜 fixture 短路（复用 _key_is_fresh）
  │    ├─ 2. 新浪实时 + 历史分位 → 回写 snapshot
  │    └─ 3. 过期 fixture 兜底
  ├─ fetch_alumina()                  [新增] AO0
  ├─ fetch_aluminum_sina()            [新增] AL0（保留原 akshare 版作可选增强）
  └─ fetch_aluminum_alumina_spread()  [新增] L2 价差 + 分位
       └─ 接入 fetch_all()["macro"]  ★ 核心缺口

数据落盘  scripts/data/macro_snapshot.json
  ├─ aluminum_cny_t / aluminum_percentile_1y
  ├─ alumina_cny_t / alumina_percentile_1y
  ├─ al_alumina_spread_cny_t / al_alumina_spread_percentile_1y
  └─ *_ts（per-key 时间戳，避免全局 TTL 短路 bug）

消费层
  ├─ market_anchor.py L246 宏观桥   [改] 透出 3 组价格 + 分位 + source
  ├─ strategies/factors/cyclical.py [改] 成本维度用价差分位替代单原料分位
  ├─ experts/scoring/sector_specialist.py [改] 周期阈值纳入价差分位
  └─ skills/stock/reports/full-template.md [改] 周期股宏观桥章节
```

### 5.2 数据契约（输出字段）

```json
{
  "macro": {
    "aluminum_cny_t": 21585.0,
    "aluminum_cny_t_source": "sina_futures",
    "aluminum_percentile_1y": 4.4,
    "alumina_cny_t": 2609.0,
    "alumina_cny_t_source": "sina_futures",
    "alumina_percentile_1y": 9.6,
    "al_alumina_spread_cny_t": 16575.7,
    "al_alumina_spread_cny_t_source": "sina_futures(derived)",
    "al_alumina_spread_percentile_1y": 6.4,
    "al_alumina_spread_ratio": 1.92,
    "al_alumina_spread_note": "简化口径 L2，未扣电力/预焙阳极"
  },
  "data_quality": {
    "degraded_fields": []
  }
}
```

**缺失字段一律 `null`，不得用 0 占位**（遵循 SKILL.md P0-4a 约定）。

---

## 六、代码骨架（关键函数）

```python
_SINA_FUTURES_REALTIME = {
    "aluminum": ("nf_AL0", 8, 10, 17),   # 品种 -> (代码, 最新价idx, 昨结算idx, 日期idx)
    "alumina":  ("nf_AO0", 8, 10, 17),
}
_SINA_FUTURES_HISTORY = {"aluminum": "AL0", "alumina": "AO0"}  # 历史用无前缀
_ALUMINA_PER_TON_AL = 1.92  # 吨铝耗氧化铝系数

def _sina_futures_realtime(code: str, price_idx: int, settle_idx: int, date_idx: int):
    """实时快照；nf_ 前缀；失败返回 None（不抛）"""
    try:
        req = urllib.request.Request(
            f"https://hq.sinajs.cn/list={code}",
            headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
        )
        raw = urllib.request.urlopen(req, timeout=5).read().decode("gbk", errors="replace")
        m = re.search(r'hq_str_' + code + r'="([^"]*)"', raw)
        if not m or not m.group(1):
            return None
        f = m.group(1).split(",")
        price = float(f[price_idx])
        return {"price": price, "settle": float(f[settle_idx]), "date": f[date_idx]}
    except Exception as e:
        log_silent_fallback("macro_indicators._sina_futures_realtime", e)
        return None

def _sina_futures_history(sym: str, lookback: int = 250):
    """历史 close 序列；⚠️ 无 nf_ 前缀；JSONP 需正则提取"""
    try:
        url = (f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
               f"var%20_{sym}=/InnerFuturesNewService.getDailyKLine?symbol={sym}")
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn",
                                                   "User-Agent": "Mozilla/5.0"})
        txt = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", "replace")
        rows = json.loads(re.search(r"=\((\[.*\])\);?", txt).group(1))
        return [float(r["c"]) for r in rows[-lookback:]]
    except Exception as e:
        log_silent_fallback("macro_indicators._sina_futures_history", e)
        return None

def fetch_aluminum_alumina_spread() -> dict | None:
    """L2 冶炼价差 = AL - 1.92*AO，含近 1 年分位"""
    al = fetch_aluminum_sina()      # 内部已回写 snapshot
    ao = fetch_alumina()
    if not al or not ao:
        return None
    spread = al["value"] - _ALUMINA_PER_TON_AL * ao["value"]
    # 用两者历史序列按日对齐算价差分位（缺一历史则退化为简单相减无分位）
    al_hist, ao_hist = al.get("history"), ao.get("history")
    pct = None
    if al_hist and ao_hist:
        n = min(len(al_hist), len(ao_hist))
        spread_hist = [a - _ALUMINA_PER_TON_AL * o
                       for a, o in zip(al_hist[-n:], ao_hist[-n:])]
        pct = _calc_percentile(spread_hist + [spread])
    return {"value": round(spread, 2), "percentile": pct,
            "ratio": _ALUMINA_PER_TON_AL, "source": "sina_futures(derived)"}
```

---

## 六·五、实施阶段（建议 4 个 PR）

| Phase | 范围 | 交付物 | 验收标准 |
| --- | --- | --- | --- |
| **P0 数据层** | macro_indicators.py 新增 3 个 fetch_* + 2 个 helper；接入 fetch_all() | 单元测试（mock HTTP，离线可跑） | `fetch_all()["macro"]["al_alumina_spread_cny_t"]` 非 null；断网时降级为 fixture(stale) |
| **P1 锚定透出** | market_anchor.py 宏观桥透出 3 组价格/分位/source | `python3 scripts/market_anchor.py sz000807 -j` | macro 段含 9 个新字段；data_quality.degraded_fields 正确标注 |
| **P2 消费层** | cyclical.py 成本维度改用价差分位；sector_specialist 周期阈值 | 周期评分变更 | 云铝周期评分有量化依据，reason 引用具体分位值 |
| **P3 报告层** | full-template.md 周期股宏观桥章节；SKILL.md 触发说明 | 模板更新 | 云铝报告不再出现"铝价分位数据缺失"护栏 |
| **P4 可选增强** | akshare 可选安装时优先用其现货价；L3 完全成本毛利 | — | 不破坏零依赖基线 |

**Fixture 更新**：P0 完成后需将实测值写入 `scripts/data/macro_snapshot.json`（铝 21585 / 氧化铝 2609 / 价差 16575.7 / 分位 4.4/9.6/6.4），作为离线兜底基线。

---

## 七、测试方案

1. **离线单测（必跑）**：mock `urllib.request.urlopen`，验证
   - nf_ 前缀解析正确（字段 8/10/17）
   - 历史 JSONP 正则提取正确
   - 分位计算：构造已知序列，校验 `_calc_percentile`
   - 价差公式：AL=21585, AO=2609 → 16575.7
   - 断网时三段式正确降级为 `fixture(stale)`
2. **联网冒烟（人工）**：实拉校验与本文 §三 快照一致（允许 1 日内波动）
3. **回归**：`python3 -m pytest tests/ -x -q` 不影响现有测试

---

## 八、风险与坑

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 🔴 nf_ 前缀混用 | 实时必须 `nf_AL0`，历史必须 `AL0`，混用得到 2024 过期数据 | 常量表分离，单元测试断言日期在近 7 日内 |
| 🔴 连续合约换月跳空 | 主力换月导致历史序列跳变，分位有噪音 | 已用连续合约（已平滑处理）；输出标注"连续合约口径" |
| 🟠 数据协议 | 新浪无明确商用协议（见 `docs/data-source-license.md`） | 与现有 sina quote/kline 同级使用，商用前自行评估 |
| 🟠 现货 vs 期货口径 | 期货连续 ≠ 云铝实际售价/采购价 | 输出标注"期货连续合约"；L3 二期接入现货 |
| 🟠 时点差 1 天 | 实时快照 11-21，历史收盘 11-20 | 分位计算用同一历史序列末值，避免跨源混算 |
| 🟡 氧化铝历史仅 830 条 | 2023-06 上市，近 250 日够用，但更长周期分位不可得 | 明确标注"近 1 年分位"，不伪装为全历史分位 |

---

## 九、对上一轮结论的影响（重要）

实测价差分位 **6.4%（近 1 年低位）**，意味着：

1. 上一轮报告"铝价高位 + 氧化铝低位剪刀差"的假设**需要修正**——铝价本身也在低位（4.4%）
2. 云铝 ROE 31.33% 的"周期顶部特征"判断**需要复核**——从价差看更接近周期底部区域
3. 这可能解释为何价值专家（林奇/价值锚）给出高分：**他们可能是对的**，而纯 ROE 顶部判断过于机械

**建议**：P0 完成后立即重跑云铝分析，用价差分位重新校准周期定位，并回看宝丰能源的化工品价差（聚乙烯/聚丙烯已有 `fetch_polyethylene`/`fetch_polypropylene`，同样未接入 `fetch_all()`）。

---

## 十、实施记录（2026-11-22）

### 已改动文件

| 文件 | 改动 |
| --- | --- |
| `scripts/macro_indicators.py` | 新增 `_sina_futures_realtime` / `_sina_futures_history` / `fetch_commodity_sina` / `fetch_aluminum_sina` / `fetch_alumina` / `fetch_aluminum_alumina_spread`；接入 `fetch_all()` macro 段与 CLI；新增价差 fixture 短路与回写 |
| `scripts/market_anchor.py` | 宏观桥文本报告透出沪铝/氧化铝/冶炼价差及近 1 年分位；fixture 字段清单同步 |
| `scripts/data/macro_snapshot.json` | 回写实测值：铝 21585（分位 3.2）、氧化铝 2609（分位 11.2）、价差 16575.72（分位 6.4） |
| `tests/unit/test_macro_sina_futures.py` | 新增 47 项单元测试（实时解析 / nf_ 前缀防坑 / 历史 JSONP / 三段式 / 价差公式 / fetch_all 契约） |
| `tests/unit/test_macro_sina_fallback.py`、`test_macro_extra_sources.py` | 隔离列表加入 3 个新 fetcher，避免测试联网 |
| `docs/data-source-license.md` | 补充新浪期货合约数据源条目 |

### 验证结果

- **单元测试**：新增 47 项全绿；全量 `tests/unit/` **2706 passed**（99.2s）
- **实拉验证**：`fetch_all()` 输出 `aluminum_cny_t=21585.0`、`alumina_cny_t=2609.0`、`al_alumina_spread_cny_t=16575.72`、分位 `3.2/11.2/6.4`；`degraded_fields` 不再含铝相关字段
- **文本报告**：`market_anchor.py sz000807` 宏观段显示「冶炼价差(AL-1.92×AO): ¥16575.72/吨 (近1年分位 6.4%)」
- **lint**：新增代码均用 `log_silent_fallback`；`--strict` 报的 2 处裸 except 位于 `scripts/dev/scheduled_task.py:203`、`verify_sector_names.py:245`，为既有问题，与本次改动无关

### P2/P3 实施记录（同日续做）

| 阶段 | 文件 | 改动 |
| --- | --- | --- |
| P2 | `scripts/strategies/factors/cyclical.py` | 新增 `_spread_dimension` / `_effective_cost_dimension`；电解铝成本维度优先用价差分位，缺失时回退单铝价；`_RAW_MATERIAL_FETCHERS` 增加 `al_alumina_spread` 映射 |
| P2 | `experts/scoring/sector_specialist.py` | ① 补「铝/铜」进周期关键词（此前云铝误落 default 阈值）；② 周期股基本面分按价差分位校准（低分位 +12 / 高分位 −18） |
| P2 | `scripts/dev/experts_cli.py` | `build_stock_data` 为铝/周期标的注入 `macro_features`（价差值 + 分位 + 来源） |
| P2 | `tests/unit/test_sector_specialist_cycle.py` | 新增 8 项测试（行业分类、价差校准方向、非周期/缺失数据不调整） |
| P2 | `tests/unit/test_cyclical_factor.py` | 新增 7 项价差维度测试；修正 1 项旧断言以适配价差优先逻辑 |
| P3 | `skills/stock/reports/full-template.md` | 3.4.2 周期股必渲染字段补充；新增 §3.4.5 电解铝冶炼价差表与判读规则 |
| P3 | `skills/stock/SKILL.md` | Step 0 增加周期股宏观桥说明，要求用价差分位而非单纯 ROE/PE 判断周期位置 |

**端到端验证（云铝股份 sz000807）**：

| 指标 | P0 前 | P2/P3 后 |
| --- | --- | --- |
| 行业专家评分 | 61.8（中性） | **71.0（强烈看多）**，基本面 70→85、估值 55→70 |
| 圆桌综合分 | 59.8 | 60.8 |
| 周期因子位置 | 依赖单铝价分位（不可靠） | **low（周期底部）**，评分 91.0 |
| 周期因子 detail | — | `冶炼价差=16575.72 分位6.4%(盈利谷底/周期底部)` |

这从数据上确认了上一轮的疑点：**纯 ROE 顶部判断过于机械，价差分位显示云铝处于周期底部区域**，价值专家的高分是有依据的。

### 已知限制

- 1 小时 TTL 内重跑会命中 `fixture` 短路，`_source_tag` 显示 `[fixture]`（表示新鲜缓存，非陈旧占位）；价差分位依赖首次联网时回写，断网后从 fixture 恢复
- 氧化铝历史仅 830 条（2023-06 上市），"近 1 年分位"够用，更长周期不可得

---

## 十一、验收清单

- [x] `fetch_all()` 输出含 `aluminum_cny_t` / `alumina_cny_t` / `al_alumina_spread_cny_t` 及各分位
- [x] 断网时全部降级为 `fixture(stale)`，`degraded_fields` 正确标注，不阻塞主流程
- [x] `market_anchor.py sz000807 -j` 宏观桥显示价差与分位（JSON + 文本）
- [x] 云铝报告周期章节引用具体分位值（如"价差分位 6.4%"）—— 模板 §3.4.5 + SKILL Step 0 已固化；实际报告需在下次 `/stock` 调用时渲染
- [x] 单元测试全绿，新增代码无裸 except（既有 lint 问题除外）
- [x] `docs/data-source-license.md` 补充新浪期货合约数据源条目
