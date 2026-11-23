// Service worker: (1) keeps every app file in a cache so the app works offline after the first load;
// (2) adds the two headers that turn on cross-origin isolation, which WebAssembly threads need. GitHub Pages
// cannot set headers, so they are added here (the page reloads once after the worker first takes control).
// FILES and VERSION are filled in by app/scripts/build.mjs.
const FILES = self.__FILES__ || []; // [[url, bytes], ...]
const VERSION = self.__VERSION__ || "dev";
const CACHE = `wheat-app-${VERSION}`;

async function tell(msg) {
  for (const c of await self.clients.matchAll({ includeUncontrolled: true })) c.postMessage(msg);
}

async function precache() {
  const cache = await caches.open(CACHE);
  const total = FILES.reduce((n, f) => n + f[1], 0);
  let loaded = 0;
  for (const [url, bytes] of FILES) {
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
    await cache.put(url, res);
    loaded += bytes;
    await tell({ type: "sw-progress", loaded, total });
  }
}

self.addEventListener("install", (e) => {
  e.waitUntil(precache().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k.startsWith("wheat-app-") && k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

function isolate(res) {
  if (!res || res.status === 0 || res.type === "opaque") return res;
  const h = new Headers(res.headers);
  h.set("Cross-Origin-Opener-Policy", "same-origin");
  h.set("Cross-Origin-Embedder-Policy", "require-corp");
  h.set("Cross-Origin-Resource-Policy", "same-origin");
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = req.mode === "navigate" ? new URL("./", self.registration.scope).href : req;
    let res = await cache.match(key, { ignoreSearch: true });
    if (!res) {
      try {
        res = await fetch(req);
        if (res.ok && new URL(req.url).pathname.includes("/fonts/")) await cache.put(req, res.clone());
      } catch {
        res = await cache.match(new URL("./", self.registration.scope).href);
      }
    }
    return isolate(res);
  })());
});
