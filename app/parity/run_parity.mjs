// Parity test, JavaScript side: run the browser pipeline (app/web/js) in Node with onnxruntime-web (WebAssembly,
// 1 thread, like a phone without cross-origin isolation) on the photos exported by `python -m src.mobile.parity`.
//
// Usage (from the repository root):  node app/parity/run_parity.mjs data/mobile_parity
// Reads  <dir>/inputs/index.jsonl and <dir>/inputs/<i>.rgb (raw RGB bytes of the capped photo)
// Writes <dir>/js_results.jsonl and <dir>/js_masks/<i>_{region,leaf}.bin (one byte per pixel)

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { analyse } from "../web/js/pipeline.js";
import { createRuntime } from "../web/js/models.js";

const require = createRequire(import.meta.url);
const ort = require("onnxruntime-web");
ort.env.wasm.numThreads = 1;

const dir = process.argv[2] || "data/mobile_parity";
const web = path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", "web");
const policy = JSON.parse(fs.readFileSync(path.join(web, "policy.json"), "utf8"));
const runtime = await createRuntime(ort, policy, async (key) => new Uint8Array(fs.readFileSync(path.join(web, policy.models[key].file))));

const rows = fs.readFileSync(path.join(dir, "inputs", "index.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
fs.mkdirSync(path.join(dir, "js_masks"), { recursive: true });
const out = fs.createWriteStream(path.join(dir, "js_results.jsonl"));
for (const r of rows) {
  const data = new Uint8Array(fs.readFileSync(path.join(dir, "inputs", `${r.i}.rgb`)));
  const photo = { width: r.w, height: r.h, data };
  const res = await analyse(photo, r.disease, r.click, runtime, policy);
  fs.writeFileSync(path.join(dir, "js_masks", `${r.i}_region.bin`), res.region);
  fs.writeFileSync(path.join(dir, "js_masks", `${r.i}_leaf.bin`), res.leaf);
  const t = res.timing;
  out.write(JSON.stringify({
    i: r.i, name: r.name, action: res.action === "retake_no_leaf" ? "retake" : res.action, severity: res.severity,
    level: res.level, decision: res.decision, uncertainty: res.uncertainty, failed: res.failed, features: res.features,
    shape: [res.image.height, res.image.width],
    ms: { gate: t.gate - t.start, region: t.region - t.gate, encoder: t.encoder - t.region, decoder: t.decoder - t.encoder,
          colour: t.end - t.decoder, total: t.end - t.start },
  }) + "\n");
  console.log(`${r.i + 1}/${rows.length} ${r.name.slice(0, 40)} ${res.action} ${res.severity?.toFixed(2)} ${t.end - t.start} ms`);
}
out.end();
runtime.release();
