import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface GlobalInventory {
  producto: { id_producto: number; nombre: string; estado: boolean };
  categoria: { id_categoria: number; nombre: string };
  variante: { id_variante_producto: number; sku: string; estado: boolean };
  talla: { id_talla: number; nombre: string };
  color: { id_color: number; nombre: string };
  total_stock_actual: number;
  total_stock_reservado: number;
  total_stock_disponible: number;
  cantidad_sucursales: number;
  cantidad_sucursales_con_stock: number;
}

export interface GlobalInventoryBranch {
  id_sucursal: number;
  nombre_sucursal: string;
  estado_sucursal: boolean;
  id_ciudad: number;
  nombre_ciudad: string;
  id_inventario_sucursal: number;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
  stock_minimo: number;
}

export interface GlobalInventoryDetail extends GlobalInventory {
  sucursales: GlobalInventoryBranch[];
}

export interface GlobalInventoryPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface GlobalInventoryFilters {
  search?: string;
  id_categoria?: number;
  id_producto?: number;
  id_talla?: number;
  id_color?: number;
  id_ciudad?: number;
  id_sucursal?: number;
  page?: number;
  pageSize?: number;
}

export interface GlobalInventoryListResponse {
  success: true;
  data: GlobalInventory[];
  message: string;
  pagination: GlobalInventoryPagination;
}

export interface GlobalInventoryDetailResponse {
  success: true;
  data: GlobalInventoryDetail;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class AdminGlobalInventoryService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/admin/global-inventory`;

  listGlobalInventory(
    filters: GlobalInventoryFilters = {},
  ): Observable<GlobalInventoryListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);
    for (const key of [
      'search',
      'id_categoria',
      'id_producto',
      'id_talla',
      'id_color',
      'id_ciudad',
      'id_sucursal',
    ] as const) {
      const raw = filters[key];
      const value = typeof raw === 'string' ? raw.trim() : raw;
      if (value != null && value !== '') params = params.set(key, value);
    }
    return this.http.get<GlobalInventoryListResponse>(this.url, {
      params,
      headers: this.headers(),
    });
  }

  getGlobalInventoryDetail(idVarianteProducto: number): Observable<GlobalInventoryDetailResponse> {
    return this.http.get<GlobalInventoryDetailResponse>(`${this.url}/${idVarianteProducto}`, {
      headers: this.headers(),
    });
  }

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }
}
