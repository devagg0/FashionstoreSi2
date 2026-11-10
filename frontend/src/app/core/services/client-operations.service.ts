import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, from, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { OfflineStorageService } from './offline-storage.service';
import { SessionService } from './session.service';

export interface OperationPaymentSummary {
  id_pago: number;
  id_venta?: number | null;
  medio: string;
  proveedor: string;
  entorno: string;
  estado: string;
  confirmado: boolean;
  monto: number | string;
  moneda: string;
  referencia_externa?: string | null;
  fecha_aprobacion?: string | null;
  created_at?: string | null;
}

export interface OperationItemDetail {
  id_producto?: number | null;
  producto: string;
  sku?: string | null;
  talla?: string | null;
  color?: string | null;
  codigo_hex?: string | null;
  cantidad: number;
  precio_unitario: number | string;
  subtotal: number | string;
  imagen_principal?: string | null;
}

export interface ClientOperationItem {
  id_operacion: string;
  tipo: 'COMPRA' | 'RESERVA' | 'PAGO';
  id_referencia: number;
  codigo: string;
  codigo_referencia?: string | null;
  fecha: string;
  importe: number | string;
  moneda: string;
  estado: string;
  estado_etiqueta: string;
  confirmada: boolean;
  origen: 'ONLINE' | 'OFFLINE_SYNC' | 'LOCAL_OFFLINE';
  sucursal?: string | null;
  id_sucursal?: number | null;
  cantidad_prendas: number;
  pago?: OperationPaymentSummary | null;
  detalles?: OperationItemDetail[] | null;
  motivo?: string | null;
  uuid_offline?: string | null;
  fecha_atencion_programada?: string | null;
  fecha_expiracion?: string | null;
}

export interface ClientOperationsListResponse {
  success: boolean;
  items: ClientOperationItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  totales_por_tipo: Record<string, number>;
  totales_por_estado: Record<string, number>;
}

export interface ClientOperationDetailResponse {
  success: boolean;
  data: ClientOperationItem;
}

export interface ClientOperationsSummaryResponse {
  success: boolean;
  total_operaciones: number;
  total_compras: number;
  total_reservas: number;
  total_pagos: number;
  pendientes: number;
  confirmadas: number;
  rechazadas: number;
  importe_total_compras: number | string;
}

export interface ClientOperationsFilterParams {
  tipo?: 'COMPRA' | 'RESERVA' | 'PAGO' | '';
  estado?: string;
  desde?: string;
  hasta?: string;
  page?: number;
  page_size?: number;
}

@Injectable({ providedIn: 'root' })
export class ClientOperationsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly baseUrl = `${environment.apiUrl}/api/client/operations`;

  private getHeaders(): HttpHeaders {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }

  getOperations(params?: ClientOperationsFilterParams): Observable<ClientOperationsListResponse> {
    let httpParams = new HttpParams();
    if (params?.tipo) httpParams = httpParams.set('tipo', params.tipo);
    if (params?.estado) httpParams = httpParams.set('estado', params.estado);
    if (params?.desde) httpParams = httpParams.set('desde', params.desde);
    if (params?.hasta) httpParams = httpParams.set('hasta', params.hasta);
    if (params?.page) httpParams = httpParams.set('page', params.page.toString());
    if (params?.page_size) httpParams = httpParams.set('page_size', params.page_size.toString());

    return this.http.get<ClientOperationsListResponse>(this.baseUrl, {
      params: httpParams,
      headers: this.getHeaders(),
    });
  }

  getOperationDetail(tipo: string, idReferencia: number): Observable<ClientOperationDetailResponse> {
    return this.http.get<ClientOperationDetailResponse>(
      `${this.baseUrl}/${tipo.toUpperCase()}/${idReferencia}`,
      { headers: this.getHeaders() }
    );
  }

  getSummary(): Observable<ClientOperationsSummaryResponse> {
    return this.http.get<ClientOperationsSummaryResponse>(`${this.baseUrl}/summary`, {
      headers: this.getHeaders(),
    });
  }

  /**
   * Lee operaciones locales en cola de sincronización pendientes de envío al servidor.
   * Permite que el cliente visualice que tiene transacciones aún no confirmadas ni sincronizadas.
   */
  getLocalPendingOperations(): Observable<ClientOperationItem[]> {
    const user = this.session.getUser();
    if (!user) return of([]);

    const empresaId = user.id_empresa || 1;
    return from(this.offlineStorage.getOfflineQueue(empresaId, user.id_usuario)).pipe(
      map((queue) => {
        const pendingItems = queue.filter(
          (q) => q.estado === 'PENDIENTE_SINCRONIZACION' || q.estado === 'CONFLICTO'
        );

        return pendingItems.map((item, index) => {
          const isReserva = item.tipo_operacion === 'RESERVA';
          const p = item.payload || {};
          const isConflict = item.estado === 'CONFLICTO';

          return {
            id_operacion: `LOCAL:${item.uuid_operacion || item.uuid_entidad || index}`,
            tipo: (isReserva ? 'RESERVA' : 'COMPRA') as 'COMPRA' | 'RESERVA',
            id_referencia: index + 1,
            codigo: `LOCAL-${(item.uuid_entidad || item.uuid_operacion || 'PEND').slice(0, 8).toUpperCase()}`,
            codigo_referencia: null,
            fecha: item.created_at || new Date().toISOString(),
            importe: p.total || p.subtotal || 0,
            moneda: 'BOB',
            estado: item.estado,
            estado_etiqueta: isConflict
              ? 'CONFLICTO LOCAL'
              : 'PENDIENTE DE SINCRONIZACIÓN (DISPOSITIVO)',
            confirmada: false,
            origen: 'LOCAL_OFFLINE' as const,
            sucursal: p.sucursal_nombre || 'Sucursal local',
            id_sucursal: p.id_sucursal,
            cantidad_prendas: Array.isArray(p.detalles) ? p.detalles.length : 1,
            pago: null,
            motivo: item.ultimo_error || (isConflict ? 'Conflicto de stock o regla offline' : null),
            uuid_offline: item.uuid_entidad,
          };
        });
      }),
      catchError(() => of([]))
    );
  }
}
