const CACHE = "last-mile-v3";
const ASSETS = ["/", "/assets/styles.css", "/assets/app.js", "/assets/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("last-mile-") && key !== CACHE).map((key) => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  // Only the public shell is saved automatically. Plans require explicit opt-in.
  // Never return an HTML shell for a failed API, audio, or third-party request.
  if (url.origin !== self.location.origin || url.search || !ASSETS.includes(url.pathname)) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(event.request, clone)));
        }
        return response;
      })
      .catch(() => caches.open(CACHE).then((cache) => cache.match(event.request))
        .then((cached) => cached || Response.error()))
  );
});
