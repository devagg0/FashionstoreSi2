import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type MovementType =
  'ENTRADA' | 'SALIDA' | 'TRANSFERENCIA' | 'AJUSTE_POSITIVO' | 'AJUSTE_NEGATIVO';
export type MovementState = 'PENDIENTE' | 'CONFIRMADO' | 'ANULADO';
export interface Movement {
  id_movimiento_inventario: number;
  tipo_movimiento: MovementType;
  estado: MovementState;
  fecha_movimiento: string;
  motivo: string | null;
  id_sucursal_origen: number | null;
  sucursal_origen: string | null;
  id_sucursal_destino: number | null;
  sucursal_destino: string | null;
  id_empleado_sucursal: number;
  id_empleado: number;
  nombre_empleado: string;
  rol: string;
  created_at: string;
  updated_at: string;
}
export interface MovementDetail {
  id_variante_producto: number;
  sku: string;
  producto: string;
  talla: string;
  color: string;
  cantidad: number;
  costo_unitario: string | null;
}
export interface MovementFullData extends Movement {
  detalles: MovementDetail[];
}
export interface MovementPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
export interface MovementDetailCreate {
  id_variante_producto: number;
  cantidad: number;
  costo_unitario?: number | null;
}
export interface MovementCreateRequest {
  tipo_movimiento: MovementType;
  id_sucursal_origen?: number | null;
  id_sucursal_destino?: number | null;
  id_empleado_sucursal: number;
  motivo?: string | null;
  detalles: MovementDetailCreate[];
}
export interface MovementListResponse {
  success: true;
  data: Movement[];
  pagination: MovementPagination;
}
export interface MovementResponse {
  success: true;
  data: MovementFullData;
}
export interface MovementFilters {
  search?: string;
  tipo_movimiento?: MovementType;
  estado?: MovementState;
  id_sucursal?: number;
  id_variante_producto?: number;
  fecha_desde?: string;
  fecha_hasta?: string;
  page?: number;
  pageSize?: number;
}

@Injectable({ providedIn: 'root' })
export class AdminInventoryMovementsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly movementsUrl = `${environment.apiUrl}/api/admin/inventory-movements`;

  listMovements(filters: MovementFilters = {}): Observable<MovementListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);
    for (const key of [
      'search',
      'tipo_movimiento',
      'estado',
      'id_sucursal',
      'id_variante_producto',
      'fecha_desde',
      'fecha_hasta',
    ] as const) {
      const raw = filters[key];
      const value = typeof raw === 'string' ? raw.trim() : raw;
      if (value !== undefined && value !== '') params = params.set(key, value);
    }
    return this.http.get<MovementListResponse>(this.movementsUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }
  getMovement(id: number): Observable<MovementResponse> {
    return this.http.get<MovementResponse>(`${this.movementsUrl}/${id}`, {
      headers: this.authenticatedHeaders(),
    });
  }
  createMovement(fields: MovementCreateRequest): Observable<MovementResponse> {
    return this.http.post<MovementResponse>(this.movementsUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }
  confirmMovement(id: number): Observable<MovementResponse> {
    return this.http.patch<MovementResponse>(
      `${this.movementsUrl}/${id}/confirm`,
      {},
      { headers: this.authenticatedHeaders() },
    );
  }
  cancelMovement(id: number): Observable<MovementResponse> {
    return this.http.patch<MovementResponse>(
      `${this.movementsUrl}/${id}/cancel`,
      {},
      { headers: this.authenticatedHeaders() },
    );
  }
  private authenticatedHeaders(): HttpHeaders {
    const accessToken = this.sessionService.getAccessToken();
    return accessToken
      ? new HttpHeaders({ Authorization: `Bearer ${accessToken}` })
      : new HttpHeaders();
  }
}
