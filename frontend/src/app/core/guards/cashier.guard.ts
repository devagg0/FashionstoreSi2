import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SessionService } from '../services/session.service';

export const cashierGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  const user = session.getUser();
  if (!session.getAccessToken() || !user) return router.createUrlTree(['/login']);
  return user.rol.toUpperCase() === 'CAJERO' ? true : router.createUrlTree(['/']);
};
