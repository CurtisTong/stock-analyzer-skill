# 贡献指南

本项目所有协作流程（提交、分支、Tag）须遵守本文规范。规范仅约束**协作行为**，不限制代码风格与功能设计。

> 一句话原则：**一次提交只做一件事，标题一句话说清，必要时正文给理由。**

---

## 1. 提交信息规范（Commit Message）

采用 [Conventional Commits](https://www.conventionalcommits.org/) 1.0.0 的结构，但**标题与正文均使用中文**。结构如下：

```
<type>(<scope>): <中文标题>

<中文正文：说明"为什么"而不是"做了什么">

<可选脚注>
```

### 1.1 标题行（必须）

- **type**：必须小写英文，取自下表。
- **scope**：可选，表示影响范围，建议小写英文或简写。本项目常用值：
  - `*` 或省略：跨多个模块的通用变更（与项目历史风格一致）
  - `stock` / `market` / `sector` / `portfolio` / `screener` / `monitor` / `backtest` / `research` / `technical`：对应 skill（`financial-analyst` 与 `investment-researcher` 已合并入 `research`）
  - `experts`：专家人设（experts/\*.md 与 scoring/）
  - `scripts`：底层 Python 工具
  - `data`：示例数据、配置
  - `docs`：文档（README、方法论、CHANGELOG）
  - `ci` / `deps`：工作流、依赖
- **中文标题**：
  - 不加句号、不加末尾标点
  - 长度 ≤ 50 个字符（不含 type 与 scope）
  - 用动词开头（"新增"、"修复"、"重构"、"调整"、"移除"、"升级"……）
  - 避免空泛词（"优化"、"完善"、"update"）

### 1.2 常用 type

| type       | 含义                               | 是否更新 CHANGELOG |
| ---------- | ---------------------------------- | ------------------ |
| `feat`     | 新增功能                           | 是                 |
| `fix`      | 修复 Bug                           | 是                 |
| `docs`     | 仅文档变更（注释、README、方法论） | 否                 |
| `style`    | 不影响逻辑的格式调整（空格、缩进） | 否                 |
| `refactor` | 既不修 Bug 也不加功能的代码重构    | 否                 |
| `perf`     | 性能优化                           | 是                 |
| `test`     | 新增/修改测试                      | 否                 |
| `build`    | 构建系统、依赖、脚本目录调整       | 否                 |
| `ci`       | CI 配置变更                        | 否                 |
| `chore`    | 杂项（如 .gitignore、目录调整）    | 否                 |
| `revert`   | 回滚某次提交                       | 是                 |

### 1.3 正文（强烈建议）

- 与标题之间空一行。
- 回答"**为什么**这样改"：解释动机、取舍、限制、副作用。
- 多段落用空行分隔；每行建议 ≤ 72 个字符。
- 若有非显而易见的设计权衡（"为什么用 A 而不用 B"），必须写出来。

### 1.4 脚注（可选）

格式 `Token: 值`，常用：

- `Refs: #123` —— 关联 Issue / PR
- `Closes: #123` —— 关闭 Issue
- `BREAKING CHANGE: <说明>` —— 破坏性变更，必须单独成段

### 1.5 示例

#### ✅ 好的提交

```
feat(stock): 新增 15 人专家圆桌多空辩论模式

原五层框架只能产出单边结论，长线持有者无法验证
持仓股是否被市场主流逻辑证伪。新增 debate 模式调用
4 名看多 + 4 名看空专家独立打分，最终按加权一致性
输出结论，便于人工复核。

Refs: #42
```

```
fix(quote): 修复腾讯接口字段缺失导致 0 报价

请求返回中"昨收"字段为空时旧代码抛 KeyError。改为
容错取实时价作为兜底，并在日志中标记降级。

BREAKING CHANGE: 当 data['last_close'] 为空时，
返回的 change_pct 字段不再抛异常，但会标注为"估算"。
```

```
docs(*): 在 README 中补充 install.sh 的使用说明
```

#### ❌ 不合格的提交

```
fix: 改了点东西
```

→ 没说清改了什么、为什么改。

```
feat(stock): 新增功能、优化体验、完善细节
```

→ 一句话塞了三件事；"优化"、"完善"是空泛词。

```
Update README
```

→ 不是 Conventional 格式；中文环境下标题未使用中文。

---

## 2. 分支命名规范

所有非个人分支须遵循 `<type>/<短描述>` 格式，**全部使用小写英文 + 连字符**，避免中文路径在不同工具下出现转义问题。

| 用途     | 分支模式              | 示例                        |
| -------- | --------------------- | --------------------------- |
| 新功能   | `feat/<短描述>`       | `feat/stock-debate-mode`    |
| 修复     | `fix/<短描述>`        | `fix/quote-keyerror`        |
| 紧急热修 | `hotfix/<短描述>`     | `hotfix/install-permission` |
| 重构     | `refactor/<短描述>`   | `refactor/finance-cache`    |
| 文档     | `docs/<短描述>`       | `docs/methodology-update`   |
| 个人探索 | `exp/<作者>/<短描述>` | `exp/curtis/try-new-render` |
| 长期集成 | `release/<版本号>`    | `release/v1.2.0`            |

- 主干分支固定为 `main`，受保护：仅允许 PR 合入，禁止直推。
- 短描述使用 2~4 个英文单词，必要时加版本号或日期。
- 分支完成后删除（`git push origin --delete <branch>`），保持仓库整洁。

---

## 3. Tag 与版本号

- 触发正式发布时打 Tag，命名 `v<MAJOR>.<MINOR>.<PATCH>`，遵循 [SemVer 2.0](https://semver.org/)。
- Tag 须用 `git tag -s v1.2.0 -m "..."` 签名（GPG 可用时）。
- 预发布版本加后缀：`v1.2.0-rc.1`、`v1.2.0-beta.2`。
- Tag 一经推送不允许修改或删除，需变更则打新 Tag。

---

## 4. 提交粒度与频率

- **一个提交 = 一个原子变更**。不要把功能开发与顺手重构混在一起。
- WIP 状态请留在本地或自己的 `exp/` 分支，不要污染主干。
- 推送前自查：
  - `git diff --staged` 是否包含无关文件
  - 是否引入了调试代码、注释掉的死代码
  - 是否需要拆成多个提交
- 提 PR 前本地 rebase 到 `main`，避免历史分叉。

---

## 5. 工具辅助

### 5.1 提交模板

`git config commit.template .gitmessage` 后，新建 `.gitmessage`：

```
<type>(<scope>): <中文标题>

# 正文：解释"为什么"而不是"做了什么"
# 多段落用空行分隔
#
# 脚注（可选）：
# Refs: #123
# BREAKING CHANGE: 说明
```

### 5.2 commitlint（可选）

若团队启用 CI 检查，可在 `package.json` 旁维护一份 `commitlint.config.js`：

```js
module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "subject-max-length": [2, "always", 50],
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
      ],
    ],
  },
};
```

### 5.3 推荐的本地工作流

> **首次 clone 后必须执行一次**：`pip install pre-commit && pre-commit install`
> 安装 git hook（black 格式化 + ruff 静态检查 + 快速核心测试），后续每次 `git commit` 自动触发。
> 未安装时本地提交无门禁，只能靠 CI 兜底。

```bash
# 0. 首次 clone 后：安装 pre-commit hooks（仅一次）
pip install pre-commit && pre-commit install

# 1. 拉取最新主干
git checkout main && git pull --rebase

# 2. 新建功能分支
git checkout -b feat/<short-desc>

# 3. 多次小提交（写好中文 commit message）
git add -p
git commit              # 弹出模板，照填即可

# 4. 推送分支并开 PR
git push -u origin feat/<short-desc>

# 5. PR 通过并合并后，删除远端与本地分支
git push origin --delete feat/<short-desc>
git branch -d feat/<short-desc>
```

---

## 6. 例外与豁免

以下场景允许偏离规范，请在 PR 描述中明确说明：

- **首次提交（init）**：`first commit`、`chore: 初始化项目骨架` 等历史性 commit。
- **自动化脚本产生的提交**（如 `release-please`、Dependabot）：保持工具默认输出即可。
- **临时回滚**：`revert:` 提交可仅含 commit 引用，正文写自动生成说明。

---

## 7. 自检清单（提交前过一遍）

- [ ] type 在合法枚举内，小写
- [ ] 标题中文，≤ 50 字，无句号
- [ ] 正文解释了"为什么"，不只是"做了什么"
- [ ] 破坏性变更用 `BREAKING CHANGE:` 标注
- [ ] 一个提交只改一件事；无关文件已 `git reset`
- [ ] 分支命名符合 `<type>/<短描述>` 规范
- [ ] 已 rebase 到最新 `main`，历史线性

---

## 8. Claude Code Skill 开发规范

本项目的 skill 位于 `.claude/skills/<name>/SKILL.md`，供 Claude Code 使用。以下是开发规范：

### 8.1 路径规范

**核心原则**：Claude Code 运行 Bash 时，工作目录**自动是项目根目录**，不是 skill 文件所在目录。

```bash
# ❌ 错误：使用相对路径 cd ../../..
cd ../../..
python3 scripts/quote.py sh600989

# ✅ 正确：直接运行脚本
python3 scripts/quote.py sh600989
python3 scripts/finance.py SH600989
python3 scripts/kline.py sh600989 240 30
```

如果 SKILL.md 中需要说明项目根目录，使用通用描述而非硬编码路径：

```markdown
# ❌ 错误：硬编码用户路径

项目根目录为 `/Users/curtis/Documents/curtis/stock-analyzer-skill`

# ✅ 正确：通用描述

Claude Code 运行时工作目录即为项目根目录
```

### 8.2 避免循环导入

Python 模块级导入顺序很重要。以下模式会导致循环导入错误：

```
common.py (line 32)  →  from data.cache import ...
  → 触发加载 data/__init__.py (line 21)
    → from common import to_float, to_int  ← 此时 common.py 还没执行完！
      → ImportError
```

**解决方案**：使用延迟导入（在函数内部导入）：

```python
# ❌ 错误：模块顶层导入
from common import to_float, to_int

# ✅ 正确：延迟导入
def _get_common_helpers():
    """延迟导入 common，避免循环导入。"""
    from common import to_float, to_int
    return to_float, to_int

def _dict_to_quote(d: dict) -> Quote:
    to_float, to_int = _get_common_helpers()
    return Quote(price=to_float(d.get("price")), ...)
```

### 8.3 权限配置

项目级权限配置放在 `.claude/settings.json`（注意不是 `settings.local.json`）。

权限规则应使用通配符匹配脚本名，而非硬编码具体股票代码：

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 scripts/quote.py *)",
      "Bash(python3 scripts/finance.py *)",
      "Bash(python3 scripts/kline.py *)",
      "Bash(python3 scripts/technical.py *)",
      "Bash(python3 scripts/screener.py *)"
    ]
  }
}
```

### 8.4 测试验证

修改 SKILL.md 或权限配置后，必须验证：

```bash
# 1. 脚本直接运行正常
python3 scripts/quote.py sh600989

# 2. 测试套件通过
python3 -m pytest tests/ -x -q
```

### 8.5 本地调试

在 Claude Code 中调试 skill 时：

1. 先在终端验证脚本可以正常运行
2. 检查 Claude Code 的工作目录：`pwd`
3. 查看权限是否匹配：权限规则需要精确匹配命令格式

### 8.6 SKILL.md frontmatter 规范

每个 SKILL.md **必须**含以下 frontmatter 字段（CI 强制校验）：

```yaml
---
name: <skill-name> # 必填，与目录名一致
description: <能力 + 触发场景> # 必填，≤ 250 字符
version: 1.3.x # 与 package.json 对齐
model: haiku | sonnet | opus # 按复杂度分配
allowed-tools: Bash(python3 scripts/*) Read(<paths>)
disable-model-invocation: true # 仅命令式 skill
---
```

**description 写作要求**：

- 第三人称（"用于 / 提供 / 包含"），不写"我"
- 描述**能力 + 触发场景**，不硬编码命令字面量（`/X 时触发`）
- cross-reference 允许（"参考 `/screener`"），但禁止"输入 `/X` 时触发"这种触发句
- 长度 ≤ 250 字符（社区最佳实践 80-150）

**model 分配参考**：

- `opus`：深度分析（stock full / financial-analyst / investment-researcher）
- `sonnet`：实时分析（market / sector / portfolio / screener / technical / monitor）
- `haiku`：命令式（backtest / stock-init / help）

**allowed-tools 模式**：

- 优先用通配符 `Bash(python3 scripts/*)` 而非逐个列举
- `Read(<path>)` 路径必须用绝对路径
- 命令式 skill 可省略（除脚本白名单外）

### 8.7 共享 references 规范

跨 skill 复用的约定/数据集中放到 `skills/_shared/references/`：

| 文件                | 内容                                     |
| ------------------- | ---------------------------------------- |
| `code-prefix.md`    | 股票代码 `sh`/`sz`/`SH`/`SZ` 大小写规则  |
| `script-catalog.md` | 脚本目录与参数（quote/finance/kline 等） |
| `five-layer.md`     | 五层分析框架定义与评级阈值               |

**新增共享 reference** 时：

1. 在 `_shared/references/` 下新建 `<topic>.md`
2. 在需要引用的 SKILL.md 中加 1 行引用（不要全文复制）
3. `cross-reference 一致性测试` 会自动校验脚本/数据文件存在性

skill 内部的子文件（如 `skills/stock/reports/full-template.md`）按需放，不入共享目录。

### 8.8 元数据与一致性测试

修改 SKILL.md 后**必须**跑：

```bash
# 172 个元数据 + 一致性测试
python3 -m pytest tests/test_skill_metadata.py tests/test_skill_consistency.py -q

# install.sh 集成测试
bash tests/integration/test_install.sh
```

测试覆盖：

- frontmatter 必填字段、name 匹配目录、description 长度与触发句
- model 复杂度匹配、章节别名兼容
- SKILL.md 引用的 `scripts/*.py` / `data/*.json` 真实存在（含运行时生成白名单）
- install.sh 13 个 skill 数组完整性、软链化、清理调用

新增 skill 时，把对应名称加入：

- `tests/test_skill_metadata.py::EXPECTED_SKILLS`
- `install.sh::SKILLS` 数组
- `tests/test_skill_consistency.py::DESCRIPTION_KEYWORDS`（核心能力词）

CI 会在 PR 中自动跑这些测试，**全部通过**才允许合并。
