import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type PaymentMethod = 'EFECTIVO' | 'QR' | 'TARJETA';
export type PaymentAction = 'APROBADO' | 'RECHAZADO';
export interface Payment {
  id_pago: number;
  id_venta: number;
  medio: PaymentMethod;
  proveedor: 'MANUAL' | 'STRIPE';
  entorno: 'LOCAL' | 'TEST';
  estado: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO' | 'EXPIRADO' | 'REEMBOLSADO';
  estado_venta: 'PENDIENTE' | 'COMPLETADA' | 'ANULADA';
  monto: string;
  moneda: 'BOB';
  referencia_externa: string | null;
  clave_idempotencia: string;
  fecha_aprobacion: string | null;
  created_at: string;
  updated_at: string;
}
export interface PaymentResponse {
  success: true;
  data: Payment;
}
export interface CheckoutResponse {
  success: true;
  data: { payment: Payment; session_id: string; url: string };
}
export interface PaymentSale {
  id: number;
  numero: string;
  sucursal: string;
  canal: 'DIGITAL' | 'PRESENCIAL';
  estado: 'PENDIENTE' | 'COMPLETADA' | 'ANULADA';
  fecha: string | null;
  subtotal: string;
  descuento: string;
  total: string;
  items: {
    id: number;
    nombre: string;
    talla?: string;
    color?: string;
    imagen?: string | null;
    cantidad: number;
    precio: string;
    subtotal: string;
  }[];
}
export interface PaymentAttempt {
  key: string;
  medio: PaymentMethod;
  idPago?: number;
  action?: PaymentAction;
}

@Injectable({ providedIn: 'root' })
export class PaymentsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api`;
  private headers() {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
  start(id: number, method: PaymentMethod, key: string) {
    return this.http.post<PaymentResponse>(
      `${this.url}/sales/${id}/payments`,
      { medio: method },
      { headers: this.headers().set('Idempotency-Key', key) },
    );
  }
  get(id: number) {
    return this.http.get<PaymentResponse>(`${this.url}/payments/${id}`, {
      headers: this.headers(),
    });
  }
  manual(id: number, action: PaymentAction) {
    return this.http.post<PaymentResponse>(
      `${this.url}/payments/${id}/manual/confirm`,
      { resultado: action },
      { headers: this.headers() },
    );
  }
  qr(id: number) {
    return this.http.post<PaymentResponse>(
      `${this.url}/payments/${id}/qr/confirm`,
      {},
      { headers: this.headers() },
    );
  }
  checkout(id: number) {
    return this.http.post<CheckoutResponse>(
      `${this.url}/payments/${id}/stripe/checkout-session`,
      {},
      { headers: this.headers() },
    );
  }
  sync(id: number) {
    return this.http.post<PaymentResponse>(
      `${this.url}/payments/${id}/stripe/sync`,
      {},
      { headers: this.headers() },
    );
  }
  private storageKey(id: number, kind: string) {
    return `fashionstore_cu22_${this.session.getUser()?.id_usuario}_${id}_${kind}`;
  }
  saveSale(sale: PaymentSale): void {
    sessionStorage.setItem(this.storageKey(sale.id, 'sale'), JSON.stringify(sale));
  }
  sale(id: number): PaymentSale | null {
    try {
      const data = JSON.parse(
        sessionStorage.getItem(this.storageKey(id, 'sale')) ?? 'null',
      ) as PaymentSale | null;
      return data?.id === id &&
        ['DIGITAL', 'PRESENCIAL'].includes(data.canal) &&
        typeof data.numero === 'string' &&
        Array.isArray(data.items)
        ? data
        : null;
    } catch {
      return null;
    }
  }
  saveAttempt(id: number, attempt: PaymentAttempt): void {
    sessionStorage.setItem(this.storageKey(id, 'attempt'), JSON.stringify(attempt));
  }
  attempt(id: number): PaymentAttempt | null {
    try {
      const data = JSON.parse(
        sessionStorage.getItem(this.storageKey(id, 'attempt')) ?? 'null',
      ) as PaymentAttempt | null;
      return data &&
        /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(data.key) &&
        ['EFECTIVO', 'QR', 'TARJETA'].includes(data.medio) &&
        (data.idPago === undefined || (Number.isSafeInteger(data.idPago) && data.idPago > 0)) &&
        (data.action === undefined || ['APROBADO', 'RECHAZADO'].includes(data.action))
        ? data
        : null;
    } catch {
      return null;
    }
  }
  clearAttempt(id: number): void {
    sessionStorage.removeItem(this.storageKey(id, 'attempt'));
  }
}
