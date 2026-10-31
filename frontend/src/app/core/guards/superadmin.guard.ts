import { inject } from '@angular/core';
import { CanActivateChildFn, CanActivateFn, Router } from '@angular/router';
import { SessionService } from '../services/session.service';

function canAccessSuperadmin(): boolean | ReturnType<Router['createUrlTree']> {
  const sessionService = inject(SessionService);
  const router = inject(Router);
  const user = sessionService.getUser();

  if (!sessionService.getAccessToken() || !user) {
    return router.createUrlTree(['/login']);
  }

  return user.rol.toUpperCase() === 'SUPERADMIN' ? true : router.createUrlTree(['/']);
}

export const superadminGuard: CanActivateFn = () => canAccessSuperadmin();
export const superadminChildGuard: CanActivateChildFn = () => canAccessSuperadmin();
