// Doomsday Prep — Service Worker v1
// Handles Web Push notifications for risk level changes

const CACHE_NAME = "doomsday-v1";

// ── Push event ──────────────────────────────────────────────────────────────
self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "Doomsday Prep", body: event.data.text() };
  }

  const { title = "☢ Doomsday Prep", body = "", data = {} } = payload;

  const riskColors = {
    green: "#16a34a",
    yellow: "#ca8a04",
    orange: "#ea580c",
    red: "#dc2626",
  };

  const options = {
    body,
    icon: "/favicon.ico",
    badge: "/favicon.ico",
    data,
    tag: data.country ? `risk-${data.country}` : "doomsday-generic",
    renotify: true,
    requireInteraction: data.type === "risk_level_change" && data.level === "red",
    vibrate: data.level === "red" ? [300, 100, 300, 100, 300] : [200, 100, 200],
    actions: [
      { action: "open",    title: "Ver mapa" },
      { action: "dismiss", title: "Fechar" },
    ],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// ── Notification click ───────────────────────────────────────────────────────
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  if (event.action === "dismiss") return;

  const country = event.notification.data?.country;
  const url = country ? `/?country=${country}` : "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      // Focus existing tab if open
      for (const client of list) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.focus();
          client.postMessage({ type: "OPEN_COUNTRY", country });
          return;
        }
      }
      // Otherwise open new tab
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

// ── Install / activate (minimal — no cache strategy for now) ─────────────────
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});
