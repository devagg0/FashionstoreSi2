import { HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { SessionService } from './session.service';

export interface AdminErrorMessages {
  notFound?: string;
  conflict?: string;
  fallback?: string;
}

@Injectable({ providedIn: 'root' })
export class AdminApiErrorService {
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);

  resolve(error: HttpErrorResponse, messages: AdminErrorMessages = {}): string {
    if (error.status === 401) {
      this.endInvalidSession();
      return 'Tu sesión expiró. Inicia sesión nuevamente.';
    }

    if (error.status === 403) {
      return 'Acceso no autorizado.';
    }

    if (error.status === 404) {
      return messages.notFound ?? 'No se encontró el recurso solicitado.';
    }

    if (error.status === 409) {
      return messages.conflict ?? this.apiMessage(error) ?? 'La operación no pudo completarse.';
    }

    if (error.status === 422) {
      return 'Revisa los datos ingresados.';
    }

    return messages.fallback ?? 'No pudimos completar la solicitud. Inténtalo nuevamente.';
  }

  private endInvalidSession(): void {
    this.sessionService.logout();
    void this.router.navigateByUrl('/login');
  }

  private apiMessage(error: HttpErrorResponse): string | null {
    const body: unknown = error.error;
    if (typeof body !== 'object' || body === null || !('message' in body)) {
      return null;
    }

    const message = body.message;
    return typeof message === 'string' ? message : null;
  }
}
