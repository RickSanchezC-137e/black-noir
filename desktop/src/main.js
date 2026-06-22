// Black Noir HUD — Pip-Boy CRT + 3D core cloud on LIVE data (no demo).
// Thin client over /api/* + /ws/*. Tauri window controls + auto-updater.
// View ported literally from desktop_reference/hud_reference.html; data is live only.
import * as THREE from "three";

const params = new URLSearchParams(location.search);
const isTauri = !!window.__TAURI_INTERNALS__ || !!window.__TAURI__;
// PWA: register service worker so the app is installable on phone/tablet home screen.
if (!isTauri && "serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
const API = (params.get("api") || window.NOIR_API_BASE || (window.__VITE_API_BASE__) ||
  (isTauri ? "https://jarvisgod.duckdns.org" : "")).replace(/\/$/, "");   // "" = same-origin (browser)
const WS = API ? API.replace(/^http/, "ws") : (location.origin.replace(/^http/, "ws"));

// ===== Owner auth — Fallout/Pip-Boy login overlay (replaces native basic_auth popup) =====
(function initAuth() {
  const ov = document.getElementById("login"); if (!ov) return;
  const boot = document.getElementById("lboot"), msg = document.getElementById("lg-msg");
  const lines = ["ИНИЦИАЛИЗАЦИЯ ROBCO INDUSTRIES(TM) MF BOOT AGENT v2.3.0",
    "RETROS BIOS 4.02.08.00 52EE5.E7.E8", "(C) ROBCO INDUST. — UNAUTHORISED ACCESS PROHIBITED",
    "КАНАЛ: jarvisgod.duckdns.org .......... [ OK ]", "SET TERMINAL/INQUIRE",
    ">>> ЗАЩИЩЁННЫЙ СЕАНС УСТАНОВЛЕН"];
  let li = 0, ci = 0;
  function type() {
    if (li >= lines.length) return;
    const ln = lines[li];
    boot.textContent = lines.slice(0, li).join("\n") + (li ? "\n" : "") + ln.slice(0, ci);
    if (ci < ln.length) { ci++; setTimeout(type, 11); }
    else { li++; ci = 0; setTimeout(type, 85); }
  }
  const show = () => { ov.classList.remove("hidden"); type(); const u = document.getElementById("lg-user"); if (u) u.focus(); };
  const hide = () => ov.classList.add("hidden");
  fetch(API + "/api/auth/me").then((r) => r.json()).then((d) => { d && d.authed ? hide() : show(); }).catch(show);
  document.getElementById("lform").addEventListener("submit", async (e) => {
    e.preventDefault(); msg.className = "lmsg"; msg.textContent = "> ПРОВЕРКА ДОСТУПА…";
    const login = (document.getElementById("lg-user").value || "").trim();
    const password = document.getElementById("lg-pass").value || "";
    try {
      const r = await fetch(API + "/api/auth/login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ login, password }) });
      const d = await r.json();
      if (d.ok) { msg.textContent = "> ДОСТУП РАЗРЕШЁН — ЗАГРУЗКА ТЕРМИНАЛА…"; setTimeout(() => location.reload(), 400); }
      else { msg.className = "lmsg err"; msg.textContent = d.reason || "ДОСТУП ЗАПРЕЩЁН"; }
    } catch (err) { msg.className = "lmsg err"; msg.textContent = "ОШИБКА СВЯЗИ С ТЕРМИНАЛОМ"; }
  });
})();
const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
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
  if (!isTauri) { const wb = document.querySelector(".winbar .wbtns"); if (wb) wb.style.display = "none"; return; }
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
let vbTalk = 0;
(function anim() {
  requestAnimationFrame(anim);
  const t = Date.now() / 1000, fig = $("#vbFig"), arm = $("#vbArm"), head = $("#vbHead");
  vbTalk *= 0.96;
  const wave = Math.pow(Math.max(0, Math.sin(t * 0.5)), 6);            // periodic Fallout-style wave
  const bob = Math.sin(t * 2.2) * 2.4 * (1 + vbTalk);
  const armA = Math.sin(t * 6) * 7 + wave * Math.sin(t * 14) * 22 + vbTalk * Math.sin(t * 18) * 10;
  const headA = Math.sin(t * 1.4) * 1.6 * (1 + vbTalk * 4);
  if (fig) fig.setAttribute("transform", `translate(0 ${bob.toFixed(2)})`);
  if (arm) arm.setAttribute("transform", `rotate(${armA.toFixed(2)} 130 120)`);
  if (head) head.setAttribute("transform", `rotate(${headA.toFixed(2)} 100 118)`);
})();

// ---------- companion: system-guide chat + hide/show ----------
(function companion() {
  const screen = $("#screen");
  const show = el("div", "vbshow", "\u25B8 VOLT-BRO"); show.id = "vbshow"; show.title = "показать помощника"; screen.appendChild(show);
  const port = $("#vbport"), chat = $("#vbchat"), ro = $("#vbro");
  const vbAppend = (cls, t) => { const e = el("div", "msg " + cls, esc(t)); $("#vblog").appendChild(e); $("#vblog").scrollTop = 1e9; return e; };
  if (port) port.onclick = (e) => { if (e.target.closest(".vbx")) return; chat.classList.toggle("on"); if (chat.classList.contains("on")) { $("#vbi").focus(); if (!$("#vblog").children.length) vbAppend("sys", "Спроси про систему: кластеры, модули, Governor, самоулучшение…"); } };
  async function vbSend() { const i = $("#vbi"), t = i.value.trim(); if (!t) return; i.value = ""; vbAppend("me", "» " + t); const b = vbAppend("ai", "…"); try { const r = await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: t, agent: "guide", session_id: "guide-companion" }) }); b.textContent = pickReply(r); vbTalk = 1; } catch (e) { b.textContent = "[нет связи]"; b.className = "msg sys"; } }
  if ($("#vbsend")) $("#vbsend").onclick = vbSend;
  if ($("#vbi")) $("#vbi").addEventListener("keydown", (e) => { if (e.key === "Enter") vbSend(); });
  if ($("#vbhide")) $("#vbhide").onclick = (e) => { e.stopPropagation(); ro.style.display = "none"; show.classList.add("on"); localStorage.setItem("noir.vbhidden", "1"); };
  show.onclick = () => { ro.style.display = ""; show.classList.remove("on"); localStorage.removeItem("noir.vbhidden"); };
  if (localStorage.getItem("noir.vbhidden")) { ro.style.display = "none"; show.classList.add("on"); }
})();

// ====================================================================
//  Shared right inspector drawer (module / core / task / idea)
// ====================================================================
const insp = $("#insp"), inspTabs = $("#insp-tabs"), inspBody = $("#insp-body");
$("#insp-x").onclick = () => insp.classList.remove("open");

// ====================================================================
//  Full module view (#modview) — open a module as a complete tab
// ====================================================================
const mv = $("#modview");
$("#mv-x").onclick = () => mv.classList.remove("on");
function improvePanel(b, module) {
  b.innerHTML = `<div style="display:flex;gap:6px;margin-bottom:8px"><input id="imp-i" style="flex:1;background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:6px;border-radius:4px" placeholder="что улучшить в «${esc(module)}»…"/><button class="ico" id="imp-go">УЛУЧШИТЬ</button></div><div id="imp-out" class="m" style="opacity:.7">Builder соберёт изменение в песочнице, прогонит eval и покажет диф — внедрение только по твоему подтверждению (с авто-откатом при провале).</div>`;
  $("#imp-go").onclick = async () => {
    const intent = $("#imp-i").value.trim(); if (!intent) return;
    $("#imp-out").innerHTML = "<div class='empty'>Builder работает + eval… минуту-две</div>";
    try { const r = await api("/api/systems/selfimprove/improve", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ module, intent }) }); renderImprove(r); }
    catch (e) { $("#imp-out").innerHTML = "<div class='empty'>ошибка сборки</div>"; }
  };
}
function renderImprove(r) {
  const out = $("#imp-out"); if (!out) return; const ev = r.eval || {};
  out.innerHTML = `<div class="row"><span>решение</span><span class="chip">${esc(r.decision)}</span></div>`
    + (r.reason ? `<div class="m" style="margin:4px 0">${esc(r.reason)}</div>` : "")
    + (ev.ok !== undefined ? `<div class="row"><span>eval (песочница)</span><span>${ev.ok ? "✓" : "✗"}</span></div>` : "")
    + (r.diff_stat ? `<div class="m" style="white-space:pre-wrap;opacity:.7;margin-top:4px">${esc(r.diff_stat)}</div>` : "")
    + (r.diff ? `<pre style="max-height:220px;overflow:auto;font-size:10px;border:1px solid rgba(127,127,127,.5);border-radius:4px;padding:6px;white-space:pre-wrap">${esc(r.diff)}</pre>` : "")
    + (r.decision === "would_promote" && r.token ? `<button class="ico" id="imp-prom">ВНЕДРИТЬ (подтвердить)</button>` : "");
  const pr = $("#imp-prom"); if (pr) pr.onclick = async () => { pr.textContent = "…"; try { const p = await api("/api/systems/selfimprove/improve/promote", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: r.token }) }); toast(p.ok ? "Внедрено, ядро перезапущено" : ("Откат/отказ: " + (p.reason || ""))); if (p.ok) setTimeout(loadModules, 4000); } catch (e) { toast("Внедрение не удалось"); } };
}

function mvOpen(title, sub) { mv.classList.add("on"); $("#mv-title").textContent = title; $("#mv-sub").textContent = sub || ""; }
let mvTimer = null;
function clearMvTimer() { if (mvTimer) { clearInterval(mvTimer); mvTimer = null; } }
function mvLive(fn, ms) { clearMvTimer(); fn(); mvTimer = setInterval(() => { if (!mv.classList.contains("on")) return clearMvTimer(); fn(); }, ms || 4000); }
function mvTabset(defs, def) {
  const tabs = $("#mv-tabs"), body = $("#mv-body"); tabs.innerHTML = ""; let active = def;
  const render = async () => {
    clearMvTimer();
    tabs.querySelectorAll(".mvtab").forEach((x) => x.classList.toggle("on", x.dataset.k === active));
    body.innerHTML = "<div class='empty'>загрузка…</div>";
    try { await defs.find((d) => d[0] === active)[2](body); } catch (e) { body.innerHTML = `<div class='empty'>нет данных (${esc(e.message)})</div>`; }
  };
  defs.forEach(([k, lbl]) => { const t = el("span", "mvtab", lbl); t.dataset.k = k; t.onclick = () => { active = k; render(); }; tabs.appendChild(t); });
  render();
}
function mvDetail(html, backFn) {
  clearMvTimer(); const body = $("#mv-body");
  body.innerHTML = `<div style="margin-bottom:8px"><button class="ico" id="mv-back">← НАЗАД</button></div>` + html;
  const bk = $("#mv-back"); if (bk) bk.onclick = backFn;
}
const J = (x) => esc(JSON.stringify(x));
async function openHyp(id, backFn) {
  const d = await api(`/api/systems/selfimprove/hypothesis/${id}`); const h = d.hypothesis, e = d.experiment, v = d.verdict;
  let html = `<h5>ГИПОТЕЗА · <span class="chip">${esc(h.status)}</span></h5><div style="margin:6px 0">${esc(h.summary || h.intent)}</div>`
    + `<div class="row"><span>источник</span><span>${esc(h.source)}</span></div>`
    + `<div class="row"><span>тип · домен</span><span>${esc(h.kind)} · ${esc(h.domain)}</span></div>`
    + `<div class="row"><span>impact / confidence / cost</span><span>${h.impact} / ${h.confidence} / ${h.cost}</span></div>`
    + `<div class="row"><span>приоритет</span><span>${h.priority}</span></div>`
    + (h.intent && h.intent !== h.summary ? `<div class="m" style="margin-top:6px">${esc(h.intent)}</div>` : "")
    + (h.archived_reason ? `<div class="m" style="margin-top:6px;color:#ff7a6b">причина: ${esc(h.archived_reason)}</div>` : "");
  html += `<h5 style="margin-top:12px">ХОД АНАЛИЗА</h5>`;
  if (e) html += `<div class="mvcard">эксперимент ${esc((e.id || "").slice(0, 8))} · <span class="chip">${esc(e.status)}</span><div class="m">конституция: ${J(e.constitution)}</div><div class="m">eval: ${J(e.eval)}</div></div>`;
  else html += `<div class="empty">эксперимент ещё не запускался (в очереди)</div>`;
  if (v) html += `<div class="mvcard">вердикт: <span class="chip">${esc(v.decision)}</span><div class="m">governor: ${J(v.governor)}</div><div class="m">quality: ${J(v.quality_gate)}</div></div>`;
  if (h.status === "rejected" || h.status === "skip") html += `<h5 style="margin-top:12px">ВЕРНУТЬ НА ДОРАБОТКУ</h5><div style="display:flex;gap:6px"><input id="rw-i" style="flex:1;background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:6px;border-radius:4px" placeholder="промт к доработке (что учесть)…"/><button class="ico" id="rw-go">ВЕРНУТЬ В ОЧЕРЕДЬ</button></div>`;
  mvDetail(html, backFn);
  const rw = $("#rw-go"); if (rw) rw.onclick = async () => { await api(`/api/systems/selfimprove/hypothesis/${id}/rework`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ prompt: $("#rw-i").value }) }); toast("Гипотеза возвращена в очередь на доработку"); backFn(); };
}
async function openExp(id, backFn) {
  const d = await api(`/api/systems/selfimprove/experiment/${id}`); const e = d.experiment, v = d.verdict;
  const ev = (e.eval && typeof e.eval === "object") ? e.eval : {};
  const co = (e.constitution && typeof e.constitution === "object") ? e.constitution : {};
  const html = `<h5>ЭКСПЕРИМЕНТ ${esc((e.id || "").slice(0, 8))}</h5>`
    + `<div class="row"><span>домен</span><span>${esc(e.domain)}</span></div>`
    + `<div class="row"><span>статус</span><span class="chip">${esc(e.status)}</span></div>`
    + `<div class="row"><span>гипотеза</span><span>${esc((e.hypothesis_id || "").slice(0, 8))}</span></div>`
    + `<div class="row"><span>начат</span><span>${esc((e.started_at || "").slice(0, 19).replace("T", " "))}</span></div>`
    + `<h5 style="margin-top:10px">КОНСТИТУЦИЯ</h5><div class="row"><span>пройдена</span><span>${co.passed ? "✓" : "✗"}</span></div>` + (co.reason ? `<div class="m">${esc(co.reason)}</div>` : "")
    + `<h5 style="margin-top:10px">EVAL</h5>`
    + (Object.keys(ev).length ? `<div class="row"><span>тесты</span><span>${ev.passed ?? "?"}/${ev.total ?? "?"}</span></div><div class="row"><span>успех</span><span>${ev.success_rate ?? "?"}</span></div><div class="row"><span>нарушений безопасности</span><span>${ev.safety_violations ?? 0}</span></div><div class="row"><span>итог</span><span class="chip">${ev.ok ? "OK" : "FAIL"}</span></div>` : "<div class='empty'>нет данных eval</div>")
    + (v ? `<div class="mvcard" style="margin-top:10px">вердикт: <span class="chip">${esc(v.decision)}</span></div>` : "");
  mvDetail(html, backFn);
}
async function improveModulesList(b) {
  b.innerHTML = `<div class="m" style="margin-bottom:8px;opacity:.7">выбери модуль — как он построен сейчас, лог улучшений и улучшить:</div>`
    + modules.map((m) => `<div class="mvcard" data-im="${esc(m.name)}" style="cursor:pointer">${esc(m.display_name || m.name)} <span class="chip">${esc(m.cluster)}</span><div class="m">${esc(m.status)} · v${esc(m.version)} · ${(m.tools || []).length} tools</div></div>`).join("") || "<div class='empty'>нет модулей</div>";
  b.querySelectorAll("[data-im]").forEach((c) => c.onclick = () => openModuleImprove(c.getAttribute("data-im"), () => improveModulesList(b)));
}
async function openModuleImprove(id, backFn) {
  const s = await api(`/api/modules/${id}/source`);
  const html = `<h5>${esc(id)} — КАК ПОСТРОЕН СЕЙЧАС</h5><div class="m">файлы: ${esc((s.files || []).join(", ")) || "—"}</div>`
    + (s.manifest ? `<pre style="max-height:200px;overflow:auto;font-size:10px;border:1px solid rgba(127,127,127,.5);border-radius:4px;padding:6px;white-space:pre-wrap">${esc(s.manifest)}</pre>` : "")
    + `<h5 style="margin-top:10px">ЛОГ УЛУЧШЕНИЙ</h5>` + ((s.improvements || []).map((v) => `<div class="row"><span>v${esc(v.version)} · ${esc((v.created_at || "").slice(0, 16).replace("T", " "))}</span><span class="chip">${v.active ? "активна" : ""}</span></div>`).join("") || "<div class='empty'>пока без улучшений</div>")
    + `<h5 style="margin-top:10px">УЛУЧШИТЬ</h5><div id="imp-host"></div>`;
  mvDetail(html, backFn);
  improvePanel($("#imp-host"), id);
}
async function renderAiList(b) {
  const r = await api("/api/core/ai"); const list = r.ai || [];
  b.innerHTML = `<div style="margin-bottom:8px"><button class="ico" id="ai-add">+ ДОБАВИТЬ ИИ</button></div>`
    + list.map((a) => `<div class="mvcard" data-ai="${esc(a.id)}" style="cursor:pointer"><b>${esc(a.name)}</b> <span class="chip">${esc(a.role)}</span> <span class="chip">${a.active ? "вкл" : "выкл"}</span><div class="m">${esc(a.model)}</div></div>`).join("");
  const ad = $("#ai-add"); if (ad) ad.onclick = async () => { const n = prompt("Имя нового ИИ:"); if (!n) return; await api("/api/core/ai", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: n }) }); toast("ИИ добавлен"); renderAiList(b); };
  b.querySelectorAll("[data-ai]").forEach((c) => c.onclick = () => openAiDetail(c.getAttribute("data-ai"), () => renderAiList(b)));
}
async function openAiDetail(aid, backFn) {
  const r = await api("/api/core/ai"); const a = (r.ai || []).find((x) => x.id === aid) || { id: aid };
  const sid = "agent:ai:" + aid;
  const ip = "background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:5px;border-radius:4px";
  const html = `<h5>НАСТРОЙКИ</h5>`
    + `<div class="row"><span>имя</span><input id="ai-name" value="${esc(a.name || "")}" style="${ip}"/></div>`
    + `<div class="row"><span>роль</span><input id="ai-role" value="${esc(a.role || "")}" style="${ip}"/></div>`
    + `<div class="row"><span>модель</span><input id="ai-model" value="${esc(a.model || "")}" style="${ip}"/></div>`
    + `<div class="row"><span>активен</span><input type="checkbox" id="ai-act" ${a.active ? "checked" : ""}/></div>`
    + `<h5 style="margin-top:8px">ПЕРСОНА / ИНСТРУКЦИЯ</h5><textarea id="ai-sys" style="${ip};width:100%;min-height:70px">${esc(a.system || "")}</textarea>`
    + `<div style="margin-top:8px;display:flex;gap:6px"><button class="ico" id="ai-save">СОХРАНИТЬ</button><button class="ico" id="ai-log">ЛОГ ОТВЕТОВ</button></div>`
    + `<h5 style="margin-top:10px">ЛИЧНЫЙ ЧАТ</h5><div id="ai-chathost"></div>`;
  mvDetail(html, backFn);
  agentChat($("#ai-chathost"), "ai:" + aid, "написать " + (a.name || "ИИ") + "…");
  $("#ai-save").onclick = async () => { await api("/api/core/ai/" + aid, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: $("#ai-name").value, role: $("#ai-role").value, model: $("#ai-model").value, system: $("#ai-sys").value, active: $("#ai-act").checked }) }); toast("Сохранено"); };
  $("#ai-log").onclick = async () => { const h = await api("/api/chat/history?session_id=" + encodeURIComponent(sid)); const box = $("#ai-chathost"); box.innerHTML = (h.messages || []).map((m) => `<div class="msg ${m.role === "user" ? "me" : "ai"}">${esc(m.content)}</div>`).join("") || "<div class='empty'>лог пуст</div>"; };
}
function openCore() {
  mvOpen("ЯДРО", "оркестратор + совет моделей");
  async function rOverview(b) {
    let m = {}, council = [], tasks = 0, ideas = 0, c = {};
    try { m = await api("/api/systems/metrics"); } catch (e) {}
    try { council = (await api("/api/core/council")).council || []; } catch (e) {}
    try { tasks = ((await api("/api/tasks")).tasks || []).filter((x) => x.status === "pending" || x.status === "running").length; } catch (e) {}
    try { ideas = ((await api("/api/ideas")).ideas || []).length; } catch (e) {}
    try { c = await api("/api/core"); } catch (e) {}
    const work = council.filter((x) => x.ok === true).length;
    b.innerHTML = `<div class="syswrap">`
      + `<div class="card"><h5>ЯДРО</h5><div class="row"><span>статус</span><span class="chip">${esc(c.status)}</span></div><div class="row"><span>версия</span><span>${esc(c.version)}</span></div><div class="row"><span>Governor</span><span>${esc(c.governor)}</span></div><div class="row"><span>оркестратор</span><span>${esc(c.model)}</span></div></div>`
      + `<div class="card"><h5>ХОСТ (live)</h5><div class="row"><span>CPU</span><span>${m.cpu ?? "?"}%</span></div><div class="bar"><i style="width:${Math.min(100, m.cpu || 0)}%"></i></div><div class="row"><span>RAM</span><span>${m.ram ?? "?"}%</span></div><div class="bar"><i style="width:${m.ram || 0}%"></i></div><div class="row"><span>uptime</span><span>${esc(m.uptime || "?")}</span></div></div>`
      + `<div class="card"><h5>СОВЕТ (${work}/${council.length} работает)</h5>${council.map((x) => `<div class="row"><span>${esc(x.name)}</span><span>${x.ok === true ? "✓" : (x.enabled ? "✗" : "—")}${x.active ? "" : " (откл)"}</span></div>`).join("")}</div>`
      + `<div class="card"><h5>СИСТЕМА</h5><div class="row"><span>модулей</span><span>${modules.length}</span></div><div class="row"><span>активных задач</span><span>${tasks}</span></div><div class="row"><span>идей</span><span>${ideas}</span></div></div>`
      + `</div>`;
  }
  async function rCouncil(b) {
    b.innerHTML = "<div class='empty'>проверяю модели (пинг)…</div>";
    const r = await api("/api/core/council"); const cl = r.council || [];
    const stat = (m) => m.ok === true ? "✓ работает" : (m.ok === false ? ("✗ " + esc((m.error || "не отвечает").slice(0, 36))) : (m.enabled ? "проверяю" : "нет ключа"));
    b.innerHTML = `<h5>МОДЕЛИ СОВЕТА — работают ${cl.filter((m) => m.ok === true).length}/${cl.length}</h5>`
      + cl.map((m) => `<div class="mvcard"><div class="row"><span><b>${esc(m.name)}</b> <span class="chip">${esc(m.model)}</span></span><span>${stat(m)}</span></div>${m.balance ? `<div class="m" style="opacity:.85">баланс: ${esc(m.balance)}</div>` : ""}<div style="margin-top:6px;display:flex;gap:6px;align-items:center">`
        + (m.enabled ? `<button class="ico" data-tog="${esc(m.id)}" data-act="${m.active ? 0 : 1}">${m.active ? "ВЫКЛ из совета" : "ВКЛ в совет"}</button><span class="chip">${m.active ? "в совете" : "отключён"}</span>` : `<button class="ico" data-key="${esc(m.id)}">+ ДОБАВИТЬ КЛЮЧ</button>`)
        + `</div></div>`).join("")
      + `<div class="m" style="margin-top:8px;opacity:.7">Запрос идёт ко всем включённым (✓ работают) моделям параллельно; упавшие выбывают; Opus синтезирует. Статус — реальный пинг (кэш 5 мин). Серые без ключа — доступны к добавлению.</div>`;
    b.querySelectorAll("[data-tog]").forEach((x) => x.onclick = async () => { await api(`/api/core/council/${x.getAttribute("data-tog")}/toggle`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ active: x.getAttribute("data-act") === "1" }) }); toast("Совет обновлён"); rCouncil(b); });
    b.querySelectorAll("[data-key]").forEach((x) => x.onclick = async () => { const k = prompt("API-ключ для " + x.getAttribute("data-key") + ":"); if (!k) return; toast("Сохраняю ключ, ядро перезапустится…"); try { await api(`/api/core/council/${x.getAttribute("data-key")}/key`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: k }) }); } catch (e) {} setTimeout(() => rCouncil(b), 7000); });
  }
  mvTabset([
    ["overview", "ОБЗОР", rOverview],
    ["council", "СОВЕТ", rCouncil],
    ["ai", "4 ИИ", async (b) => renderAiList(b)],
    ["chat", "ЧАТ С ЯДРОМ", async (b) => agentChat(b, "core", "сообщение ядру…")],
  ], "overview");
}
function openModule(id) {
  if (id === "selfimprove") return openSelfImprove();
  if (id === "intake") return openIntake();
  if (id === "factory") return openFactory();
  const m = modules.find((x) => x.name === id) || { name: id };
  mvOpen(m.display_name || m.name, (m.cluster || "") + " · " + (m.status || ""));
  mvTabset([
    ["overview", "ОБЗОР", async (b) => { b.innerHTML = `<div class="row"><span>статус</span><span class="chip">${esc(m.status)}</span></div><div class="row"><span>кластер</span><span>${esc(m.cluster)}</span></div><div class="row"><span>версия</span><span>v${esc(m.version)}</span></div><div class="row"><span>инструменты</span><span>${esc((m.tools || []).join(", "))}</span></div>`; }],
    ["logs", "ЛОГИ (live)", async (b) => mvLive(async () => { const d = await api(`/api/modules/${id}/logs?tail=60`); b.innerHTML = (d.logs || []).map((l) => `<div class="tlog">${esc((l.ts || "").slice(11, 19))} [${esc(l.level)}] ${esc(l.event)} ${esc(l.payload || "")}</div>`).join("") || "<div class='empty'>нет логов</div>"; }, 4000)],
    ["mem", "ПАМЯТЬ", async (b) => { const d = await api(`/api/memory?module=${id}`); b.innerHTML = (d.items || []).map((x) => `<div class="row"><span>${esc(x.value)}</span><span class="chip">${esc(x.type || x.key)}</span></div>`).join("") || "<div class='empty'>нет данных</div>"; }],
    ["cfg", "НАСТРОЙКИ", async (b) => {
      const cfg = m.config || [];
      const inp = "background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:3px 6px;border-radius:3px";
      let html = `<div class="row"><span>включён</span><span class="chip">${m.enabled ? "да" : "нет"}</span></div><div style="margin:8px 0"><button class="ico" id="mv-tog">${m.enabled ? "ОТКЛЮЧИТЬ" : "ВКЛЮЧИТЬ"}</button></div>`;
      if (cfg.length) {
        html += `<h5>НАСТРОЙКИ МОДУЛЯ</h5>` + cfg.map((f) => {
          const v = f.value !== undefined ? f.value : (f.default !== undefined ? f.default : "");
          if (f.type === "toggle") return `<div class="row"><span>${esc(f.label || f.key)}</span><input type="checkbox" data-ck="${esc(f.key)}" ${(v === true || String(v) === "true") ? "checked" : ""}/></div>`;
          if (f.type === "select") return `<div class="row"><span>${esc(f.label || f.key)}</span><select data-ck="${esc(f.key)}" style="${inp}">${(f.options || []).map((o) => `<option ${String(v) === String(o) ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`;
          return `<div class="row"><span>${esc(f.label || f.key)}</span><input type="${f.type === "number" ? "number" : "text"}" data-ck="${esc(f.key)}" value="${esc(v)}" style="${inp}"/></div>`;
        }).join("") + `<div style="margin-top:8px"><button class="ico" id="cfg-save">СОХРАНИТЬ</button></div>`;
      } else html += `<div class="m" style="opacity:.6;margin-top:6px">у модуля нет настраиваемых параметров</div>`;
      b.innerHTML = html;
      const t = $("#mv-tog"); if (t) t.onclick = async () => { await api(`/api/modules/${id}/${m.enabled ? "disable" : "enable"}`, { method: "POST" }); await loadModules(); openModule(id); };
      const sv = $("#cfg-save"); if (sv) sv.onclick = async () => { for (const e of b.querySelectorAll("[data-ck]")) { const key = e.getAttribute("data-ck"); const val = e.type === "checkbox" ? e.checked : e.value; await api(`/api/modules/${id}/config`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key, value: val }) }); } toast("Настройки сохранены"); await loadModules(); };
    }],
    ["improve", "УЛУЧШИТЬ", async (b) => improvePanel(b, id)],
    ["chat", "ЧАТ-АГЕНТ", async (b) => agentChat(b, "module:" + id, "агенту " + id + "…")],
  ], "overview");
}
async function openBuildDetail(bid, backFn) {
  const x = await api(`/api/modules/factory/build/${bid}`);
  $("#mv-sub").textContent = (x.name || x.repo || bid);
  const html = `<div class="row"><span>статус сборки</span><span class="chip">${esc(x.status)}</span></div>`
    + `<div class="row"><span>прогресс</span><span>${x.progress || 0}%</span></div><div class="bar"><i style="width:${x.progress || 0}%"></i></div>`
    + `<div class="row"><span>тип</span><span class="chip">${esc(x.kind)}</span></div>`
    + `<div class="row"><span>кластер</span><span>${esc(x.cluster)}</span></div>`
    + (x.repo ? `<div class="row"><span>репозиторий</span><span>${esc(x.repo)}</span></div>` : "")
    + (x.purpose ? `<h5 style="margin-top:10px">ЧТО / ЗАЧЕМ / КУДА</h5><div class="m" style="opacity:.88">${esc(x.purpose)}</div>` : "")
    + (x.reason ? `<h5 style="margin-top:10px">РЕЗУЛЬТАТ</h5><div class="m">${esc(x.reason)}</div>` : "")
    + (x.log ? `<h5 style="margin-top:10px">ЛОГ СБОРКИ</h5><pre style="max-height:200px;overflow:auto;font-size:10px;border:1px solid rgba(127,127,127,.5);border-radius:4px;padding:6px;white-space:pre-wrap">${esc(x.log)}</pre>` : "")
    + (x.status === "ready" && x.token ? `<div style="margin-top:10px"><button class="ico" id="bd-prom">ВНЕДРИТЬ (подтвердить)</button></div>` : "");
  mvDetail(html, backFn);
  const bp = $("#bd-prom"); if (bp) bp.onclick = async () => { const r = await api("/api/modules/factory/promote", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: x.token }) }); toast(r.ok ? "Модуль создан" : ("Отказ: " + (r.reason || ""))); if (r.ok) setTimeout(loadModules, 4000); backFn(); };
}
function openFactory() {
  mvOpen("ФАБРИКА МОДУЛЕЙ", "C4 · автономная сборка (off-core) · заказ — в чате с агентом");
  const COLS = [["ОЧЕРЕДЬ", ["queued"]], ["СБОРКА", ["building"]], ["ГОТОВО", ["ready"]], ["ОШИБКА", ["failed"]]];
  async function render(b) {
    const q = await api("/api/modules/factory/queue"); const builds = q.builds || [];
    b.innerHTML = `<div style="display:flex;gap:6px;align-items:center;margin-bottom:10px;flex-wrap:wrap"><button class="ico" id="f-tick">СОБРАТЬ СЛЕДУЮЩИЙ СЕЙЧАС</button><button class="ico" id="f-ref">ОБНОВИТЬ</button><span class="m" style="opacity:.7">Заказать модуль — во вкладке «ЧАТ-АГЕНТ»: просто опиши, что нужно.</span></div>`
      + `<div class="mvkb" style="grid-template-columns:repeat(4,1fr)">${COLS.map(([lbl, sts]) => { const here = builds.filter((x) => sts.includes(x.status)); return `<div><h4>${lbl} · ${here.length}</h4>${here.map((x) => `<div class="mvcard" data-build="${esc(x.id)}" style="cursor:pointer"><b>${esc(x.name || x.repo || x.id)}</b> <span class="chip">${esc(x.kind)}</span><div class="bar" style="margin:4px 0 2px"><i style="width:${x.progress || 0}%"></i></div><div class="m">${x.progress || 0}%</div>${x.status === "ready" && x.token ? `<div style="margin-top:6px"><button class="ico" data-prom="${esc(x.token)}" onclick="event.stopPropagation()">ВНЕДРИТЬ</button></div>` : ""}</div>`).join("") || "<div class='empty'>—</div>"}</div>`; }).join("")}</div>`
      + `<h5 style="margin-top:12px">МОДУЛИ СЕЙЧАС (${modules.length})</h5>` + modules.map((m) => `<div class="row"><span>${esc(m.display_name || m.name)}</span><span class="chip">${esc(m.cluster)}</span></div>`).join("");
    $("#f-ref").onclick = () => render(b);
    $("#f-tick").onclick = async () => { toast("Фабрика собирает следующий из очереди…"); try { const r = await api("/api/modules/factory/tick", { method: "POST" }); toast(r.ran ? ("Сборка: " + (r.verdict || r.error || "")) : "очередь пуста"); } catch (e) { toast("ошибка сборки"); } render(b); };
    b.querySelectorAll("[data-build]").forEach((c) => c.onclick = () => openBuildDetail(c.getAttribute("data-build"), () => render(b)));
    b.querySelectorAll("[data-prom]").forEach((c) => c.onclick = async () => { const r = await api("/api/modules/factory/promote", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: c.getAttribute("data-prom") }) }); toast(r.ok ? "Модуль создан, ядро перезапущено" : ("Отказ: " + (r.reason || ""))); if (r.ok) setTimeout(loadModules, 4000); render(b); });
  }
  mvTabset([["queue", "КАНБАН СБОРОК", render], ["chat", "ЧАТ-АГЕНТ (заказать)", async (b) => agentChat(b, "module:factory", "опиши модуль, который нужен…")]], "queue");
}
function openIntake() {
  mvOpen("РАЗБОР ВХОДЯЩЕГО", "C4 · приём/сортировка → самоулучшение");
  async function render(b) {
    const d = await api("/api/ideas?limit=60"); const it = d.ideas || [];
    const cols = [["НА РАЗБОРЕ", ["new", "review"]], ["ХОРОШИЕ → самоулучшение", ["accepted"]], ["ПЛОХИЕ", ["rejected"]]];
    b.innerHTML = `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">`
      + `<select id="mvi-src" style="background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:6px;border-radius:4px"><option value="repo">GitHub-репо</option><option value="youtube">YouTube</option><option value="reel">Рилс</option><option value="link">ссылка</option><option value="video">видео</option><option value="text">текст</option></select>`
      + `<input id="mvi-val" placeholder="ссылка / репо / текст…" style="flex:1;min-width:220px;background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:6px;border-radius:4px"/>`
      + `<button class="ico" id="mvi-go">РАЗОБРАТЬ</button></div>`
      + `<div class="mvkb">${cols.map(([lbl, sts]) => { const here = it.filter((i) => sts.includes(i.status)); return `<div><h4>${lbl} · ${here.length}</h4>${here.map((i) => `<div class="mvcard" data-idea="${esc(i.id)}" style="cursor:pointer">${esc(i.text)}<div class="bar" style="margin:4px 0 2px"><i style="width:${i.progress || 0}%"></i></div><div class="m">${esc(i.status)} · ${i.progress || 0}%</div></div>`).join("") || "<div class='empty'>—</div>"}</div>`; }).join("")}</div>`;
    b.querySelectorAll("[data-idea]").forEach((c) => c.onclick = () => openIdeaDetail(c.getAttribute("data-idea"), () => openIntake()));
    $("#mvi-go").onclick = async () => { const src = $("#mvi-src").value, val = $("#mvi-val").value.trim(); if (!val) return; $("#mvi-go").textContent = "…"; try { const r = await api("/api/ideas/intake", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ source: src, value: val }) }); toast("Разбор: " + (r.category || "?") + (r.routed ? " → самоулучшение" : "")); } catch (e) { toast("ошибка разбора"); } render(b); };
  }
  mvTabset([["board", "РАЗБОР", render], ["chat", "ЧАТ-АГЕНТ", async (b) => agentChat(b, "module:intake", "агенту разбора входящего…")]], "board");
}
function openSelfImprove() {
  mvOpen("САМОУЛУЧШЕНИЕ", "C4 · автономный контур 24/7");
  const HCOLS = [["ОЧЕРЕДЬ", ["queued", "new"]], ["ПРИНЯТО", ["promoted", "confirmed"]], ["ОТКЛОНЕНО", ["rejected", "skip"]]];
  const board = () => api("/api/systems/selfimprove/board");
  async function rOverview(b) {
    const d = await board(); const bd = d.budget || {}, a = (d.analysis || {}).signals || {};
    const byS = {}; (d.hypotheses || []).forEach((h) => byS[h.status] = (byS[h.status] || 0) + 1);
    const act = (d.versions || []).filter((v) => v.active).length;
    b.innerHTML = `<div class="syswrap">`
      + `<div class="card"><h5>ГИПОТЕЗЫ</h5>${Object.entries(byS).map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span>${v}</span></div>`).join("") || "<div class='empty'>—</div>"}</div>`
      + `<div class="card"><h5>КОНТУР</h5><div class="row"><span>Экспериментов</span><span>${d.experiments.length}</span></div><div class="row"><span>Версий (активных)</span><span>${d.versions.length} (${act})</span></div><div class="row"><span>Модулей</span><span>${modules.length}</span></div></div>`
      + `<div class="card"><h5>БЮДЖЕТ (сегодня)</h5>${Object.entries(bd).map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("") || "<div class='empty'>—</div>"}</div>`
      + `<div class="card"><h5>САМОАНАЛИЗ</h5><div class="row"><span>Сигналов</span><span>${a.total_findings || 0}</span></div><div class="row"><span>сбои/модули/задачи</span><span>${a.exec_failures || 0}/${a.module_errors || 0}/${a.task_errors || 0}</span></div><div style="margin-top:8px"><button class="ico" id="mv-an">ЗАПУСТИТЬ САМОАНАЛИЗ</button></div></div>`
      + `</div>`;
    const an = $("#mv-an"); if (an) an.onclick = async () => { an.textContent = "…"; await api("/api/systems/selfimprove/analyze", { method: "POST" }); toast("Самоанализ выполнен"); rOverview(b); };
  }
  async function rHyps(b) {
    const d = await board();
    b.innerHTML = `<div class="mvkb">${HCOLS.map(([lbl, sts]) => { const here = d.hypotheses.filter((h) => sts.includes(h.status)); return `<div><h4>${lbl} · ${here.length}</h4>${here.map((h) => `<div class="mvcard" data-h="${esc(h.id)}" style="cursor:pointer">${esc(h.summary || h.intent || h.id)}<div class="m">${esc(h.kind || "")} · ${esc(h.domain || "")} · prio ${h.priority ?? ""}</div></div>`).join("") || "<div class='empty'>—</div>"}</div>`; }).join("")}</div>`;
    b.querySelectorAll("[data-h]").forEach((c) => c.onclick = () => openHyp(c.getAttribute("data-h"), () => rHyps(b)));
  }
  async function rExp(b) {
    const d = await board();
    b.innerHTML = `<h5>ЭКСПЕРИМЕНТЫ</h5>` + (d.experiments.map((e) => `<div class="mvcard" data-e="${esc(e.id)}" style="cursor:pointer">${esc(e.domain)} <span class="chip">${esc(e.status)}</span><div class="m">${esc((e.started_at || "").slice(0, 19).replace("T", " "))}</div></div>`).join("") || "<div class='empty'>—</div>") + `<h5 style="margin-top:12px">ВЕРСИИ</h5>` + (d.versions.map((v) => `<div class="row"><span>${esc(v.domain || "")} v${esc(v.version ?? "")}</span><span class="chip">${v.active ? "активна" : ""}</span></div>`).join("") || "<div class='empty'>—</div>");
    b.querySelectorAll("[data-e]").forEach((c) => c.onclick = () => openExp(c.getAttribute("data-e"), () => rExp(b)));
  }
  async function rActivity(b) {
    mvLive(async () => { const d = await board(); b.innerHTML = (d.audit || []).map((a) => `<div class="tlog">${esc((a.created_at || "").slice(11, 19))} ${esc(a.module)}.${esc(a.tool)} → ${esc(a.decision)} ${a.ok ? "ok" : "fail"}</div>`).join("") || "<div class='empty'>—</div>"; }, 4000);
  }
  async function rTasks(b) {
    const d = await board(); const byH = {}; (d.experiments || []).forEach((e) => { (byH[e.hypothesis_id] = byH[e.hypothesis_id] || []).push(e); });
    b.innerHTML = (d.hypotheses || []).slice(0, 24).map((h) => `<div class="mvcard"><b data-h="${esc(h.id)}" style="cursor:pointer">${esc(h.summary || h.intent || h.id)}</b> <span class="chip">${esc(h.status)}</span>` + ((byH[h.id] || []).map((e) => `<div class="m" data-e="${esc(e.id)}" style="cursor:pointer">↳ эксперимент ${esc((e.id || "").slice(0, 8))} · ${esc(e.status)}</div>`).join("") || "<div class='m' style='opacity:.5'>подзадач нет</div>") + `</div>`).join("") || "<div class='empty'>нет задач контура</div>";
    b.querySelectorAll("[data-h]").forEach((c) => c.onclick = () => openHyp(c.getAttribute("data-h"), () => rTasks(b)));
    b.querySelectorAll("[data-e]").forEach((c) => c.onclick = () => openExp(c.getAttribute("data-e"), () => rTasks(b)));
  }
  mvTabset([
    ["overview", "ОБЗОР", rOverview],
    ["hyps", "ГИПОТЕЗЫ", rHyps],
    ["exp", "ЭКСПЕРИМЕНТЫ/ВЕРСИИ", rExp],
    ["activity", "ЛОГ КОНТУРА (live)", rActivity],
    ["tasks", "ЗАДАЧИ/ПОДЗАДАЧИ", rTasks],
    ["improve", "УЛУЧШИТЬ", improveModulesList],
    ["chat", "ЧАТ-АГЕНТ", async (b) => agentChat(b, "module:selfimprove", "агенту самоулучшения…")],
  ], "overview");
}

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
let VB = { x: 0, y: 0, w: 1000, h: 640 }, vbAuto = true;   // map viewBox (pan/zoom/auto-fit)
function applyVB() { const svg = $("#s2svg"); if (svg) svg.setAttribute("viewBox", `${VB.x.toFixed(1)} ${VB.y.toFixed(1)} ${VB.w.toFixed(1)} ${VB.h.toFixed(1)}`); }
function fitVB() {
  const xs = [500], ys = [320]; Object.values(s2nodes).forEach((n) => { xs.push(n.x); ys.push(n.y); });
  const minX = Math.min(...xs) - 160, maxX = Math.max(...xs) + 160, minY = Math.min(...ys) - 100, maxY = Math.max(...ys) + 100;
  VB = { x: minX, y: minY, w: Math.max(420, maxX - minX), h: Math.max(320, maxY - minY) }; applyVB();
}
function setupPanZoom() {
  const svg = $("#s2svg"); if (!svg || svg.__pz) return; svg.__pz = 1;
  const pts = new Map();              // active pointers: id -> {x,y}
  let pan = false, sx, sy, ox, oy;    // 1-finger pan baseline
  let pinch = null;                   // last 2-finger frame {dist,cx,cy}
  const toWorld = (cx, cy, r) => ({ x: VB.x + (cx - r.left) / r.width * VB.w, y: VB.y + (cy - r.top) / r.height * VB.h });
  const zoomAt = (cx, cy, f, r) => { vbAuto = false; const w0 = toWorld(cx, cy, r);
    VB.w = Math.max(120, Math.min(3000, VB.w * f)); VB.h = Math.max(80, Math.min(2000, VB.h * f));
    VB.x = w0.x - (cx - r.left) / r.width * VB.w; VB.y = w0.y - (cy - r.top) / r.height * VB.h; applyVB(); };

  svg.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".nd") && pts.size === 0) return;   // single tap on a node opens it
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try { svg.setPointerCapture(e.pointerId); } catch (_) {}
    if (pts.size === 1) { pan = true; sx = e.clientX; sy = e.clientY; ox = VB.x; oy = VB.y; }
    else { pan = false; pinch = null; }                      // 2nd finger down → pinch begins
  });
  svg.addEventListener("pointermove", (e) => {
    if (!pts.has(e.pointerId)) return;
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const r = svg.getBoundingClientRect();
    if (pts.size >= 2) {                                      // pinch-zoom + two-finger pan
      const [a, b] = [...pts.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y), cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2;
      if (pinch && dist > 0) zoomAt(cx, cy, pinch.dist / dist, r);
      pinch = { dist, cx, cy };
      return;
    }
    if (pan) { VB.x = ox - (e.clientX - sx) * VB.w / r.width; VB.y = oy - (e.clientY - sy) * VB.h / r.height; vbAuto = false; applyVB(); }
  });
  const up = (e) => {
    pts.delete(e.pointerId); try { svg.releasePointerCapture(e.pointerId); } catch (_) {}
    if (pts.size < 2) pinch = null;
    if (pts.size === 1) { const p = [...pts.values()][0]; pan = true; sx = p.x; sy = p.y; ox = VB.x; oy = VB.y; }
    else if (pts.size === 0) pan = false;
  };
  svg.addEventListener("pointerup", up);
  svg.addEventListener("pointercancel", up);
  svg.addEventListener("wheel", (e) => { e.preventDefault(); const r = svg.getBoundingClientRect(); zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 1.1 : 0.9, r); }, { passive: false });
  // double-tap to zoom in (touch convenience)
  let lastTap = 0;
  svg.addEventListener("pointerup", (e) => { if (e.pointerType !== "touch") return; const now = e.timeStamp; if (now - lastTap < 300) { const r = svg.getBoundingClientRect(); zoomAt(e.clientX, e.clientY, 0.6, r); } lastTap = now; });
}
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
  (byCl.C4 = byCl.C4 || []).unshift({ name: "selfimprove", display_name: "Самоулучшение", status: "busy" });
  (byCl.C4 = byCl.C4 || []).unshift({ name: "intake", display_name: "Разбор входящего", status: "idle" });
  (byCl.C4 = byCl.C4 || []).unshift({ name: "factory", display_name: "Фабрика модулей", status: "busy" });
  const pos = {};
  cnames.forEach((cid, i) => { const a = -Math.PI / 2 + i * (2 * Math.PI / n); pos[cid] = { x: cx + 200 * Math.cos(a), y: cy + 200 * Math.sin(a), a }; });
  s2nodes = {}; s2corePos = { x: cx, y: cy };
  const parts = []; let active = 0, total = 0;
  // Pip-Boy map backdrop: grid graticule + concentric rings (visual; pans/zooms with content)
  parts.push('<defs>'
    + '<pattern id="g1" width="38" height="38" patternUnits="userSpaceOnUse"><path d="M38 0 L0 0 0 38" fill="none" stroke="currentColor" stroke-width="0.5" opacity="0.09"/></pattern>'
    + '<pattern id="g2" width="190" height="190" patternUnits="userSpaceOnUse"><path d="M190 0 L0 0 0 190" fill="none" stroke="currentColor" stroke-width="0.8" opacity="0.16"/></pattern>'
    + '</defs>'
    + '<rect x="-3000" y="-3000" width="6000" height="6000" fill="url(#g1)"/>'
    + '<rect x="-3000" y="-3000" width="6000" height="6000" fill="url(#g2)"/>'
    + '<g opacity="0.14" stroke="currentColor" fill="none">'
    + [120, 230, 340, 470].map((r) => `<circle cx="500" cy="320" r="${r}" stroke-width="0.7"/>`).join('')
    + '<line x1="-3000" y1="320" x2="3000" y2="320" stroke-width="0.5"/><line x1="500" y1="-3000" x2="500" y2="3000" stroke-width="0.5"/>'
    + '</g>');
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
  svg.querySelectorAll("[data-mod]").forEach((c) => c.onclick = () => openModule(c.getAttribute("data-mod")));
  const ce = svg.querySelector("[data-core]"); if (ce) ce.onclick = () => openCore();
  $("#s2act").textContent = total ? `${active}/${total} ACTIVE` : "нет модулей";
  if (vbAuto) fitVB(); else applyVB();
}
$("#s2search").addEventListener("input", (e) => { s2q = e.target.value.trim().toLowerCase(); render2D(); });
$("#s2fit").onclick = () => { vbAuto = true; fitVB(); };

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
const TCOLS = { pending: "В ОЧЕРЕДИ", running: "В ПРОЦЕССЕ", done: "ГОТОВО", error: "ОШИБКА" };
let colOpen = {};
async function loadTasks() {
  try {
    const d = await api("/api/tasks"); const t = d.tasks || [];
    const CAP = 10;
    const card = (x) => `<div class="tk" data-task="${esc(x.id)}">${esc(x.kind || x.id)}<div class="bar" style="margin:4px 0 2px"><i style="width:${x.progress || 0}%"></i></div><div class="m" style="opacity:.6">${esc(x.status)} · ${x.progress || 0}% · ${esc((x.updated_at || x.created_at || "").slice(11, 16))}</div></div>`;
    const COLS = [["pending", "В ОЧЕРЕДИ"], ["running", "В ПРОЦЕССЕ"], ["done", "ВЫПОЛНЕНО"], ["error", "ОШИБКА"]];
    $("#tasks").innerHTML = `<div class="kb" style="grid-template-columns:repeat(4,1fr)">` + COLS.map(([k, lbl]) => {
      const here = t.filter((x) => x.status === k); const open = !!colOpen[k];
      const shown = open ? here : here.slice(0, CAP); const more = here.length - shown.length;
      let btn = "";
      if (more > 0) btn = `<button class="ico kbmore" data-col="${k}">развернуть ещё ${more} ▾</button>`;
      else if (open && here.length > CAP) btn = `<button class="ico kbmore" data-col="${k}">свернуть ▴</button>`;
      return `<div class="kbcol"><h4>${lbl} · ${here.length}</h4><div class="kbscroll">${shown.map(card).join("") || "<div class='empty'>—</div>"}${btn}</div></div>`;
    }).join("") + `</div>`;
    $("#tasks").querySelectorAll("[data-task]").forEach((c) => c.onclick = () => openTaskInspector(c.getAttribute("data-task")));
    $("#tasks").querySelectorAll("[data-col]").forEach((c) => c.onclick = () => { const k = c.getAttribute("data-col"); colOpen[k] = !colOpen[k]; loadTasks(); });
    const act = t.filter((x) => x.status === "running" || x.status === "pending").length;
    const tab = document.querySelector(".tab[data-go=tasks]"); if (tab) tab.textContent = act ? `ЗАДАЧИ (${act})` : "ЗАДАЧИ";
  } catch (e) { $("#tasks").innerHTML = "<div class='empty'>нет связи с ядром</div>"; }
}
function openTaskInspector(id) {
  drawer("ЗАДАЧА " + id.slice(0, 8));
  tabset([
    ["info", "ИНФО", async (b) => {
      const d = await api(`/api/tasks/${id}`); const t = d.task;
      const pr = t.progress || 0;
      const done = t.status === "done", err = t.status === "error";
      b.innerHTML = `<div style="font-size:13px;margin-bottom:6px">${esc(t.kind)}</div>`
        + `<div class="row"><span>статус</span><span class="chip">${esc(t.status)}</span></div>`
        + `<div class="row"><span>выполнено</span><span>${pr}%</span></div><div class="bar"><i style="width:${pr}%"></i></div>`
        + `<div class="row"><span>создана</span><span>${esc((t.created_at || "").slice(0, 19).replace("T", " "))}</span></div>`
        + (t.payload ? `<h5 style="margin-top:9px">ПЛАН</h5><div class="m" style="opacity:.88;white-space:pre-wrap">${esc(t.payload)}</div>` : "")
        + (t.result ? `<div class="m" style="margin-top:7px">РЕЗУЛЬТАТ: ${esc(t.result)}</div>` : "")
        + (t.error ? `<div class="m" style="margin-top:7px;color:#ff7a6b">ОШИБКА: ${esc(t.error)}</div>` : "")
        + `<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">`
        + (done ? "" : `<button class="ico" id="t-run">▶ ВЫПОЛНИТЬ СЕЙЧАС</button>`)
        + (done ? "" : `<button class="ico" id="t-cancel">ОТМЕНИТЬ</button>`)
        + (err ? `<button class="ico" id="t-retry">ПОВТОРИТЬ</button>` : "")
        + `<button class="ico" id="t-del" style="border-color:#ff7a6b;color:#ff7a6b">УДАЛИТЬ</button>`
        + `</div>`;
      const tn = $("#t-run"); if (tn) tn.onclick = async () => { tn.textContent = "выполняется…"; try { await api(`/api/tasks/${id}/run`, { method: "POST" }); toast("Задача выполнена"); } catch (e) { toast("ошибка выполнения"); } await loadTasks(); openTaskInspector(id); };
      const tc = $("#t-cancel"); if (tc) tc.onclick = async () => { await api(`/api/tasks/${id}/cancel`, { method: "POST" }); toast("Задача отменена"); await loadTasks(); openTaskInspector(id); };
      const tr = $("#t-retry"); if (tr) tr.onclick = async () => { await api(`/api/tasks/${id}/retry`, { method: "POST" }); toast("Задача возвращена в очередь"); await loadTasks(); openTaskInspector(id); };
      const td = $("#t-del"); if (td) td.onclick = async () => { await api(`/api/tasks/${id}/delete`, { method: "POST" }); toast("Задача удалена"); insp.classList.remove("open"); await loadTasks(); };
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
    pushMetric(Number(m.cpu) || 0, Number(m.ram) || 0);
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
        const c = el("div", "idea", `${esc(i.text)}<div class="bar" style="margin:4px 0 2px"><i style="width:${i.progress || 0}%"></i></div><div class="m">${esc(i.status)} · готовность ${i.progress || 0}%</div>`);
        c.onclick = () => openIdeaDetail(i.id, () => mv.classList.remove("on")); col.appendChild(c);
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
function openIdeaDetail(id, backFn) {
  mvOpen("РАЗБОР ЭЛЕМЕНТА", "");
  async function render(b) {
    const d = await api(`/api/ideas/${id}`); const i = d.idea || {}, x = d.data; const p = d.progress || 0;
    $("#mv-sub").textContent = (i.text || "").slice(0, 80);
    const sec = (t, v) => v ? `<h5 style="margin-top:10px">${t}</h5><div class="m" style="opacity:.88">${esc(v)}</div>` : "";
    let html = `<div class="row"><span>готовность к интеграции</span><span>${p}%</span></div><div class="bar"><i style="width:${p}%"></i></div>`
      + `<div class="row"><span>статус</span><span class="chip">${esc(i.status)}</span></div>`;
    if (!x) html += `<div class="m" style="margin:8px 0;opacity:.7">ещё не разобрано — запусти глубокий разбор.</div>`;
    else html += sec("ЧТО ЭТО", x.what) + sec("ЗАЧЕМ", x.why) + sec("СТРУКТУРА", x.structure)
      + `<h5 style="margin-top:10px">КУДА ИНТЕГРИРОВАТЬ</h5><div class="row"><span>кластер</span><span class="chip">${esc(x.fit_cluster || "?")}</span></div><div class="m" style="opacity:.88">${esc(x.fit_reason || "")}</div>` + (x.overlaps ? `<div class="m" style="opacity:.6">пересечение: ${esc(x.overlaps)}</div>` : "")
      + (x.license !== undefined ? `<div class="row" style="margin-top:8px"><span>лицензия / безопасность</span><span>${esc(x.license || "?")} ${x.license_ok ? "✓" : "✗"} · ${x.security_ok ? "чисто" : "риски"}</span></div>` : "")
      + sec("РЕКОМЕНДАЦИЯ", x.recommendation) + sec("ТЕСТ-ПЛАН", x.test_plan);
    const isRepo = (i.text || "").startsWith("[repo]") || (x && x.source === "repo");
    html += `<div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap"><button class="ico" id="d-an">РАЗОБРАТЬ ГЛУБЖЕ</button>`
      + (isRepo ? `<button class="ico" id="d-wrap">СОБРАТЬ ОБЁРТКУ</button>` : "")
      + `<button class="ico" id="d-si">В САМОУЛУЧШЕНИЕ</button><button class="ico" id="d-acc">ПРИНЯТЬ</button><button class="ico" id="d-rej">ОТКАЗАТЬ</button></div><div id="d-out" style="margin-top:8px"></div>`;
    b.innerHTML = html;
    $("#d-an").onclick = async () => { $("#d-out").innerHTML = "<div class='empty'>разбираю (клон + анализ)… минуту</div>"; await api(`/api/ideas/${id}/analyze`, { method: "POST" }); toast("Разбор обновлён"); render(b); };
    $("#d-acc").onclick = async () => { const r = await api(`/api/ideas/${id}/accept`, { method: "POST" }); toast("Принято → задача " + (r.task_id || "").slice(0, 8)); await loadIdeas(); render(b); };
    $("#d-rej").onclick = async () => { await api(`/api/ideas/${id}/reject`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" }); toast("Отклонено"); await loadIdeas(); render(b); };
    const w = $("#d-wrap"); if (w) w.onclick = async () => {
      const repo = ((i.text || "").match(/\[repo\]\s*(\S+)/) || [])[1]; if (!repo) return;
      $("#d-out").innerHTML = "<div class='empty'>Builder собирает обёртку + контракт-тест… минуту-две</div>";
      try { const r = await api("/api/ideas/adopt/build", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ repo }) });
        $("#d-out").innerHTML = `<div class="row"><span>обёртка</span><span class="chip">${esc(r.verdict)}</span></div>` + (r.reason ? `<div class="m">${esc(r.reason)}</div>` : "") + (r.verdict === "ready" && r.token ? `<button class="ico" id="d-prom">ВНЕДРИТЬ (подтвердить)</button>` : "");
        const pr = $("#d-prom"); if (pr) pr.onclick = async () => { const pp = await api("/api/ideas/adopt/promote", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: r.token }) }); toast(pp.ok ? "Внедрено, ядро перезапущено" : ("Отказ: " + (pp.reason || ""))); if (pp.ok) setTimeout(loadModules, 4000); };
      } catch (e) { $("#d-out").innerHTML = "<div class='empty'>ошибка сборки</div>"; }
    };
  }
  mvTabset([["detail", "РАЗБОР", render], ["chat", "ЧАТ-АГЕНТ", async (b) => agentChat(b, "idea:" + id, "обсудить этот элемент: эффективность, интеграция…")]], "detail");
  const bk = el("span", "mvtab", "← НАЗАД"); bk.onclick = backFn || (() => mv.classList.remove("on")); $("#mv-tabs").insertBefore(bk, $("#mv-tabs").firstChild);
}
$("#genidea").onclick = async () => { $("#genidea").textContent = "…"; try { await api("/api/ideas/generate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ n: 2 }) }); await loadIdeas(); } catch (e) {} $("#genidea").textContent = "+ СГЕНЕРИРОВАТЬ"; };
async function intake(source, value) { if (!value.trim()) return; toast("Разбираю…"); try { const r = await api("/api/ideas/intake", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ source, value }) }); toast("Разбор: " + (r.category || "?") + (r.routed ? " → самоулучшение" : "")); await loadIdeas(); } catch (e) { toast("Не удалось разобрать"); } }
async function adoptRepo(repo) {
  if (!repo.trim()) return; toast("Разбираю репозиторий…");
  try {
    const r = await api("/api/ideas/adopt", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ repo, cluster: "C6" }) });
    renderRepo(r, repo);
  } catch (e) { toast("Не удалось разобрать репо"); }
}
function renderRepo(r, repo) {
  const lic = r.license || {}, secSafe = !r.security || r.security.safe !== false;
  drawer("РАЗБОР РЕПО"); inspTabs.innerHTML = "";
  inspBody.innerHTML = `<div style="margin-bottom:8px">${esc(r.repo || repo)}</div>`
    + `<div class="row"><span>вердикт</span><span class="chip">${esc(r.verdict)}</span></div>`
    + `<div class="row"><span>лицензия</span><span>${esc(lic.license || "?")} ${lic.compatible ? "✓" : "✗"}</span></div>`
    + `<div class="row"><span>безопасность</span><span>${secSafe ? "чисто" : "найдены риски"}</span></div>`
    + (r.eval ? `<div class="row"><span>контракт</span><span>${r.eval.contract_ok ? "✓" : "✗"}</span></div>` : "")
    + (r.module_id ? `<div class="row"><span>модуль</span><span class="chip">${esc(r.module_id)}</span></div>` : "")
    + (r.reason ? `<div class="m" style="margin-top:6px">${esc(r.reason)}</div>` : "")
    + (r.overlaps && r.overlaps.length ? `<div class="m" style="margin-top:6px;opacity:.6">в кластере уже: ${esc(r.overlaps.join(", "))}</div>` : "")
    + `<div id="repoact" style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap"></div>`;
  const act = $("#repoact");
  if (r.verdict === "defer" && secSafe && lic.compatible) {
    const b = el("button", "ico", "СОБРАТЬ ОБЁРТКУ (Builder)"); b.onclick = () => buildWrapper(r.repo || repo); act.appendChild(b);
  }
  if (r.verdict === "ready" && r.token) {
    const b = el("button", "ico", "ВНЕДРИТЬ (подтвердить)"); b.onclick = () => promoteWrapper(r.token); act.appendChild(b);
    if (r.diff_stat) inspBody.innerHTML += `<div class="m" style="margin-top:6px;opacity:.7;white-space:pre-wrap">${esc(r.diff_stat)}</div>`;
  }
  toast("Репо: " + r.verdict);
}
async function buildWrapper(repo) {
  toast("Собираю MCP-обёртку (Builder) — это займёт минуты…");
  $("#repoact") && ($("#repoact").innerHTML = "<span class='vlbl'>Builder работает…</span>");
  try { const r = await api("/api/ideas/adopt/build", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ repo, cluster: "C6" }) }); renderRepo(r, repo); }
  catch (e) { toast("Сборка обёртки не удалась"); }
}
async function promoteWrapper(token) {
  toast("Внедряю обёртку…");
  try { const r = await api("/api/ideas/adopt/promote", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }) });
    toast(r.ok ? "Модуль внедрён, ядро перезапускается" : ("Отказ: " + (r.reason || ""))); if (r.ok) { insp.classList.remove("open"); setTimeout(loadModules, 4000); } }
  catch (e) { toast("Внедрение не удалось"); }
}
$("#iadd").onclick = () => { const src = $("#isrc").value, val = $("#ival").value; $("#ival").value = ""; intake(src, val); };
$("#ival").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#iadd").click(); });
$("#ifile").onclick = () => $("#ideafileinp").click();
$("#ideafileinp").onchange = (e) => { for (const f of e.target.files) intake("file", f.name); e.target.value = ""; };
$("#addtask").onclick = async () => { try { await api("/api/tasks", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ kind: "ручная", payload: "создана из десктопа" }) }); toast("Задача создана"); document.querySelector(".tab[data-go=tasks]").click(); await loadTasks(); } catch (e) { toast("Не удалось создать"); } };
$("#ideachat").onclick = () => { drawer("АГЕНТ МОДУЛЯ ИДЕЙ"); inspTabs.innerHTML = ""; agentChat(inspBody, "module:ideas", "спросить агента идей…"); };
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
    const securityCard = `<div class="card"><h5>БЕЗОПАСНОСТЬ</h5><div class="row"><span>Логин</span><span>Rick</span></div><div style="margin-top:8px"><button class="ico" id="pw-change">СМЕНИТЬ ПАРОЛЬ</button></div></div>`;
    $("#prof").innerHTML = domains + metrics + hypsCard + healthCard + schedCard + securityCard;
    const pc = $("#pw-change"); if (pc) pc.onclick = async () => { const np = prompt("Новый пароль (мин. 6 символов):"); if (!np) return; try { const r = await api("/api/systems/auth/password", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ new_password: np }) }); toast(r.ok ? "Пароль изменён — войди заново при следующем запросе" : ("Ошибка: " + (r.reason || ""))); } catch (e) { toast("Не удалось сменить пароль"); } };
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
const CHANNELS = { mediator: "ПЕРЕДАТЧИК", core: "ЯДРО", claude_code: "CLAUDE CODE", council: "СОВЕТ" };
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
    : ch === "claude_code" ? "Чат с Claude Code — видно его работу вживую: вызовы инструментов, чтение файлов, затем ответ. Может думать 1–4 мин." : "Прямой чат с ядром.");
}
function renderDrafts() {
  const d = $("#cdraft"); d.innerHTML = "";
  drafts.forEach((t, i) => { const c = el("span", "att", `<b>${esc(t.slice(0, 44))}</b><span class="rm" data-i="${i}">✕</span>`); c.querySelector(".rm").onclick = () => { drafts.splice(i, 1); renderDrafts(); }; d.appendChild(c); });
  d.style.display = (ch === "mediator" && drafts.length) ? "flex" : "none";
}
function switchChannel(c) {
  ch = c; localStorage.setItem("noir.ch", c); drafts = [];
  document.querySelectorAll(".chtab").forEach((b) => b.classList.toggle("on", b.dataset.ch === c));
  $("#msg").placeholder = c === "mediator" ? "сообщение Передатчику — он сформирует задачу ядру и вернёт суть…"
    : c === "claude_code" ? "вопрос Claude Code…" : c === "council" ? "вопрос совету (Opus+DeepSeek+Gemini)…" : "сообщение ядру…";
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
  const st = chGet(ch);
  if (ch === "claude_code") { await sendCC(text, st); return; }
  const bubble = appendMsg("ai", "…");
  try {
    const r = await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: text, agent: ch, session_id: st.sid || null, cc_session: st.cc || null }) });
    st.sid = r.session_id; if (r.cc_session) st.cc = r.cc_session; chSet(ch, st);
    if (ch === "mediator" && r.task) { appendMsg("sys", "→ ядру: " + r.task); pushHist(ch, "sys", "→ ядру: " + r.task); }
    if (ch === "council" && r.members) { const ln = "совет: " + r.members.map((m) => m.provider + (m.ok ? " ✓" : " ✗")).join(" · "); appendMsg("sys", ln); pushHist(ch, "sys", ln); }
    bubble.textContent = pickReply(r) || "(пустой ответ)"; pushHist(ch, "ai", bubble.textContent); faceSpeak(0.7);
    if (ch === "core" && r.actions && r.actions.length) { const ln = "выполнено: " + r.actions.map((a) => a.tool).join(", "); appendMsg("sys", ln); pushHist(ch, "sys", ln); loadTasks(); loadIdeas(); }
  } catch (e) { bubble.textContent = "[нет связи с ядром]"; bubble.className = "msg sys"; }
  $("#chatlog").scrollTop = 1e9;
}
// Claude Code channel: stream live tool activity (SSE over POST) so you SEE it work.
async function sendCC(text, st) {
  const head = appendMsg("ai", "● CLAUDE CODE работает…"); head.classList.add("ccwork");
  const logbox = el("div", "cclog"); $("#chatlog").appendChild(logbox);
  const t0 = Date.now();
  const tick = setInterval(() => { if (!head.dataset.done) head.textContent = "● CLAUDE CODE работает… " + Math.round((Date.now() - t0) / 1000) + "с"; }, 1000);
  const addline = (s, cls) => { const e = el("div", "ccline " + (cls || ""), esc(s)); logbox.appendChild(e); $("#chatlog").scrollTop = 1e9; return e; };
  let finalText = "";
  try {
    const resp = await fetch(API + "/api/chat/cc/stream", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: text, agent: "claude_code", session_id: st.sid || null, cc_session: st.cc || null }) });
    if (!resp.ok || !resp.body) throw new Error("http " + resp.status);
    const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, idx).replace(/^data:\s?/, "").trim(); buf = buf.slice(idx + 2);
        if (!line) continue;
        let ev; try { ev = JSON.parse(line); } catch (e) { continue; }
        if (ev.t === "start") { st.sid = ev.session_id; }
        else if (ev.t === "init") { if (ev.cc_session) st.cc = ev.cc_session; addline("⚙ запуск · " + (ev.model || ""), "dim"); }
        else if (ev.t === "tool") { addline("🔧 " + (ev.name || "") + (ev.input ? " · " + ev.input : ""), "tool"); }
        else if (ev.t === "tool_done") { const l = logbox.lastChild; if (l) l.classList.add("ok"); }
        else if (ev.t === "text" && ev.text) { addline("· " + ev.text, "dim"); }
        else if (ev.t === "done") { finalText = ev.text || ""; if (ev.cc_session) st.cc = ev.cc_session; }
        else if (ev.t === "error") { addline(ev.text || "ошибка", "err"); }
      }
    }
  } catch (e) { addline("[обрыв связи со стримом Claude Code]", "err"); }
  clearInterval(tick); head.dataset.done = "1";
  head.textContent = "✓ CLAUDE CODE · " + Math.round((Date.now() - t0) / 1000) + "с";
  if (finalText) { appendMsg("ai", finalText); pushHist(ch, "ai", finalText); try { faceSpeak(0.7); } catch (e) {} }
  chSet(ch, st); $("#chatlog").scrollTop = 1e9;
}

$("#send").onclick = sendChat;
$("#msg").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
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
let faceScene, faceRen, faceCam, facePts, faceMat, faceBase, faceType, faceRAF, faceSpeakLvl = 0;
function faceSpeak(l) { faceSpeakLvl = Math.max(faceSpeakLvl, Math.min(1, l * 1.6)); }
function buildFace() {
  const c = $("#facecv"); c.width = c.clientWidth || 260; c.height = 220;
  faceScene = new THREE.Scene(); faceCam = new THREE.PerspectiveCamera(50, c.width / c.height, .1, 100); faceCam.position.z = 2.6;
  faceRen = new THREE.WebGLRenderer({ canvas: c, antialias: true, alpha: true }); faceRen.setSize(c.width, c.height); faceRen.setClearColor(0, 0);
  // front-facing particle FACE: head fill + two eyes (blink) + a mouth that opens on speech
  const P = [], HEAD = 900;
  for (let i = 0; i < HEAD; i++) { const a = i * 2.39996, r = Math.sqrt((i + .5) / HEAD), x = Math.cos(a) * r * 0.92, y = Math.sin(a) * r * 1.12, z = 0.3 * (1 - (x * x + y * y)); P.push(x, y, z, 0); }
  const EYE = 120;
  [[-0.36, 0.30], [0.36, 0.30]].forEach(([ex, ey]) => { for (let i = 0; i < EYE; i++) { const a = i * 2.39996, r = Math.sqrt((i + .5) / EYE) * 0.12; P.push(ex + Math.cos(a) * r, ey + Math.sin(a) * r, 0.42, 1); } });
  const MOUTH = 180;
  for (let i = 0; i < MOUTH; i++) { const u = i / (MOUTH - 1); P.push((u - 0.5) * 0.66, -0.45, 0.44, 2); }
  const N = P.length / 4, pos = new Float32Array(N * 3); faceBase = new Float32Array(N * 3); faceType = new Int8Array(N);
  for (let i = 0; i < N; i++) { pos[i*3]=faceBase[i*3]=P[i*4]; pos[i*3+1]=faceBase[i*3+1]=P[i*4+1]; pos[i*3+2]=faceBase[i*3+2]=P[i*4+2]; faceType[i]=P[i*4+3]; }
  const geo = new THREE.BufferGeometry(); geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  faceMat = new THREE.PointsMaterial({ color: new THREE.Color(theme === "green" ? 0x62ffb2 : 0xffd24a), size: 0.04, transparent: true, opacity: .92, blending: THREE.AdditiveBlending, depthWrite: false });
  facePts = new THREE.Points(geo, faceMat); faceScene.add(facePts);
  window.__facephos = (hex) => faceMat.color.set(hex);
  (function loop() {
    faceRAF = requestAnimationFrame(loop);
    if (!$("#facewin").classList.contains("on")) return;
    const t = Date.now() / 1000, breathe = 1 + Math.sin(t * 1.6) * 0.02, speak = faceSpeakLvl, blink = (Math.sin(t * 0.9) > 0.985) ? 1 : 0;
    const p = facePts.geometry.attributes.position.array;
    for (let i = 0; i < N; i++) {
      const ti = faceType[i], bx = faceBase[i*3], by = faceBase[i*3+1], bz = faceBase[i*3+2];
      let x = bx * breathe, y = by * breathe;
      if (ti === 1 && blink) y = 0.30 + (by - 0.30) * 0.12;                                  // eyes blink
      if (ti === 2) y = by - (0.04 + speak * 0.22) * Math.cos(bx * 4.7) - speak * 0.03 * Math.sin(t * 22);  // mouth opens
      p[i*3] = x; p[i*3+1] = y; p[i*3+2] = bz;
    }
    facePts.geometry.attributes.position.needsUpdate = true;
    facePts.rotation.y = Math.sin(t * 0.6) * 0.22; faceSpeakLvl *= 0.92;                       // gentle look-around
    faceRen.render(faceScene, faceCam);
  })();
}

// ---------- ВИЗУАЛ: режимы Лицо / Графики(live) / Кадр ----------
let vMode = "face", cpuHist = [], ramHist = [];
function setVMode(m) {
  vMode = m;
  document.querySelectorAll("#facewin .vmode").forEach((b) => b.classList.toggle("on", b.dataset.vm === m));
  $("#facecv").style.display = m === "face" ? "block" : "none";
  $("#vchart").style.display = m === "chart" ? "block" : "none";
  $("#vimg").style.display = m === "img" ? "flex" : "none";
  if (m === "chart") drawChart();
  if (m === "img") loadVisual();
}
document.querySelectorAll("#facewin .vmode").forEach((b) => b.onclick = (e) => { e.stopPropagation(); setVMode(b.dataset.vm); });
function pushMetric(cpu, ram) {
  cpuHist.push(cpu); ramHist.push(ram);
  if (cpuHist.length > 60) { cpuHist.shift(); ramHist.shift(); }
  if (vMode === "chart" && $("#facewin").classList.contains("on")) drawChart();
}
function drawChart() {
  const c = $("#vchart"); if (!c) return; c.width = c.clientWidth || 260; c.height = 220;
  const g = c.getContext("2d"), col = getComputedStyle($("#px")).color;
  g.clearRect(0, 0, c.width, c.height);
  g.strokeStyle = col; g.globalAlpha = .15;
  for (let i = 0; i <= 4; i++) { const y = 10 + i * (c.height - 20) / 4; g.beginPath(); g.moveTo(0, y); g.lineTo(c.width, y); g.stroke(); }
  g.globalAlpha = 1;
  const line = (arr, alpha) => { if (arr.length < 2) return; g.strokeStyle = col; g.globalAlpha = alpha; g.lineWidth = 1.6; g.beginPath(); arr.forEach((v, i) => { const x = i / (arr.length - 1) * c.width, y = c.height - (v / 100) * (c.height - 20) - 10; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); g.globalAlpha = 1; };
  line(ramHist, .45); line(cpuHist, 1);
  g.fillStyle = col; g.font = "10px monospace";
  g.fillText(`CPU ${cpuHist.length ? cpuHist[cpuHist.length - 1] : 0}%  ·  RAM ${ramHist.length ? ramHist[ramHist.length - 1] : 0}%  (live)`, 6, 14);
}
async function loadVisual() {
  const box = $("#vimg"); if (!box) return;
  try {
    const v = await api("/api/visual");
    if (v.kind === "image" && v.payload) box.innerHTML = `<img src="${esc(v.payload)}"/>`;
    else if (v.kind === "text" && v.payload) box.innerHTML = `<div>${esc(v.payload)}</div>`;
    else if (v.kind === "chart" && v.payload) box.innerHTML = `<div style="opacity:.7">данные графика получены — переключись на ГРАФИКИ</div>`;
    else box.innerHTML = `<div style="opacity:.5">нет кадра — сюда ядро выводит графики/изображения в реальном времени</div>`;
  } catch (e) {}
}
$("#visual").onclick = () => { const w = $("#facewin"); w.classList.toggle("on"); if (w.classList.contains("on") && !faceScene) buildFace(); };
$("#faceclose").onclick = () => $("#facewin").classList.remove("on");
(function faceDrag() {
  const w = $("#facewin"), h = $("#facehead"); let sx, sy, sl, st, drag = false;
  h.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".x") || e.target.closest(".vmode")) return;   // not on controls
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
  if (vMode === "img" && $("#facewin").classList.contains("on")) loadVisual();
}

// ---------- boot ----------
applyTheme();
render2D();
setupPanZoom();
window.addEventListener("contextmenu", (e) => e.preventDefault());  // no browser context menu (save-image etc.)
setupWindow();
loadBotStatus();
refresh(); setInterval(refresh, 5000);
wsNotify();
checkUpdate();
window.__noirReady = true;
