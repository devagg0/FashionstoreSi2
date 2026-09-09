import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface Inventory {
  id_inventario_sucursal: number;
  id_sucursal: number;
  sucursal: string;
  sucursal_estado: boolean;
  id_ciudad: number;
  ciudad: string;
  id_producto: number;
  producto: string;
  producto_estado: boolean;
  id_variante_producto: number;
  sku: string;
  variante_estado: boolean;
  id_talla: number;
  talla: string;
  id_color: number;
  color: string;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
  stock_minimo: number;
  created_at: string;
  updated_at: string;
}
export interface InventoryPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
export interface InventoryFilters {
  search?: string;
  id_sucursal?: number;
  id_ciudad?: number;
  id_categoria?: number;
  id_producto?: number;
  id_variante_producto?: number;
  id_talla?: number;
  id_color?: number;
  page?: number;
  pageSize?: number;
}
export interface InventoryCreateRequest {
  id_sucursal: number;
  id_variante_producto: number;
  stock_minimo?: number;
}
export interface InventoryUpdateRequest {
  stock_minimo: number;
}
export interface InventoryResponse {
  success: true;
  data: Inventory;
}
export interface InventoryListResponse {
  success: true;
  data: Inventory[];
  pagination: InventoryPagination;
}

@Injectable({ providedIn: 'root' })
export class AdminInventoryService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/admin/inventory`;

  listInventory(filters: InventoryFilters = {}): Observable<InventoryListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);
    for (const key of [
      'search',
      'id_sucursal',
      'id_ciudad',
      'id_categoria',
      'id_producto',
      'id_variante_producto',
      'id_talla',
      'id_color',
    ] as const) {
      const raw = filters[key];
      const value = typeof raw === 'string' ? raw.trim() : raw;
      if (value != null && value !== '') params = params.set(key, value);
    }
    return this.http.get<InventoryListResponse>(this.url, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }
  getInventory(id: number): Observable<InventoryResponse> {
    return this.http.get<InventoryResponse>(`${this.url}/${id}`, {
      headers: this.authenticatedHeaders(),
    });
  }
  createInventory(fields: InventoryCreateRequest): Observable<InventoryResponse> {
    const body = {
      id_sucursal: fields.id_sucursal,
      id_variante_producto: fields.id_variante_producto,
      stock_minimo: fields.stock_minimo ?? 0,
    };
    return this.http.post<InventoryResponse>(this.url, body, {
      headers: this.authenticatedHeaders(),
    });
  }
  updateInventory(id: number, fields: InventoryUpdateRequest): Observable<InventoryResponse> {
    return this.http.patch<InventoryResponse>(
      `${this.url}/${id}`,
      { stock_minimo: fields.stock_minimo },
      { headers: this.authenticatedHeaders() },
    );
  }
  private authenticatedHeaders(): HttpHeaders {
    const token = this.sessionService.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }
}
