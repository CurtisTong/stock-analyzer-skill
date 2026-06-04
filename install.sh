#!/usr/bin/env bash
# 将 stock-analyzer-skill 包的 6 个 skill 注册到 ~/.claude/skills/（扁平结构）
# Claude Code 的 slash command 解析器只扫描 ~/.claude/skills/*/SKILL.md 一层，
# 所以 symlink 必须直接在 ~/.claude/skills/ 下，不能嵌套命名空间。

set -e

PKG_ROOT="$(cd "$(dirname "$0")" && pwd)"
GLOBAL_SKILLS="$HOME/.claude/skills"
LOCAL_SKILLS="$PKG_ROOT/.claude/skills"
CODEX_SKILLS="$PKG_ROOT/.agents/skills"

SKILLS=(stock market sector portfolio financial-analyst investment-researcher)

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
echo "✓ 安装完成。重新启动 Claude Code 即可识别 6 个 slash command。"
