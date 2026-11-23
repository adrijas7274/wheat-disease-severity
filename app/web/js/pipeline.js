// Wheat severity, mobile version (final-v1-mobile): the final-v1 pipeline ported to JavaScript.
//
// Pure functions on RGB images {data: Uint8Array (RGB, row-major), width, height}; no DOM, so the same file runs
// in the browser and in Node (parity test against the Python reference, src/mobile/pipeline_ref.py).
// Every frozen value comes from policy.json (written by `python -m src.mobile.export_web_policy`).
// OpenCV operations are re-implemented to match cv2's integer arithmetic where it matters (INTER_AREA,
// RGB2GRAY, RGB2HSV); the parity test reports how close the port is.
//
// Levels and recommendations are PLACEHOLDERS, not validated agronomic advice.

// ----------------------------------------------------------------------------------------------- small helpers

/** Python's round(): half to even. */
export function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

/** cvRound / numpy rint: half to even. */
const rint = pyRound;

function clampByte(v) { return v < 0 ? 0 : v > 255 ? 255 : v; }

export function makeImage(width, height) { return { width, height, data: new Uint8Array(width * height * 3) }; }

function countTrue(mask) { let n = 0; for (let i = 0; i < mask.length; i++) n += mask[i]; return n; }

// --------------------------------------------------------------------------------------------------- resizing

/** Per-axis INTER_AREA tables (cv2 computeResizeAreaTab): list of [dst, src, weight]. */
function areaTable(srcSize, dstSize) {
  const scale = srcSize / dstSize;
  const tab = [];
  for (let dx = 0; dx < dstSize; dx++) {
    const fsx1 = dx * scale, fsx2 = fsx1 + scale;
    const cellWidth = Math.min(scale, srcSize - fsx1);
    const sx2 = Math.min(Math.floor(fsx2), srcSize - 1);
    const sx1 = Math.min(Math.ceil(fsx1), sx2);
    if (sx1 - fsx1 > 1e-3) tab.push([dx, sx1 - 1, Math.fround((sx1 - fsx1) / cellWidth)]);
    for (let sx = sx1; sx < sx2; sx++) tab.push([dx, sx, Math.fround(1.0 / cellWidth)]);
    if (fsx2 - sx2 > 1e-3) tab.push([dx, sx2, Math.fround(Math.min(Math.min(fsx2 - sx2, 1.0), cellWidth) / cellWidth)]);
  }
  return tab;
}

/** cv2.resize(..., INTER_AREA) for downscaling a multi-channel uint8 image. */
export function resizeArea(img, w, h) {
  const { width: W, height: H, data } = img;
  if (w === W && h === H) return { width: w, height: h, data: data.slice() };
  const intScale = W % w === 0 && H % h === 0;
  if (intScale) {
    // cv2's integer-scale path: plain average of the block, rounded
    const sx = W / w, sy = H / h, area = sx * sy, out = makeImage(w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++) {
      let s = 0;
      for (let yy = 0; yy < sy; yy++) { const row = ((y * sy + yy) * W + x * sx) * 3 + c; for (let xx = 0; xx < sx; xx++) s += data[row + xx * 3]; }
      // cv2's 2x2 fast path rounds half up ((a+b+c+d+2)>>2); larger integer blocks use cvRound
      out.data[(y * w + x) * 3 + c] = clampByte(area === 4 ? (s + 2) >> 2 : rint(s / area));
    }
    return out;
  }
  const xt = areaTable(W, w), yt = areaTable(H, h);
  const rows = new Float64Array(h * W * 3);
  for (const [dy, sy, wy] of yt) {
    const src = sy * W * 3, dst = dy * W * 3;
    for (let i = 0; i < W * 3; i++) rows[dst + i] += data[src + i] * wy;
  }
  const out = makeImage(w, h), acc = new Float64Array(w * 3);
  for (let y = 0; y < h; y++) {
    acc.fill(0);
    const base = y * W * 3;
    for (const [dx, sx, wx] of xt) for (let c = 0; c < 3; c++) acc[dx * 3 + c] += rows[base + sx * 3 + c] * wx;
    for (let i = 0; i < w * 3; i++) out.data[y * w * 3 + i] = clampByte(rint(acc[i]));
  }
  return out;
}

/** cv2.resize(..., INTER_LINEAR) for uint8 images (11-bit fixed-point coefficients, as cv2). */
export function resizeBilinear(img, w, h) {
  const { width: W, height: H, data } = img;
  const sxs = W / w, sys = H / h;
  const xi = new Int32Array(w * 2), xa = new Int32Array(w * 2);
  for (let x = 0; x < w; x++) {
    let fx = (x + 0.5) * sxs - 0.5, sx = Math.floor(fx); fx -= sx;
    if (sx < 0) { fx = 0; sx = 0; }
    if (sx >= W - 1) { fx = 0; sx = W - 1; }
    const a0 = rint((1 - fx) * 2048);
    xi[2 * x] = sx; xi[2 * x + 1] = Math.min(sx + 1, W - 1); xa[2 * x] = a0; xa[2 * x + 1] = 2048 - a0;
  }
  const out = makeImage(w, h);
  const r0 = new Int32Array(w * 3), r1 = new Int32Array(w * 3);
  const hrow = (sy, dst) => {
    const base = sy * W * 3;
    for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++)
      dst[x * 3 + c] = data[base + xi[2 * x] * 3 + c] * xa[2 * x] + data[base + xi[2 * x + 1] * 3 + c] * xa[2 * x + 1];
  };
  for (let y = 0; y < h; y++) {
    let fy = (y + 0.5) * sys - 0.5, sy = Math.floor(fy); fy -= sy;
    if (sy < 0) { fy = 0; sy = 0; }
    if (sy >= H - 1) { fy = 0; sy = H - 1; }
    const b0 = rint((1 - fy) * 2048), b1 = 2048 - b0;
    hrow(sy, r0); hrow(Math.min(sy + 1, H - 1), r1);
    for (let i = 0; i < w * 3; i++) out.data[y * w * 3 + i] = clampByte((r0[i] * b0 + r1[i] * b1 + (1 << 21)) >> 22);
  }
  return out;
}

/** cv2.resize(float map, (w, h), INTER_LINEAR) evaluated only as "value >= 0" -> Uint8Array mask. */
export function bilinearMaskGE0(map, W, H, w, h) {
  const out = new Uint8Array(w * h);
  const sxs = W / w, sys = H / h;
  const x0 = new Int32Array(w), x1 = new Int32Array(w), fxs = new Float32Array(w);
  for (let x = 0; x < w; x++) {
    let fx = (x + 0.5) * sxs - 0.5, sx = Math.floor(fx); fx -= sx;
    if (sx < 0) { fx = 0; sx = 0; }
    if (sx >= W - 1) { fx = 0; sx = W - 1; }
    x0[x] = sx; x1[x] = Math.min(sx + 1, W - 1); fxs[x] = fx;
  }
  for (let y = 0; y < h; y++) {
    let fy = (y + 0.5) * sys - 0.5, sy = Math.floor(fy); fy -= sy;
    if (sy < 0) { fy = 0; sy = 0; }
    if (sy >= H - 1) { fy = 0; sy = H - 1; }
    const ra = sy * W, rb = Math.min(sy + 1, H - 1) * W;
    for (let x = 0; x < w; x++) {
      const fx = fxs[x];
      const top = map[ra + x0[x]] * (1 - fx) + map[ra + x1[x]] * fx;
      const bot = map[rb + x0[x]] * (1 - fx) + map[rb + x1[x]] * fx;
      out[y * w + x] = top * (1 - fy) + bot * fy >= 0 ? 1 : 0;
    }
  }
  return out;
}

/** cv2 INTER_NEAREST resize of a mask. */
export function resizeNearest(mask, W, H, w, h) {
  const out = new Uint8Array(w * h), fx = W / w, fy = H / h;
  const xs = new Int32Array(w);
  for (let x = 0; x < w; x++) xs[x] = Math.min(Math.floor(x * fx), W - 1);
  for (let y = 0; y < h; y++) {
    const sy = Math.min(Math.floor(y * fy), H - 1) * W;
    for (let x = 0; x < w; x++) out[y * w + x] = mask[sy + xs[x]];
  }
  return out;
}

/** src.external.phase7.cap_long_side: INTER_AREA downscale to at most `maxSide` on the long side. */
export function capLongSide(img, maxSide) {
  const { width: w, height: h } = img;
  if (!maxSide || Math.max(h, w) <= maxSide) return img;
  const s = maxSide / Math.max(h, w);
  return resizeArea(img, Math.max(1, pyRound(w * s)), Math.max(1, pyRound(h * s)));
}

// ------------------------------------------------------------------------------------------- quality gate

/** cv2 RGB2GRAY for uint8 (14-bit fixed point). */
export function gray(img) {
  const n = img.width * img.height, g = new Uint8Array(n), d = img.data;
  for (let i = 0; i < n; i++) g[i] = (d[3 * i] * 4899 + d[3 * i + 1] * 9617 + d[3 * i + 2] * 1868 + 8192) >> 14;
  return g;
}

const reflect101 = (i, n) => (n === 1 ? 0 : i < 0 ? -i : i >= n ? 2 * n - 2 - i : i);

/** src.uncertainty.quality_gate.features (on the capped photo). */
export function gateFeatures(img, policy) {
  const { width: w, height: h } = img;
  const scale = policy.gate_long_side / Math.max(h, w);
  const small = scale < 1 ? resizeArea(img, Math.max(1, pyRound(w * scale)), Math.max(1, pyRound(h * scale))) : img;
  const W = small.width, H = small.height, g = gray(small);
  // Laplacian (ksize 1, BORDER_REFLECT_101), variance
  let sum = 0, sum2 = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const c = g[y * W + x];
    const v = g[reflect101(y - 1, H) * W + x] + g[reflect101(y + 1, H) * W + x] + g[y * W + reflect101(x - 1, W)] + g[y * W + reflect101(x + 1, W)] - 4 * c;
    sum += v; sum2 += v * v;
  }
  const n = W * H, mean = sum / n;
  // Immerkaer noise: interior only
  let nsum = 0;
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    const p = (yy, xx) => g[yy * W + xx];
    const v = p(y - 1, x - 1) - 2 * p(y - 1, x) + p(y - 1, x + 1) - 2 * p(y, x - 1) + 4 * p(y, x) - 2 * p(y, x + 1)
      + p(y + 1, x - 1) - 2 * p(y + 1, x) + p(y + 1, x + 1);
    nsum += Math.abs(v);
  }
  const noise = Math.sqrt(Math.PI / 2) * nsum / (6.0 * Math.max((W - 2) * (H - 2), 1));
  let gsum = 0, hi = 0, lo = 0;
  const lin = [0, 0, 0], gamma = policy.gate_gamma;
  const lut = new Float64Array(256);
  for (let i = 0; i < 256; i++) lut[i] = Math.pow(i / 255, gamma);
  for (let i = 0; i < n; i++) {
    gsum += g[i];
    const r = small.data[3 * i], gg = small.data[3 * i + 1], b = small.data[3 * i + 2];
    const m = Math.max(r, gg, b);
    if (m >= 250) hi++;
    if (m <= 5) lo++;
    lin[0] += lut[r]; lin[1] += lut[gg]; lin[2] += lut[b];
  }
  const means = lin.map((v) => v / n + 1e-6), mm = (means[0] + means[1] + means[2]) / 3;
  return {
    sharpness: sum2 / n - mean * mean, noise, luma: gsum / n / 255, clip_high: hi / n, clip_low: lo / n,
    cast: Math.max(...means.map((v) => Math.abs(Math.log(v / mm)))), min_side: Math.min(h, w),
  };
}

/** src.uncertainty.quality_gate.blockiness (full resolution). */
export function blockiness(img, block = 8) {
  const { width: W, height: H } = img, g = gray(img);
  const ratio = (len, other, at) => {
    // steps between k and k+1 along an axis of length `len`, for `other` lines
    let bs = 0, bn = 0, os = 0, on = 0;
    for (let k = 0; k < len - 1; k++) {
      const boundary = (k + 1) % block === 0;
      for (let j = 0; j < other; j++) {
        const s = Math.abs(at(j, k + 1) - at(j, k));
        if (boundary) { bs += s; bn++; } else { os += s; on++; }
      }
    }
    if (bn === 0 || on === 0) return 1.0;
    return (bs / bn + 1e-3) / (os / on + 1e-3);
  };
  const rh = ratio(W, H, (j, k) => g[j * W + k]);
  const rv = ratio(H, W, (j, k) => g[k * W + j]);
  return (rh + rv) / 2;
}

export function failedChecks(feats, ranges) {
  const out = [];
  for (const [name, [lo, hi]] of Object.entries(ranges)) {
    if ((lo !== null && feats[name] < lo) || (hi !== null && feats[name] > hi)) out.push(name);
  }
  return out;
}

// -------------------------------------------------------------------------------------------------- region

/** final-v1 SegFormer input: long side to 512 (INTER_LINEAR), centre padding with 0, ImageNet normalisation. */
export function segformerInput(img, policy) {
  const S = policy.image_size, { width: w, height: h } = img;
  const s = S / Math.max(h, w);
  const nw = pyRound(w * s), nh = pyRound(h * s);
  const r = resizeBilinear(img, nw, nh);
  const top = Math.floor((S - nh) / 2), left = Math.floor((S - nw) / 2);
  const x = new Float32Array(3 * S * S);
  const mean = policy.imagenet_mean, std = policy.imagenet_std;
  for (let c = 0; c < 3; c++) {
    const pad = (0 - mean[c]) / std[c];
    x.fill(pad, c * S * S, (c + 1) * S * S);
    for (let y = 0; y < nh; y++) for (let xx = 0; xx < nw; xx++)
      x[c * S * S + (y + top) * S + xx + left] = (r.data[(y * nw + xx) * 3 + c] / 255 - mean[c]) / std[c];
  }
  return { tensor: x, top, left, nw, nh, size: S };
}

/** Region mask at the photo's size from the 1x2xSxS logits (argmax, crop the padding, nearest resize). */
export function regionFromLogits(logits, info, width, height) {
  const { size: S, top, left, nw, nh } = info, plane = S * S;
  const small = new Uint8Array(nw * nh);
  for (let y = 0; y < nh; y++) for (let x = 0; x < nw; x++) {
    const i = (y + top) * S + x + left;
    small[y * nw + x] = logits[plane + i] > logits[i] ? 1 : 0;
  }
  return { region: resizeNearest(small, nw, nh, width, height), small, smallW: nw, smallH: nh };
}

// ---------------------------------------------------------------------------------------------------- leaf

/** EfficientSAM input: photo at most 1024 px (INTER_AREA), 0..1 floats, CHW. */
export function leafInput(img, policy) {
  const { width: w, height: h } = img;
  const s = Math.min(1, policy.leaf_max_side / Math.max(h, w));
  const small = s < 1 ? resizeArea(img, pyRound(w * s), pyRound(h * s)) : img;
  const n = small.width * small.height, x = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) x[c * n + i] = small.data[3 * i + c] / 255;
  return { tensor: x, scale: s, w: small.width, h: small.height };
}

/** src.severity.leaf_mask.select_leaf (rules min_area and best_score). */
export function selectLeaf(masks, scores, rule, minShare) {
  let best = 0;
  for (let i = 1; i < scores.length; i++) if (scores[i] > scores[best]) best = i;
  if (rule === "best_score") return best;
  if (rule !== "min_area") throw new Error(`unsupported leaf rule ${rule}`);
  const shares = masks.map((m) => countTrue(m) / m.length);
  const big = shares.map((s, i) => [s, i]).filter(([s]) => s >= minShare).map(([, i]) => i);
  if (!big.length) { let j = 0; for (let i = 1; i < shares.length; i++) if (shares[i] > shares[j]) j = i; return j; }
  let k = big[0];
  for (const i of big) if (scores[i] > scores[k]) k = i;
  return k;
}

/** Leaf mask at the photo's size from the decoder outputs (1x1x3xhxw logits, 1x1x3 scores). */
export function leafFromDecoder(logits, scores, info, width, height, policy) {
  const n = info.w * info.h, masks = [];
  for (let k = 0; k < 3; k++) {
    const map = logits.subarray(k * n, (k + 1) * n);
    masks.push(info.w === width && info.h === height
      ? Uint8Array.from(map, (v) => (v >= 0 ? 1 : 0))
      : bilinearMaskGE0(map, info.w, info.h, width, height));
  }
  const pick = selectLeaf(masks, Array.from(scores).slice(0, 3), policy.leaf_rule, policy.leaf_min_area_share);
  return { leaf: masks[pick], candidates: masks, pick };
}

// ------------------------------------------------------------------------------------------- colour rule

const SRGB = (v) => (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
const SRGB_LUT = Float64Array.from({ length: 256 }, (_, i) => SRGB(Math.fround(i / 255)));

/** cv2 float RGB2Lab (D65) of one pixel: [L, a, b]. */
export function labPixel(r, g, b) {
  const R = SRGB_LUT[r], G = SRGB_LUT[g], B = SRGB_LUT[b];
  const X = (0.412453 * R + 0.35758 * G + 0.180423 * B) / 0.950456;
  const Y = 0.212671 * R + 0.71516 * G + 0.072169 * B;
  const Z = (0.019334 * R + 0.119193 * G + 0.950227 * B) / 1.088754;
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const fx = f(X), fy = f(Y), fz = f(Z);
  const L = Y > 0.008856 ? 116 * fy - 16 : 903.3 * Y;
  return [L, 500 * (fx - fy), 200 * (fy - fz)];
}

const SDIV = Int32Array.from({ length: 256 }, (_, i) => (i ? rint((255 << 12) / i) : 0));
const HDIV = Int32Array.from({ length: 256 }, (_, i) => (i ? rint((180 << 12) / (6 * i)) : 0));

/** cv2 RGB2HSV for uint8 (H 0..179): [H, S, V]. */
export function hsvPixel(r, g, b) {
  const v = Math.max(r, g, b), vmin = Math.min(r, g, b), diff = v - vmin;
  const s = (diff * SDIV[v] + (1 << 11)) >> 12;
  let h;
  if (v === r) h = g - b; else if (v === g) h = b - r + 2 * diff; else h = r - g + 4 * diff;
  h = (h * HDIV[diff] + (1 << 11)) >> 12;
  if (h < 0) h += 180;
  return [h, s, v];
}

const inRange = (p, [lo, hi]) => p[0] >= lo[0] && p[0] <= hi[0] && p[1] >= lo[1] && p[1] <= hi[1] && p[2] >= lo[2] && p[2] <= hi[2];

/** 8-connected components of `candidates` that touch `seeds` (src.severity.refinement.touching). */
export function touching(candidates, seeds, W, H) {
  const out = new Uint8Array(W * H), stack = [];
  for (let i = 0; i < W * H; i++) {
    if (!candidates[i] || out[i]) continue;
    const y = (i / W) | 0, x = i - y * W;
    let near = false;
    for (let dy = -1; dy <= 1 && !near; dy++) for (let dx = -1; dx <= 1; dx++) {
      const yy = y + dy, xx = x + dx;
      if (yy >= 0 && yy < H && xx >= 0 && xx < W && seeds[yy * W + xx]) { near = true; break; }
    }
    if (!near) continue;
    out[i] = 1; stack.push(i);
    while (stack.length) {
      const j = stack.pop(), jy = (j / W) | 0, jx = j - jy * W;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        const yy = jy + dy, xx = jx + dx;
        if (yy < 0 || yy >= H || xx < 0 || xx >= W) continue;
        const k = yy * W + xx;
        if (candidates[k] && !out[k]) { out[k] = 1; stack.push(k); }
      }
    }
  }
  return out;
}

/** C1 lesion mask inside `mask` (= region AND leaf) for one picture (an RGB byte accessor via `px`). */
export function refineC1(mask, px, W, H, group, thr, policy) {
  const n = W * H, lesion = new Uint8Array(n), yellow = new Uint8Array(n);
  let any = false;
  for (let i = 0; i < n; i++) {
    if (!mask[i]) continue;
    const r = px(3 * i), g = px(3 * i + 1), b = px(3 * i + 2);
    const [L, a, bb] = labPixel(r, g, b);
    let hit;
    if (group === "rust" || group === "necrotic") hit = a >= thr;
    else if (group === "mildew") hit = Math.hypot(a, bb) <= thr && L >= policy.mildew_min_lightness;
    else throw new Error(`unknown group ${group}`);
    if (hit) { lesion[i] = 1; any = true; } else if (inRange(hsvPixel(r, g, b), policy.yellow_hsv)) yellow[i] = 1;
  }
  if (!any) return lesion;
  const halo = touching(yellow, lesion, W, H);
  for (let i = 0; i < n; i++) if (halo[i]) lesion[i] = 1;
  return lesion;
}

export function severityPct(lesion, leaf) {
  let nl = 0, nboth = 0;
  for (let i = 0; i < leaf.length; i++) if (leaf[i]) { nl++; if (lesion[i]) nboth++; }
  return nl ? (100 * nboth) / nl : NaN;
}

/** Per-channel lookup tables of the photometric views (src.uncertainty.scores.photometric_views). */
export function photometricLuts(policy) {
  const g = policy.photometric_gamma, cast = { warm: [1, 0, -1], cool: [-1, 0, 1] };
  return policy.photometric_views.map(([kind, amount]) => {
    const gains = kind === "gain" ? [amount, amount, amount] : cast[kind].map((c) => Math.fround(1 + amount * c));
    return gains.map((gain) => Uint8Array.from({ length: 256 }, (_, v) => {
      const lin = Math.fround(Math.pow(Math.fround(v / 255), g));
      const y = Math.min(1, Math.max(0, Math.fround(lin * gain)));
      return clampByte(rint(Math.fround(Math.fround(Math.pow(y, 1 / g)) * 255)));
    }));
  });
}

export function spread(values) {
  const v = values.filter((x) => x !== null && Number.isFinite(x));
  if (v.length < 2) return 0;
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  return Math.sqrt(v.reduce((a, b) => a + (b - m) * (b - m), 0) / v.length);
}

export function severityLevel(sev, t) {
  const s = sev / 100;
  if (s <= 0) return "none";
  if (s < t.low_max) return "low";
  if (s < t.medium_max) return "medium";
  return "high";
}

/** Severity, spread and lesion mask of one disease group, given region and leaf. */
export function severityAndSpread(img, region, leaf, group, policy) {
  const { width: W, height: H, data } = img, n = W * H;
  const mask = new Uint8Array(n);
  for (let i = 0; i < n; i++) mask[i] = region[i] & leaf[i];
  const thr = policy.colour_thresholds[group];
  const lesion = refineC1(mask, (k) => data[k], W, H, group, thr, policy);
  const sev = severityPct(lesion, leaf);
  const values = [sev];
  for (const lut of photometricLuts(policy)) {
    const view = refineC1(mask, (k) => lut[k % 3][data[k]], W, H, group, thr, policy);
    values.push(severityPct(view, leaf));
  }
  return { severity: sev, spread: spread(values), lesion };
}

/** src.demo.pipeline.explain: the action. Reasons are looked up in the UI's strings file. */
export function decideAction(failed, score, threshold, severity) {
  if (failed.length) return "retake";
  if (severity === null) return "retake_no_leaf";
  if (score > threshold) return "consult";
  return "answer";
}

// --------------------------------------------------------------------------------------- full pipeline

/**
 * The whole mobile pipeline for one photo. `runtime` wraps the three ONNX sessions:
 *   region(tensor Float32Array 3xSxS) -> Float32Array logits (2xSxS)
 *   leafEncoder(tensor, w, h) -> embeddings (opaque)
 *   leafDecoder(embeddings, [x, y], [h, w]) -> {logits Float32Array 3xhxw, scores Float32Array 3}
 * `click` is in the original photo's pixels.
 */
export async function analyse(photo, disease, click, runtime, policy, opts = {}) {
  const st = await analysePhoto(photo, runtime, policy, opts);
  if (st.stopped) return st.result;
  return finishAnalysis(st, disease, click, runtime, policy);
}

/**
 * Stage 1, needs only the photo: cap, quality gate, region model and leaf encoder. The app runs this while the
 * farmer chooses the disease and taps, so the slow encoder is (mostly) done by the time of the tap.
 * Returns a state for finishAnalysis; with opts.stopAtRetake a failed gate ends early ({stopped, result}).
 */
export async function analysePhoto(photo, runtime, policy, opts = {}) {
  const t = { start: Date.now() };
  const img = capLongSide(photo, policy.max_long_side);
  const features = { ...gateFeatures(img, policy), blockiness: blockiness(img, policy.jpeg_block) };
  const failed = failedChecks(features, policy.gate_ranges);
  t.gate = Date.now();
  if (failed.length && opts.stopAtRetake) {
    t.end = t.gate;
    return { stopped: true, result: { action: "retake", failed, features, image: img, timing: t } };
  }
  const info = segformerInput(img, policy);
  const logits = await runtime.region(info.tensor);
  const { region } = regionFromLogits(logits, info, img.width, img.height);
  t.region = Date.now();
  const li = leafInput(img, policy);
  const emb = await runtime.leafEncoder(li.tensor, li.w, li.h);
  t.encoder = Date.now();
  return { stopped: false, photo, img, features, failed, region, li, emb, t };
}

/** Stage 2, after the tap: leaf decoder, colour rule, uncertainty, action. `click` is in the original photo's pixels. */
export async function finishAnalysis(st, disease, click, runtime, policy) {
  const { photo, img, features, failed, region, li, emb } = st;
  const t = { ...st.t, tap: Date.now() };
  const s = img.height / photo.height;
  const c = [pyRound(click[0] * s), pyRound(click[1] * s)];
  const dec = await runtime.leafDecoder(emb, [c[0] * li.scale, c[1] * li.scale], [li.h, li.w]);
  const { leaf } = leafFromDecoder(dec.logits, dec.scores, li, img.width, img.height, policy);
  t.decoder = Date.now();
  const group = policy.disease_groups[disease];
  const r = severityAndSpread(img, region, leaf, group, policy);
  const severity = Number.isFinite(r.severity) ? r.severity : null;
  const level = severity !== null ? severityLevel(severity, policy.severity_thresholds) : null;
  const decision = level ? policy.decision_mapping[level] : null;
  const action = decideAction(failed, r.spread, policy.uncertainty_threshold, severity);
  t.end = Date.now();
  return { action, severity, level, decision, uncertainty: r.spread, failed, features, click: c,
           region, leaf, lesion: r.lesion, image: img, timing: t };
}

/** Compute time of one photo (the 10 s rule): stage 1 plus stage 2, without the time the farmer spends choosing. */
export function computeMs(t) {
  if (t.tap === undefined) return t.end - t.start;
  return (t.encoder - t.start) + (t.end - t.tap);
}
