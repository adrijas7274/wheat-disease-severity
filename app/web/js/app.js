// Screens: language -> how-to (first start) -> home -> camera (or gallery) -> disease -> tap the leaf (scanning)
// -> result; plus history and about. The pipeline runs in a worker (worker.js); stage 1 (gate, region model, leaf
// encoder) starts as soon as the photo is chosen, stage 2 (decoder, colour rule) on the tap.
import * as i18n from "./i18n.js";
import * as speech from "./speech.js";
import * as camera from "./camera.js";
import * as history from "./history.js";
import { adviceFor, outcomeFor } from "./advice.js";

const $ = (id) => document.getElementById(id);
const SCREENS = ["s-lang", "s-howto", "s-home", "s-camera", "s-disease", "s-tap", "s-result", "s-history", "s-about"];
const HOWTO_SEEN = "wheat-app-howto-seen";
const LEVELS = ["none", "low", "medium", "high"];

// disease key (config/policy name) -> strings key and a small original drawing of the symptom
const DISEASES = [
  ["wheat stripe rust", "d_stripe_rust", '<rect width="52" height="52" fill="#4c8c2b"/><path d="M8 4v44M20 4v44M32 4v44M44 4v44" stroke="#f2c230" stroke-width="5" stroke-dasharray="7 4"/>'],
  ["wheat leaf rust", "d_leaf_rust", '<rect width="52" height="52" fill="#4c8c2b"/><g fill="#9a4a12"><circle cx="12" cy="12" r="4"/><circle cx="34" cy="9" r="3.5"/><circle cx="24" cy="26" r="4"/><circle cx="42" cy="30" r="3.5"/><circle cx="12" cy="40" r="3.5"/><circle cx="32" cy="43" r="4"/></g>'],
  ["wheat powdery mildew", "d_powdery_mildew", '<rect width="52" height="52" fill="#4c8c2b"/><g fill="#f4f4ef" opacity=".92"><ellipse cx="16" cy="16" rx="10" ry="7"/><ellipse cx="36" cy="30" rx="11" ry="8"/><ellipse cx="14" cy="40" rx="8" ry="5"/></g>'],
  ["wheat septoria blotch", "d_septoria", '<rect width="52" height="52" fill="#4c8c2b"/><g fill="#7a5a33" stroke="#3b2a17" stroke-width="1.5"><path d="M6 10q14-6 20 6t-6 14Q8 28 6 10z"/><path d="M30 30q12-4 16 6t-10 12q-8-4-6-18z"/></g>'],
  ["wheat bacterial leaf streak (black chaff)", "d_black_chaff", '<rect width="52" height="52" fill="#4c8c2b"/><path d="M14 2l4 48M30 2l-3 48M42 2l2 48" stroke="#2b2018" stroke-width="4"/>'],
];
const DISEASE_KEY = Object.fromEntries(DISEASES.map(([n, k]) => [n, k]));

// outcome icons: every colour also has its own shape, so colour is never the only signal
const ICONS = {
  no_action: '<svg viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>',
  monitor: '<svg viewBox="0 0 24 24"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  treat: '<svg viewBox="0 0 24 24"><path d="M9 9h6v12H9zM10 9V6h4v3M14 6h3M17 4v4M19 5h2M19 7h2M8 13h8"/></svg>',
  treat_urgently: '<svg viewBox="0 0 24 24"><path d="M6 9h6v12H6zM7 9V6h4v3M11 6h3"/><path d="M18 4v10M18 18v1"/></svg>',
  retake: '<svg viewBox="0 0 24 24"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><path d="M15 13a3 3 0 1 1-1-2.2M15 9.5V11h-1.5"/></svg>',
  consult: '<svg viewBox="0 0 24 24"><circle cx="9" cy="7" r="3.5"/><path d="M3 20c0-4 3-6.5 6-6.5s6 2.5 6 6.5"/><path d="M17 8.5a2.5 2.5 0 1 1 3 2.4c-.6.2-1 .7-1 1.3V13M19 16v.5"/></svg>',
};
const REASONS = { sharpness: "r_blurred", noise: "r_noisy", luma: "r_exposure", clip_high: "r_bright", clip_low: "r_dark",
                  blockiness: "r_compressed", min_side: "r_small" };

const app = { worker: null, ready: false, photoId: 0, photo: null, bitmap: null, disease: null, click: null,
              gate: null, result: null, diag: {}, speakText: "", stack: [], view: "disease", savedId: 0 };

// ------------------------------------------------------------------------------------------------ navigation

function show(id, { push = true } = {}) {
  const cur = app.stack[app.stack.length - 1];
  if (cur === "s-camera" && id !== "s-camera") camera.stop();
  if (id === "s-home") app.stack = ["s-home"];
  else if (push && cur !== id) app.stack.push(id);
  for (const s of SCREENS) $(s).hidden = s !== id;
  $("backBtn").hidden = app.stack.length < 2 || id === "s-home";
  window.scrollTo(0, 0);
}

function back() {
  speech.stop();
  if (app.stack.length < 2) return;
  const from = app.stack.pop();
  let to = app.stack[app.stack.length - 1];
  // leaving a photo's screens goes back home; late results for that photo are ignored
  if (["s-disease", "s-tap", "s-result"].includes(from)) { app.photoId += 1; to = "s-home"; }
  if (to === "s-tap" || to === "s-camera") to = "s-home";
  show(to, { push: false });
}

// ------------------------------------------------------------------------------------------------ language

function applyStrings() {
  for (const el of document.querySelectorAll("[data-t]")) el.textContent = i18n.t(el.dataset.t);
  for (const el of document.querySelectorAll("[data-t-label]")) el.setAttribute("aria-label", i18n.t(el.dataset.tLabel));
  document.title = i18n.t("app_title");
  const cur = i18n.current();
  $("langName").textContent = cur.native;
  $("unverified").hidden = cur.status === "verified";
  for (const b of document.querySelectorAll("#diseases .choice")) b.querySelector("span").textContent = i18n.t(b.dataset.key);
  // re-render even while hidden (the language picker covers them), so they are in the new language on return
  if (app.result && app.bitmap) renderResult();
  renderHistory();
}

function buildLanguages() {
  const list = $("langList");
  const fonts = app.strings.fonts;
  for (const l of i18n.languages()) {
    const wrap = document.createElement("div");
    wrap.className = "langWrap";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "langTile";
    b.lang = l.code;
    b.dir = l.dir;
    b.style.fontFamily = l.font ? `"${fonts[l.font]}", "Noto Sans", sans-serif` : "";
    b.innerHTML = '<span class="native"></span><span class="latin"></span>';
    b.querySelector(".native").textContent = l.native;
    b.querySelector(".latin").textContent = l.name;
    b.onclick = () => pickLanguage(l.code);
    const say = document.createElement("button");
    say.type = "button";
    say.className = "iconBtn soft say";
    say.setAttribute("aria-label", `${l.name}: listen`);
    say.innerHTML = '<svg><use href="#i-speaker"/></svg>';
    say.onclick = () => speech.speak(`${l.native}. ${l.strings.lang_title}`, l.tts);
    wrap.append(b, say);
    list.appendChild(wrap);
  }
}

function openLanguages() {
  i18n.loadAllFonts();
  const code = i18n.current().code;
  for (const b of document.querySelectorAll(".langTile")) b.setAttribute("aria-current", String(b.lang === code));
  show("s-lang");
}

function pickLanguage(code) {
  speech.stop();
  i18n.setLanguage(code, true);
  applyStrings();
  let seen = false;
  try { seen = localStorage.getItem(HOWTO_SEEN) === "1"; } catch { /* ignore */ }
  if (!seen) return show("s-howto");
  if (app.stack.length > 1) back(); else show("s-home");
}

// ------------------------------------------------------------------------------------------------ worker

function startWorker() {
  app.worker = new Worker(new URL("./worker.js", import.meta.url), { type: "module" });
  app.worker.onmessage = (e) => onWorker(e.data);
  app.worker.onerror = (e) => fail(e.message || "worker failed to start");
  app.worker.postMessage({ type: "init" });
  $("loading").hidden = false;
}

function onWorker(m) {
  if (m.type === "progress") {
    $("meterFill").style.width = `${Math.min(100, (100 * m.loaded) / m.total).toFixed(0)}%`;
  } else if (m.type === "ready") {
    app.ready = true;
    Object.assign(app.diag, { tag: m.tag, threads: m.threads, crossOriginIsolated: m.isolated, cores: m.cores,
                              modelLoadMs: m.loadMs });
    $("loading").hidden = true;
    if (app.queued) { const q = app.queued; app.queued = null; sendPhoto(q); }
  } else if (m.type === "photo") {
    if (m.id !== app.photoId) return;
    app.gate = m;
    if (m.retake) {
      app.result = { action: "retake", failed: m.failed, computeMs: m.computeMs };
      app.diag.lastComputeMs = m.computeMs;
      showResult();
    } else {
      app.diag.lastStage1Ms = m.stage1Ms;
    }
  } else if (m.type === "result") {
    if (m.id !== app.photoId) return;
    app.result = m;
    Object.assign(app.diag, { lastComputeMs: m.computeMs, lastStepsMs: m.ms });
    highlightLeaf(m).then(showResult);
  } else if (m.type === "error") {
    fail(m.message);
  }
}

function fail(msg) {
  console.error(msg);
  app.diag.lastError = msg;
  $("working").hidden = true;
  $("scan").hidden = true;
  alert(`${i18n.t("out_retake")}\n\n(${msg})`);
  show("s-home");
}

// ------------------------------------------------------------------------------------------------ photo

async function decode(file) {
  try {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    const url = URL.createObjectURL(file);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return await createImageBitmap(img);
    } finally {
      URL.revokeObjectURL(url);
    }
  }
}

function rgbOf(bitmap) {
  const c = document.createElement("canvas");
  c.width = bitmap.width;
  c.height = bitmap.height;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(bitmap, 0, 0);
  const rgba = ctx.getImageData(0, 0, c.width, c.height).data;
  const rgb = new Uint8Array(c.width * c.height * 3);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j += 3) { rgb[j] = rgba[i]; rgb[j + 1] = rgba[i + 1]; rgb[j + 2] = rgba[i + 2]; }
  c.width = c.height = 0;
  return rgb;
}

async function onFile(input) {
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  await usePhoto(await decode(file), file);
}

async function usePhoto(bitmap, blob) {
  speech.stop();
  app.photoId += 1;
  app.result = null;
  app.gate = null;
  app.click = null;
  app.view = "disease";
  app.bitmap?.close?.();
  app.bitmap = bitmap;
  if (app.thumbUrl) URL.revokeObjectURL(app.thumbUrl);
  app.thumbUrl = URL.createObjectURL(blob);
  $("thumb").src = app.thumbUrl;
  const msg = { type: "photo", id: app.photoId, width: bitmap.width, height: bitmap.height, data: rgbOf(bitmap).buffer };
  app.photo = { width: msg.width, height: msg.height };
  if (app.ready) sendPhoto(msg); else app.queued = msg;
  show("s-disease");
}

function sendPhoto(msg) { app.worker.postMessage(msg, [msg.data]); }

// ------------------------------------------------------------------------------------------------ camera

async function openCamera() {
  if (!camera.cameraAvailable()) return $("camera").click();
  show("s-camera");
  setHint("cam_place");
  try {
    await camera.start($("video"), setHint);
  } catch (e) {
    app.diag.camera = `live camera failed: ${e.name || e}`;
    back();
    $("camera").click(); // the phone's own camera app instead
  }
}

function setHint(key) {
  $("camHint").querySelector("span").textContent = i18n.t(key);
  $("camHint").querySelector("use").setAttribute("href", key === "cam_ok" ? "#i-check" : "#i-warn");
  $("s-camera").querySelector(".cam").classList.toggle("ok", key === "cam_ok");
}

async function onShutter() {
  const video = $("video");
  if (!video.videoWidth) return;
  const { bitmap, blob } = await camera.capture(video);
  camera.stop();
  await usePhoto(bitmap, blob);
}

// ------------------------------------------------------------------------------------------------ disease + tap

function buildDiseases() {
  const box = $("diseases");
  for (const [name, key, svg] of DISEASES) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "choice";
    b.dataset.key = key;
    b.innerHTML = `<svg class="sw" viewBox="0 0 52 52" aria-hidden="true" style="stroke:none">${svg}</svg><span></span>`;
    b.onclick = () => { app.disease = name; showTap(); };
    box.appendChild(b);
  }
}

function fitCanvas(canvas, w, h, maxW = 1080) {
  const s = Math.min(1, maxW / w);
  canvas.width = Math.round(w * s);
  canvas.height = Math.round(h * s);
  return s;
}

function showTap() {
  if (app.result && app.result.action === "retake") return showResult();
  const cv = $("photo");
  fitCanvas(cv, app.bitmap.width, app.bitmap.height);
  cv.getContext("2d").drawImage(app.bitmap, 0, 0, cv.width, cv.height);
  for (const id of ["tapDot", "working", "scan", "leafGlow"]) $(id).hidden = true;
  cv.onclick = (e) => {
    if (!$("working").hidden) return;
    const r = cv.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width;
    const fy = (e.clientY - r.top) / r.height;
    app.click = [fx * app.photo.width, fy * app.photo.height];
    const dot = $("tapDot");
    dot.style.left = `${fx * 100}%`;
    dot.style.top = `${fy * 100}%`;
    dot.hidden = false;
    $("working").hidden = false;
    $("scan").hidden = false;
    app.worker.postMessage({ type: "tap", id: app.photoId, disease: app.disease, click: app.click });
  };
  show("s-tap");
}

/** Briefly show the leaf the app found (gold) before the result. */
function highlightLeaf(r) {
  $("scan").hidden = true;
  if (!r.leaf || $("s-tap").hidden) return Promise.resolve();
  const cv = $("leafGlow");
  fitCanvas(cv, r.width, r.height, 540);
  const ctx = cv.getContext("2d");
  const img = ctx.createImageData(cv.width, cv.height);
  const sx = r.width / cv.width;
  const sy = r.height / cv.height;
  for (let y = 0; y < cv.height; y++) {
    const my = Math.min(r.height - 1, Math.floor((y + 0.5) * sy)) * r.width;
    for (let x = 0; x < cv.width; x++) {
      const i = 4 * (y * cv.width + x);
      if (r.leaf[my + Math.min(r.width - 1, Math.floor((x + 0.5) * sx))]) { img.data[i] = 224; img.data[i + 1] = 178; img.data[i + 2] = 60; img.data[i + 3] = 110; }
      else img.data[i + 3] = 120;
    }
  }
  ctx.putImageData(img, 0, 0);
  cv.hidden = false;
  return new Promise((res) => setTimeout(res, matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700));
}

// ------------------------------------------------------------------------------------------------ result

function gaugeTicks() {
  const g = $("gaugeTicks");
  g.textContent = "";
  for (const t of [app.policy.severity_thresholds.low_max, app.policy.severity_thresholds.medium_max]) {
    const a = -Math.PI / 2 + 2 * Math.PI * t;
    const p = (r) => [100 + r * Math.cos(a), 100 + r * Math.sin(a)];
    const [x1, y1] = p(72);
    const [x2, y2] = p(96);
    const l = document.createElementNS("http://www.w3.org/2000/svg", "line");
    Object.entries({ x1, y1, x2, y2, class: "tick" }).forEach(([k, v]) => l.setAttribute(k, v));
    g.appendChild(l);
  }
}

function renderLevelScale(level) {
  const ol = $("levelScale");
  ol.textContent = "";
  for (const lv of LEVELS) {
    const li = document.createElement("li");
    li.className = `lv-${lv}${lv === level ? " on" : ""}`;
    li.innerHTML = '<span class="arrow">▼</span><span></span>';
    li.lastChild.textContent = i18n.t(`lvl_${lv}`);
    ol.appendChild(li);
  }
}

function addRow(dl, label, value) {
  if (!value) return;
  const dt = document.createElement("dt");
  dt.textContent = i18n.t(label);
  const dd = document.createElement("dd");
  const v = document.createElement("span");
  v.className = "ltr";
  v.textContent = value;
  dd.appendChild(v);
  dl.append(dt, dd);
}

const litres = (w) => (w && /^\d+(\.\d+)?(\s*-\s*\d+(\.\d+)?)?$/.test(String(w).trim()) ? `${w} L` : w);

function renderOptions(products) {
  const box = $("advList");
  box.textContent = "";
  const said = [];
  for (const p of products) {
    const div = document.createElement("div");
    div.className = "option";
    const h = document.createElement("h4");
    h.textContent = p.name;
    const dl = document.createElement("dl");
    addRow(dl, "adv_dose_litre", p.dosePerLitre);
    // a per-litre figure printed in the per-hectare column is shown once, as the per-litre dose
    if (!/litre/i.test(p.formulationPerHa || "")) addRow(dl, "adv_dose_ha", p.formulationPerHa);
    addRow(dl, "adv_water_ha", litres(p.waterPerHa));
    div.append(h, dl);
    // converted amounts: grouped under their own label, never mixed with the official figures
    const conv = document.createElement("dl");
    addRow(conv, "adv_per_acre", p.perAcreConverted);
    addRow(conv, "adv_water_acre", p.waterPerAcreConverted);
    addRow(conv, "adv_per_tank", p.perTankConverted);
    if (conv.children.length) {
      const head = document.createElement("p");
      head.className = "convHead";
      head.textContent = i18n.t("adv_converted");
      div.append(head, conv);
    }
    if (p.waitingDays) {
      const w = document.createElement("p");
      w.className = "wait";
      w.textContent = i18n.t("adv_waiting", { days: p.waitingDays });
      div.appendChild(w);
    }
    const src = document.createElement("p");
    src.className = "src";
    src.textContent = `${i18n.t("adv_source")}: ${p.sourceShort}`;
    div.appendChild(src);
    box.appendChild(div);
    const rows = (x) => [...x.querySelectorAll("dt")].map((dt) => `${dt.textContent}: ${dt.nextSibling.firstChild.textContent}`);
    said.push(p.name, ...rows(dl));
    if (conv.children.length) said.push(i18n.t("adv_converted"), ...rows(conv));
    if (p.waitingDays) said.push(i18n.t("adv_waiting", { days: p.waitingDays }));
  }
  return said;
}

function renderResult() {
  const r = app.result;
  const adv = adviceFor(r, app.disease, app.advice);
  const o = outcomeFor(r, adv);
  $("card").style.setProperty("--oc", `var(--o-${o})`);
  $("cardIcon").innerHTML = ICONS[o];
  const msg = adv.action === "ask_expert" ? i18n.t("act_no_registered")
    : i18n.t(o === "retake" ? "out_retake" : o === "consult" ? "out_consult" : `out_${o}`);
  $("cardMsg").textContent = msg;
  const level = adv.level ? i18n.t(`lvl_${adv.level}`) : "";
  $("cardLevel").textContent = level;
  $("cardLevel").hidden = !level;
  const answered = r.action === "answer";
  $("gaugeBox").hidden = !answered;
  $("levelScale").hidden = !answered;
  let sev = "";
  if (answered) {
    sev = i18n.t("severity", { pct: i18n.num(r.severity, 1) });
    $("gaugePct").textContent = `${i18n.num(r.severity, 1)}%`;
    const c = 2 * Math.PI * 84;
    const arc = $("gaugeArc");
    arc.style.strokeDasharray = `0 ${c}`;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      arc.style.strokeDasharray = `${(c * Math.min(100, r.severity)) / 100} ${c}`;
    }));
    renderLevelScale(adv.level);
  }
  $("cardSev").textContent = sev;
  $("cardSev").hidden = !sev;
  let reasons = [];
  if (r.action === "retake") reasons = [...new Set(r.failed.map((f) => REASONS[f] || "r_unsure"))].map((k) => i18n.t(k));
  else if (r.action === "retake_no_leaf") reasons = [i18n.t("r_no_leaf")];
  else if (r.action === "consult") reasons = [i18n.t("r_unsure")];
  $("cardReason").textContent = reasons.join(" ");
  $("cardReason").hidden = !reasons.length;
  $("noVoice").hidden = true;
  $("viewToggle").hidden = !r.leaf;
  const said = [level, msg, sev, ...reasons];
  // treatment details only when adviceFor() returned products (answered photo, spraying level, registered product)
  const has = adv.products && adv.products.length > 0;
  $("advice").hidden = !has;
  if (has) {
    $("advWarn").hidden = !adv.warning;
    said.push(i18n.t("adv_title"), i18n.t("adv_options"), ...renderOptions(adv.products), i18n.t("adv_label"));
    if (adv.warning) said.push(i18n.t("adv_unverified"));
  }
  said.push(i18n.t("kcc"));
  app.speakText = said.filter(Boolean).join(". ");
  drawOverlay(r);
  saveToHistory(r, adv, o);
}

function setView(v) {
  app.view = v;
  $("viewPhoto").setAttribute("aria-pressed", String(v === "photo"));
  $("viewDisease").setAttribute("aria-pressed", String(v === "disease"));
  drawOverlay(app.result);
}

function drawOverlay(r) {
  const cv = $("overlay");
  fitCanvas(cv, app.bitmap.width, app.bitmap.height, 900);
  const ctx = cv.getContext("2d");
  ctx.drawImage(app.bitmap, 0, 0, cv.width, cv.height);
  if (!r.leaf || app.view === "photo") return;
  // masks are at the capped size (r.width x r.height); sample them at the canvas size
  const img = ctx.getImageData(0, 0, cv.width, cv.height);
  const d = img.data;
  const sx = r.width / cv.width;
  const sy = r.height / cv.height;
  for (let y = 0; y < cv.height; y++) {
    const my = Math.min(r.height - 1, Math.floor((y + 0.5) * sy)) * r.width;
    for (let x = 0; x < cv.width; x++) {
      const m = my + Math.min(r.width - 1, Math.floor((x + 0.5) * sx));
      const i = 4 * (y * cv.width + x);
      if (r.lesion && r.lesion[m]) { d[i] = 255; d[i + 1] = 30; d[i + 2] = 200; }
      else if (!r.leaf[m]) { d[i] *= 0.35; d[i + 1] *= 0.35; d[i + 2] *= 0.35; }
    }
  }
  ctx.putImageData(img, 0, 0);
  if (app.click) {
    ctx.lineWidth = 4;
    ctx.strokeStyle = "#fff";
    ctx.beginPath();
    ctx.arc(app.click[0] * cv.width / app.photo.width, app.click[1] * cv.height / app.photo.height, 12, 0, 7);
    ctx.stroke();
  }
}

function showResult() {
  $("working").hidden = true;
  $("scan").hidden = true;
  renderResult();
  show("s-result");
}

async function onSpeak() {
  const ok = await speech.speak(app.speakText, i18n.current().tts);
  $("noVoice").hidden = ok;
}

// ------------------------------------------------------------------------------------------------ history

function saveToHistory(r, adv, outcome) {
  if (app.savedId === app.photoId || r.action === "retake" || r.action === "retake_no_leaf") return;
  app.savedId = app.photoId;
  history.add({ t: Date.now(), disease: app.disease, severity: r.action === "answer" ? r.severity : null,
                level: adv.level, outcome, thumb: history.thumbnail(app.bitmap) });
}

function renderHistory() {
  const list = history.load();
  const ul = $("histList");
  ul.textContent = "";
  $("histEmpty").hidden = list.length > 0;
  $("histClear").hidden = list.length === 0;
  const fmt = new Intl.DateTimeFormat(i18n.current().code, { dateStyle: "medium", timeStyle: "short" });
  for (const e of list) {
    const li = document.createElement("li");
    li.className = "histItem";
    li.style.setProperty("--oc", `var(--o-${e.outcome})`);
    li.innerHTML = '<img alt=""><div class="meta"><b></b><span></span></div><span class="chip"></span>';
    li.querySelector("img").src = e.thumb;
    li.querySelector("b").textContent = i18n.t(DISEASE_KEY[e.disease] || "d_stripe_rust");
    li.querySelector(".meta span").textContent = fmt.format(new Date(e.t));
    const chip = li.querySelector(".chip");
    chip.innerHTML = ICONS[e.outcome] || "";
    chip.append(e.severity !== null ? `${i18n.num(e.severity, 1)}%` : "–");
    ul.appendChild(li);
  }
  // trend of the most recent disease: one bar per answered scan, oldest first, with the level lines
  const box = $("histChart");
  const pts = list.length ? history.trend(list, list[0].disease) : [];
  box.hidden = pts.length < 2;
  if (pts.length >= 2) {
    const W = 300;
    const H = 110;
    const bw = W / pts.length;
    const y = (v) => H - (H * Math.min(100, v)) / 100;
    const lines = [app.policy.severity_thresholds.low_max, app.policy.severity_thresholds.medium_max]
      .map((t) => `<line x1="0" x2="${W}" y1="${y(t * 100)}" y2="${y(t * 100)}" stroke="#4F5A4C" stroke-dasharray="4 3"/>`).join("");
    const bars = pts.map((p, i) => `<rect x="${i * bw + 4}" y="${y(p.severity)}" width="${bw - 8}" height="${H - y(p.severity)}" rx="4" fill="var(--o-${p.outcome})"/>`).join("");
    box.innerHTML = `<h4></h4><svg viewBox="0 0 ${W} ${H}" role="img">${lines}${bars}</svg>`;
    box.querySelector("h4").textContent = i18n.t(DISEASE_KEY[pts[0].disease]);
  }
}

// ------------------------------------------------------------------------------------------------ about

function diagText() {
  const mem = performance.memory ? `${(performance.memory.usedJSHeapSize / 1e6).toFixed(0)} MB JS heap (main thread)` : "not available";
  const d = app.diag;
  return [
    `version: ${d.tag || "…"}`,
    `threads: ${d.threads ?? "…"} (cross-origin isolated: ${d.crossOriginIsolated ?? "…"}, cores: ${d.cores ?? "?"})`,
    `model loading: ${d.modelLoadMs != null ? (d.modelLoadMs / 1000).toFixed(1) + " s" : "…"}`,
    `last photo, compute time: ${d.lastComputeMs != null ? (d.lastComputeMs / 1000).toFixed(2) + " s" : "-"}`,
    d.lastStepsMs ? `  steps (ms): ${Object.entries(d.lastStepsMs).map(([k, v]) => `${k} ${v}`).join(", ")}` : "",
    `memory: ${mem}`,
    `device memory hint: ${navigator.deviceMemory ? navigator.deviceMemory + " GB" : "not available"}`,
    `app: ${globalThis.Capacitor?.isNativePlatform?.() ? "Android app" : "browser"}; ${navigator.userAgent}`,
    d.camera ? d.camera : "",
    d.lastError ? `last error: ${d.lastError}` : "",
  ].filter(Boolean).join("\n");
}

async function onVoiceCheck() {
  const pre = $("voices");
  pre.hidden = false;
  pre.textContent = "…";
  const rows = await speech.voiceReport(i18n.languages());
  pre.textContent = rows.map((r) => `${r.code.padEnd(4)} ${r.tts.padEnd(7)} ${r.ok ? "voice found" : "no voice"}`
    + (r.offline === true ? " (on-device)" : r.offline === false ? " (network voice)" : "")
    + (r.voice ? ` - ${r.voice}` : "")).join("\n");
}

// ------------------------------------------------------------------------------------------------ start

/** Offline cache + cross-origin isolation (for threads). Returns true when the page is about to reload once. */
async function registerServiceWorker() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return false;
  let reg;
  try {
    reg = await navigator.serviceWorker.register("sw.js");
  } catch (e) {
    app.diag.serviceWorker = `failed: ${e.message}`;
    return false;
  }
  let reloaded = false;
  try { reloaded = sessionStorage.getItem("coi-reload") === "1"; } catch { /* ignore */ }
  if (window.crossOriginIsolated || reloaded) return false;
  const reload = () => { try { sessionStorage.setItem("coi-reload", "1"); } catch { /* ignore */ } location.reload(); };
  if (navigator.serviceWorker.controller) { reload(); return true; }
  // first visit: the service worker downloads every file once (shown on the meter), then the page reloads
  // isolated and loads the models from the cache, so nothing is downloaded twice
  $("loading").hidden = false;
  navigator.serviceWorker.addEventListener("message", (e) => {
    if (e.data && e.data.type === "sw-progress") $("meterFill").style.width = `${(100 * e.data.loaded / e.data.total).toFixed(0)}%`;
  });
  navigator.serviceWorker.addEventListener("controllerchange", reload, { once: true });
  const sw = reg.installing || reg.waiting;
  sw?.addEventListener("statechange", () => {
    if (sw.state === "redundant") { app.diag.serviceWorker = "install failed: running without offline cache"; startWorker(); }
  });
  return true;
}

function firstScreen(saved) {
  let seen = false;
  try { seen = localStorage.getItem(HOWTO_SEEN) === "1"; } catch { /* ignore */ }
  if (!saved) return openLanguages();
  show(seen ? "s-home" : "s-howto");
}

async function main() {
  app.strings = await i18n.loadStrings();
  app.advice = await (await fetch("advice.json")).json();
  app.policy = await (await fetch("policy.json")).json();
  let saved = null; // read before setLanguage(), which saves the choice
  try { saved = localStorage.getItem("wheat-app-lang"); } catch { /* ignore */ }
  i18n.setLanguage(i18n.pickLanguage());
  buildDiseases();
  buildLanguages();
  gaugeTicks();
  applyStrings();
  $("langBtn").onclick = openLanguages;
  $("backBtn").onclick = back;
  firstScreen(saved);
  if (await registerServiceWorker()) return;
  $("camera").onchange = (e) => onFile(e.target);
  $("gallery").onchange = (e) => onFile(e.target);
  $("cameraBtn").onclick = openCamera;
  $("shutter").onclick = onShutter;
  $("howtoBtn").onclick = () => show("s-howto");
  $("howtoDone").onclick = () => { try { localStorage.setItem(HOWTO_SEEN, "1"); } catch { /* ignore */ } speech.stop(); show("s-home"); };
  $("howtoSpeak").onclick = () => speech.speak(["howto", "step1", "step2", "step3"].map((k) => i18n.t(k)).join(". "), i18n.current().tts);
  $("historyBtn").onclick = () => { renderHistory(); show("s-history"); };
  $("histClear").onclick = () => { if (confirm(`${i18n.t("hist_clear")}?`)) { history.clear(); renderHistory(); } };
  $("again").onclick = () => { speech.stop(); show("s-home"); };
  $("speak").onclick = onSpeak;
  $("viewPhoto").onclick = () => setView("photo");
  $("viewDisease").onclick = () => setView("disease");
  $("aboutBtn").onclick = () => { $("diag").textContent = diagText(); show("s-about"); };
  $("aboutBack").onclick = back;
  $("voiceCheck").onclick = onVoiceCheck;
  startWorker();
}

main().catch((e) => fail(String(e)));
