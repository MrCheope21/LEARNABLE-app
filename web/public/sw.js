/* Recallable service worker: makes the app installable and keeps it opening without a network.
 *
 * - Never touches /api or /health: answers, grades and schedules always come from the server.
 * - Pages (navigations): network first; without a network, the cached app shell opens and shows
 *   its own "you're offline" notice.
 * - Fingerprinted files under /assets/ never change: cache first.
 * - Everything else of ours (icons, manifest): network first, cache as a fallback.
 *
 * Bump VERSION to drop old caches after a change to this file.
 */
const VERSION = "v2";
const CACHE = `learnable-${VERSION}`;
const SHELL = ["/", "/manifest.json", "/favicon.svg", "/icons/icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key.startsWith("learnable-") && key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

function put(request, response) {
  if (response && response.ok && response.type === "basic") {
    const copy = response.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api") || url.pathname === "/health" || url.pathname === "/sw.js") return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Every route is the same single page: keep the latest copy under "/".
          if (response.ok) put(new Request("/"), response.clone());
          return response;
        })
        .catch(() => caches.match("/").then((cached) => cached || Response.error())),
    );
    return;
  }
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => put(request, response))));
    return;
  }
  event.respondWith(
    fetch(request)
      .then((response) => put(request, response))
      .catch(() => caches.match(request).then((cached) => cached || Response.error())),
  );
});

// A push from the server (the daily review reminder): show it; a tap opens the app there.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Recallable", {
      body: data.body || "",
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: "learnable-reminder",
      data: { url: data.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client) {
          client.navigate(target).catch(() => undefined);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
