// Build the installable web app into app/www (used by GitHub Pages and by Capacitor for the APK).
//   app/web/*                                -> www/
//   onnxruntime-web WebAssembly build        -> www/ort/
//   Noto fonts (only 400 and 700, one script subset each) -> www/fonts/<key>.css + .woff2
//   sw.js gets the list of every file (for the offline cache) and a version hash.
// Usage: npm run build   (from app/)
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WEB = path.join(APP, "web");
const WWW = path.join(APP, "www");
const NM = path.join(APP, "node_modules");

// font key (strings.json) -> [fontsource package, subset]
const FONTS = {
  latin: [["noto-sans", "latin"], ["noto-sans", "latin-ext"]],
  devanagari: [["noto-sans-devanagari", "devanagari"]],
  bengali: [["noto-sans-bengali", "bengali"]],
  gujarati: [["noto-sans-gujarati", "gujarati"]],
  gurmukhi: [["noto-sans-gurmukhi", "gurmukhi"]],
  kannada: [["noto-sans-kannada", "kannada"]],
  malayalam: [["noto-sans-malayalam", "malayalam"]],
  odia: [["noto-sans-oriya", "oriya"]],
  tamil: [["noto-sans-tamil", "tamil"]],
  telugu: [["noto-sans-telugu", "telugu"]],
  urdu: [["noto-nastaliq-urdu", "arabic"]],
  naskh: [["noto-naskh-arabic", "arabic"]],
  olchiki: [["noto-sans-ol-chiki", "ol-chiki"]],
  meetei: [["noto-sans-meetei-mayek", "meetei-mayek"]],
};
const FAMILY = (pkg) => JSON.parse(fs.readFileSync(path.join(NM, "@fontsource", pkg, "package.json"), "utf8"))
  .description?.match(/^Self-host the (.+?) font/)?.[1] || pkg.replace(/(^|-)(\w)/g, (_, s, c) => (s ? " " : "") + c.toUpperCase());

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, e.name);
    const d = path.join(dst, e.name);
    if (e.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

function walk(dir, base = dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, base, out);
    else out.push(path.relative(base, p).split(path.sep).join("/"));
  }
  return out;
}

// 1. fresh www (a fixed path inside app/, never a variable from outside)
fs.rmSync(WWW, { recursive: true, force: true });
copyDir(WEB, WWW);

// 2. onnxruntime-web, WebAssembly only (SIMD + threads build; it runs single-threaded when not isolated)
const ORT = path.join(NM, "onnxruntime-web", "dist");
fs.mkdirSync(path.join(WWW, "ort"));
for (const f of ["ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"]) {
  fs.copyFileSync(path.join(ORT, f), path.join(WWW, "ort", f));
}
const ortVersion = JSON.parse(fs.readFileSync(path.join(NM, "onnxruntime-web", "package.json"), "utf8")).version;
fs.writeFileSync(path.join(WWW, "ort", "LICENSE.txt"),
  `onnxruntime-web ${ortVersion}, Copyright (c) Microsoft Corporation. MIT License.\nhttps://github.com/microsoft/onnxruntime/blob/main/LICENSE\n`);

// 3. fonts
const FONT_DIR = path.join(WWW, "fonts");
fs.mkdirSync(FONT_DIR);
for (const [key, parts] of Object.entries(FONTS)) {
  let css = "";
  for (const [pkg, subset] of parts) {
    const family = key === "latin" ? "Noto Sans" : FAMILY(pkg);
    for (const w of [400, 700]) {
      const file = `${pkg}-${subset}-${w}-normal.woff2`;
      fs.copyFileSync(path.join(NM, "@fontsource", pkg, "files", file), path.join(FONT_DIR, file));
      css += `@font-face{font-family:"${family}";font-style:normal;font-weight:${w};font-display:swap;src:url(${file}) format("woff2")}\n`;
    }
  }
  fs.writeFileSync(path.join(FONT_DIR, `${key}.css`), css);
}
fs.copyFileSync(path.join(NM, "@fontsource", "noto-sans", "LICENSE"), path.join(FONT_DIR, "OFL.txt"));

// 4. offline file list + version for the service worker
// Script fonts are NOT precached: a phone downloads only the fonts it shows (the chosen language's, or all of them
// once if the language picker is opened); the service worker caches each one when it is first used.
const all = walk(WWW).filter((f) => f !== "sw.js").sort();
const files = all.filter((f) => !f.startsWith("fonts/") || /^fonts\/(latin\.css|noto-sans-latin)/.test(f));
const hash = crypto.createHash("sha256");
for (const f of all) hash.update(f).update(fs.readFileSync(path.join(WWW, f)));
const version = hash.digest("hex").slice(0, 12);
const list = [["./", fs.statSync(path.join(WWW, "index.html")).size],
  ...files.map((f) => [f, fs.statSync(path.join(WWW, f)).size])];
const sw = fs.readFileSync(path.join(WWW, "sw.js"), "utf8");
fs.writeFileSync(path.join(WWW, "sw.js"),
  `self.__FILES__ = ${JSON.stringify(list)};\nself.__VERSION__ = "${version}";\n${sw}`);
fs.writeFileSync(path.join(WWW, "version.json"), JSON.stringify({ version, files: list.length }) + "\n");
const mb = list.reduce((n, f) => n + f[1], 0) / 1e6;
const fontMb = all.filter((f) => f.startsWith("fonts/") && !files.includes(f)).reduce((n, f) => n + fs.statSync(path.join(WWW, f)).size, 0) / 1e6;
console.log(`built app/www: ${list.length} precached files, ${mb.toFixed(1)} MB; script fonts on demand ${fontMb.toFixed(2)} MB in all; version ${version}`);
