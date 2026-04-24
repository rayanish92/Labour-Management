self.addEventListener('install', (e) => {
    console.log('[Service Worker] Install');
});
self.addEventListener('fetch', (e) => {
    // Basic fetch handler for PWA requirements
    e.respondWith(fetch(e.request).catch(() => console.log("Offline mode not fully set up yet")));
});
