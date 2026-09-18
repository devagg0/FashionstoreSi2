import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type PurchaseState = 'PENDIENTE' | 'COMPLETADA' | 'ANULADA';
export type PurchaseChannel = 'DIGITAL' | 'PRESENCIAL';
export interface PurchasePayment {
  id_pago: number;
  medio: 'EFECTIVO' | 'QR' | 'TARJETA';
  estado: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO' | 'EXPIRADO' | 'REEMBOLSADO';
  monto: string;
  moneda: string;
  fecha_aprobacion: string | null;
}
export interface PurchaseSummary {
  id_venta: number;
  numero_venta: string;
  fecha: string;
  fecha_completada: string | null;
  canal: PurchaseChannel;
  estado: PurchaseState;
  subtotal: string;
  descuento_total: string;
  total: string;
  moneda: string;
  sucursal: { id_sucursal: number; nombre: string };
  pago: PurchasePayment | null;
}
export interface PurchaseItem {
  id_detalle_venta: number;
  id_variante_producto: number;
  nombre: string | null;
  talla: string | null;
  color: string | null;
  cantidad: number;
  precio_unitario: string;
  descuento_unitario: string;
  subtotal_linea: string;
  imagen?: string | null;
}
export interface PurchaseReturn {
  id_devolucion: number;
  tipo: 'DEVOLUCION' | 'CANCELACION';
  estado: 'SOLICITADA' | 'APROBADA' | 'RECHAZADA' | 'PROCESADA';
  motivo: string;
  fecha: string;
  fecha_resolucion: string | null;
  fecha_procesamiento: string | null;
}
export interface PurchaseRefund {
  id_reembolso: number;
  id_devolucion: number;
  id_pago: number;
  estado: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO';
  monto: string;
  fecha: string;
  fecha_aprobacion: string | null;
}
export interface PurchaseDetail extends PurchaseSummary {
  productos: PurchaseItem[];
  pagos: PurchasePayment[];
  devoluciones: PurchaseReturn[];
  reembolsos: PurchaseRefund[];
}
export interface PurchaseListResponse {
  success: true;
  data: { items: PurchaseSummary[]; total: number; limit: number; offset: number };
}
export interface PurchaseResponse {
  success: true;
  data: PurchaseDetail;
}
@Injectable({ providedIn: 'root' })
export class ClientPurchasesService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/client/purchases`;
  private headers() {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
  list(estado: PurchaseState | '', canal: PurchaseChannel | '', offset = 0) {
    let params = new HttpParams().set('limit', 12).set('offset', offset);
    if (estado) params = params.set('estado', estado);
    if (canal) params = params.set('canal', canal);
    return this.http.get<PurchaseListResponse>(this.url, { params, headers: this.headers() });
  }
  detail(id: number) {
    return this.http.get<PurchaseResponse>(`${this.url}/${id}`, { headers: this.headers() });
  }
}
