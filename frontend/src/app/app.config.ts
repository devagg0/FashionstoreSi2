import { isPlatformBrowser } from '@angular/common';
import {
  ApplicationConfig,
  ENVIRONMENT_INITIALIZER,
  PLATFORM_ID,
  inject,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { PreloadAllModules, provideRouter, withPreloading } from '@angular/router';
import { routes } from './app.routes';

export function registerFashionStoreServiceWorker(
  nav: Pick<Navigator, 'serviceWorker'> | undefined = typeof navigator !== 'undefined'
    ? navigator
    : undefined,
): Promise<ServiceWorkerRegistration | null> {
  if (!nav || !('serviceWorker' in nav) || !nav.serviceWorker) {
    return Promise.resolve(null);
  }
  return nav.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => null);
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
    provideRouter(routes, withPreloading(PreloadAllModules)),
    {
      provide: ENVIRONMENT_INITIALIZER,
      multi: true,
      useValue: () => {
        const platformId = inject(PLATFORM_ID);
        if (isPlatformBrowser(platformId)) {
          void registerFashionStoreServiceWorker();
        }
      },
    },
  ],
};
