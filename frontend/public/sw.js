/**
 * FashionStore PWA Service Worker (PK08 - CU08)
 * Gestiona el App Shell (HTML, JS, CSS, iconos, manifest) y la caché de imágenes del catálogo
 * para permitir reabrir la PWA sin conexión a internet ni dependencia de FastAPI.
 */

const APP_SHELL_CACHE = 'fashionstore-app-shell-v1';
const OFFLINE_IMAGES_CACHE = 'fashionstore-offline-images-v1';

const CORE_SHELL_URLS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.ico',
  '/icons/icon-192x192.svg',
  '/icons/icon-512x512.svg',
];

function extractIndexBundleUrls(htmlText) {
  const urls = new Set();
  const scriptRegex = /<script[^>]+src=["']([^"']+\.js)["']/gi;
  const styleRegex = /<link[^>]+href=["']([^"']+\.css)["']/gi;
  let match;
  while ((match = scriptRegex.exec(htmlText)) !== null) {
    if (match[1] && !match[1].startsWith('http')) {
      urls.add(match[1].startsWith('/') ? match[1] : `/${match[1]}`);
    }
  }
  while ((match = styleRegex.exec(htmlText)) !== null) {
    if (match[1] && !match[1].startsWith('http')) {
      urls.add(match[1].startsWith('/') ? match[1] : `/${match[1]}`);
    }
  }
  return [...urls];
}

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    (async () => {
      const cache = await caches.open(APP_SHELL_CACHE);
      await Promise.all(
        CORE_SHELL_URLS.map(async (url) => {
          try {
            const resp = await fetch(url, { cache: 'no-cache' });
            if (resp && resp.ok) {
              await cache.put(url, resp.clone());
              if (url === '/index.html' || url === '/') {
                const html = await resp.text();
                const bundleUrls = extractIndexBundleUrls(html);
                await Promise.all(
                  bundleUrls.map(async (bundleUrl) => {
                    try {
                      const bundleResp = await fetch(bundleUrl);
                      if (bundleResp && bundleResp.ok) {
                        await cache.put(bundleUrl, bundleResp);
                      }
                    } catch {
                      // Ignorar si un recurso secundario no está listo aún
                    }
                  }),
                );
              }
            }
          } catch {
            // Continuar instalación de forma resiliente
          }
        }),
      );
    })(),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.map((key) => {
          if (key !== APP_SHELL_CACHE && key !== OFFLINE_IMAGES_CACHE) {
            return caches.delete(key);
          }
          return Promise.resolve(false);
        }),
      );
      await self.clients.claim();
    })(),
  );
});

function isImageRequest(request, url) {
  if (request.destination === 'image') return true;
  return /\.(png|jpe?g|webp|avif|gif|svg|ico)(\?.*)?$/i.test(url.pathname);
}

function isStaticShellAsset(request, url) {
  if (
    request.destination === 'script' ||
    request.destination === 'style' ||
    request.destination === 'font' ||
    request.destination === 'manifest'
  ) {
    return true;
  }
  return /\.(js|mjs|css|woff2?|ttf|otf|webmanifest|json)(\?.*)?$/i.test(url.pathname);
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // 1. Peticiones a la API FastAPI (/api/...): nunca interceptar con HTML ni falsear mutaciones
  if (url.pathname.startsWith('/api/')) {
    return;
  }

  // 2. Navegación SPA (reabrir cualquier ruta de la PWA sin internet):
  // Network-First con respaldo inmediato a /index.html almacenado en caché
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        const cache = await caches.open(APP_SHELL_CACHE);
        try {
          const networkResponse = await fetch(request);
          if (networkResponse && networkResponse.ok) {
            await cache.put('/index.html', networkResponse.clone());
          }
          return networkResponse;
        } catch {
          const cachedIndex = (await cache.match('/index.html')) || (await cache.match('/'));
          if (cachedIndex) {
            return cachedIndex;
          }
          return new Response(
            '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>FashionStore Offline</title></head><body><p>Modo sin conexión activo. Abra la aplicación nuevamente tras preparar los recursos.</p></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } },
          );
        }
      })(),
    );
    return;
  }

  // 3. Imágenes del catálogo y recursos gráficos:
  // Servir desde caché local si ya fueron preparadas, o descargar y almacenar en caché
  if (isImageRequest(request, url)) {
    event.respondWith(
      (async () => {
        const imgCache = await caches.open(OFFLINE_IMAGES_CACHE);
        const cachedImg =
          (await imgCache.match(request)) ||
          (await imgCache.match(request.url)) ||
          (await caches.match(request));
        if (cachedImg) {
          return cachedImg;
        }

        try {
          const networkResponse = await fetch(request);
          if (networkResponse && (networkResponse.ok || networkResponse.type === 'opaque')) {
            await imgCache.put(request, networkResponse.clone());
          }
          return networkResponse;
        } catch {
          const fallbackIcon = await caches.match('/icons/icon-192x192.svg');
          return fallbackIcon || Response.error();
        }
      })(),
    );
    return;
  }

  // 4. Bundles estáticos de Angular (JS, CSS, fuentes, manifest):
  // Cache-First con actualización en segundo plano (Stale-While-Revalidate)
  if (url.origin === self.location.origin && isStaticShellAsset(request, url)) {
    event.respondWith(
      (async () => {
        const shellCache = await caches.open(APP_SHELL_CACHE);
        const cachedAsset = await shellCache.match(request);
        const fetchPromise = fetch(request)
          .then(async (networkResponse) => {
            if (networkResponse && networkResponse.ok) {
              await shellCache.put(request, networkResponse.clone());
            }
            return networkResponse;
          })
          .catch(() => null);

        if (cachedAsset) {
          return cachedAsset;
        }
        const netResult = await fetchPromise;
        return netResult || Response.error();
      })(),
    );
  }
});

