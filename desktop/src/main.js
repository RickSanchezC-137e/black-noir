// Black Noir HUD — Pip-Boy CRT + 3D core cloud on LIVE data (no demo).
// Thin client over /api/* + /ws/*. Tauri window controls + auto-updater.
// View ported literally from desktop_reference/hud_reference.html; data is live only.
import * as THREE from "three";

const params = new URLSearchParams(location.search);
const API = (params.get("api") || window.NOIR_API_BASE || (window.__VITE_API_BASE__) ||
  "https://jarvisgod.duckdns.org").replace(/\/$/, "");
const WS = API.replace(/^http/, "ws");
const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const isTauri = !!window.__TAURI_INTERNALS__ || !!window.__TAURI__;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const CLUSTERS = {
  C1: { n: "C1 ВЗАИМОДЕЙСТВИЕ", p: [0, 30, -150] },
  C2: { n: "C2 ПАМЯТЬ", p: [-155, 0, 30] },
  C3: { n: "C3 ВОСПРИЯТИЕ", p: [125, 35, -65] },
  C4: { n: "C4 САМОУЛУЧШЕНИЕ", p: [45, -25, 150] },
  C5: { n: "C5 БЕЗОПАСНОСТЬ", p: [-100, 35, 105] },
  C6: { n: "C6 ИНСТРУМЕНТЫ", p: [150, -20, 55] },
};

async function api(p, opt) { const r = await fetch(API + p, opt); if (!r.ok) throw new Error(r.status); return r.json(); }
const pickReply = (d) => d?.reply ?? d?.response ?? d?.message ?? d?.text ?? (typeof d === "string" ? d : "");

let modules = [], core = null;

// ---------- window controls (Tauri) ----------
async function setupWindow() {
  if (!isTauri) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    const w = getCurrentWindow();
    $("#w-min").onclick = () => w.hide();   // свернуть в трей (вернуть — клик по иконке в трее)
    $("#w-max").onclick = () => w.toggleMaximize();
    $("#w-close").onclick = () => w.close();
    window.addEventListener("keydown", async (e) => {
      if (e.key === "F11") { e.preventDefault(); w.setFullscreen(!(await w.isFullscreen())); }
    });
  } catch (e) { console.warn("window api", e); }
}

// ---------- auto-updater ----------
async function checkUpdate() {
  if (!isTauri) return;
  try {
    const { check } = await import("@tauri-apps/plugin-updater");
    const upd = await check();
    if (upd) {
      toast(`Обновление ${upd.version} — устанавливаю…`);
      await upd.downloadAndInstall();
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    }
  } catch (e) { console.warn("updater", e); }
}

// ---------- theme ----------
let theme = localStorage.getItem("noir.theme") || "green";
function applyTheme() { $("#px").classList.toggle("gold", theme === "gold"); const hex = theme === "green" ? 0x4dffa0 : 0xf5bd3a; if (window.__facephos) window.__facephos(hex); }
$("#theme").onclick = () => { theme = theme === "green" ? "gold" : "green"; localStorage.setItem("noir.theme", theme); applyTheme(); };

// ---------- tabs ----------
let cur = "map";
document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
  cur = b.dataset.go;
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("hidden", p.dataset.tab !== cur));
  // close floating overlays so they don't linger/overlap on other tabs
  $("#insp").classList.remove("open");
  if (cur !== "chat") $("#facewin").classList.remove("on");
  if (cur === "map") render2D();
});
// hotkeys Ctrl+1..6
const TABORDER = ["map", "tasks", "chat", "sys", "ideas", "prof"];
window.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key >= "1" && e.key <= "6") { const t = TABORDER[+e.key - 1]; const b = document.querySelector(`.tab[data-go=${t}]`); if (b) b.click(); }
});

// ---------- notifications ----------
let unread = 0;
function toast(text) {
  const n = $("#notifs"); const e = el("div", "toast", "● " + esc(text)); n.appendChild(e);
  while (n.children.length > 3) n.removeChild(n.firstChild);
  setTimeout(() => e.remove(), 5000);
  unread++; const c = $("#bellcnt"); c.textContent = unread; c.classList.remove("hidden");
}
$("#bell").onclick = () => { unread = 0; $("#bellcnt").classList.add("hidden"); };

// ---------- clock + companion ----------
function clock() { const t = new Date(), p = (x) => x < 10 ? "0" + x : x; $("#clock").textContent = p(t.getHours()) + ":" + p(t.getMinutes()) + " · live"; }
clock(); setInterval(clock, 30000);
(function anim() {
  requestAnimationFrame(anim);
  const t = Date.now() / 1000, fig = $("#vbFig"), arm = $("#vbArm"), head = $("#vbHead");
  if (fig) fig.setAttribute("transform", `translate(0 ${(Math.sin(t * 2.2) * 2.4).toFixed(2)})`);
  if (arm) arm.setAttribute("transform", `rotate(${(Math.sin(t * 6) * 7).toFixed(2)} 130 120)`);
  if (head) head.setAttribute("transform", `rotate(${(Math.sin(t * 1.4) * 1.6).toFixed(2)} 100 118)`);
})();

// ====================================================================
//  Shared right inspector drawer (module / core / task / idea)
// ====================================================================
const insp = $("#insp"), inspTabs = $("#insp-tabs"), inspBody = $("#insp-body");
$("#insp-x").onclick = () => insp.classList.remove("open");
function drawer(title) { insp.classList.add("open"); $("#insp-title").textContent = title; inspTabs.innerHTML = ""; inspBody.innerHTML = ""; }
function tabset(defs, def) {
  let active = def;
  const render = async () => {
    inspTabs.querySelectorAll(".it").forEach((x) => x.classList.toggle("on", x.dataset.k === active));
    inspBody.innerHTML = "<div class='empty'>загрузка…</div>";
    const fn = defs.find((d) => d[0] === active)[2];
    try { await fn(inspBody); } catch (e) { inspBody.innerHTML = `<div class='empty'>нет данных (${esc(e.message)})</div>`; }
  };
  defs.forEach(([k, lbl]) => { const t = el("span", "it", lbl); t.dataset.k = k; t.onclick = () => { active = k; render(); }; inspTabs.appendChild(t); });
  render();
}
function agentChat(body, target, ph) {
  body.innerHTML = `<div id="agl" style="max-height:62vh;overflow:auto"></div><div style="display:flex;gap:5px;margin-top:7px"><input id="agi" style="flex:1;background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:5px;border-radius:4px" placeholder="${esc(ph)}"/><button class="ico" id="ags">→</button></div>`;
  const send = async () => {
    const v = $("#agi").value.trim(); if (!v) return; $("#agi").value = "";
    $("#agl").appendChild(el("div", "msg me", "» " + esc(v)));
    try { const r = await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: v, target }) }); $("#agl").appendChild(el("div", "msg ai", esc(pickReply(r)))); }
    catch (e) { $("#agl").appendChild(el("div", "msg sys", "[нет связи]")); }
    $("#agl").scrollTop = 1e9;
  };
  $("#ags").onclick = send; $("#agi").onkeydown = (e) => { if (e.key === "Enter") send(); };
}

// ---- module / core inspector (Map) ----
function openInspector(kind, id) {
  if (kind === "core") {
    drawer("СОСТАВ ИИ ЯДРА");
    inspBody.innerHTML = (core?.ai || []).map((a) =>
      `<div class="row"><span>${esc(a.name)} <span class="chip">${esc(a.role)}</span></span><span>${esc(a.status)}</span></div><div class="m" style="opacity:.6;margin-bottom:7px">${esc(a.model)}</div>`).join("")
      + `<div style="margin-top:8px"><button class="ico" id="ck-upd">ПРОВЕРИТЬ ОБНОВЛЕНИЯ</button> <button class="ico" id="ck-chat">ЧАТ С ЯДРОМ</button></div>`;
    const u = $("#ck-upd"); if (u) u.onclick = checkUpdate;
    const c = $("#ck-chat"); if (c) c.onclick = () => document.querySelector(".tab[data-go=chat]").click();
    return;
  }
  drawer(id);
  const m = modules.find((x) => x.name === id);
  tabset([
    ["logs", "ЛОГИ", async (b) => {
      const d = await api(`/api/modules/${id}/logs?tail=40`);
      b.innerHTML = (d.logs || []).map((l) => `<div class="m">${esc((l.ts || "").slice(11, 19))} [${esc(l.level)}] ${esc(l.event)} ${esc(l.payload || "")}</div>`).join("") || "<div class='empty'>нет логов</div>";
    }],
    ["chat", "ЧАТ-АГЕНТА", async (b) => agentChat(b, "module:" + id, "агенту " + id + "…")],
    ["mem", "ПАМЯТЬ", async (b) => {
      const d = await api(`/api/memory?module=${id}`);
      b.innerHTML = (d.items || []).map((x) => `<div class="row"><span>${esc(x.value)}</span><span class="chip">${esc(x.type || x.key)}</span></div>`).join("") || "<div class='empty'>нет данных</div>";
    }],
    ["cfg", "НАСТРОЙКИ", async (b) => {
      b.innerHTML = `<div class="row"><span>статус</span><span class="chip">${esc(m?.status)}</span></div><div class="row"><span>кластер</span><span>${esc(m?.cluster)}</span></div><div class="row"><span>версия</span><span>v${esc(m?.version)}</span></div><div class="row"><span>инструменты</span><span>${esc((m?.tools || []).join(", "))}</span></div><div style="margin-top:9px"><button class="ico" id="md-tog">${m?.enabled ? "ОТКЛЮЧИТЬ" : "ВКЛЮЧИТЬ"}</button></div>`;
      const tog = $("#md-tog"); if (tog) tog.onclick = async () => { await api(`/api/modules/${id}/${m?.enabled ? "disable" : "enable"}`, { method: "POST" }); await loadModules(); openInspector("module", id); };
    }],
  ], "logs");
}

// ====================================================================
//  3D core cloud (Map) — raycaster click + camera fly-in (подлёт)
// ====================================================================
let s2q = "", s2hidden = new Set();
let s2nodes = {}, s2corePos = null;        // live SVG positions for packet animation
const s2statusClass = (s) => s === "error" ? "err" : s === "busy" ? "busy" : s === "offline" ? "offline" : "live";

function render2D() {
  const svg = $("#s2svg"); if (!svg) return;
  const cx = 500, cy = 320, cnames = Object.keys(CLUSTERS), n = cnames.length;
  const chips = $("#s2chips"); chips.innerHTML = "";
  cnames.forEach((cid) => {
    const ch = el("span", "s2chip" + (s2hidden.has(cid) ? "" : " on"), cid); ch.title = CLUSTERS[cid].n;
    ch.onclick = () => { s2hidden.has(cid) ? s2hidden.delete(cid) : s2hidden.add(cid); render2D(); };
    chips.appendChild(ch);
  });
  const byCl = {}; modules.forEach((m) => { (byCl[m.cluster] = byCl[m.cluster] || []).push(m); });
  const pos = {};
  cnames.forEach((cid, i) => { const a = -Math.PI / 2 + i * (2 * Math.PI / n); pos[cid] = { x: cx + 200 * Math.cos(a), y: cy + 200 * Math.sin(a), a }; });
  s2nodes = {}; s2corePos = { x: cx, y: cy };
  const parts = []; let active = 0, total = 0;
  cnames.forEach((cid) => {
    if (s2hidden.has(cid)) return;
    const p = pos[cid];
    parts.push(`<line class="lnk flow" x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}"/>`);
    const mods = byCl[cid] || [], k = mods.length, spread = Math.min(0.36, 1.5 / Math.max(1, k));
    mods.forEach((m, j) => {
      total++; if (m.status === "busy" || m.status === "idle") active++;
      const a = p.a + (j - (k - 1) / 2) * spread, mx = p.x + 120 * Math.cos(a), my = p.y + 120 * Math.sin(a);
      s2nodes[m.name] = { x: mx, y: my };
      const dim = (!s2q || (m.display_name || m.name).toLowerCase().includes(s2q)) ? "" : " dim";
      const anchor = Math.cos(a) < -0.25 ? "end" : Math.cos(a) > 0.25 ? "start" : "middle";
      const tx = mx + 11 * Math.cos(a), ty = my + 11 * Math.sin(a);
      parts.push(`<line class="lnk flow${dim}" x1="${p.x.toFixed(1)}" y1="${p.y.toFixed(1)}" x2="${mx.toFixed(1)}" y2="${my.toFixed(1)}"/>`);
      parts.push(`<circle class="nd glow ${s2statusClass(m.status)}${dim}" data-mod="${esc(m.name)}" cx="${mx.toFixed(1)}" cy="${my.toFixed(1)}" r="6"><title>${esc(m.display_name || m.name)} · ${esc(m.status)}</title></circle>`);
      parts.push(`<text class="${dim.trim()}" x="${tx.toFixed(1)}" y="${(ty + 3).toFixed(1)}" text-anchor="${anchor}">${esc(m.display_name || m.name)}</text>`);
    });
    parts.push(`<circle class="nd glow live" data-cl="${cid}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="11"><title>${esc(CLUSTERS[cid].n)}</title></circle>`);
    parts.push(`<text class="cl" x="${p.x.toFixed(1)}" y="${(p.y - 16).toFixed(1)}" text-anchor="middle">${esc(cid)}</text>`);
  });
  parts.push(`<circle class="nd glow live core" data-core="1" cx="${cx}" cy="${cy}" r="22"/>`);
  parts.push(`<text class="cl" x="${cx}" y="${cy + 4}" text-anchor="middle">NOIR</text>`);
  parts.push(`<g id="s2pkts"></g>`);
  svg.innerHTML = parts.join("");
  svg.querySelectorAll("[data-mod]").forEach((c) => c.onclick = () => openInspector("module", c.getAttribute("data-mod")));
  const ce = svg.querySelector("[data-core]"); if (ce) ce.onclick = () => openInspector("core");
  $("#s2act").textContent = total ? `${active}/${total} ACTIVE` : "нет модулей";
}
$("#s2search").addEventListener("input", (e) => { s2q = e.target.value.trim().toLowerCase(); render2D(); });

// data-exchange packets travelling along the links (live activity)
let packets = [];
function spawnPacket(from, to) {
  const g = $("#s2pkts"); if (!g || !from || !to) return;
  const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  c.setAttribute("r", "3.2"); c.setAttribute("class", "pkt");
  c.setAttribute("cx", from.x); c.setAttribute("cy", from.y);
  g.appendChild(c); packets.push({ el: c, from, to, t0: performance.now(), dur: 850 });
}
function fireExchange(moduleName) {
  const nd = s2nodes[moduleName]; if (!nd || !s2corePos) return;
  spawnPacket(s2corePos, nd); setTimeout(() => spawnPacket(nd, s2corePos), 260);
}
(function animatePackets() {
  requestAnimationFrame(animatePackets);
  if (!packets.length || cur !== "map") return;
  const now = performance.now();
  for (let i = packets.length - 1; i >= 0; i--) {
    const p = packets[i], t = (now - p.t0) / p.dur;
    if (t >= 1) { p.el.remove(); packets.splice(i, 1); continue; }
    p.el.setAttribute("cx", (p.from.x + (p.to.x - p.from.x) * t).toFixed(1));
    p.el.setAttribute("cy", (p.from.y + (p.to.y - p.from.y) * t).toFixed(1));
    p.el.setAttribute("opacity", (t < .12 ? t * 8 : t > .88 ? (1 - t) * 8 : 1).toFixed(2));
  }
})();

// detect live activity from the Governor audit → animate exchanges between core & modules
let seenAudit = null;
async function pumpActivity() {
  try {
    const g = await api("/api/governor/audit?limit=25"); const rows = g.audit || [];
    const key = (a) => `${a.created_at}|${a.module}|${a.tool}`;
    if (seenAudit) rows.forEach((a) => { if (!seenAudit.has(key(a))) fireExchange(a.module); });
    seenAudit = new Set(rows.map(key));
  } catch (e) {}
}

// ====================================================================
//  TASKS — kanban + inspector ИНФО/ЛОГ/ВЕТВЬ/ЧАТ (live)
// ====================================================================
const TCOLS = { queued: "В ОЧЕРЕДИ", running: "В ПРОЦЕССЕ", done: "ГОТОВО", error: "ОШИБКА" };
async function loadTasks() {
  try {
    const d = await api("/api/tasks"); const t = d.tasks || [];
    const wrap = $("#tasks"); wrap.innerHTML = "";
    Object.entries(TCOLS).forEach(([k, lbl]) => {
      const col = el("div", "kbcol"); col.appendChild(el("h4", null, `${lbl} · ${t.filter((x) => x.status === k).length}`));
      const here = t.filter((x) => x.status === k);
      if (!here.length) col.appendChild(el("div", "empty", "—"));
      here.forEach((x) => {
        const card = el("div", "tk", `${esc(x.kind || x.id)}<div class="m" style="opacity:.6">${esc(x.id.slice(0, 8))} · ${esc((x.updated_at || x.created_at || "").slice(11, 16))}</div>`);
        card.onclick = () => openTaskInspector(x.id); col.appendChild(card);
      });
      wrap.appendChild(col);
    });
    // active-task badge on the nav tab
    const act = t.filter((x) => x.status === "running" || x.status === "queued").length;
    const tab = document.querySelector(".tab[data-go=tasks]");
    if (tab) tab.textContent = act ? `ЗАДАЧИ (${act})` : "ЗАДАЧИ";
  } catch (e) { $("#tasks").innerHTML = "<div class='empty'>нет связи с ядром</div>"; }
}
function openTaskInspector(id) {
  drawer("ЗАДАЧА " + id.slice(0, 8));
  tabset([
    ["info", "ИНФО", async (b) => {
      const d = await api(`/api/tasks/${id}`); const t = d.task;
      b.innerHTML = `<div class="row"><span>тип</span><span class="chip">${esc(t.kind)}</span></div><div class="row"><span>статус</span><span class="chip">${esc(t.status)}</span></div><div class="row"><span>создана</span><span>${esc((t.created_at || "").slice(0, 19).replace("T", " "))}</span></div><div class="row"><span>обновлена</span><span>${esc((t.updated_at || "").slice(0, 19).replace("T", " "))}</span></div>`
        + (t.payload ? `<div class="m" style="margin-top:7px;opacity:.8">${esc(t.payload)}</div>` : "")
        + (t.result ? `<div class="m" style="margin-top:7px">РЕЗУЛЬТАТ: ${esc(t.result)}</div>` : "")
        + (t.error ? `<div class="m" style="margin-top:7px;color:#ff7a6b">ОШИБКА: ${esc(t.error)}</div>` : "")
        + `<div style="margin-top:9px;display:flex;gap:6px"><button class="ico" id="t-cancel">ОТМЕНИТЬ</button><button class="ico" id="t-retry">ПОВТОРИТЬ</button></div>`;
      $("#t-cancel").onclick = async () => { await api(`/api/tasks/${id}/cancel`, { method: "POST" }); toast("Задача отменена"); await loadTasks(); openTaskInspector(id); };
      $("#t-retry").onclick = async () => { await api(`/api/tasks/${id}/retry`, { method: "POST" }); toast("Задача поставлена в очередь"); await loadTasks(); openTaskInspector(id); };
    }],
    ["log", "ЛОГ", async (b) => {
      const d = await api(`/api/tasks/${id}`);
      b.innerHTML = (d.log || []).map((l) => `<div class="tlog">${esc((l.created_at || "").slice(11, 19))} ${esc(l.module)}.${esc(l.tool)} → ${esc(l.decision)} ${l.ok ? "ok" : "fail"}</div>`).join("") || "<div class='empty'>лог пуст (live /ws/tasks)</div>";
    }],
    ["branch", "ВЕТВЬ", async (b) => {
      const d = await api(`/api/tasks/${id}`); const t = d.task;
      if (t.branch || t.pr_url) b.innerHTML = `<div class="row"><span>ветка</span><span>${esc(t.branch || "—")}</span></div>` + (t.pr_url ? `<div style="margin-top:7px"><button class="ico" id="t-pr">ОТКРЫТЬ PR</button></div>` : "");
      else b.innerHTML = "<div class='empty'>git-ветвь к задаче не привязана</div>";
    }],
    ["chat", "ЧАТ", async (b) => agentChat(b, "task:" + id, "агенту задачи…")],
  ], "info");
}

// ====================================================================
//  SYSTEMS (live)
// ====================================================================
function setConn(s, ok) { $("#conn").innerHTML = `&#9679; ${esc(s)}`; $("#conn").style.opacity = ok ? ".9" : ".5"; }
async function loadSystems() {
  try {
    const m = await api("/api/systems/metrics");
    $("#metrics").innerHTML = `<h5>МЕТРИКИ ХОСТА (live)</h5><div class="row"><span>CPU</span><span>${m.cpu}%</span></div><div class="bar"><i style="width:${Math.min(100, m.cpu)}%"></i></div><div class="row"><span>RAM</span><span>${m.ram}% (${m.ram_used_mb}/${m.ram_total_mb} МБ)</span></div><div class="bar"><i style="width:${m.ram}%"></i></div><div class="row"><span>Uptime</span><span>${esc(m.uptime)}</span></div><div class="row"><span>Ядра / GPU</span><span>${m.cores} / ${m.gpu ? "да" : "нет"}</span></div>`;
    const s = await api("/api/systems"); const h = s.hardware || {};
    $("#hw").innerHTML = `<h5>ЛОКАЛЬНЫЙ СЛОЙ</h5><div class="row"><span>Профиль</span><span>${esc(h.local_layer || h.profile || "—")}</span></div><div class="row"><span>Reflex</span><span>${esc(h.reflex || "cloud")}</span></div><div class="row"><span>Embeddings</span><span>${esc(s.embedding?.model || "—")} (${esc(s.embedding?.dim || "")})</span></div><div class="row"><span>Модулей</span><span>${modules.length}</span></div>`;
  } catch (e) { $("#metrics").innerHTML = "<div class='empty'>нет связи с ядром</div>"; }
  try { const g = await api("/api/governor/audit?limit=10"); $("#gov").innerHTML = `<h5>GOVERNOR · АУДИТ</h5>` + ((g.audit || []).map((a) => `<div class="row"><span>${esc(a.module)}.${esc(a.tool)} <span class="chip">${esc(a.action_class)}</span></span><span>${esc(a.decision)} ${a.ok ? "ok" : "fail"}</span></div>`).join("") || "<div class='empty'>аудит пуст</div>"); } catch (e) {}
  try {
    const a = await api("/api/systems/selfimprove/analysis"); const s = a.signals || {};
    const hdr = `<h5>САМОАНАЛИЗ · АВТО-УЛУЧШЕНИЕ <button class="ico" id="run-selfan">ЗАПУСТИТЬ</button></h5>`;
    $("#selfan").innerHTML = hdr + ((a.findings || []).length
      ? `<div class="row"><span>Сигналов</span><span>${s.total_findings || 0} (сбои ${s.exec_failures || 0} · модули ${s.module_errors || 0} · задачи ${s.task_errors || 0})</span></div>`
        + (a.findings || []).slice(0, 5).map((f) => `<div class="row"><span>${esc(f.signal)}</span><span class="chip">${f.count}× ${esc(f.kind)}</span></div>`).join("")
        + `<div class="m" style="opacity:.6;margin-top:6px">обновлено ${esc((a.generated_at || "").slice(11, 19))} · гипотез в очереди: ${(a.enqueued || []).length}</div>`
      : "<div class='empty'>отчётов ещё нет — нажмите ЗАПУСТИТЬ</div>");
    const rb = $("#run-selfan"); if (rb) rb.onclick = async () => { rb.textContent = "…"; try { await api("/api/systems/selfimprove/analyze", { method: "POST" }); toast("Самоанализ выполнен"); await loadSystems(); } catch (e) { rb.textContent = "ЗАПУСТИТЬ"; } };
  } catch (e) {}
}

// ====================================================================
//  IDEAS — columns на разборе/хорошие/плохие + intake + inspector
// ====================================================================
const ICOLS = [["НА РАЗБОРЕ", ["new", "review"]], ["ХОРОШИЕ", ["accepted"]], ["ПЛОХИЕ", ["rejected"]]];
async function loadIdeas() {
  try {
    const d = await api("/api/ideas?limit=60"); const it = d.ideas || [];
    const wrap = $("#ideacols"); wrap.innerHTML = "";
    ICOLS.forEach(([lbl, sts]) => {
      const col = el("div", "ideacol"); const here = it.filter((i) => sts.includes(i.status));
      col.appendChild(el("h4", null, `${lbl} · ${here.length}`));
      if (!here.length) col.appendChild(el("div", "empty", "—"));
      here.forEach((i) => {
        const c = el("div", "idea", `${esc(i.text)}<div class="m">${esc(i.status)}${i.score != null ? " · " + i.score : ""}</div>`);
        c.onclick = () => openIdeaInspector(i); col.appendChild(c);
      });
      wrap.appendChild(col);
    });
  } catch (e) { $("#ideacols").innerHTML = "<div class='empty'>нет связи с ядром</div>"; }
}
function openIdeaInspector(i) {
  drawer("ИДЕЯ");
  tabset([
    ["info", "ИНФО", async (b) => {
      b.innerHTML = `<div style="margin-bottom:8px">${esc(i.text)}</div><div class="row"><span>статус</span><span class="chip">${esc(i.status)}</span></div>` + (i.score != null ? `<div class="row"><span>оценка</span><span>${i.score}</span></div>` : "")
        + `<div style="margin-top:10px;display:flex;gap:6px"><button class="ico" id="i-acc">ПРИНЯТЬ</button><button class="ico" id="i-rej">ОТКАЗАТЬ</button></div>`;
      $("#i-acc").onclick = async () => { const r = await api(`/api/ideas/${i.id}/accept`, { method: "POST" }); toast("Идея принята → задача " + (r.task_id || "").slice(0, 8)); insp.classList.remove("open"); await loadIdeas(); await loadTasks(); document.querySelector(".tab[data-go=tasks]").click(); };
      $("#i-rej").onclick = async () => { await api(`/api/ideas/${i.id}/reject`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" }); toast("Идея отклонена"); insp.classList.remove("open"); await loadIdeas(); };
    }],
    ["tests", "ТЕСТЫ", async (b) => { b.innerHTML = "<div class='empty'>тесты по идее ещё не запускались</div>"; }],
    ["chat", "ЧАТ", async (b) => agentChat(b, "idea:" + i.id, "обсудить идею…")],
  ], "info");
}
$("#genidea").onclick = async () => { $("#genidea").textContent = "…"; try { await api("/api/ideas/generate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ n: 2 }) }); await loadIdeas(); } catch (e) {} $("#genidea").textContent = "+ СГЕНЕРИРОВАТЬ"; };
async function intake(source, value) { if (!value.trim()) return; try { await api("/api/ideas/intake", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ source, value }) }); toast("Принято в разбор"); await loadIdeas(); } catch (e) { toast("Не удалось принять"); } }
$("#iadd").onclick = () => { intake($("#isrc").value, $("#ival").value); $("#ival").value = ""; };
$("#ival").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#iadd").click(); });
$("#ifile").onclick = () => $("#ideafileinp").click();
$("#ideafileinp").onchange = (e) => { for (const f of e.target.files) intake("file", f.name); e.target.value = ""; };
async function loadBotStatus() { try { const d = await api("/api/ideas/bot"); const tg = d.telegram; $("#botstat").textContent = tg && tg.username ? "TG-бот: @" + tg.username : "TG-бот: не настроен"; } catch (e) { $("#botstat").textContent = "TG-бот: —"; } }

// ====================================================================
//  PROFILE — домены/метрики/гипотезы/здоровье/расписание (live §11)
// ====================================================================
async function loadProfile() {
  try {
    const d = await api("/api/memory?module=owner_profile");
    const items = d.items || [], hyps = d.hypotheses || [], health = d.health || [], schedule = d.schedule || [], goals = d.goals || [];
    const by = {}; items.forEach((f) => { (by[f.type] = by[f.type] || []).push(f); });
    const domains = `<div class="card"><h5>ДОМЕНЫ</h5>${Object.keys(by).length ? Object.entries(by).map(([dom, fs]) => `<div class="row"><span>${esc(dom)}</span><span>${fs.length} факт.</span></div>`).join("") : "<div class='empty'>нет данных</div>"}</div>`;
    const metrics = `<div class="card"><h5>КЛЮЧЕВЫЕ МЕТРИКИ</h5><div class="row"><span>Фактов профиля</span><span>${items.length}</span></div><div class="row"><span>Гипотез</span><span>${hyps.length}</span></div><div class="row"><span>Показателей здоровья</span><span>${health.length}</span></div><div class="row"><span>Целей</span><span>${goals.length}</span></div></div>`;
    const hypsCard = `<div class="card"><h5>ГИПОТЕЗЫ</h5>${hyps.length ? hyps.map((h) => `<div class="row"><span>${esc(h.statement)}</span><span class="chip">${esc(h.verdict || h.status)}</span></div>`).join("") : "<div class='empty'>нет гипотез</div>"}</div>`;
    const healthCard = `<div class="card"><h5>ЗДОРОВЬЕ (наблюдение)</h5>${health.length ? health.slice(0, 8).map((m) => `<div class="row"><span>${esc(m.metric)}</span><span>${esc(m.value)}${m.unit ? " " + esc(m.unit) : ""}</span></div>`).join("") : "<div class='empty'>нет показателей</div>"}</div>`;
    const schedCard = `<div class="card"><h5>РАСПИСАНИЕ</h5>${schedule.length ? schedule.slice(0, 8).map((s) => `<div class="row"><span>${esc(s.title)}</span><span>${esc((s.start || "").slice(0, 16).replace("T", " "))}</span></div>`).join("") : "<div class='empty'>нет событий</div>"}</div>`;
    $("#prof").innerHTML = domains + metrics + hypsCard + healthCard + schedCard;
  } catch (e) { $("#prof").innerHTML = "<div class='empty'>нет данных профиля</div>"; }
}

// ====================================================================
//  CHAT — voice equalizer + ws stream + attachments + visual face
// ====================================================================
let atts = [];
function renderAtts() {
  const wrap = $("#atts"); wrap.innerHTML = "";
  atts.forEach((a, idx) => { const c = el("div", "att", `<b>${esc(a.name)}</b><span class="rm" data-i="${idx}">✕</span>`); c.querySelector(".rm").onclick = () => { atts.splice(idx, 1); renderAtts(); }; wrap.appendChild(c); });
}
function addAtt(name, kind) { atts.push({ name, kind }); renderAtts(); }
$("#attbtn").onclick = () => $("#fileinp").click();
$("#fileinp").onchange = (e) => { for (const f of e.target.files) addAtt(f.name, f.type); e.target.value = ""; };
$("#msg").addEventListener("paste", (e) => { const items = e.clipboardData?.items || []; for (const it of items) { if (it.kind === "file") { const f = it.getAsFile(); if (f) addAtt(f.name || ("вставка." + (it.type.split("/")[1] || "bin")), it.type); } } });
(function dnd() {
  const pane = document.querySelector(".pane[data-tab=chat]"), mask = $("#dropmask"); let depth = 0;
  ["dragenter", "dragover"].forEach((ev) => pane.addEventListener(ev, (e) => { e.preventDefault(); depth = ev === "dragenter" ? depth + 1 : depth; mask.classList.add("on"); }));
  pane.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) mask.classList.remove("on"); });
  pane.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; mask.classList.remove("on"); for (const f of e.dataTransfer.files) addAtt(f.name, f.type); });
})();

// Channels (06_desktop.md §6.3): Передатчик / Ядро / Claude Code — each with
// persistent per-channel history + session, kept in localStorage.
const CHANNELS = { mediator: "ПЕРЕДАТЧИК", core: "ЯДРО", claude_code: "CLAUDE CODE" };
let ch = localStorage.getItem("noir.ch") || "mediator";
let drafts = [];
const chKey = (c) => "noir.chat." + c;
const chGet = (c) => { try { return JSON.parse(localStorage.getItem(chKey(c))) || {}; } catch (e) { return {}; } };
const chSet = (c, s) => localStorage.setItem(chKey(c), JSON.stringify(s));
function pushHist(c, role, text) { const s = chGet(c); s.hist = (s.hist || []).concat([{ role, text }]).slice(-120); chSet(c, s); }

function appendMsg(cls, text) { const e = el("div", "msg " + cls, esc(text)); $("#chatlog").appendChild(e); $("#chatlog").scrollTop = 1e9; return e; }
function renderChat() {
  const log = $("#chatlog"); log.innerHTML = "";
  (chGet(ch).hist || []).forEach((m) => appendMsg(m.role, m.text));
  if (!log.children.length) appendMsg("sys", ch === "mediator"
    ? "Передатчик: соберу твои реплики в одну задачу ядру и верну суть кратко."
    : ch === "claude_code" ? "Чат с Claude Code (read-only)." : "Прямой чат с ядром.");
}
function renderDrafts() {
  const d = $("#cdraft"); d.innerHTML = "";
  drafts.forEach((t, i) => { const c = el("span", "att", `<b>${esc(t.slice(0, 44))}</b><span class="rm" data-i="${i}">✕</span>`); c.querySelector(".rm").onclick = () => { drafts.splice(i, 1); renderDrafts(); }; d.appendChild(c); });
  d.style.display = (ch === "mediator" && drafts.length) ? "flex" : "none";
}
function switchChannel(c) {
  ch = c; localStorage.setItem("noir.ch", c); drafts = [];
  document.querySelectorAll(".chtab").forEach((b) => b.classList.toggle("on", b.dataset.ch === c));
  $("#msg").placeholder = c === "mediator" ? "реплика… (Enter — в буфер, кнопка — собрать и отправить ядру)"
    : c === "claude_code" ? "вопрос Claude Code…" : "сообщение ядру…";
  $("#send").textContent = c === "mediator" ? "⮞" : "→";
  renderDrafts(); renderChat();
}
document.querySelectorAll(".chtab").forEach((b) => b.onclick = () => switchChannel(b.dataset.ch));

async function sendChat() {
  const i = $("#msg"), cur = i.value.trim();
  let text;
  if (ch === "mediator") {
    if (cur) { drafts.push(cur); i.value = ""; }
    if (!drafts.length && !atts.length) return;
    text = drafts.join("\n");
  } else { text = cur; if (!text && !atts.length) return; i.value = ""; }
  if (atts.length) text += (text ? "\n" : "") + "[вложения: " + atts.map((a) => a.name).join(", ") + "]";
  drafts = []; renderDrafts(); atts = []; renderAtts();
  appendMsg("me", "» " + text); pushHist(ch, "me", "» " + text);
  const bubble = appendMsg("ai", "…");
  const st = chGet(ch);
  try {
    const r = await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: text, agent: ch, session_id: st.sid || null, cc_session: st.cc || null }) });
    st.sid = r.session_id; if (r.cc_session) st.cc = r.cc_session; chSet(ch, st);
    if (ch === "mediator" && r.task) { appendMsg("sys", "→ ядру: " + r.task); pushHist(ch, "sys", "→ ядру: " + r.task); }
    bubble.textContent = pickReply(r) || "(пустой ответ)"; pushHist(ch, "ai", bubble.textContent); faceSpeak(0.7);
  } catch (e) { bubble.textContent = "[нет связи с ядром]"; bubble.className = "msg sys"; }
  $("#chatlog").scrollTop = 1e9;
}
$("#send").onclick = sendChat;
$("#msg").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (ch === "mediator") { const v = e.target.value.trim(); if (v) { drafts.push(v); e.target.value = ""; renderDrafts(); } }
  else sendChat();
});
switchChannel(ch);

// ---- voice equalizer (real mic audio, WebAudio AnalyserNode) ----
let audioCtx, analyser, micStream, eqRAF, audioLevel = 0;
async function toggleMic() {
  const btn = $("#mic"), lbl = $("#vlbl");
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; btn.classList.remove("rec"); lbl.textContent = "голос: ожидание"; cancelAnimationFrame(eqRAF); clearEq(); return; }
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser(); analyser.fftSize = 64;
    audioCtx.createMediaStreamSource(micStream).connect(analyser);
    btn.classList.add("rec"); lbl.textContent = "голос: слушаю (live)";
    drawEq();
  } catch (e) { lbl.textContent = "голос: нет доступа к микрофону"; }
}
function clearEq() { const c = $("#eq"); if (!c) return; const g = c.getContext("2d"); g.clearRect(0, 0, c.width, c.height); }
function drawEq() {
  const c = $("#eq"); c.width = c.clientWidth; c.height = c.clientHeight; const g = c.getContext("2d");
  const data = new Uint8Array(analyser.frequencyBinCount);
  const col = getComputedStyle($("#px")).color;
  (function loop() {
    eqRAF = requestAnimationFrame(loop);
    analyser.getByteFrequencyData(data);
    g.clearRect(0, 0, c.width, c.height);
    const n = data.length, bw = c.width / n; let sum = 0;
    g.fillStyle = col;
    for (let i = 0; i < n; i++) { const v = data[i] / 255; sum += v; const h = Math.max(1, v * c.height); g.fillRect(i * bw, (c.height - h) / 2, bw - 1, h); }
    audioLevel = sum / n; faceSpeak(audioLevel);
  })();
}
$("#mic").onclick = toggleMic;

// ---- visual face: core made of particles (Three.js Points) ----
let faceScene, faceRen, faceCam, facePts, faceMat, faceBase, faceRAF, faceSpeakLvl = 0;
function faceSpeak(l) { faceSpeakLvl = Math.max(faceSpeakLvl, Math.min(1, l * 1.6)); }
function buildFace() {
  const c = $("#facecv"); c.width = c.clientWidth || 260; c.height = 220;
  faceScene = new THREE.Scene(); faceCam = new THREE.PerspectiveCamera(50, c.width / c.height, .1, 100); faceCam.position.z = 3.2;
  faceRen = new THREE.WebGLRenderer({ canvas: c, antialias: true, alpha: true }); faceRen.setSize(c.width, c.height); faceRen.setClearColor(0, 0);
  const N = 1400, pos = new Float32Array(N * 3); faceBase = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) { const a = i * 2.39996, b = Math.acos(1 - 2 * (i + .5) / N), rr = 1; const x = rr * Math.sin(b) * Math.cos(a), y = rr * Math.cos(b), z = rr * Math.sin(b) * Math.sin(a); pos[i * 3] = faceBase[i * 3] = x; pos[i * 3 + 1] = faceBase[i * 3 + 1] = y; pos[i * 3 + 2] = faceBase[i * 3 + 2] = z; }
  const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  faceMat = new THREE.PointsMaterial({ color: new THREE.Color(theme === "green" ? 0x4dffa0 : 0xf5bd3a), size: 0.035, transparent: true, opacity: .9, blending: THREE.AdditiveBlending, depthWrite: false });
  facePts = new THREE.Points(geo, faceMat); faceScene.add(facePts);
  window.__facephos = (hex) => faceMat.color.set(hex);
  (function loop() {
    faceRAF = requestAnimationFrame(loop);
    if (!$("#facewin").classList.contains("on")) return;
    const t = Date.now() / 1000; const breathe = 1 + Math.sin(t * 1.5) * 0.03; const speak = faceSpeakLvl;
    const p = facePts.geometry.attributes.position.array;
    for (let i = 0; i < faceBase.length; i += 3) { const k = breathe + speak * 0.5 * (0.5 + 0.5 * Math.sin(faceBase[i + 1] * 6 + t * 8)); p[i] = faceBase[i] * k; p[i + 1] = faceBase[i + 1] * k; p[i + 2] = faceBase[i + 2] * k; }
    facePts.geometry.attributes.position.needsUpdate = true;
    facePts.rotation.y += 0.003; faceSpeakLvl *= 0.92;
    faceRen.render(faceScene, faceCam);
  })();
}
$("#visual").onclick = () => { const w = $("#facewin"); w.classList.toggle("on"); if (w.classList.contains("on") && !faceScene) buildFace(); };
$("#faceclose").onclick = () => $("#facewin").classList.remove("on");
(function faceDrag() {
  const w = $("#facewin"), h = $("#facehead"); let sx, sy, sl, st, drag = false;
  h.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".x")) return;            // don't start a drag on the close button
    drag = true; sx = e.clientX; sy = e.clientY; sl = w.offsetLeft; st = w.offsetTop;  // offsetParent-relative
    w.style.right = "auto"; w.style.left = sl + "px"; w.style.top = st + "px";
    h.setPointerCapture(e.pointerId);
  });
  h.addEventListener("pointermove", (e) => { if (!drag) return; w.style.left = (sl + e.clientX - sx) + "px"; w.style.top = (st + e.clientY - sy) + "px"; });
  h.addEventListener("pointerup", (e) => { drag = false; try { h.releasePointerCapture(e.pointerId); } catch (_) {} });
})();

// ====================================================================
//  Live data orchestration
// ====================================================================
async function loadCore() {
  try {
    core = await api("/api/core"); setConn(core.status === "ok" ? "online" : core.status, core.status === "ok");
    $("#brand").textContent = (core.name || "BLACK NOIR").toUpperCase();
    $("#ver").textContent = "v" + (core.version || "");
    $("#vbub").textContent = "Связь есть. Ядро " + (core.name || "Black Noir") + " на линии.";
  } catch (e) { setConn("нет связи с ядром", false); $("#vbub").textContent = "Нет связи с ядром…"; }
}
async function loadModules() {
  try { const d = await api("/api/modules"); modules = d.modules || []; render2D(); } catch (e) {}
}

// live notifications derived from real diffs (new tasks/ideas) + /ws/notify
let seenTasks = null, seenIdeas = null;
async function diffNotify() {
  try {
    const td = await api("/api/tasks"); const ids = new Set((td.tasks || []).map((t) => t.id));
    if (seenTasks) [...ids].filter((x) => !seenTasks.has(x)).forEach(() => toast("НОВАЯ ЗАДАЧА В ОЧЕРЕДИ"));
    seenTasks = ids;
    const idd = await api("/api/ideas?limit=60"); const iids = new Set((idd.ideas || []).map((i) => i.id));
    if (seenIdeas) [...iids].filter((x) => !seenIdeas.has(x)).forEach(() => toast("НОВАЯ ИДЕЯ НА РАЗБОРЕ"));
    seenIdeas = iids;
  } catch (e) {}
}
function wsNotify() {
  try {
    const ws = new WebSocket(WS + "/ws/notify");
    ws.onmessage = (ev) => { try { const d = JSON.parse(ev.data); if (d.type !== "hello" && (d.title || d.data)) toast(d.title || d.data); } catch (e) {} };
    ws.onclose = () => setTimeout(wsNotify, 5000);
  } catch (e) { setTimeout(wsNotify, 8000); }
}

async function refresh() {
  await loadCore();
  await Promise.all([loadModules(), loadSystems(), loadTasks(), loadIdeas(), loadProfile(), diffNotify(), pumpActivity()]);
}

// ---------- boot ----------
applyTheme();
render2D();
window.addEventListener("contextmenu", (e) => e.preventDefault());  // no browser context menu (save-image etc.)
setupWindow();
loadBotStatus();
refresh(); setInterval(refresh, 5000);
wsNotify();
checkUpdate();
window.__noirReady = true;
