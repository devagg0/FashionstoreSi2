import { inject } from '@angular/core';
import { CanActivateChildFn, CanActivateFn, Router } from '@angular/router';
import { SessionService } from '../services/session.service';

function canAccessAdmin(): boolean | ReturnType<Router['createUrlTree']> {
  const sessionService = inject(SessionService);
  const router = inject(Router);
  const user = sessionService.getUser();
  const hasAdminSession =
    sessionService.getAccessToken() !== null && user?.rol.toUpperCase() === 'ADMINISTRADOR';

  return hasAdminSession ? true : router.createUrlTree(['/']);
}

export const adminGuard: CanActivateFn = () => canAccessAdmin();
export const adminChildGuard: CanActivateChildFn = () => canAccessAdmin();
