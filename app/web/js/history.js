// Scan history, stored on this phone only (localStorage; nothing is uploaded). Each entry keeps a small thumbnail,
// the disease, the severity (null when the app did not answer), the level and the outcome.

export const KEY = "wheat-app-history";
export const MAX = 60;

/** Add an entry to a list, newest first, keeping at most MAX. Pure function. */
export function withEntry(list, entry) {
  return [entry, ...list].slice(0, MAX);
}

/** Answered scans of one disease, oldest first, for the trend chart. Pure function. */
export function trend(list, disease, n = 10) {
  return list.filter((e) => e.disease === disease && e.severity !== null).slice(0, n).reverse();
}

export function load() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

export function save(list) {
  for (let keep = list.length; keep > 0; keep = Math.floor(keep / 2)) {
    try {
      localStorage.setItem(KEY, JSON.stringify(list.slice(0, keep)));
      return true;
    } catch { /* storage full: keep fewer entries */ }
  }
  return false;
}

export function add(entry) { return save(withEntry(load(), entry)); }

export function clear() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}

/** A small JPEG data URL of the photo, for the history list. */
export function thumbnail(bitmap, side = 96) {
  const s = side / Math.min(bitmap.width, bitmap.height);
  const c = document.createElement("canvas");
  c.width = c.height = side;
  const w = bitmap.width * s;
  const h = bitmap.height * s;
  c.getContext("2d").drawImage(bitmap, (side - w) / 2, (side - h) / 2, w, h);
  const url = c.toDataURL("image/jpeg", 0.7);
  c.width = c.height = 0;
  return url;
}
