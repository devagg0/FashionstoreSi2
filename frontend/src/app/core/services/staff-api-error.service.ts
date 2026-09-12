import { HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { SessionService } from './session.service';

@Injectable({ providedIn: 'root' })
export class StaffApiErrorService {
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);

  resolve(error: HttpErrorResponse, fallback: string): string {
    if (error.status === 401) {
      this.session.logout();
      void this.router.navigateByUrl('/login');
      return 'Tu sesión expiró. Inicia sesión nuevamente.';
    }
    if (error.status === 403) return 'No tienes permisos o una sucursal activa asignada.';
    if (error.status === 404) return 'La reserva no existe o pertenece a otra sucursal.';
    const message = this.apiMessage(error);
    if ([409, 422].includes(error.status) && message) return message;
    return fallback;
  }

  private apiMessage(error: HttpErrorResponse): string | null {
    const body: unknown = error.error;
    if (typeof body !== 'object' || body === null || !('message' in body)) return null;
    return typeof body.message === 'string' ? body.message : null;
  }
}
