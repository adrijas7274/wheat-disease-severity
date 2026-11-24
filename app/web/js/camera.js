// Live camera with hints (too dark / too bright / hold steady / too blurry). The hints only help the farmer take a
// better photo; they are NOT the quality gate. Every photo still goes through the frozen Phase 6 gate in the
// pipeline. Thresholds are hand-set, uncalibrated UI heuristics on a 160-pixel-wide grey frame (logged in LOG.md).

export const HINT_W = 160;
export const LIMITS = { dark: 60, bright: 200, clipped: 0.3, motion: 10, sharp: 40 };

let stream = null;
let timer = null;

/** Statistics of one grey frame (Uint8Array, w x h): mean, share of near-white pixels, Laplacian variance, and the
 *  mean absolute change from the previous frame (null for the first one). Pure function. */
export function frameStats(gray, w, h, prev = null) {
  const n = w * h;
  let sum = 0;
  let clip = 0;
  let motion = 0;
  for (let i = 0; i < n; i++) {
    sum += gray[i];
    if (gray[i] >= 250) clip++;
    if (prev) motion += Math.abs(gray[i] - prev[i]);
  }
  let lsum = 0;
  let lsq = 0;
  let m = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const l = gray[i - 1] + gray[i + 1] + gray[i - w] + gray[i + w] - 4 * gray[i];
      lsum += l;
      lsq += l * l;
      m++;
    }
  }
  const lmean = m ? lsum / m : 0;
  return { mean: sum / n, clipped: clip / n, sharp: m ? lsq / m - lmean * lmean : 0, motion: prev ? motion / n : null };
}

/** The strings key of the hint for these statistics, most important problem first. Pure function. */
export function hintFor(s) {
  if (s.mean < LIMITS.dark) return "cam_dark";
  if (s.mean > LIMITS.bright || s.clipped > LIMITS.clipped) return "cam_bright";
  if (s.motion !== null && s.motion > LIMITS.motion) return "cam_steady";
  if (s.sharp < LIMITS.sharp) return "cam_blur";
  return "cam_ok";
}

export function cameraAvailable() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

/** Start the back camera in the video element and call onHint(key) a few times a second. */
export async function start(video, onHint) {
  stream = await navigator.mediaDevices.getUserMedia({
    audio: false, video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } },
  });
  video.srcObject = stream;
  await video.play();
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d", { willReadFrequently: true });
  let prev = null;
  timer = setInterval(() => {
    if (!video.videoWidth) return;
    c.width = HINT_W;
    c.height = Math.max(1, Math.round((HINT_W * video.videoHeight) / video.videoWidth));
    ctx.drawImage(video, 0, 0, c.width, c.height);
    const rgba = ctx.getImageData(0, 0, c.width, c.height).data;
    const gray = new Uint8Array(c.width * c.height);
    for (let i = 0, j = 0; j < gray.length; i += 4, j++) gray[j] = (rgba[i] * 299 + rgba[i + 1] * 587 + rgba[i + 2] * 114) / 1000;
    onHint(hintFor(frameStats(gray, c.width, c.height, prev)));
    prev = gray;
  }, 300);
}

export function stop() {
  if (timer) clearInterval(timer);
  timer = null;
  if (stream) for (const t of stream.getTracks()) t.stop();
  stream = null;
}

/** The current frame at full camera resolution, as an ImageBitmap and a JPEG blob (for the thumbnail). */
export async function capture(video) {
  const c = document.createElement("canvas");
  c.width = video.videoWidth;
  c.height = video.videoHeight;
  c.getContext("2d").drawImage(video, 0, 0);
  const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.95));
  const bitmap = await createImageBitmap(c);
  c.width = c.height = 0;
  return { bitmap, blob };
}
