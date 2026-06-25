"""
HTML 模板模块 v2.0。

包含内联 HTML 模板 — 全量改造：
- 中文化所有界面元素
- 实时行情（现价/涨跌/市值/浮盈）
- 持仓行内操作按钮
- 交易日志面板
- 加载骨架屏 + 空状态引导
- Token 安全加固（sessionStorage）
- 键盘快捷键
- 动态 Webhook cURL
- 虚拟持仓模式标识
"""

INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio · Claude Code</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --elevated: #1c2333;
    --border: #30363d; --border-focus: #e07a5f;
    --text: #e6edf3; --text-secondary: #8b949e; --text-muted: #6e7681;
    --accent: #e07a5f; --accent-hover: #c96b52; --accent-glow: rgba(224,122,95,.15);
    --success: #3fb950; --success-bg: rgba(63,185,80,.12);
    --error: #f85149; --error-bg: rgba(248,81,73,.12);
    --warning: #d29922; --warning-bg: rgba(210,153,34,.12);
    --mono: "SF Mono", "Fira Code", "JetBrains Mono", "Cascadia Code", monospace;
    --sans: -apple-system, "SF Pro Text", "PingFang SC", system-ui, sans-serif;
    --radius: 8px; --radius-sm: 6px;
  }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: var(--sans); background: var(--bg); color: var(--text);
         font-size: 14px; line-height: 1.6; padding: 20px; -webkit-font-smoothing: antialiased; }
  .container { max-width: 860px; margin: 0 auto; }

  /* Header */
  header { display: flex; align-items: center; justify-content: space-between;
           margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px;
              display: flex; align-items: center; gap: 10px; }
  header h1 .logo { color: var(--accent); font-size: 20px; }
  .badge { font-family: var(--mono); font-size: 11px; color: var(--text-muted);
           background: var(--elevated); border: 1px solid var(--border);
           padding: 2px 8px; border-radius: 999px; }
  .badge-mode { font-size: 11px; padding: 3px 10px; border-radius: 999px; font-weight: 600; }
  .badge-mode.real { background: var(--success-bg); color: var(--success); border: 1px solid rgba(63,185,80,.3); }
  .badge-mode.virtual { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(210,153,34,.3); }
  .btn-icon { background: none; border: 1px solid var(--border); color: var(--text-secondary);
              border-radius: var(--radius-sm); cursor: pointer; padding: 6px 12px;
              font-size: 13px; font-family: var(--sans); transition: all .15s;
              min-height: 34px; display: inline-flex; align-items: center; gap: 6px; }
  .btn-icon:hover { background: var(--elevated); color: var(--text); border-color: var(--text-muted); }

  /* Panels */
  .panel { background: var(--surface); border: 1px solid var(--border);
           border-radius: var(--radius); margin-bottom: 16px; overflow: hidden; }
  .panel-header { padding: 12px 16px; border-bottom: 1px solid var(--border);
                  display: flex; align-items: center; justify-content: space-between; }
  .panel-header h2 { font-size: 13px; font-weight: 600; color: var(--text-secondary);
                     text-transform: uppercase; letter-spacing: 0.5px; }
  .panel-body { padding: 0; overflow-x: auto; }

  /* Tables */
  table { width: 100%; border-collapse: collapse; font-size: 13px; font-family: var(--mono); }
  th { padding: 8px 14px; text-align: left; font-weight: 500; color: var(--text-muted);
       background: var(--elevated); font-size: 11px; text-transform: uppercase;
       letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  td { padding: 10px 14px; border-bottom: 1px solid rgba(48,54,61,.5); color: var(--text); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(224,122,95,.04); }
  .code-tag { font-family: var(--mono); font-size: 11px; color: var(--accent);
              background: var(--accent-glow); padding: 2px 7px; border-radius: 4px;
              margin-right: 4px; display: inline-block; }
  .empty { color: var(--text-muted); font-style: italic; padding: 20px 14px;
           text-align: center; font-size: 13px; }
  .empty-hint { color: var(--text-muted); font-size: 12px; margin-top: 6px; }
  .positive { color: var(--success); } .negative { color: var(--error); }
  .neutral { color: var(--text-muted); }

  /* Inline action buttons */
  .row-actions { display: flex; gap: 4px; }
  .btn-row { background: var(--elevated); border: 1px solid var(--border); color: var(--text-secondary);
             border-radius: 4px; cursor: pointer; padding: 2px 8px; font-size: 11px;
             font-family: var(--sans); transition: all .15s; }
  .btn-row:hover { color: var(--text); border-color: var(--text-muted); }
  .btn-row.danger:hover { color: var(--error); border-color: rgba(248,81,73,.4); }

  /* Forms */
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; padding: 16px; }
  .form-group { display: flex; flex-direction: column; gap: 4px; }
  .form-group.full { grid-column: span 2; }
  label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
  input, select {
    font-family: var(--mono); font-size: 13px; color: var(--text);
    background: var(--elevated); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 10px; width: 100%;
    transition: border-color .15s, box-shadow .15s;
  }
  input::placeholder { color: var(--text-muted); }
  input:focus, select:focus { outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow); }
  select { cursor: pointer; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 5l3 3 3-3' fill='none' stroke='%238b949e' stroke-width='1.5'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 10px center; padding-right: 28px; }
  input[type="date"]::-webkit-calendar-picker-indicator { filter: invert(.7); cursor: pointer; }
  .required { color: var(--error); margin-left: 2px; }
  .optional-hint { color: var(--text-muted); font-size: 11px; }

  /* Buttons */
  .btn-submit { width: 100%; padding: 10px 20px; font-family: var(--sans);
                font-size: 14px; font-weight: 500; color: #fff; background: var(--accent);
                border: 0; border-radius: var(--radius-sm); cursor: pointer;
                transition: background .15s, transform .1s; min-height: 40px; }
  .btn-submit:hover { background: var(--accent-hover); }
  .btn-submit:active { transform: scale(.98); }
  .btn-submit:disabled { background: var(--text-muted); cursor: not-allowed; transform: none; }
  .btn-copy { font-family: var(--mono); font-size: 11px; color: var(--text-secondary);
              background: var(--elevated); border: 1px solid var(--border);
              border-radius: var(--radius-sm); padding: 4px 10px; cursor: pointer;
              transition: all .15s; }
  .btn-copy:hover { color: var(--text); border-color: var(--text-muted); }

  /* Code block */
  pre { background: var(--bg); color: var(--text-secondary); padding: 14px 16px;
        font-family: var(--mono); font-size: 12px; line-height: 1.5;
        overflow-x: auto; border-top: 1px solid var(--border); }
  pre .kw { color: var(--accent); } pre .str { color: #a5d6ff; }

  /* Toast */
  .toast { position: fixed; top: calc(20px + env(safe-area-inset-top, 0px)); left: 50%; transform: translateX(-50%) translateY(-8px);
           z-index: 1000; max-width: 440px; padding: 10px 16px; border-radius: var(--radius-sm);
           font-size: 13px; font-family: var(--sans); border: 1px solid;
           opacity: 0; transition: opacity .25s, transform .25s; pointer-events: none; }
  .toast.visible { opacity: 1; pointer-events: auto; transform: translateX(-50%) translateY(0); }
  .toast.ok { background: var(--success-bg); border-color: rgba(63,185,80,.3); color: var(--success); }
  .toast.err { background: var(--error-bg); border-color: rgba(248,81,73,.3); color: var(--error); }

  /* Destructive */
  .destructive { border: 1px solid rgba(248,81,73,.3); background: var(--error-bg);
                 padding: 10px 14px; border-radius: var(--radius-sm);
                 font-size: 12px; color: var(--error); font-family: var(--sans); }

  /* Auth error overlay */
  .auth-error { position: fixed; inset: 0; background: var(--bg); z-index: 2000;
                display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 16px; }
  .auth-error h2 { font-size: 20px; color: var(--error); }
  .auth-error p { color: var(--text-secondary); font-size: 14px; }

  /* Skeleton loading */
  .skeleton { background: linear-gradient(90deg, var(--elevated) 25%, rgba(255,255,255,.05) 50%, var(--elevated) 75%);
              background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 4px; height: 16px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  /* Stats grid */
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; padding: 16px; }
  .stat-item { text-align: center; }
  .stat-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-value { font-size: 18px; font-weight: 600; font-family: var(--mono); margin-top: 2px; }

  /* Highlight row animation */
  @keyframes highlight { 0% { background: rgba(224,122,95,.15); } 100% { background: transparent; } }
  tr.highlight td { animation: highlight 1.5s ease-out; }

  /* Responsive */
  @media (max-width: 640px) {
    body { padding: 12px; }
    .container { max-width: 100%; }
    .form-grid { grid-template-columns: 1fr; padding: 12px; }
    .form-group.full { grid-column: 1; }
    input, select { padding: 10px 12px; font-size: 16px; }
    .btn-submit { padding: 12px 20px; font-size: 16px; min-height: 44px; }
    .btn-icon, .btn-copy { min-height: 44px; min-width: 44px; }
    header h1 { font-size: 16px; }
    /* 移动端表格卡片化 */
    table, thead, tbody, th, td, tr { display: block; }
    thead { display: none; }
    tr { border: 1px solid var(--border); border-radius: var(--radius-sm); margin-bottom: 8px; padding: 8px; }
    td { border: none; padding: 4px 8px; display: flex; justify-content: space-between; font-size: 13px; }
    td::before { content: attr(data-label); font-weight: 500; color: var(--text-muted); font-size: 12px; }
    .row-actions { justify-content: flex-end; padding-top: 8px; border-top: 1px solid var(--border); margin-top: 4px; }
  }
</style>
</head>
<body>

<!-- 认证失败遮罩 -->
<div id="auth-overlay" class="auth-error" style="display:none">
  <h2>🔐 认证失败</h2>
  <p>Token 无效或已过期，请重新打开服务</p>
  <code style="color:var(--text-muted)">python3 scripts/portfolio_web.py --open</code>
</div>

<div class="container">

  <header>
    <h1>
      <span class="logo">◆</span> Portfolio
      <span class="badge">v__VERSION__</span>
      <span id="mode-badge" class="badge-mode real" style="display:none"></span>
    </h1>
    <div style="display:flex;gap:8px;align-items:center">
      <button class="btn-icon" id="refresh" aria-label="刷新" title="Ctrl+R">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 8A6 6 0 1 1 8 2"/><path d="M8 2v4l3-2"/></svg>
        刷新
      </button>
    </div>
  </header>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <!-- 持仓 -->
  <div class="panel">
    <div class="panel-header">
      <h2>📊 持仓</h2>
      <span id="positions-count" class="badge">加载中…</span>
    </div>
    <div class="panel-body" id="positions" aria-live="polite">
      <div style="padding:16px"><div class="skeleton" style="width:100%;height:120px"></div></div>
    </div>
  </div>

  <!-- 操作表单（上移到持仓和自选之间） -->
  <div class="panel">
    <div class="panel-header"><h2>✏️ 操作</h2></div>
    <form id="entry" class="form-grid">
      <div class="form-group full">
        <label for="action">操作类型</label>
        <select id="action">
          <option value="add_position">买入 / 加仓</option>
          <option value="reduce_position">减仓</option>
          <option value="remove_position">清仓</option>
          <option value="update_position">编辑持仓</option>
          <option value="tag_position">追加标签</option>
          <option value="untag_position">删除标签</option>
          <option value="add_watch">加入自选</option>
          <option value="update_watch">编辑自选</option>
          <option value="remove_watch">删除自选</option>
        </select>
      </div>
      <div class="form-group">
        <label for="code">股票代码</label>
        <input id="code" list="codes" autocomplete="off" autocapitalize="off" autocorrect="off"
               placeholder="sh600989" required>
        <datalist id="codes">__DATALIST__</datalist>
      </div>
      <div class="form-group" data-show="add_position">
        <label for="name">名称 <span class="optional-hint">(可选)</span></label>
        <input id="name" placeholder="宝丰能源">
      </div>
      <div class="form-group" data-show="add_position update_position">
        <label for="cost">成本价 <span class="required" data-required="add_position">*</span></label>
        <input id="cost" type="number" step="0.001" placeholder="18.500">
      </div>
      <div class="form-group" data-show="add_position reduce_position update_position">
        <label for="quantity">数量 <span class="required" data-required="add_position reduce_position">*</span></label>
        <input id="quantity" type="number" step="1" placeholder="1000">
      </div>
      <div class="form-group" data-show="reduce_position">
        <label for="sell_price">卖出价 <span class="optional-hint">(可选，记录盈亏)</span></label>
        <input id="sell_price" type="number" step="0.001" placeholder="22.000">
      </div>
      <div class="form-group" data-show="add_position">
        <label for="buy_date">买入日期</label>
        <input id="buy_date" type="date">
      </div>
      <div class="form-group" data-show="add_position tag_position untag_position update_position">
        <label for="tags">标签 <span class="optional-hint" data-warn="update_position">⚠ 整体替换</span></label>
        <input id="tags" placeholder="长线, 能源">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="name_w">名称 <span class="optional-hint">(可选)</span></label>
        <input id="name_w" placeholder="华友钴业">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="target_buy">目标买入价</label>
        <input id="target_buy" type="number" step="0.01" placeholder="28.00">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="target_sell">目标卖出价</label>
        <input id="target_sell" type="number" step="0.01" placeholder="42.00">
      </div>
      <div class="form-group full" data-show="remove_position reduce_position" id="confirm-wrap" style="display:none">
        <div class="destructive">⚠ 确认执行此不可逆操作</div>
      </div>
      <div class="form-group full" style="display:flex;flex-direction:row;gap:8px">
        <button type="submit" class="btn-submit" id="submit-btn" style="flex:1">提交</button>
        <button type="button" class="btn-icon" id="clear-btn" style="min-width:80px">清空</button>
      </div>
    </form>
  </div>

  <!-- 自选 -->
  <div class="panel">
    <div class="panel-header">
      <h2>👁 自选</h2>
      <span id="watch-count" class="badge">—</span>
    </div>
    <div class="panel-body" id="watchlist" aria-live="polite">
      <div class="empty">暂无自选股</div>
    </div>
  </div>

  <!-- 策略监控 -->
  <div class="panel">
    <div class="panel-header">
      <h2>📡 策略监控</h2>
      <span class="badge" id="monitor-status">检查中…</span>
    </div>
    <div class="panel-body" id="monitor-alerts" aria-live="polite">
      <div class="empty">加载中…</div>
    </div>
  </div>

  <!-- 交易日志 -->
  <div class="panel">
    <div class="panel-header">
      <h2>📋 交易记录</h2>
      <span id="trades-count" class="badge">—</span>
    </div>
    <div id="trades-stats" class="stats-grid" style="display:none"></div>
    <div class="panel-body" id="trades-history" aria-live="polite">
      <div class="empty">暂无交易记录</div>
    </div>
  </div>

  <!-- Webhook -->
  <div class="panel">
    <div class="panel-header">
      <h2>🔗 Webhook</h2>
      <button class="btn-copy" id="copy" aria-label="复制 cURL">复制</button>
    </div>
    <pre id="curl"><span class="kw">curl</span> -X POST http://127.0.0.1:8765/api/positions \\
  -H <span class="str">'Content-Type: application/json'</span> \\
  -H <span class="str">'Authorization: Bearer <span id="curl-token">&lt;TOKEN&gt;</span></span>' \\
  -d <span class="str">'{"action":"add_position","code":"sh600989","cost":18.5,"quantity":1000}'</span></pre>
  </div>

  <!-- 快捷键提示 -->
  <div style="text-align:center;padding:12px;color:var(--text-muted);font-size:11px">
    <kbd style="background:var(--elevated);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-family:var(--mono)">Ctrl+Enter</kbd> 提交
    &nbsp;·&nbsp;
    <kbd style="background:var(--elevated);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-family:var(--mono)">Ctrl+R</kbd> 刷新
    &nbsp;·&nbsp;
    <kbd style="background:var(--elevated);border:1px solid var(--border);border-radius:3px;padding:1px 5px;font-family:var(--mono)">Esc</kbd> 清空表单
  </div>

</div>

<script>
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
let toastTimer;
let currentData = { positions: [], watchlist: [], virtual: false };

// ── Token 安全加固 ──
function getToken() {
  let t = sessionStorage.getItem("pw_token");
  if (t) return t;
  const u = new URLSearchParams(location.search).get("token");
  if (u) { sessionStorage.setItem("pw_token", u); history.replaceState(null, "", location.pathname); return u; }
  return "";
}
const TOKEN = getToken();
const AUTH = TOKEN ? {"Authorization": "Bearer " + TOKEN} : {};

if (!TOKEN) {
  $("#auth-overlay").style.display = "flex";
  document.querySelector(".container").style.display = "none";
}

// ── Toast ──
function showToast(msg, ok) {
  const t = $("#toast");
  t.className = "toast " + (ok ? "ok" : "err");
  t.textContent = msg;
  t.offsetHeight;
  t.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("visible"), ok ? 3000 : 6000);
}

// ── 错误信息友好映射 ──
const ERR_MAP = {
  "unauthorized": "认证失败，请重新打开服务",
  "missing_code": "请填写股票代码",
  "invalid_cost": "请输入有效的成本价",
  "invalid_quantity": "请输入有效的数量（大于0）",
  "position_not_found": "未找到该持仓，请检查代码",
  "missing_tags": "请填写至少一个标签",
  "no_update_fields": "请至少填写一个要修改的字段",
};
function friendlyError(err, detail) {
  return ERR_MAP[err] || detail || err || "操作失败";
}

// ── 操作结果摘要 ──
function buildSuccessMsg(action, data, body) {
  const code = body.code || "";
  switch (action) {
    case "add_position": {
      const d = data || {};
      return `✓ 已买入 ${code} ${d.name||""} ${d.quantity||0} 股 @ ¥${d.cost||0}`;
    }
    case "reduce_position": {
      const qty = body.quantity || 0;
      return data ? `✓ 已减仓 ${code} ${qty} 股，剩余 ${data.quantity} 股` : `✓ 已清仓 ${code}（减仓归零）`;
    }
    case "remove_position": return `✓ 已清仓 ${code}`;
    case "update_position": return `✓ 已更新 ${code}`;
    case "tag_position": return `✓ 已给 ${code} 追加标签`;
    case "untag_position": return `✓ 已移除 ${code} 标签`;
    case "add_watch": return `✓ 已加入自选 ${code} ${(data||{}).name||""}`;
    case "update_watch": return `✓ 已更新自选 ${code}`;
    case "remove_watch": return `✓ 已移除自选 ${code}`;
    default: return "✓ 操作成功";
  }
}

const WARN_MAP = {
  update_position_replaces_tags: "标签已整体替换（非合并）",
  position_removed: "持仓已全部卖出并清除",
};

// ── 表单同步 ──
function syncFields() {
  const a = $("#action").value;
  $$("[data-show]").forEach(el => {
    const vis = el.dataset.show.split(" ").includes(a);
    el.style.display = vis ? "" : "none";
    if (!vis) el.querySelectorAll("input,select").forEach(i => { if (i.id !== "code") i.value = ""; });
  });
  $$("[data-required]").forEach(el => {
    el.style.display = el.dataset.required.split(" ").includes(a) ? "" : "none";
  });
  $$("[data-warn]").forEach(el => {
    el.style.display = el.dataset.warn === a ? "" : "none";
  });
  const cw = $("#confirm-wrap");
  if (cw) cw.style.display = (a === "remove_position" || a === "reduce_position") ? "" : "none";
}

// ── 盈亏颜色 ──
function profitClass(v) { return v > 0 ? "positive" : v < 0 ? "negative" : "neutral"; }
function fmtPct(v) { return v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(2) + "%"; }
function fmtPrice(v) { return v == null ? "—" : v.toFixed(2); }
function fmtMoney(v) { return v == null ? "—" : "¥" + v.toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
function escapeHTML(s) { if (s == null) return ""; return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

// ── 加载持仓列表 ──
async function loadList() {
  try {
    const r = await fetch("/api/positions", {headers: AUTH});
    if (r.status === 401) { $("#auth-overlay").style.display = "flex"; document.querySelector(".container").style.display = "none"; return; }
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    currentData = j.data;
    renderPositions(j.data.positions);
    renderWatch(j.data.watchlist);
    // 虚拟持仓标识
    const mb = $("#mode-badge");
    if (j.data.virtual) { mb.textContent = "模拟盘"; mb.className = "badge-mode virtual"; mb.style.display = ""; }
    else { mb.textContent = "实盘"; mb.className = "badge-mode real"; mb.style.display = ""; }
  } catch (e) {
    showToast("加载失败: " + e.message, false);
  }
}

// ── 渲染持仓表 ──
function renderPositions(rows) {
  const el = $("#positions");
  $("#positions-count").textContent = rows.length + " 只";
  if (!rows.length) {
    el.innerHTML = '<div class="empty">暂无持仓<div class="empty-hint">在下方操作表单中选择「买入 / 加仓」添加第一笔持仓</div></div>';
    return;
  }
  let h = '<table><tr><th>代码</th><th>名称</th><th>现价</th><th>涨跌</th><th>成本</th><th>数量</th><th>市值</th><th>浮盈</th><th>标签</th><th></th></tr>';
  for (const p of rows) {
    const pc = profitClass(p.profit_pct);
    const cc = profitClass(p.change_pct);
    const ec = escapeHTML(p.code);
    const en = escapeHTML(p.name||"—");
    const tags = (p.tags||[]).map(t => '<span class="code-tag">'+escapeHTML(t)+'</span>').join("");
    h += '<tr data-code="'+ec+'">'
      + '<td data-label="代码"><span class="code-tag">'+ec+'</span></td>'
      + '<td data-label="名称">'+en+'</td>'
      + '<td data-label="现价" class="'+pc+'">'+fmtPrice(p.current_price)+'</td>'
      + '<td data-label="涨跌" class="'+cc+'">'+fmtPct(p.change_pct)+'</td>'
      + '<td data-label="成本">'+fmtPrice(p.cost)+'</td>'
      + '<td data-label="数量">'+(p.quantity||0)+'</td>'
      + '<td data-label="市值">'+fmtMoney(p.market_value)+'</td>'
      + '<td data-label="浮盈" class="'+pc+'">'+(p.profit_pct!=null?fmtPct(p.profit_pct):"—")+'<br><span style="font-size:11px">'+(p.profit_amount!=null?fmtMoney(p.profit_amount):"")+'</span></td>'
      + '<td data-label="标签">'+(tags||"—")+'</td>'
      + '<td><div class="row-actions">'
      + '<button class="btn-row" onclick="fillAction(this.closest(\'tr\').dataset.code,\'reduce_position\')">减仓</button>'
      + '<button class="btn-row" onclick="fillAction(this.closest(\'tr\').dataset.code,\'update_position\')">编辑</button>'
      + '<button class="btn-row danger" onclick="fillAction(this.closest(\'tr\').dataset.code,\'remove_position\')">清仓</button>'
      + '</div></td></tr>';
  }
  h += '</table>';
  el.innerHTML = h;
}

// ── 渲染自选表 ──
function renderWatch(rows) {
  const el = $("#watchlist");
  $("#watch-count").textContent = rows.length + " 只";
  if (!rows.length) {
    el.innerHTML = '<div class="empty">暂无自选股<div class="empty-hint">选择「加入自选」添加关注标的</div></div>';
    return;
  }
  let h = '<table><tr><th>代码</th><th>名称</th><th>现价</th><th>涨跌</th><th>目标买</th><th>距买</th><th>目标卖</th><th>距卖</th><th></th></tr>';
  for (const w of rows) {
    const bg = profitClass(w.buy_gap_pct);
    const sg = profitClass(w.sell_gap_pct);
    const wc = escapeHTML(w.code);
    const wn = escapeHTML(w.name||"—");
    h += '<tr data-code="'+wc+'">'
      + '<td data-label="代码"><span class="code-tag">'+wc+'</span></td>'
      + '<td data-label="名称">'+wn+'</td>'
      + '<td data-label="现价">'+fmtPrice(w.current_price)+'</td>'
      + '<td data-label="涨跌" class="'+profitClass(w.change_pct)+'">'+fmtPct(w.change_pct)+'</td>'
      + '<td data-label="目标买">'+(w.target_buy||"—")+'</td>'
      + '<td data-label="距买" class="'+bg+'">'+fmtPct(w.buy_gap_pct)+'</td>'
      + '<td data-label="目标卖">'+(w.target_sell||"—")+'</td>'
      + '<td data-label="距卖" class="'+sg+'">'+fmtPct(w.sell_gap_pct)+'</td>'
      + '<td><div class="row-actions">'
      + '<button class="btn-row" onclick="fillAction(this.closest(\'tr\').dataset.code,\'update_watch\')">编辑</button>'
      + '<button class="btn-row danger" onclick="fillAction(this.closest(\'tr\').dataset.code,\'remove_watch\')">删除</button>'
      + '</div></td></tr>';
  }
  h += '</table>';
  el.innerHTML = h;
}

// ── 行内操作按钮 ──
function fillAction(code, action) {
  $("#action").value = action;
  $("#code").value = code;
  syncFields();
  // 如果是编辑，自动填充当前数据
  if (action === "update_position") {
    const p = (currentData.positions||[]).find(x => x.code === code);
    if (p) { $("#cost").value = p.cost || ""; $("#quantity").value = p.quantity || ""; }
  }
  if (action === "update_watch") {
    const w = (currentData.watchlist||[]).find(x => x.code === code);
    if (w) { $("#name_w").value = w.name || ""; $("#target_buy").value = w.target_buy || ""; $("#target_sell").value = w.target_sell || ""; }
  }
  // 滚动到表单
  $("#entry").scrollIntoView({behavior: "smooth", block: "center"});
  $("#code").focus();
}

// ── 表单重置 ──
function resetForm() {
  ["#name","#name_w","#cost","#quantity","#buy_date","#tags","#target_buy","#target_sell","#sell_price"].forEach(id => {
    const el = $(id); if (el) el.value = "";
  });
}

// ── 加载交易日志 ──
async function loadTrades() {
  try {
    const r = await fetch("/api/trades", {headers: AUTH});
    if (r.status === 401) return;
    const j = await r.json();
    if (!j.ok) return;
    const d = j.data;
    const history = d.history || [];
    const stats = d.stats || {};
    $("#trades-count").textContent = history.length + " 条";

    // 渲染统计
    const statsEl = $("#trades-stats");
    if (history.length > 0) {
      const winRate = stats.win_rate != null ? (stats.win_rate * 100).toFixed(1) + "%" : "—";
      const totalPnl = stats.total_pnl != null ? fmtMoney(stats.total_pnl) : "—";
      const avgHold = stats.avg_hold_days != null ? stats.avg_hold_days.toFixed(1) + " 天" : "—";
      statsEl.innerHTML = ''
        + '<div class="stat-item"><div class="stat-label">总交易</div><div class="stat-value">' + history.length + '</div></div>'
        + '<div class="stat-item"><div class="stat-label">胜率</div><div class="stat-value ' + (stats.win_rate > 0.5 ? 'positive' : stats.win_rate < 0.5 ? 'negative' : '') + '">' + winRate + '</div></div>'
        + '<div class="stat-item"><div class="stat-label">总盈亏</div><div class="stat-value ' + profitClass(stats.total_pnl) + '">' + totalPnl + '</div></div>'
        + '<div class="stat-item"><div class="stat-label">平均持仓</div><div class="stat-value">' + avgHold + '</div></div>';
      statsEl.style.display = "";
    } else {
      statsEl.style.display = "none";
    }

    // 渲染历史
    const el = $("#trades-history");
    if (!history.length) { el.innerHTML = '<div class="empty">暂无交易记录</div>'; return; }
    let h = '<table><tr><th>日期</th><th>代码</th><th>名称</th><th>成本</th><th>卖出</th><th>数量</th><th>盈亏</th><th>原因</th></tr>';
    for (const t of history.slice().reverse()) {
      const pnl = (t.sell_price && t.cost) ? (t.sell_price - t.cost) * t.quantity : null;
      const reason = escapeHTML({manual:"手动清仓",reduce_to_zero:"减仓归零",partial_reduce:"部分减仓"}[t.reason] || t.reason);
      h += '<tr>'
        + '<td data-label="日期">'+(t.date||"—")+'</td>'
        + '<td data-label="代码"><span class="code-tag">'+escapeHTML(t.code||"")+'</span></td>'
        + '<td data-label="名称">'+escapeHTML(t.name||"—")+'</td>'
        + '<td data-label="成本">'+fmtPrice(t.cost)+'</td>'
        + '<td data-label="卖出">'+fmtPrice(t.sell_price)+'</td>'
        + '<td data-label="数量">'+(t.quantity||0)+'</td>'
        + '<td data-label="盈亏" class="'+profitClass(pnl)+'">'+(pnl!=null?fmtMoney(pnl):"—")+'</td>'
        + '<td data-label="原因">'+reason+'</td>'
        + '</tr>';
    }
    h += '</table>';
    el.innerHTML = h;
  } catch (e) {
    // 静默失败
  }
}

// ── 加载监控状态 ──
async function loadMonitor() {
  try {
    const r = await fetch("/api/monitor", {headers: AUTH});
    if (r.status === 401) return;
    const j = await r.json();
    if (!j.ok) return;
    const d = j.data;
    const statusEl = $("#monitor-status");
    const alertsEl = $("#monitor-alerts");
    if (d.enabled) {
      statusEl.textContent = d.trading_hours ? "🟢 盘中监控中" : "⏸ 非交易时段";
      statusEl.style.color = d.trading_hours ? "var(--success)" : "var(--text-muted)";
    } else {
      statusEl.textContent = "❌ 已禁用";
      statusEl.style.color = "var(--error)";
    }
    const lr = d.last_result;
    if (!lr || !lr.details || !lr.details.length) {
      alertsEl.innerHTML = '<div class="empty">暂无预警（等待首次扫描…）</div>';
      return;
    }
    const typeMap = {support_touch:"支撑触及",resistance_touch:"压力触及",target_buy:"到目标买",target_sell:"到目标卖",macd_golden:"MACD金叉",macd_dead:"MACD死叉",ma_break:"均线突破",near_limit:"涨跌停近",stop_loss:"止损",take_profit:"止盈"};
    let h = '<table><tr><th>标的</th><th>类型</th><th>预警</th><th>价格</th><th>状态</th></tr>';
    for (const a of lr.details) {
      const icon = a.pushed ? "✅" : "⏭️";
      h += '<tr><td data-label="标的"><span class="code-tag">'+escapeHTML(a.code)+'</span> '+escapeHTML(a.name||"")+'</td><td data-label="类型">'+escapeHTML(typeMap[a.type]||a.type)+'</td><td data-label="预警">'+escapeHTML(a.message)+'</td><td data-label="价格">'+escapeHTML(a.price)+'</td><td data-label="状态">'+icon+'</td></tr>';
    }
    h += '</table>';
    h += '<div style="padding:8px 14px;font-size:12px;color:var(--text-muted)">扫描: '+lr.scanned+' | 预警: '+lr.alerts+' | 推送: '+lr.pushed+' · '+lr.timestamp+'</div>';
    alertsEl.innerHTML = h;
  } catch (e) {
    // 静默失败
  }
}

// ── 动态 Webhook cURL ──
function updateCurl() {
  const a = $("#action").value;
  const code = $("#code").value || "sh600989";
  const body = {action: a, code};
  if (a === "add_position") {
    body.cost = parseFloat($("#cost").value) || 18.5;
    body.quantity = parseInt($("#quantity").value) || 1000;
  } else if (a === "reduce_position") {
    body.quantity = parseInt($("#quantity").value) || 500;
    const sp = parseFloat($("#sell_price").value);
    if (sp) body.sell_price = sp;
  }
  const bodyStr = JSON.stringify(body);
  const tok = TOKEN || "<TOKEN>";
  $("#curl").innerHTML = '<span class="kw">curl</span> -X POST http://127.0.0.1:8765/api/positions \\\\\n  -H <span class="str">\'Content-Type: application/json\'</span> \\\\\n  -H <span class="str">\'Authorization: Bearer ' + tok + '</span>\' \\\\\n  -d <span class="str">\'' + bodyStr + '\'</span>';
}

// ── 事件绑定 ──
$("#action").addEventListener("change", syncFields);
$("#action").addEventListener("change", updateCurl);
$("#code").addEventListener("input", updateCurl);
syncFields();

// 表单提交
$("#entry").addEventListener("submit", async (e) => {
  e.preventDefault();
  const a = $("#action").value;
  const code = $("#code").value.trim();
  if (!code) { showToast("请填写股票代码", false); return; }

  if (a === "remove_position" && !confirm("确认清仓 " + code + "？此操作不可撤销。")) return;
  if (a === "reduce_position") {
    const q = parseInt($("#quantity").value);
    if (!q || q <= 0) { showToast("请输入有效的减仓数量", false); return; }
    if (!confirm("确认减仓 " + code + " " + q + " 股？")) return;
  }

  const body = { action: a, code };
  const set = (id, key) => { const v = $(id).value.trim(); if (v !== "") body[key] = isNaN(+v) ? v : +v; };

  if (a === "add_position") {
    const cost = parseFloat($("#cost").value), qty = parseInt($("#quantity").value);
    if (!cost && cost !== 0) { showToast("请输入成本价", false); return; }
    if (!qty || qty <= 0) { showToast("数量须大于 0", false); return; }
    if ($("#name").value) body.name = $("#name").value;
    body.cost = cost; body.quantity = qty;
    if ($("#buy_date").value) body.buy_date = $("#buy_date").value;
    if ($("#tags").value) body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  } else if (a === "reduce_position") {
    set("#quantity", "quantity");
    const sp = parseFloat($("#sell_price").value);
    if (sp > 0) body.sell_price = sp;
  } else if (a === "update_position") {
    if ($("#cost").value) body.cost = +$("#cost").value;
    if ($("#quantity").value) body.quantity = +$("#quantity").value;
    if ($("#tags").value) body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  } else if (a === "tag_position" || a === "untag_position") {
    body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
    if (!body.tags.length) { showToast("请填写至少一个标签", false); return; }
  } else if (a === "add_watch" || a === "update_watch") {
    if ($("#name_w").value) body.name = $("#name_w").value;
    if ($("#target_buy").value) body.target_buy = +$("#target_buy").value;
    if ($("#target_sell").value) body.target_sell = +$("#target_sell").value;
  }

  const btn = $("#submit-btn");
  btn.disabled = true; btn.textContent = "提交中…";
  try {
    const r = await fetch("/api/positions", {
      method: "POST", headers: { "Content-Type": "application/json", ...AUTH },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.ok) { showToast(friendlyError(j.error, j.detail), false); return; }
    let msg = buildSuccessMsg(a, j.data, body);
    if (j.warn && j.warn.length) msg += " · " + j.warn.map(w => WARN_MAP[w]||w).join("；");
    showToast(msg, true);
    resetForm();
    await loadList();
    // 高亮变更行
    setTimeout(() => { const row = document.querySelector('tr[data-code="'+code+'"]'); if (row) { row.classList.add("highlight"); row.scrollIntoView({behavior:"smooth",block:"center"}); } }, 100);
  } catch (e) {
    showToast("请求失败: " + e.message, false);
  } finally {
    btn.disabled = false; btn.textContent = "提交";
  }
});

// 清空按钮
$("#clear-btn").addEventListener("click", resetForm);

// 刷新按钮
$("#refresh").addEventListener("click", () => { loadList(); loadMonitor(); loadTrades(); });

// 复制 cURL
$("#copy").addEventListener("click", async () => {
  const raw = $("#curl").textContent;
  try { await navigator.clipboard.writeText(raw); showToast("已复制到剪贴板", true); }
  catch { showToast("复制失败", false); }
});

// ── 键盘快捷键 ──
document.addEventListener("keydown", (e) => {
  // Ctrl+Enter 提交
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); $("#entry").requestSubmit(); }
  // Esc 清空表单
  if (e.key === "Escape") { resetForm(); }
});

// ── 初始化加载 ──
loadList();
loadMonitor();
loadTrades();
</script>
</body>
</html>
"""
