self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch {
    message = {};
  }
  const expiresAt = Date.parse(message.expiresAt || "");
  if (!Number.isFinite(expiresAt) || Date.now() > expiresAt) return;
  event.waitUntil(
    self.registration.showNotification(message.title || "WetMap", {
      body: message.body || "Regn er på vej.",
      icon: "/pwa-192.png",
      badge: "/pwa-192.png",
      tag: message.tag || "wetmap-rain",
      renotify: true,
      data: { url: message.url || "/" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(
    event.notification.data?.url || "/",
    self.location.origin,
  ).href;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        const existing = clients.find((client) =>
          client.url.startsWith(self.location.origin),
        );
        if (existing) {
          existing.navigate(target);
          return existing.focus();
        }
        return self.clients.openWindow(target);
      }),
  );
});
