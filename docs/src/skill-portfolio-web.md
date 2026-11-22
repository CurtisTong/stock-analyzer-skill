# /portfolio-web

**Web 录入服务（HTTP API :8765）。** 嫌 CLI 麻烦时用浏览器或手机录持仓。

## 直接复制

```bash
python3 scripts/portfolio_web.py --port 8765
```

浏览器打开 http://127.0.0.1:8765/ （脚本默认会尝试自动打开浏览器）。

在 Claude Code / DSH 里也可以直接输入 `/portfolio web --port 8765`。

## 什么时候用

| 你的问题 | 做法 |
| --- | --- |
| 手机 / 浏览器录持仓 | 启动上面的服务后访问 `127.0.0.1:8765` |
| 不想接收推送通知 | 关闭通知通道，或直接用 CLI 录入 |

服务只监听本机，接口带 token 鉴权；数据落在项目内，与 CLI 持仓共用同一份文件。

> ⚠️ 持仓录入与调仓建议**仅供参考，不构成投资建议**。

**更多**：[skills/portfolio-web/SKILL.md](../../skills/portfolio-web/SKILL.md) · [使用者指南](../user-guide.md)
