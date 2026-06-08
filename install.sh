#!/usr/bin/env bash
# 将 stock-analyzer-skill 包的 8 个 skill 注册到 ~/.claude/skills/（扁平结构）
# Claude Code 的 slash command 解析器只扫描 ~/.claude/skills/*/SKILL.md 一层，
# 所以 symlink 必须直接在 ~/.claude/skills/ 下，不能嵌套命名空间。

set -e

PKG_ROOT="$(cd "$(dirname "$0")" && pwd)"
GLOBAL_SKILLS="$HOME/.claude/skills"
LOCAL_SKILLS="$PKG_ROOT/.claude/skills"
CODEX_SKILLS="$PKG_ROOT/.agents/skills"

SKILLS=(stock market sector portfolio screener financial-analyst investment-researcher technical)

echo "==> 注册 symlink 到 $GLOBAL_SKILLS/"
for s in "${SKILLS[@]}"; do
  SRC="$LOCAL_SKILLS/$s"
  CODEX_SRC="$CODEX_SKILLS/$s"
  DST="$GLOBAL_SKILLS/$s"
  if [ ! -d "$SRC" ]; then
    echo "  ✗ 源目录缺失: $SRC"
    exit 1
  fi
  if [ ! -d "$CODEX_SRC" ]; then
    echo "  ✗ Codex 源目录缺失: $CODEX_SRC"
    exit 1
  fi
  if ! cmp -s "$SRC/SKILL.md" "$CODEX_SRC/SKILL.md"; then
    echo "  ✗ .claude 与 .agents 的 $s/SKILL.md 不一致"
    exit 1
  fi
  rm -f "$DST"
  ln -sf "$SRC" "$DST"
  echo "  ✓ $s -> $SRC"
done

echo
echo "==> 清理旧的命名空间目录（如有）"
if [ -d "$GLOBAL_SKILLS/stock-analyzer" ]; then
  if [ -z "$(ls -A "$GLOBAL_SKILLS/stock-analyzer" 2>/dev/null)" ]; then
    rmdir "$GLOBAL_SKILLS/stock-analyzer"
    echo "  ✓ 已删除空目录 stock-analyzer/"
  else
    echo "  ⚠ stock-analyzer/ 非空，请手动检查"
  fi
fi

echo
echo "==> 全局 skill 列表："
for s in "${SKILLS[@]}"; do
  DST="$GLOBAL_SKILLS/$s"
  if [ -L "$DST" ]; then
    echo "  ✓ $s -> $(readlink "$DST")"
  fi
done
echo
echo "==> 初始化股票池"
INIT_SCRIPT="$PKG_ROOT/scripts/init_pool.py"
if command -v python3 &>/dev/null; then
  python3 "$INIT_SCRIPT"
else
  echo "  ⚠ Python3 未安装，跳过初始化"
  echo "  稍后可手动运行: python3 $INIT_SCRIPT"
fi

echo
echo "✓ 安装完成。重新启动 Claude Code 即可识别 9 个 slash command（含 /init）。"
