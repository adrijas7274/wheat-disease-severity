// Runs the whole mobile pipeline off the main thread so the screen stays responsive.
// Messages in:  {type:"init"} | {type:"photo", id, width, height, data:ArrayBuffer RGB} | {type:"tap", id, disease, click:[x,y]}
// Messages out: {type:"progress", loaded, total} | {type:"ready", ...diag} | {type:"photo", id, retake, failed}
//               | {type:"result", id, ...} | {type:"error", message}
import * as ort from "../ort/ort.wasm.min.mjs";
import { analysePhoto, finishAnalysis, computeMs } from "./pipeline.js";
import { createRuntime } from "./models.js";

let policy = null;
let runtime = null;
let state = null; // stage-1 result of the current photo
let stateId = -1;
let pending = null; // stage-1 promise of the current photo
let chain = Promise.resolve(); // one model run at a time (a session cannot run twice at once)

async function fetchBytes(url, onBytes) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const reader = res.body.getReader();
  const parts = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    onBytes(value.length);
  }
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

async function sha256(bytes) {
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(h, (b) => b.toString(16).padStart(2, "0")).join("");
}

async function init() {
  const t0 = Date.now();
  policy = await (await fetch("../policy.json")).json();
  const threads = self.crossOriginIsolated ? Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 2) - 1)) : 1;
  ort.env.wasm.numThreads = threads;
  ort.env.wasm.wasmPaths = new URL("../ort/", import.meta.url).href;
  const sizes = { region: 7.8e6, leaf_encoder: 8.9e6, leaf_decoder: 8.8e6 };
  const total = Object.values(sizes).reduce((a, b) => a + b, 0);
  let loaded = 0;
  const bad = [];
  runtime = await createRuntime(ort, policy, async (key) => {
    const bytes = await fetchBytes(new URL(`../${policy.models[key].file}`, import.meta.url).href, (n) => {
      loaded += n;
      postMessage({ type: "progress", loaded, total });
    });
    if (crypto.subtle && (await sha256(bytes)) !== policy.models[key].sha256) bad.push(key);
    return bytes;
  });
  if (bad.length) throw new Error(`model file changed: ${bad.join(", ")}`);
  postMessage({ type: "ready", loadMs: Date.now() - t0, threads, isolated: !!self.crossOriginIsolated, tag: policy.tag,
                cores: navigator.hardwareConcurrency || null });
}

async function photo(msg) {
  stateId = msg.id;
  state = null;
  const p = { width: msg.width, height: msg.height, data: new Uint8Array(msg.data) };
  pending = chain = chain.catch(() => {}).then(() => analysePhoto(p, runtime, policy, { stopAtRetake: true }));
  const st = await pending;
  if (stateId !== msg.id) return;
  state = st;
  if (st.stopped) {
    const r = st.result;
    postMessage({ type: "photo", id: msg.id, retake: true, failed: r.failed, computeMs: computeMs(r.timing),
                  width: r.image.width, height: r.image.height });
  } else {
    postMessage({ type: "photo", id: msg.id, retake: false, failed: [], width: st.img.width, height: st.img.height,
                  stage1Ms: st.t.encoder - st.t.start });
  }
}

async function tap(msg) {
  if (stateId !== msg.id) throw new Error("photo changed");
  const st = state || (await pending);
  if (st.stopped) return;
  const r = await (chain = chain.catch(() => {}).then(() => finishAnalysis(st, msg.disease, msg.click, runtime, policy)));
  const t = r.timing;
  postMessage({
    type: "result", id: msg.id, action: r.action, severity: r.severity, level: r.level, decision: r.decision,
    uncertainty: r.uncertainty, failed: r.failed, width: r.image.width, height: r.image.height,
    leaf: r.leaf, lesion: r.lesion, computeMs: computeMs(t),
    ms: { gate: t.gate - t.start, region: t.region - t.gate, encoder: t.encoder - t.region, decoder: t.decoder - t.tap,
          colour: t.end - t.decoder },
  });
}

self.onmessage = async (e) => {
  const msg = e.data;
  try {
    if (msg.type === "init") await init();
    else if (msg.type === "photo") await photo(msg);
    else if (msg.type === "tap") await tap(msg);
  } catch (err) {
    postMessage({ type: "error", id: msg.id, message: String(err && err.message ? err.message : err) });
  }
};
