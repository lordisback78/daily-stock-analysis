/* Service worker : met l'app en cache pour qu'elle démarre sans réseau.
   Les cours et les cartes vivent dans IndexedDB, jamais ici. */
const CACHE = 'revisions-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icon-180.png', './icon-192.png', './icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // API Claude : jamais interceptée

  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(request, { ignoreSearch: true });
    if (hit) {
      // Rafraîchit en arrière-plan sans bloquer l'affichage.
      fetch(request).then((response) => { if (response.ok) cache.put(request, response.clone()); }).catch(() => {});
      return hit;
    }
    try {
      const response = await fetch(request);
      if (response.ok) cache.put(request, response.clone());
      return response;
    } catch (error) {
      const fallback = await cache.match('./index.html');
      if (fallback && request.mode === 'navigate') return fallback;
      throw error;
    }
  })());
});
