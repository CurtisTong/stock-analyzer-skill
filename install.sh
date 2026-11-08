#!/usr/bin/env bash
# 将 stock-analyzer-skill 包的 skills 同步到 Claude Code 和 Codex
#
# Claude Code 扫描: ~/.claude/skills/ (全局) 和 .claude/skills/ (项目级)
# Codex 扫描: ~/.codex/skills/ (全局) 和 .codex/skills/ (项目级)
#
# 技能源目录: skills/ (最新版本)

set -e

PKG_ROOT="$(cd "$(dirname "$0")" && pwd)"

# 技能源目录 (最新版本)
SRC_SKILLS="$PKG_ROOT/skills"

# Claude 全局目录
CLAUDE_GLOBAL="$HOME/.claude/skills"

# Codex 全局目录
CODEX_GLOBAL="$HOME/.codex/skills"

# 项目级目录
CLAUDE_LOCAL="$PKG_ROOT/.claude/skills"
CODEX_LOCAL="$PKG_ROOT/.codex/skills"

# 12 个 skill（v1.17.0 移除 monitor，v1.20.0 起稳定）
SKILLS=(stock stock-technical market sector portfolio portfolio-web portfolio-natural screener backtest research learn stock-help)

echo "==> [1/6] 创建项目级 .claude/skills/ 链接 (Claude 项目级技能)"
mkdir -p "$CLAUDE_LOCAL"
for s in "${SKILLS[@]}"; do
  SRC="$SRC_SKILLS/$s"
  DST="$CLAUDE_LOCAL/$s"
  if [ -d "$SRC" ]; then
    rm -f "$DST"
    ln -s "../../skills/$s" "$DST"
    echo "  ✓ $s -> skills/$s"
  fi
done

echo
echo "==> [2/6] 创建项目级 .codex/skills/ 链接 (Codex 项目级技能)"
mkdir -p "$CODEX_LOCAL"
for s in "${SKILLS[@]}"; do
  SRC="$SRC_SKILLS/$s"
  DST="$CODEX_LOCAL/$s"
  if [ -d "$SRC" ]; then
    rm -f "$DST"
    ln -s "../../skills/$s" "$DST"
    echo "  ✓ $s -> skills/$s"
  fi
done

echo
echo "==> [3/6] 校验项目级链接完整性（12 个有效链接、无悬空）"
check_links() {
  local dir="$1"
  local missing=0 dangling=0
  for s in "${SKILLS[@]}"; do
    if [ ! -L "$dir/$s" ]; then
      echo "  ⚠ 缺失链接: $dir/$s"
      missing=$((missing + 1))
    elif [ ! -e "$dir/$s" ]; then
      echo "  ⚠ 悬空链接: $dir/$s（目标不存在）"
      dangling=$((dangling + 1))
    fi
  done
  # 清理目录中的残留链接（旧 skill 如 monitor 移除后留下的悬空项）
  for entry in "$dir"/*; do
    [ -L "$entry" ] || continue
    base=$(basename "$entry")
    case " ${SKILLS[*]} " in
      *" $base "*) ;;
      *) echo "  🧹 清理残留链接: $entry"
         rm -f "$entry" ;;
    esac
  done
  if [ "$missing" -eq 0 ] && [ "$dangling" -eq 0 ]; then
    echo "  ✓ $dir: ${#SKILLS[@]} 个链接全部有效"
  else
    echo "  ⚠ $dir: 缺失 $missing / 悬空 $dangling —— 请重跑 install.sh 或检查 skills/ 源目录"
  fi
}
check_links "$CLAUDE_LOCAL"
check_links "$CODEX_LOCAL"

echo
echo "==> [4/6] 同步到 Claude 全局 skills: $CLAUDE_GLOBAL"
mkdir -p "$CLAUDE_GLOBAL"
for s in "${SKILLS[@]}"; do
  SRC="$SRC_SKILLS/$s"
  DST="$CLAUDE_GLOBAL/$s"
  if [ -d "$SRC" ]; then
    rm -rf "$DST"
    ln -s "$SRC" "$DST"
    echo "  ✓ linked $s"
  fi
done

echo
echo "==> [5/6] 同步到 Codex 全局 skills: $CODEX_GLOBAL"
mkdir -p "$CODEX_GLOBAL"
for s in "${SKILLS[@]}"; do
  SRC="$SRC_SKILLS/$s"
  DST="$CODEX_GLOBAL/$s"
  if [ -d "$SRC" ]; then
    rm -rf "$DST"
    ln -s "$SRC" "$DST"
    echo "  ✓ linked $s"
  fi
done

echo
echo "==> [6/6] 初始化股票池"
INIT_SCRIPT="$PKG_ROOT/scripts/init_pool.py"
if command -v python3 &>/dev/null; then
  # PyYAML 是脚本硬依赖（scripts/config/loader.py 顶层 import）。
  # macOS 系统自带 python3 通常没有 PyYAML——缺失时给出安装指引，
  # 而不是让 init_pool.py 裸报 ImportError 且 set -e 中断整个安装
  # （此前全新机器 100% 卡在这一步，连"安装完成"都打印不出来）。
  if python3 -c "import yaml" 2>/dev/null; then
    python3 "$INIT_SCRIPT"
  else
    echo "  ⚠ Python3 缺少 PyYAML，跳过股票池初始化（其余安装不受影响）"
    echo "    └ 安装命令: python3 -m pip install PyYAML"
    echo "    └ 装好后重跑: python3 $INIT_SCRIPT"
  fi
else
  echo "  ⚠ Python3 未安装，跳过初始化"
fi

echo
echo "✓ 安装完成！"
echo ""
echo "技能列表:"
for s in "${SKILLS[@]}"; do
  echo "  /$s"
done
echo ""
echo "重新启动 Claude Code 或 Codex 即可使用这些技能。"
echo ""
echo "🚀 3 步快速上手："
echo ""
echo "  1️⃣  持仓体检:  /portfolio health         # 每天 10 分钟，先看有没有事"
echo "  2️⃣  盘前复盘:  /market quick             # 市场情绪 + 板块热度"
echo "  3️⃣  单股研究:  /stock sh600519 quick     # 单屏研判，约 1 分钟"
echo ""
echo "📚 完整文档: /stock-help"
