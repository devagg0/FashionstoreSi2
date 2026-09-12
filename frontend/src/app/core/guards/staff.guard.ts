import { inject } from '@angular/core';
import { CanActivateChildFn, CanActivateFn, Router } from '@angular/router';
import { SessionService } from '../services/session.service';

export const STAFF_ROLES = new Set(['CAJERO', 'ENCARGADO_SUCURSAL']);

function canAccessStaff(): boolean | ReturnType<Router['createUrlTree']> {
  const session = inject(SessionService);
  const router = inject(Router);
  const user = session.getUser();

  if (!session.getAccessToken() || !user) {
    return router.createUrlTree(['/login']);
  }

  return STAFF_ROLES.has(user.rol.toUpperCase())
    ? true
    : router.createUrlTree(['/']);
}

export const staffGuard: CanActivateFn = () => canAccessStaff();
export const staffChildGuard: CanActivateChildFn = () => canAccessStaff();
