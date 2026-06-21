// Black Noir HUD — Pip-Boy CRT + 3D core cloud on LIVE data (no demo).
// Thin client over /api/* + /ws/*. Tauri window controls + auto-updater.
import * as THREE from "three";

const params = new URLSearchParams(location.search);
const API = (params.get("api") || window.NOIR_API_BASE || (window.__VITE_API_BASE__) ||
  "https://jarvisgod.duckdns.org").replace(/\/$/, "");
const WS = API.replace(/^http/, "ws");
const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const isTauri = !!window.__TAURI_INTERNALS__ || !!window.__TAURI__;

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
    $("#w-min").onclick = () => w.minimize();
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
function applyTheme() { $("#px").classList.toggle("gold", theme === "gold"); if (window.__phos) window.__phos(theme === "green" ? 0x4dffa0 : 0xf5bd3a); }
$("#theme").onclick = () => { theme = theme === "green" ? "gold" : "green"; localStorage.setItem("noir.theme", theme); applyTheme(); };
applyTheme();

// ---------- tabs ----------
let cur = "map";
document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
  cur = b.dataset.go;
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("hidden", p.dataset.tab !== cur));
  if (cur === "map" && window.__resize) window.__resize();
});

// ---------- notifications ----------
let unread = 0;
function toast(text) {
  const n = $("#notifs"); const e = el("div", "toast", "● " + text); n.appendChild(e);
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

// ---------- inspector ----------
function openInspector(kind, id) {
  const insp = $("#insp"), tabs = $("#insp-tabs"), body = $("#insp-body");
  insp.classList.add("open");
  if (kind === "core") {
    $("#insp-title").textContent = "СОСТАВ ИИ ЯДРА";
    tabs.innerHTML = "";
    body.innerHTML = (core?.ai || []).map((a) =>
      `<div class="row"><span>${a.name} <span class="chip">${a.role}</span></span><span>${a.status}</span></div><div class="m" style="opacity:.6;margin-bottom:7px">${a.model}</div>`).join("") || "<div class='empty'>—</div>";
    return;
  }
  // module
  $("#insp-title").textContent = id;
  const ITABS = [["logs", "ЛОГИ"], ["chat", "ЧАТ-АГЕНТА"], ["mem", "ПАМЯТЬ"], ["cfg", "НАСТРОЙКИ"]];
  tabs.innerHTML = "";
  let active = "logs";
  const render = async () => {
    tabs.querySelectorAll(".it").forEach((x) => x.classList.toggle("on", x.dataset.k === active));
    body.innerHTML = "<div class='empty'>загрузка…</div>";
    try {
      if (active === "logs") {
        const d = await api(`/api/modules/${id}/logs?tail=40`);
        body.innerHTML = (d.logs || []).map((l) => `<div class="m">${l.ts?.slice(11, 19) || ""} [${l.level}] ${l.event} ${l.payload || ""}</div>`).join("") || "<div class='empty'>нет логов</div>";
      } else if (active === "mem") {
        const d = await api(`/api/memory?module=${id}`);
        body.innerHTML = (d.items || []).map((m) => `<div class="row"><span>${m.value}</span><span class="chip">${m.type || m.key}</span></div>`).join("") || "<div class='empty'>нет данных</div>";
      } else if (active === "cfg") {
        const m = modules.find((x) => x.name === id);
        body.innerHTML = `<div class="row"><span>статус</span><span class="chip">${m?.status}</span></div><div class="row"><span>cluster</span><span>${m?.cluster}</span></div><div class="row"><span>tools</span><span>${(m?.tools || []).join(", ")}</span></div>` +
          `<div style="margin-top:9px"><button class="ico" id="md-tog">${m?.enabled ? "ОТКЛЮЧИТЬ" : "ВКЛЮЧИТЬ"}</button></div>`;
        const tog = $("#md-tog"); if (tog) tog.onclick = async () => { await api(`/api/modules/${id}/${m?.enabled ? "disable" : "enable"}`, { method: "POST" }); await refresh(); render(); };
      } else if (active === "chat") {
        body.innerHTML = `<div id="agl" style="max-height:60vh;overflow:auto"></div><div style="display:flex;gap:5px;margin-top:7px"><input id="agi" style="flex:1;background:rgba(0,0,0,.4);border:1px solid currentColor;color:currentColor;font-family:var(--mono);padding:5px;border-radius:4px" placeholder="агенту ${id}…"/><button class="ico" id="ags">→</button></div>`;
        const send = async () => { const v = $("#agi").value.trim(); if (!v) return; $("#agi").value = ""; $("#agl").appendChild(el("div", "msg me", "» " + v)); const r = await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: v, target: "module:" + id }) }); $("#agl").appendChild(el("div", "msg ai", pickReply(r))); };
        $("#ags").onclick = send; $("#agi").onkeydown = (e) => { if (e.key === "Enter") send(); };
      }
    } catch (e) { body.innerHTML = `<div class='empty'>нет данных (${e.message})</div>`; }
  };
  ITABS.forEach(([k, lbl]) => { const t = el("span", "it", lbl); t.dataset.k = k; t.onclick = () => { active = k; render(); }; tabs.appendChild(t); });
  render();
}
$("#insp-x").onclick = () => $("#insp").classList.remove("open");

// ---------- 2D schema ----------
function render2D() {
  const wrap = $("#schema2d"); wrap.innerHTML = "";
  Object.entries(CLUSTERS).forEach(([cid, c]) => {
    const col = el("div", "col"); col.appendChild(el("h4", null, c.n));
    const here = modules.filter((m) => m.cluster === cid);
    if (!here.length) col.appendChild(el("div", "empty", "—"));
    here.forEach((m) => {
      const dotc = m.status === "idle" ? "" : m.status === "busy" ? "busy" : m.status === "error" ? "err" : "idle";
      const node = el("div", "mod", `<span class="dot ${dotc}">●</span> <b>${m.display_name || m.name}</b><div class="m">v${m.version} · ${m.status} · ${(m.tools || []).length} tools</div>`);
      node.onclick = () => openInspector("module", m.name); col.appendChild(node);
    });
    wrap.appendChild(col);
  });
}
$("#sb3d").onclick = () => { $("#sb3d").classList.add("on"); $("#sb2d").classList.remove("on"); $("#schema2d").classList.add("hidden"); $("#labels").classList.remove("hidden"); if (window.__resize) window.__resize(); };
$("#sb2d").onclick = () => { $("#sb2d").classList.add("on"); $("#sb3d").classList.remove("on"); $("#schema2d").classList.remove("hidden"); $("#labels").classList.add("hidden"); render2D(); };

// ---------- 3D core cloud ----------
let phos, scene, themed = [], moduleLabels = [], rebuildNodes;
function build3D() {
  const map = $("#map"), labels = $("#labels");
  let W = map.clientWidth || 900, H = map.clientHeight || 600;
  phos = new THREE.Color(0x4dffa0);
  scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(54, W / H, .1, 6000);
  const r = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  r.setSize(W, H); r.setClearColor(0, 0); map.insertBefore(r.domElement, map.firstChild);
  const mat = (o) => { const m = new THREE.MeshBasicMaterial(Object.assign({ color: phos.clone() }, o || {})); themed.push(m); return m; };
  const lmat = (op) => { const m = new THREE.LineBasicMaterial({ color: phos.clone(), transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false }); themed.push(m); return m; };
  const cv = document.createElement("canvas"); cv.width = cv.height = 128; const g = cv.getContext("2d");
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(.25, "rgba(255,255,255,.5)"); gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); const GT = new THREE.CanvasTexture(cv);
  const spr = (s, op) => { const m = new THREE.SpriteMaterial({ map: GT, color: phos.clone(), blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, opacity: op }); themed.push(m); const p = new THREE.Sprite(m); p.scale.set(s, s, 1); return p; };

  const stars = new Float32Array(330 * 3);
  for (let i = 0; i < 330; i++) { const rr = 460 + Math.random() * 1400, a = i * 2.39996, b = Math.acos(((i * 7) % 330) / 165 - 1); stars[i * 3] = rr * Math.sin(b) * Math.cos(a); stars[i * 3 + 1] = rr * Math.cos(b); stars[i * 3 + 2] = rr * Math.sin(b) * Math.sin(a); }
  const sg = new THREE.BufferGeometry(); sg.setAttribute("position", new THREE.BufferAttribute(stars, 3));
  scene.add(new THREE.Points(sg, new THREE.PointsMaterial({ color: 0x2e7d5a, size: 1.7, transparent: true, opacity: .5 })));

  const O = new THREE.Vector3();
  const coreMesh = new THREE.Mesh(new THREE.SphereGeometry(8, 24, 24), mat());
  scene.add(coreMesh); scene.add(new THREE.Mesh(new THREE.SphereGeometry(15, 18, 18), mat({ transparent: true, opacity: .16 }))); scene.add(spr(95, .5));

  const mk = (t, c, onClick) => { const e = el("div", "lab" + (c ? " " + c : ""), t); if (onClick) e.onclick = onClick; labels.appendChild(e); return e; };
  moduleLabels = [{ e: mk("NOIR", "cl", () => openInspector("core")), get: () => O, mesh: coreMesh }];

  const groups = {};
  Object.entries(CLUSTERS).forEach(([cid, c]) => {
    const v = new THREE.Vector3(c.p[0], c.p[1], c.p[2]);
    const grp = new THREE.Group(); grp.position.copy(v); scene.add(grp); groups[cid] = { grp, v };
    grp.add(new THREE.Mesh(new THREE.SphereGeometry(5.5, 16, 16), mat())); grp.add(spr(30, .7));
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([O, v]), lmat(.3)));
    moduleLabels.push({ e: mk(c.n, "cl"), get: () => v });
  });

  // module nodes (LIVE) — rebuilt whenever /api/modules changes
  let nodeObjs = [], nodeLabels = [];
  rebuildNodes = () => {
    nodeObjs.forEach((o) => o.parent && o.parent.remove(o));
    nodeLabels.forEach((l) => l.e.remove());
    nodeObjs = []; nodeLabels = [];
    const byCl = {};
    modules.forEach((m) => { (byCl[m.cluster] = byCl[m.cluster] || []).push(m); });
    Object.entries(byCl).forEach(([cid, mods]) => {
      const G = groups[cid]; if (!G) return;
      mods.forEach((m, j) => {
        const a = j / mods.length * 6.28, lp = new THREE.Vector3(28 * Math.cos(a), (j % 2 ? 8 : -8), 28 * Math.sin(a));
        const mm = new THREE.Mesh(new THREE.SphereGeometry(3.4, 12, 12), mat()); mm.position.copy(lp); G.grp.add(mm); nodeObjs.push(mm);
        const mgl = spr(11, .6); mgl.position.copy(lp); G.grp.add(mgl); nodeObjs.push(mgl);
        const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), lp]), lmat(.35)); G.grp.add(ln); nodeObjs.push(ln);
        const world = lp.clone().add(G.v);
        const lab = mk(m.display_name || m.name, "mod", () => openInspector("module", m.name));
        nodeLabels.push({ e: lab, get: () => world }); moduleLabels.push({ e: lab, get: () => world });
      });
    });
  };
  rebuildNodes();

  window.__phos = (hex) => { phos.set(hex); themed.forEach((m) => m.color && m.color.copy(phos)); };

  let th = .5, ph = 1.05, dist = 430, rot = false, lx, ly; const vp = new THREE.Vector3(), look = new THREE.Vector3();
  map.addEventListener("pointerdown", (e) => { rot = true; lx = e.clientX; ly = e.clientY; });
  window.addEventListener("pointermove", (e) => { if (!rot) return; th -= (e.clientX - lx) * .005; ph -= (e.clientY - ly) * .005; ph = Math.max(.2, Math.min(2.9, ph)); lx = e.clientX; ly = e.clientY; });
  window.addEventListener("pointerup", () => { rot = false; });
  map.addEventListener("wheel", (e) => { e.preventDefault(); dist *= (e.deltaY > 0 ? 1.1 : .9); dist = Math.max(60, Math.min(900, dist)); }, { passive: false });
  window.__resize = () => { W = map.clientWidth || W; H = map.clientHeight || H; r.setSize(W, H); cam.aspect = W / H; cam.updateProjectionMatrix(); };

  (function frame() {
    requestAnimationFrame(frame);
    if (cur !== "map") return;
    if (!rot) th += .0008;
    cam.position.set(look.x + dist * Math.sin(ph) * Math.sin(th), look.y + dist * Math.cos(ph), look.z + dist * Math.sin(ph) * Math.cos(th));
    cam.lookAt(look); r.render(scene, cam);
    moduleLabels.forEach((l) => { vp.copy(l.get()).project(cam); if (vp.z > 1) { l.e.style.display = "none"; return; } l.e.style.display = "block"; l.e.style.left = ((vp.x * .5 + .5) * W) + "px"; l.e.style.top = ((-vp.y * .5 + .5) * H) + "px"; });
  })();
}

// ---------- live data ----------
function setConn(s) { $("#conn").innerHTML = `&#9679; ${s}`; $("#conn").style.opacity = s === "online" ? ".9" : ".5"; }

async function loadCore() {
  try {
    core = await api("/api/core"); setConn(core.status === "ok" ? "online" : core.status);
    $("#brand").textContent = (core.name || "BLACK NOIR").toUpperCase();
    $("#ver").textContent = "v" + (core.version || "");
    $("#vbub").textContent = "Связь есть. Ядро " + (core.name || "Black Noir") + " на линии.";
  } catch (e) { setConn("нет связи с ядром"); $("#vbub").textContent = "Нет связи с ядром…"; }
}
async function loadModules() {
  try { const d = await api("/api/modules"); modules = d.modules || []; if (rebuildNodes) rebuildNodes(); if (!$("#schema2d").classList.contains("hidden")) render2D(); } catch (e) {}
}
async function loadSystems() {
  try {
    const m = await api("/api/systems/metrics");
    $("#metrics").innerHTML = `<h5>МЕТРИКИ ХОСТА</h5><div class="row"><span>CPU</span><span>${m.cpu}%</span></div><div class="bar"><i style="width:${Math.min(100, m.cpu)}%"></i></div><div class="row"><span>RAM</span><span>${m.ram}% (${m.ram_used_mb}/${m.ram_total_mb} МБ)</span></div><div class="bar"><i style="width:${m.ram}%"></i></div><div class="row"><span>Uptime</span><span>${m.uptime}</span></div><div class="row"><span>Cores / GPU</span><span>${m.cores} / ${m.gpu ? "да" : "нет"}</span></div>`;
    const s = await api("/api/systems"); const h = s.hardware;
    $("#hw").innerHTML = `<h5>ЛОКАЛЬНЫЙ СЛОЙ</h5><div class="row"><span>Профиль</span><span>${h.local_layer}</span></div><div class="row"><span>Reflex</span><span>${h.reflex}</span></div><div class="row"><span>STT/TTS</span><span>whisper-${h.whisper_model} / piper</span></div><div class="row"><span>Embeddings</span><span>${s.embedding.model} (${s.embedding.dim})</span></div>`;
  } catch (e) {}
  try { const g = await api("/api/governor/audit?limit=10"); $("#gov").innerHTML = `<h5>GOVERNOR · АУДИТ</h5>` + ((g.audit || []).map((a) => `<div class="row"><span>${a.module}.${a.tool} <span class="chip">${a.action_class}</span></span><span>${a.decision} ok=${a.ok}</span></div>`).join("") || "<div class='empty'>—</div>"); } catch (e) {}
}
async function loadTasks() {
  try {
    const d = await api("/api/tasks"); const t = d.tasks || [];
    const cols = { queued: "В ОЧЕРЕДИ", running: "В ПРОЦЕССЕ", done: "ГОТОВО", error: "ОШИБКА" };
    $("#tasks").innerHTML = Object.entries(cols).map(([k, lbl]) => {
      const here = t.filter((x) => x.status === k);
      return `<div class="kbcol"><h4>${lbl}</h4>${here.map((x) => `<div class="tk">${x.kind || x.id}<div class="m" style="opacity:.6">${x.id.slice(0, 8)}</div></div>`).join("") || "<div class='empty'>—</div>"}</div>`;
    }).join("");
  } catch (e) {}
}
async function loadIdeas() {
  try { const d = await api("/api/ideas?limit=12"); const it = d.ideas || []; $("#ideas").innerHTML = it.length ? it.map((i) => `<div class="idea">${i.text} <span class="chip">${i.status}</span></div>`).join("") : "<div class='empty'>нет идей</div>"; } catch (e) {}
}
$("#genidea").onclick = async () => { $("#genidea").textContent = "…"; try { await api("/api/ideas/generate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ n: 2 }) }); await loadIdeas(); } catch (e) {} $("#genidea").textContent = "+ СГЕНЕРИРОВАТЬ"; };

async function loadProfile() {
  // 10_owner_profile.md §11: domains, metrics, hypotheses, health, schedule — live
  try {
    const d = await api("/api/memory?module=owner_profile");
    const by = {}; (d.items || []).forEach((f) => { (by[f.type] = by[f.type] || []).push(f); });
    const health = (d.items || []).filter((f) => f.type === "health");
    const domainsCard = `<div class="card"><h5>ДОМЕНЫ</h5>${Object.keys(by).length ? Object.entries(by).map(([dom, fs]) => `<div class="row"><span>${dom}</span><span>${fs.length} факт.</span></div>`).join("") : "<div class='empty'>нет данных</div>"}</div>`;
    const hypsCard = `<div class="card"><h5>ГИПОТЕЗЫ</h5>${(d.hypotheses || []).length ? d.hypotheses.map((h) => `<div class="row"><span>${h.statement}</span><span class="chip">${h.verdict || h.status}</span></div>`).join("") : "<div class='empty'>нет гипотез</div>"}</div>`;
    const healthCard = `<div class="card"><h5>ЗДОРОВЬЕ (наблюдение)</h5>${health.length ? health.map((f) => `<div class="row"><span>${f.key || f.value}</span><span>${f.value}</span></div>`).join("") : "<div class='empty'>нет показателей</div>"}</div>`;
    const reconCard = `<div class="card"><h5>СВЕРКА</h5><div class="row"><span>Фактов всего</span><span>${(d.items || []).length}</span></div><div class="row"><span>Гипотез</span><span>${(d.hypotheses || []).length}</span></div><div class="m" style="opacity:.6;margin-top:6px">данные — из /api (модуль owner_profile)</div></div>`;
    $("#prof").innerHTML = domainsCard + healthCard + hypsCard + reconCard;
  } catch (e) { $("#prof").innerHTML = "<div class='empty'>нет данных профиля</div>"; }
}

// chat
let sid = null;
async function sendChat() {
  const i = $("#msg"), text = i.value.trim(); if (!text) return; i.value = "";
  $("#chatlog").appendChild(el("div", "msg me", "» " + text));
  try { const r = await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: text, session_id: sid }) }); sid = r.session_id; $("#chatlog").appendChild(el("div", "msg ai", pickReply(r))); }
  catch (e) { $("#chatlog").appendChild(el("div", "msg sys", "[нет связи с ядром]")); }
  $("#chatlog").scrollTop = 1e9;
}
$("#send").onclick = sendChat; $("#msg").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

// WS notify (live)
function wsNotify() {
  try {
    const ws = new WebSocket(WS + "/ws/notify");
    ws.onmessage = (ev) => { try { const d = JSON.parse(ev.data); if (d.type !== "hello" && (d.title || d.data)) toast(d.title || d.data); } catch (e) {} };
    ws.onclose = () => setTimeout(wsNotify, 5000);
  } catch (e) { setTimeout(wsNotify, 8000); }
}

async function refresh() { await loadCore(); await Promise.all([loadModules(), loadSystems(), loadTasks(), loadIdeas(), loadProfile()]); }

// ---------- boot ----------
try { build3D(); } catch (e) { console.warn("3D unavailable (no WebGL?)", e); $("#labels").innerHTML = "<div class='empty' style='position:absolute;top:60px;left:14px'>3D-облако недоступно (нет WebGL) — используйте 2D СХЕМУ</div>"; }
setupWindow();
refresh(); setInterval(refresh, 5000);
wsNotify();
checkUpdate();
window.__noirReady = true;
