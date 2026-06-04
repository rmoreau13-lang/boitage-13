const CACHE = 'boitage13-v7';
const ASSETS = [
  '/boitage-13/prospects.json',
  '/boitage-13/manifest.json',
  '/boitage-13/icon-192.png',
  '/boitage-13/icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js',
  'https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,900&family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap'
];

// URLs toujours servies depuis le réseau en priorité
const NETWORK_FIRST = [
  'index.html',
  '/boitage-13/',
  '/boitage-13/?',
  'prospects.json',
  'supabase',
  'clear.html',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = e.request.url;
  
  // Network-first : index.html, prospects.json, supabase, clear.html
  const isNetworkFirst = NETWORK_FIRST.some(p => url.includes(p));
  if (isNetworkFirst) {
    e.respondWith(
      fetch(e.request)
        .then(resp => {
          if (resp && resp.status === 200 && resp.type !== 'opaque') {
            const clone = resp.clone();
            caches.open(CACHE).then(c => c.put(e.request, clone));
          }
          return resp;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }
  
  // Cache-first pour assets statiques (JS, CSS, fonts)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        if (resp && resp.status === 200 && resp.type !== 'opaque') {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return resp;
      }).catch(() => caches.match('/boitage-13/index.html'));
    })
  );
});
