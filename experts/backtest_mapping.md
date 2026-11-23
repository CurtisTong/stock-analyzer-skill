# 回测策略 × 专家映射

> 版本：v1.0.0（2026-06-16）
> 来源：60 天**样本内**回测数据 + 专家圆桌讨论

> ⚠️ **证据等级声明（务必先读）**：下表"回测表现"是 2026-06-16 的**样本内历史回测**，
> 不是外样本验证，也不构成收益承诺。当前 6 个策略在 `data/strategy_oos_validation.json`
> 中全部为 `in_sample`，已有外样本结果均为负（balanced -6.67% / -18.32%，
> ma_volume_momentum -6.38% / -16.06%）。引用这些数字必须带 ⚠️ 样本内披露，
> 完整规则见 [docs/strategy-validation.md](../docs/strategy-validation.md)。

## 映射关系

回测策略与专家体系的对应关系。这是**结构性映射**（谁关注什么维度），不是"回测占优 → 跟着买"的信号。主导/辅助专家一律写 active 集名称，legacy 底料在括号中注明（已合并，不独立参评）。

| 回测策略        | 主导专家（active）                  | 辅助专家          | 适用市场      | 样本内回测（2026-06-16，非 OOS）        |
| --------------- | ----------------------------------- | ----------------- | ------------- | --------------------------------------- |
| defensive       | value_institution（巴菲特/段永平底料） | risk_manager      | 防御型/熊市   | +12.61%, 夏普 0.93, 胜率 80% ⚠️ 样本内  |
| balanced        | lynch + value_institution           | sector_specialist | 震荡          | +1.88%, 夏普 -1.74, 胜率 40% ⚠️ 样本内  |
| quality_value   | value_institution（含 institution 底料） | lynch         | 震荡/牛市初期 | -5.05%, 夏普 -1.94, 胜率 40% ⚠️ 样本内  |
| growth_momentum | lynch + soros                       | topic_leader      | 牛市          | -9.46%, 夏普 -3.02, 胜率 20% ⚠️ 样本内  |
| turning_point   | soros + emotion_tech                | topic_leader      | 冰点→回暖     | -2.83%, 夏普 -2.54, 胜率 20% ⚠️ 样本内  |
| ma_volume_momentum | momentum_trader + topic_leader   | emotion_tech      | 量价共振      | ⚠️ +6.39% / 胜率 71.4%（5 只样本内拟合，外样本双池全负） |

## 使用规则

1. **回测→市场状态映射**：当 `--all` 回测显示某策略夏普 > 0 且其余策略夏普 < 0 时，可**描述历史区间**曾处于该策略适配的状态；这是回顾性诊断，不是对未来行情的预测，也不构成调仓信号
2. **专家权重倾斜**：主导专家评分 ×1.15，辅助专家评分 ×1.05，其余专家不变
   > ⚠️ **当前未实现**（v1.26.0 核实）：全仓无 ×1.15/×1.05 的实现代码。
   > 目前实际生效的机制是**分组校准因子**——`compute_group_calibration` 按长线/短线
   > 组的历史准确率调整信心指数（±10 分），而非按主导/辅助身份倾斜评分。
   > 如需实现本条，应在 `vote_engine.aggregate_votes` 的分组均值计算处引入。
   > 参见 `experts/decide.md §六.3`（校准因子公式）与 `experts/calibration.py`。
3. **切换信号**：当新一轮回测显示不同策略占优时，更新映射关系和校准数据——但只有在 `validation_status == oos_verified` 时才允许把胜率/收益写进对外材料（当前无策略达标，见 [docs/strategy-validation.md](../docs/strategy-validation.md)）

## 历史记录

### 2026-06-16（防御型市场）

- 回测周期：60 天，5 轮，top 5
- 股票池：107 只
- 关键发现（⚠️ 样本内）：防守低波独赢，成长动量大幅亏损，当时市场处于结构性分化——这是历史区间的回顾结论，不外推
- 操作：初始化 `data/expert_calibration.json`，防御型专家校准率 80%（历史校准基线，非未来胜率保证）
