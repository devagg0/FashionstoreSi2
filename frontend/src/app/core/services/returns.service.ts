import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type ReturnState = 'SOLICITADA' | 'APROBADA' | 'RECHAZADA' | 'PROCESADA';
export type ReturnKind = 'CANCELACION' | 'DEVOLUCION';
export interface ReturnLine {
  id_variante_producto: number;
  cantidad: number;
  cantidad_reintegrar: number;
  importe_restitucion: string | number;
  nombre?: string;
  talla?: string;
  color?: string;
}
export interface ReturnRefund {
  id_reembolso: number;
  id_pago: number;
  estado: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO';
  monto: string | number;
  referencia_externa: string | null;
  fecha_aprobacion?: string | null;
}
export interface ReturnDetail {
  id_devolucion: number;
  id_venta: number;
  tipo: ReturnKind;
  estado: ReturnState;
  motivo: string;
  created_at?: string;
  fecha_resolucion?: string | null;
  fecha_procesamiento?: string | null;
  id_usuario_solicitante: number;
  id_usuario_resolutor?: number | null;
  lineas: ReturnLine[];
  reembolsos: ReturnRefund[];
  numero_venta?: string;
  cliente?: { nombre: string; apellido?: string };
  sucursal?: { nombre: string };
  pago?: {
    id_pago: number;
    medio: 'TARJETA' | 'QR' | 'EFECTIVO';
    proveedor: 'STRIPE' | 'MANUAL';
    entorno: 'TEST' | 'LOCAL';
    estado: string;
    monto: string | number;
    moneda: string;
  } | null;
}
export interface ReturnRequest {
  motivo: string;
  lineas?: { id_detalle_venta: number; cantidad: number }[];
}
export interface ReviewRequest {
  resultado: 'APROBADA' | 'RECHAZADA';
  lineas?: {
    id_variante_producto: number;
    cantidad_reintegrar: number;
    importe_restitucion: string;
  }[];
}
export const returnReference = (id: number) => `SOL-${String(id).padStart(5, '0')}`;
export const returnLabel = (kind: ReturnKind) =>
  kind === 'CANCELACION' ? 'Cancelación' : 'Devolución';
export const returnTone = (state: string) =>
  ['PROCESADA', 'APROBADA', 'APROBADO'].includes(state)
    ? 'good'
    : ['RECHAZADA', 'RECHAZADO'].includes(state)
      ? 'bad'
      : 'pending';
export function returnDate(value?: string | null): string {
  if (!value) return 'Fecha no disponible';
  const date = new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime())
    ? 'Fecha no disponible'
    : new Intl.DateTimeFormat('es-BO', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'America/La_Paz',
      }).format(date);
}
@Injectable({ providedIn: 'root' })
export class ReturnsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly base = `${environment.apiUrl}/api`;
  private headers(key?: string) {
    let headers = new HttpHeaders();
    const token = this.session.getAccessToken();
    if (token) headers = headers.set('Authorization', `Bearer ${token}`);
    return key ? headers.set('Idempotency-Key', key) : headers;
  }
  // Conservar UUID incluso tras recargar la página ante un resultado incierto.
  private storageKey(fingerprint: string): string {
    return `fashionstore-cu24:${this.session.getUser?.()?.id_usuario ?? 'current'}:${fingerprint}`;
  }
  attemptKey(fingerprint: string): string {
    try {
      const storage = this.storageKey(fingerprint);
      const previous = sessionStorage.getItem(storage);
      if (previous) return previous;
      const key = crypto.randomUUID();
      sessionStorage.setItem(storage, key);
      return key;
    } catch {
      return crypto.randomUUID();
    }
  }
  clearAttempt(fingerprint: string): void {
    try {
      sessionStorage.removeItem(this.storageKey(fingerprint));
    } catch {
      /* Almacenamiento no disponible. */
    }
  }
  request(sale: number, kind: ReturnKind, body: ReturnRequest, key: string) {
    const path = kind === 'CANCELACION' ? 'cancellation' : 'returns';
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/client/purchases/${sale}/${path}`,
      body,
      { headers: this.headers(key) },
    );
  }
  own(id: number) {
    return this.http.get<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/client/returns/${id}`,
      { headers: this.headers() },
    );
  }
  list(state: ReturnState | '', offset = 0) {
    let params = new HttpParams().set('limit', 20).set('offset', offset);
    if (state) params = params.set('estado', state);
    return this.http.get<{ success: boolean; data: ReturnDetail[] }>(`${this.base}/staff/returns`, {
      params,
      headers: this.headers(),
    });
  }
  detail(id: number) {
    return this.http.get<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}`,
      { headers: this.headers() },
    );
  }
  review(id: number, body: ReviewRequest) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/review`,
      body,
      { headers: this.headers() },
    );
  }
  process(id: number, reference?: string) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/process`,
      reference ? { referencia_manual: reference } : {},
      { headers: this.headers() },
    );
  }
  error(error: unknown): string {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    if (status === 401) {
      this.session.logout();
      void this.router.navigate(['/login'], { queryParams: { returnUrl: this.router.url } });
      return 'Tu sesión expiró. Inicia sesión nuevamente.';
    }
    if (status === 403) return 'No tienes permisos o una asignación activa a esta sucursal.';
    if (status === 404) return 'La compra o solicitud no está disponible para tu cuenta.';
    if ([409, 422].includes(status)) {
      const message = error instanceof HttpErrorResponse ? error.error?.message : null;
      return typeof message === 'string'
        ? message
        : status === 409
          ? 'La compra ya no admite esta acción o la solicitud ya fue resuelta. Actualiza la vista.'
          : 'Revisa el motivo, las cantidades y los importes ingresados.';
    }
    if (status === 503)
      return 'El resultado del reembolso puede estar pendiente. Actualiza y reintenta sobre la misma solicitud.';
    if (status === 0)
      return 'No pudimos confirmar el resultado. Revisa tu conexión y reintenta la misma solicitud.';
    return 'No pudimos completar la acción. Actualiza la vista antes de reintentar.';
  }
}
