import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type ReturnState =
  | 'SOLICITADA'
  | 'ACEPTADA_INICIALMENTE'
  | 'PENDIENTE_ENTREGA'
  | 'RECIBIDA'
  | 'APROBADA'
  | 'RECHAZADA'
  | 'PROCESADA';
export type ReturnKind = 'CANCELACION' | 'DEVOLUCION' | 'CAMBIO';
export type DeliveryModality = 'ENTREGA_EN_TIENDA' | 'DELIVERY_SIMULADO';

export interface ReturnLine {
  id_detalle_devolucion?: number;
  id_variante_producto: number;
  cantidad: number;
  cantidad_reintegrar: number;
  importe_restitucion: string | number;
  id_variante_reemplazo?: number | null;
  cantidad_reemplazo?: number;
  precio_original_reconocido?: string | number;
  precio_reemplazo_estimado?: string | number;
  diferencia_precio_estimada?: string | number;
  prenda_original?: {
    id_variante_producto: number;
    nombre_producto?: string | null;
    talla?: string | null;
    color?: string | null;
    sku?: string | null;
    cantidad?: number;
    valor_reconocido?: string | number;
  };
  prenda_reemplazo?: {
    id_variante_producto: number;
    nombre_producto?: string | null;
    talla?: string | null;
    color?: string | null;
    sku?: string | null;
    cantidad?: number;
    valor_reemplazo?: string | number;
    precio_unitario_actual?: string | number;
    stock_disponible_sucursal?: number;
  } | null;
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
export interface ReturnProgressStep {
  paso: number;
  clave: string;
  titulo: string;
  estado: 'COMPLETADO' | 'ACTUAL' | 'PENDIENTE' | 'RECHAZADO';
  fecha?: string | null;
  descripcion: string;
}

export interface ReturnDetail {
  id_devolucion: number;
  codigo_solicitud?: string;
  id_venta: number;
  tipo: ReturnKind;
  estado: ReturnState;
  modalidad_entrega?: DeliveryModality | null;
  motivo: string;
  motivo_rechazo?: string | null;
  created_at?: string;
  fecha_evaluacion_inicial?: string | null;
  id_usuario_evaluador?: number | null;
  evaluador?: { id_usuario?: number; nombre: string; apellido?: string } | null;
  fecha_seleccion_modalidad?: string | null;
  fecha_recepcion?: string | null;
  id_usuario_receptor?: number | null;
  receptor?: { id_usuario?: number; nombre: string; apellido?: string } | null;
  estado_fisico?: string | null;
  etiquetas_intactas?: boolean | null;
  correspondencia_compra?: boolean | null;
  observaciones_inspeccion?: string | null;
  fecha_inspeccion?: string | null;
  id_usuario_inspector?: number | null;
  inspector?: { id_usuario?: number; nombre: string; apellido?: string } | null;
  fecha_resolucion?: string | null;
  fecha_procesamiento?: string | null;
  id_usuario_solicitante: number;
  id_usuario_resolutor?: number | null;
  diferencia_definitiva?: string | number | null;
  monto_adicional_cobrado?: string | number | null;
  medio_pago_adicional?: string | null;
  referencia_pago_adicional?: string | null;
  estado_pago_adicional?: 'PENDIENTE' | 'CONFIRMADO' | 'NO_APLICA' | null;
  stripe_session_id?: string | null;
  fecha_entrega_reemplazo?: string | null;
  id_movimiento_inventario?: number | null;
  diferencia_precio_estimada?: string | number;
  importe_adicional_estimado?: string | number;
  saldo_a_favor_estimado?: string | number;
  monto_reembolsar?: string | number;
  estado_reembolso?: 'PENDIENTE' | 'CONFIRMADO' | 'FALLIDO' | 'NO_APLICA';
  apta_reintegro_stock?: boolean;
  historial_progreso?: ReturnProgressStep[];
  resumen_economico?: {
    moneda: string;
    valor_original_reconocido: string | number;
    valor_reemplazo_estimado: string | number;
    diferencia_precio_estimada: string | number;
    importe_adicional_estimado: string | number;
    saldo_a_favor_estimado: string | number;
    resultado_economico: 'IMPORTE_ADICIONAL' | 'SALDO_A_FAVOR' | 'SIN_DIFERENCIA';
  };
  lineas: ReturnLine[];
  reembolsos: ReturnRefund[];
  numero_venta?: string;
  cliente?: { nombre: string; apellido?: string };
  sucursal?: { id_sucursal?: number; nombre: string; direccion?: string; telefono?: string };
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
export interface ReturnRequestLine {
  id_detalle_venta: number;
  cantidad: number;
  id_variante_reemplazo?: number | null;
  cantidad_reemplazo?: number | null;
}
export interface ReturnRequest {
  tipo?: 'DEVOLUCION' | 'CAMBIO';
  modalidad_entrega?: DeliveryModality | null;
  motivo: string;
  lineas?: ReturnRequestLine[];
}
export interface ExchangeOptionLine {
  id_detalle_venta: number;
  id_variante_producto: number;
  id_producto: number | null;
  nombre_producto: string | null;
  sku: string;
  id_talla: number;
  talla: string | null;
  id_color: number;
  color: string | null;
  codigo_hex: string | null;
  cantidad_comprada: number;
  cantidad_usada: number;
  cantidad_disponible: number;
  precio_unitario: string | number;
  descuento_unitario: string | number;
  subtotal_linea: string | number;
  valor_unitario_reconocido: string | number;
  valor_disponible_reconocido: string | number;
}
export interface ReplacementVariant {
  id_variante_producto: number;
  id_producto: number;
  nombre_producto: string;
  sku: string;
  id_talla: number;
  talla: string;
  id_color: number;
  color: string;
  codigo_hex: string | null;
  precio_unitario: string | number;
  stock_disponible: number;
}
export interface ExchangeOptionsData {
  id_venta: number;
  numero_venta: string;
  estado_venta: string;
  moneda: string;
  id_sucursal: number;
  sucursal?: { id_sucursal: number; nombre: string; direccion?: string; telefono?: string } | null;
  fecha_completada: string | null;
  fecha_limite_solicitud: string | null;
  plazo_horas: number;
  dentro_plazo_72h: boolean;
  elegible_cambio_devolucion: boolean;
  horas_restantes: number;
  motivo_no_elegible: string | null;
  tipos_solicitud: ('CAMBIO' | 'DEVOLUCION')[];
  modalidades_entrega: DeliveryModality[];
  modalidad_entrega_pendiente?: boolean;
  mensaje_modalidad?: string;
  lineas_compra: ExchangeOptionLine[];
  variantes_reemplazo_disponibles: ReplacementVariant[];
}
export interface ReviewRequest {
  resultado: 'APROBADA' | 'RECHAZADA';
  lineas?: {
    id_variante_producto: number;
    cantidad_reintegrar: number;
    importe_restitucion: string;
  }[];
}
export interface InitialReviewRequest {
  resultado: 'ACEPTADA' | 'RECHAZADA';
  motivo_rechazo?: string;
}
export interface DeliveryModalitySelectionRequest {
  modalidad_entrega: DeliveryModality;
}
export interface ReceiveItemRequest {
  observaciones?: string;
}
export interface InspectionRequest {
  resultado: 'APROBADA' | 'RECHAZADA';
  estado_fisico: string;
  etiquetas_intactas: boolean;
  correspondencia_compra: boolean;
  observaciones?: string;
  motivo_rechazo?: string;
}
export interface ProcessExchangeRequest {
  medio_pago?: 'EFECTIVO' | 'QR' | 'TARJETA';
  referencia_manual?: string;
  reintegrar_stock_original?: boolean;
}
export const returnReference = (id: number) => `SOL-${String(id).padStart(5, '0')}`;
export const returnLabel = (kind: ReturnKind) =>
  kind === 'CANCELACION' ? 'Cancelación' : kind === 'CAMBIO' ? 'Cambio de prenda' : 'Devolución';
export const returnStateLabel = (state: string) => {
  switch (state) {
    case 'SOLICITADA':
      return 'Solicitada (Pendiente de revisión)';
    case 'ACEPTADA_INICIALMENTE':
      return 'Aceptada inicialmente (Pendiente elección de entrega)';
    case 'PENDIENTE_ENTREGA':
      return 'Pendiente de entrega';
    case 'RECIBIDA':
      return 'Prenda recibida en tienda (Pendiente de inspección)';
    case 'APROBADA':
      return 'Aprobada (Lista para procesar)';
    case 'RECHAZADA':
      return 'Rechazada';
    case 'PROCESADA':
      return 'Procesada';
    default:
      return state;
  }
};
export const returnTone = (state: string) =>
  ['PROCESADA', 'APROBADA', 'APROBADO'].includes(state)
    ? 'good'
    : ['RECHAZADA', 'RECHAZADO'].includes(state)
      ? 'bad'
      : ['RECIBIDA', 'ACEPTADA_INICIALMENTE'].includes(state)
        ? 'info'
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
    const path = kind === 'CANCELACION' ? 'cancellation' : kind === 'CAMBIO' ? 'exchanges' : 'returns';
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/client/purchases/${sale}/${path}`,
      body,
      { headers: this.headers(key) },
    );
  }
  exchangeOptions(sale: number) {
    return this.http.get<{ success: boolean; data: ExchangeOptionsData }>(
      `${this.base}/client/purchases/${sale}/exchange-options`,
      { headers: this.headers() },
    );
  }
  own(id: number) {
    return this.http.get<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/client/returns/${id}`,
      { headers: this.headers() },
    );
  }
  listOwn(
    state: ReturnState | '' = '',
    offset = 0,
    tipo?: ReturnKind | '',
    saleId?: number,
    modalidad?: DeliveryModality | '',
  ) {
    let params = new HttpParams().set('limit', 20).set('offset', offset);
    if (state) params = params.set('estado', state);
    if (tipo) params = params.set('tipo', tipo);
    if (saleId) params = params.set('id_venta', saleId);
    if (modalidad) params = params.set('modalidad_entrega', modalidad);
    return this.http.get<{ success: boolean; data: ReturnDetail[] }>(`${this.base}/client/returns`, {
      params,
      headers: this.headers(),
    });
  }
  list(
    state: ReturnState | '' = '',
    offset = 0,
    tipo?: ReturnKind | '',
    modalidad?: DeliveryModality | '',
    branchId?: number,
  ) {
    let params = new HttpParams().set('limit', 20).set('offset', offset);
    if (state) params = params.set('estado', state);
    if (tipo) params = params.set('tipo', tipo);
    if (modalidad) params = params.set('modalidad_entrega', modalidad);
    if (branchId) params = params.set('id_sucursal', branchId);
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
  initialReview(id: number, body: InitialReviewRequest) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/initial-review`,
      body,
      { headers: this.headers() },
    );
  }
  selectDeliveryModality(id: number, body: DeliveryModalitySelectionRequest) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/client/returns/${id}/delivery-modality`,
      body,
      { headers: this.headers() },
    );
  }
  receiveItem(id: number, body?: ReceiveItemRequest) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/receive`,
      body || {},
      { headers: this.headers() },
    );
  }
  inspectItem(id: number, body: InspectionRequest) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/inspect`,
      body,
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
  process(id: number, reference?: string, reintegrarStockOriginal?: boolean) {
    const body: Record<string, unknown> = {};
    if (reference) body['referencia_manual'] = reference;
    if (reintegrarStockOriginal !== undefined) body['reintegrar_stock_original'] = reintegrarStockOriginal;
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/process`,
      body,
      { headers: this.headers() },
    );
  }
  processExchange(id: number, body: ProcessExchangeRequest) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/process-exchange`,
      body,
      { headers: this.headers() },
    );
  }
  confirmExchangeDifference(id: number) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/confirm-difference`,
      {},
      { headers: this.headers() },
    );
  }
  createExchangeStripeCheckout(id: number) {
    return this.http.post<{ success: boolean; data: { session_id: string; url: string } }>(
      `${this.base}/client/returns/${id}/stripe-checkout`,
      {},
      { headers: this.headers() },
    );
  }
  confirmExchangeStripeClient(id: number, sessionId?: string) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/client/returns/${id}/stripe-confirm`,
      sessionId ? { session_id: sessionId } : {},
      { headers: this.headers() },
    );
  }
  confirmExchangeStorePayment(id: number, body: { medio_pago: 'EFECTIVO' | 'QR' | 'TARJETA'; referencia_manual?: string }) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/confirm-payment`,
      body,
      { headers: this.headers() },
    );
  }
  confirmExchangeStripeStaff(id: number, sessionId?: string) {
    return this.http.post<{ success: boolean; data: ReturnDetail }>(
      `${this.base}/staff/returns/${id}/stripe-confirm`,
      sessionId ? { session_id: sessionId } : {},
      { headers: this.headers() },
    );
  }
  error(error: unknown): string {
    if (error && typeof error === 'object' && 'name' in error && error.name === 'TimeoutError') {
      return 'El servidor tardó demasiado en responder al consultar las solicitudes. Actualiza la vista.';
    }
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    if (status === 401) {
      this.session.logout();
      void this.router.navigate(['/login'], { queryParams: { returnUrl: this.router.url } });
      return 'Tu sesión expiró. Inicia sesión nuevamente.';
    }
    if (status === 403) return 'No tienes permisos o una asignación activa a esta sucursal.';
    if (status === 404) return 'La compra o solicitud no está disponible para tu cuenta.';
    if ([409, 422, 500, 503].includes(status)) {
      const message =
        error instanceof HttpErrorResponse
          ? typeof error.error?.message === 'string'
            ? error.error.message
            : typeof error.error?.detail === 'string'
              ? error.error.detail
              : null
          : null;
      if (typeof message === 'string' && message.trim().length > 0) {
        return message;
      }
      if (status === 409)
        return 'La compra ya no admite esta acción o la solicitud ya fue resuelta. Actualiza la vista.';
      if (status === 422)
        return 'Revisa el motivo, las cantidades y los importes ingresados.';
      if (status === 503)
        return 'Servicio temporalmente no disponible. Reintenta verificar sobre la misma solicitud sin crear un nuevo pago.';
      return 'Ocurrió un error en el servidor al procesar la solicitud. Reintenta verificar la misma solicitud.';
    }
    if (status === 0)
      return 'No se pudo conectar con el servidor. Revisa tu conexión a internet o el estado del servicio.';
    return 'No pudimos completar la acción. Actualiza la vista antes de reintentar.';
  }
}
