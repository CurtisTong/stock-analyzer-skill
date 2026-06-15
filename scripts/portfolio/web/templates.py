"""
HTML 模板模块。

包含内联 HTML 模板。
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
  .container { max-width: 740px; margin: 0 auto; }

  /* ── Header ── */
  header { display: flex; align-items: center; justify-content: space-between;
           margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  header h1 { font-size: 18px; font-weight: 600; letter-spacing: -0.3px;
              display: flex; align-items: center; gap: 10px; }
  header h1 .logo { color: var(--accent); font-size: 20px; }
  .badge { font-family: var(--mono); font-size: 11px; color: var(--text-muted);
           background: var(--elevated); border: 1px solid var(--border);
           padding: 2px 8px; border-radius: 999px; }
  .btn-icon { background: none; border: 1px solid var(--border); color: var(--text-secondary);
              border-radius: var(--radius-sm); cursor: pointer; padding: 6px 12px;
              font-size: 13px; font-family: var(--sans); transition: all .15s;
              min-height: 34px; display: inline-flex; align-items: center; gap: 6px; }
  .btn-icon:hover { background: var(--elevated); color: var(--text); border-color: var(--text-muted); }

  /* ── Panels ── */
  .panel { background: var(--surface); border: 1px solid var(--border);
           border-radius: var(--radius); margin-bottom: 16px; overflow: hidden; }
  .panel-header { padding: 12px 16px; border-bottom: 1px solid var(--border);
                  display: flex; align-items: center; justify-content: space-between; }
  .panel-header h2 { font-size: 13px; font-weight: 600; color: var(--text-secondary);
                     text-transform: uppercase; letter-spacing: 0.5px; }
  .panel-body { padding: 0; overflow-x: auto; }

  /* ── Tables ── */
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
  .positive { color: var(--success); } .negative { color: var(--error); }

  /* ── Forms ── */
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
  .warn { color: var(--warning); font-size: 11px; }

  /* ── Buttons ── */
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

  /* ── Code block ── */
  pre { background: var(--bg); color: var(--text-secondary); padding: 14px 16px;
        font-family: var(--mono); font-size: 12px; line-height: 1.5;
        overflow-x: auto; border-top: 1px solid var(--border); }
  pre .kw { color: var(--accent); } pre .str { color: #a5d6ff; }

  /* ── Toast ── */
  .toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%) translateY(-8px);
           z-index: 1000; max-width: 440px; padding: 10px 16px; border-radius: var(--radius-sm);
           font-size: 13px; font-family: var(--sans); border: 1px solid;
           opacity: 0; transition: opacity .25s, transform .25s; pointer-events: none; }
  .toast.visible { opacity: 1; pointer-events: auto; transform: translateX(-50%) translateY(0); }
  .toast.ok { background: var(--success-bg); border-color: rgba(63,185,80,.3); color: var(--success); }
  .toast.err { background: var(--error-bg); border-color: rgba(248,81,73,.3); color: var(--error); }

  /* ── Destructive ── */
  .destructive { border: 1px solid rgba(248,81,73,.3); background: var(--error-bg);
                 padding: 10px 14px; border-radius: var(--radius-sm);
                 font-size: 12px; color: var(--error); font-family: var(--sans); }

  /* ── Responsive ── */
  @media (max-width: 480px) {
    body { padding: 12px; }
    .form-grid { grid-template-columns: 1fr; padding: 12px; }
    .form-group.full { grid-column: 1; }
    input, select { padding: 10px 12px; font-size: 16px; }
    .btn-submit { padding: 12px 20px; font-size: 16px; min-height: 44px; }
    .btn-icon, .btn-copy { min-height: 44px; min-width: 44px; }
    table { font-size: 12px; }
    th, td { padding: 8px 10px; }
    header h1 { font-size: 16px; }
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1><span class="logo">◆</span> Portfolio <span class="badge">v__VERSION__</span></h1>
    <button class="btn-icon" id="refresh" aria-label="刷新列表">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 8A6 6 0 1 1 8 2"/><path d="M8 2v4l3-2"/></svg>
      刷新
    </button>
  </header>

  <div id="toast" class="toast" role="status" aria-live="polite"></div>

  <div class="panel">
    <div class="panel-header"><h2>持仓</h2></div>
    <div class="panel-body" id="positions" aria-live="polite"></div>
  </div>

  <div class="panel">
    <div class="panel-header"><h2>自选</h2></div>
    <div class="panel-body" id="watchlist" aria-live="polite"></div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2>📡 策略监控</h2>
      <span class="badge" id="monitor-status">检查中…</span>
    </div>
    <div class="panel-body" id="monitor-alerts" aria-live="polite">
      <div class="empty">加载中…</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header"><h2>操作</h2></div>
    <form id="entry" class="form-grid">
      <div class="form-group full">
        <label for="action">action</label>
        <select id="action">
          <option value="add_position">add_position · 加仓/建仓</option>
          <option value="reduce_position">reduce_position · 减仓</option>
          <option value="remove_position">remove_position · 清仓</option>
          <option value="update_position">update_position · 修改字段</option>
          <option value="tag_position">tag_position · 追加标签</option>
          <option value="untag_position">untag_position · 删除标签</option>
          <option value="add_watch">add_watch · 加自选</option>
          <option value="update_watch">update_watch · 改自选</option>
          <option value="remove_watch">remove_watch · 删自选</option>
        </select>
      </div>
      <div class="form-group">
        <label for="code">code</label>
        <input id="code" list="codes" autocomplete="off" autocapitalize="off" autocorrect="off"
               placeholder="sh600989" required>
        <datalist id="codes">__DATALIST__</datalist>
      </div>
      <div class="form-group" data-show="add_position">
        <label for="name">name <span style="color:var(--text-muted)">(可选)</span></label>
        <input id="name" placeholder="宝丰能源">
      </div>
      <div class="form-group" data-show="add_position update_position update_watch">
        <label for="cost">cost <span class="required" data-required="add_position">*</span></label>
        <input id="cost" type="number" step="0.001" placeholder="18.500">
      </div>
      <div class="form-group" data-show="add_position reduce_position update_position">
        <label for="quantity">quantity <span class="required" data-required="add_position reduce_position">*</span></label>
        <input id="quantity" type="number" step="1" placeholder="1000">
      </div>
      <div class="form-group" data-show="add_position">
        <label for="buy_date">buy_date</label>
        <input id="buy_date" type="date">
      </div>
      <div class="form-group" data-show="add_position tag_position untag_position update_position">
        <label for="tags">tags <span class="warn" data-warn="update_position">⚠ 整列表替换</span></label>
        <input id="tags" placeholder="长线, 能源">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="name_w">name <span style="color:var(--text-muted)">(可选)</span></label>
        <input id="name_w" placeholder="华友钴业">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="target_buy">target_buy</label>
        <input id="target_buy" type="number" step="0.01" placeholder="28.00">
      </div>
      <div class="form-group" data-show="add_watch update_watch">
        <label for="target_sell">target_sell</label>
        <input id="target_sell" type="number" step="0.01" placeholder="42.00">
      </div>
      <div class="form-group full" data-show="remove_position reduce_position" id="confirm-wrap" style="display:none">
        <div class="destructive">⚠ 确认执行此不可逆操作</div>
      </div>
      <div class="form-group full">
        <button type="submit" class="btn-submit" id="submit-btn">提交</button>
      </div>
    </form>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2>Webhook</h2>
      <button class="btn-copy" id="copy" aria-label="复制 cURL">copy</button>
    </div>
    <pre id="curl"><span class="kw">curl</span> -X POST http://127.0.0.1:8765/api/positions \\
  -H <span class="str">'Content-Type: application/json'</span> \\
  -H <span class="str">'Authorization: Bearer &lt;YOUR_TOKEN&gt;'</span> \\
  -d <span class="str">'{"action":"add_position","code":"sh600989","cost":18.5,"quantity":1000,"tags":["长线"]}'</span></pre>
  </div>

</div>

<script>
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
let toastTimer;
const TOKEN = new URLSearchParams(location.search).get("token") || "";
const AUTH = TOKEN ? {"Authorization": "Bearer " + TOKEN} : {};

function showToast(msg, ok) {
  const t = $("#toast");
  t.className = "toast " + (ok ? "ok" : "err");
  t.textContent = msg;
  t.offsetHeight;
  t.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("visible"), ok ? 3000 : 6000);
}

const WARN_MAP = {
  update_position_replaces_tags: "tags 字段已整体替换（非合并）",
  position_removed: "持仓已全部卖出并清除",
};

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

async function loadList() {
  try {
    const r = await fetch("/api/positions", {headers: AUTH});
    const j = await r.json();
    if (!j.ok) throw new Error(j.error);
    renderPositions(j.data.positions);
    renderWatch(j.data.watchlist);
  } catch (e) {
    showToast("加载失败: " + e.message, false);
  }
}

function renderPositions(rows) {
  const el = $("#positions");
  if (!rows.length) { el.innerHTML = '<div class="empty">暂无持仓</div>'; return; }
  let h = '<table><tr><th>代码</th><th>名称</th><th>成本</th><th>数量</th><th>买入日</th><th>标签</th></tr>';
  for (const p of rows) {
    const tags = (p.tags||[]).map(t => '<span class="code-tag">'+t+'</span>').join("");
    h += '<tr><td>'+p.code+'</td><td>'+(p.name||"—")+'</td><td>'+p.cost+'</td><td>'+p.quantity+'</td><td>'+(p.buy_date||"—")+'</td><td>'+(tags||"—")+'</td></tr>';
  }
  el.innerHTML = h + "</table>";
}

function renderWatch(rows) {
  const el = $("#watchlist");
  if (!rows.length) { el.innerHTML = '<div class="empty">暂无自选</div>'; return; }
  let h = '<table><tr><th>代码</th><th>名称</th><th>目标买</th><th>目标卖</th><th>加入日</th></tr>';
  for (const w of rows) {
    h += '<tr><td>'+w.code+'</td><td>'+(w.name||"—")+'</td><td>'+(w.target_buy||"—")+'</td><td>'+(w.target_sell||"—")+'</td><td>'+(w.added_date||"—")+'</td></tr>';
  }
  el.innerHTML = h + "</table>";
}

function resetForm() {
  ["#name","#name_w","#cost","#quantity","#buy_date","#tags","#target_buy","#target_sell"].forEach(id => {
    const el = $(id); if (el) el.value = "";
  });
}

$("#action").addEventListener("change", syncFields);
syncFields();

$("#entry").addEventListener("submit", async (e) => {
  e.preventDefault();
  const a = $("#action").value;
  const code = $("#code").value.trim();
  if (!code) { showToast("请填写代码", false); return; }

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
    if (!cost && cost !== 0) { showToast("成本为必填项", false); return; }
    if (!qty || qty <= 0) { showToast("数量须 > 0", false); return; }
    if ($("#name").value) body.name = $("#name").value;
    body.cost = cost; body.quantity = qty;
    if ($("#buy_date").value) body.buy_date = $("#buy_date").value;
    if ($("#tags").value) body.tags = $("#tags").value.split(",").map(s=>s.trim()).filter(Boolean);
  } else if (a === "reduce_position") {
    set("#quantity", "quantity");
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
    if (!j.ok) { showToast(j.error + (j.detail ? ": " + j.detail : ""), false); return; }
    let msg = "✓ 成功";
    if (j.warn && j.warn.length) msg += " · " + j.warn.map(w => WARN_MAP[w]||w).join("；");
    showToast(msg, true);
    resetForm();
    await loadList();
  } catch (e) {
    showToast("请求失败: " + e.message, false);
  } finally {
    btn.disabled = false; btn.textContent = "提交";
  }
});

$("#refresh").addEventListener("click", () => { loadList(); loadMonitor(); });
$("#copy").addEventListener("click", async () => {
  const raw = $("#curl").textContent;
  try { await navigator.clipboard.writeText(raw); showToast("已复制", true); }
  catch { showToast("复制失败", false); }
});

loadList();

async function loadMonitor() {
  try {
    const r = await fetch("/api/monitor", {headers: AUTH});
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
    let h = '<table><tr><th>标的</th><th>类型</th><th>预警</th><th>价格</th><th>状态</th></tr>';
    const typeMap = {support_touch:"支撑触及",resistance_touch:"压力触及",target_buy:"到目标买",target_sell:"到目标卖",macd_golden:"MACD金叉",macd_dead:"MACD死叉",ma_break:"均线突破",near_limit:"涨跌停近",stop_loss:"止损",take_profit:"止盈"};
    for (const a of lr.details) {
      const icon = a.pushed ? "✅" : "⏭️";
      h += '<tr><td><span class="code-tag">'+a.code+'</span> '+(a.name||"")+'</td><td>'+(typeMap[a.type]||a.type)+'</td><td>'+a.message+'</td><td>'+a.price+'</td><td>'+icon+'</td></tr>';
    }
    h += '</table>';
    h += '<div style="padding:8px 14px;font-size:12px;color:var(--text-muted)">扫描: '+lr.scanned+' | 预警: '+lr.alerts+' | 推送: '+lr.pushed+' · '+lr.timestamp+'</div>';
    alertsEl.innerHTML = h;
  } catch (e) {
    // 静默失败
  }
}
loadMonitor();
</script>
</body>
</html>
"""
