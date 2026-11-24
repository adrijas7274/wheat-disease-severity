// Languages: strings.json holds every user-facing phrase. The script's Noto font is loaded only for the chosen
// language (fonts/<key>.css), plus all of them while the language picker is open so each name shows in its script.

const STORE = "wheat-app-lang";
let data = null;
let lang = "en";
const loadedFonts = new Set();

export async function loadStrings() {
  data = await (await fetch("strings.json")).json();
  return data;
}

export function languages() {
  return data.order.map((code) => ({ code, ...data.languages[code] }));
}

/** Best language for this phone: the saved choice, else the first phone language we have, else English. */
export function pickLanguage() {
  try {
    const saved = localStorage.getItem(STORE);
    if (saved && data.languages[saved]) return saved;
  } catch { /* storage blocked: fall through */ }
  for (const tag of navigator.languages || [navigator.language || "en"]) {
    const base = String(tag).toLowerCase().split(/[-_]/)[0];
    if (data.languages[base]) return base;
  }
  return "en";
}

export function loadFont(key) {
  if (!key || loadedFonts.has(key)) return;
  loadedFonts.add(key);
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = `fonts/${key}.css`;
  document.head.appendChild(link);
}

export function loadAllFonts() {
  for (const l of Object.values(data.languages)) loadFont(l.font);
}

/** Use a language; save it only when the user chose it (so the first start still shows the picker). */
export function setLanguage(code, save = false) {
  lang = data.languages[code] ? code : "en";
  if (save) try { localStorage.setItem(STORE, lang); } catch { /* ignore */ }
  const meta = data.languages[lang];
  loadFont(meta.font);
  document.documentElement.lang = lang;
  document.documentElement.dir = meta.dir;
  document.documentElement.dataset.font = meta.font || "latin";
  return meta;
}

export function current() { return { code: lang, ...data.languages[lang] }; }

/** The phrase in the chosen language; English if a phrase is missing. {name} placeholders are filled from vars. */
export function t(key, vars = {}) {
  const s = data.languages[lang].strings[key] ?? data.languages.en.strings[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : `{${k}}`));
}

/** Format a number with the language's own digits where the browser knows them (Latin digits otherwise). */
export function num(x, digits = 1) {
  try {
    return new Intl.NumberFormat(lang, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(x);
  } catch {
    return x.toFixed(digits);
  }
}
