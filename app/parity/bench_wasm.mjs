// Speed of each ONNX model in onnxruntime-web (WebAssembly) in Node: FP32 vs INT8, 1 vs 4 threads.
// Usage: node app/parity/bench_wasm.mjs <threads> <file.onnx>... (inputs are zeros of the model's photo-sized shape)
import fs from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ort = require("onnxruntime-web");
ort.env.wasm.numThreads = Number(process.argv[2]);
const feeds = {
  segformer: () => ({ image: new ort.Tensor("float32", new Float32Array(3 * 512 * 512), [1, 3, 512, 512]) }),
  efficient_sam_vitt_encoder: () => ({ batched_images: new ort.Tensor("float32", new Float32Array(3 * 768 * 1024), [1, 3, 768, 1024]) }),
  mobile_sam_encoder: () => ({ image: new ort.Tensor("float32", new Float32Array(3 * 1024 * 1024), [1, 3, 1024, 1024]) }),
};
for (const file of process.argv.slice(3)) {
  const key = Object.keys(feeds).find((k) => file.includes(k));
  const s = await ort.InferenceSession.create(new Uint8Array(fs.readFileSync(file)), { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
  await s.run(feeds[key]());
  const ts = [];
  for (let i = 0; i < 2; i++) { const t = performance.now(); await s.run(feeds[key]()); ts.push(performance.now() - t); }
  console.log(`threads=${process.argv[2]} ${file.split(/[\\/]/).pop()}: ${Math.min(...ts).toFixed(0)} ms`);
  await s.release();
}
