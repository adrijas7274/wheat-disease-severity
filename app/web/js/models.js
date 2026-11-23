// The three ONNX models of the mobile version, behind the small `runtime` interface that pipeline.js expects.
// `ort` is onnxruntime-web (browser) or the same package in Node (parity test); `loadModel(key)` returns the
// model's bytes (Uint8Array) or URL.

export async function createRuntime(ort, policy, loadModel, sessionOptions = {}) {
  const opts = { executionProviders: ["wasm"], graphOptimizationLevel: "all", ...sessionOptions };
  const make = async (key) => ort.InferenceSession.create(await loadModel(key), opts);
  const [region, encoder, decoder] = [await make("region"), await make("leaf_encoder"), await make("leaf_decoder")];
  const S = policy.image_size;
  return {
    async region(x) {
      const out = await region.run({ image: new ort.Tensor("float32", x, [1, 3, S, S]) });
      return out.logits.data;
    },
    async leafEncoder(x, w, h) {
      const out = await encoder.run({ batched_images: new ort.Tensor("float32", x, [1, 3, h, w]) });
      return out.image_embeddings;
    },
    async leafDecoder(emb, point, hw) {
      const out = await decoder.run({
        image_embeddings: emb,
        batched_point_coords: new ort.Tensor("float32", Float32Array.from(point), [1, 1, 1, 2]),
        batched_point_labels: new ort.Tensor("float32", Float32Array.from([1]), [1, 1, 1]),
        orig_im_size: new ort.Tensor("int64", BigInt64Array.from(hw.map((v) => BigInt(v))), [2]),
      });
      return { logits: out.output_masks.data, scores: out.iou_predictions.data };
    },
    release() { for (const s of [region, encoder, decoder]) s.release?.(); },
  };
}
