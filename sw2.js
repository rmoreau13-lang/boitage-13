// SW v1 — network-first pour index.html et prospects.json
const CACHE = 'boitage13-v27';
const STATIC = [
  '/boitage-13/prospects.json',
  '/boitage-13/manifest.json',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js',
];

// Jamais mis en cache : index.html et tout ce qui dépend du réseau
const NO_CACHE = ['index.html', '/boitage-13/', '/boitage-13/?', 'clear.html', 'sw', 'supabase', 'prospects.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC).catch(() => {})).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = e.request.url;
  // Ne jamais mettre en cache index.html ni prospects.json
  if (NO_CACHE.some(p => url.includes(p))) {
    e.respondWith(fetch(e.request).catch(() => new Response('Offline', {status: 503})));
    return;
  }
  // Cache-first pour les assets statiques
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        if (resp && resp.status === 200 && resp.type !== 'opaque') {
          caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        }
        return resp;
      });
    })
  );
});
