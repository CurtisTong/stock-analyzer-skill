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

SKILLS=(stock stock-technical market sector portfolio portfolio-web portfolio-natural screener monitor backtest research learn stock-help)

echo "==> [1/5] 创建项目级 .claude/skills/ 链接 (Claude 项目级技能)"
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
echo "==> [2/5] 创建项目级 .codex/skills/ 链接 (Codex 项目级技能)"
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
echo "==> [3/5] 同步到 Claude 全局 skills: $CLAUDE_GLOBAL"
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
echo "==> [4/5] 同步到 Codex 全局 skills: $CODEX_GLOBAL"
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
echo "==> [5/5] 初始化股票池"
INIT_SCRIPT="$PKG_ROOT/scripts/init_pool.py"
if command -v python3 &>/dev/null; then
  python3 "$INIT_SCRIPT"
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
echo "🚀 新手起步：直接输入 /help 或 /stock 贵州茅台 quick"
