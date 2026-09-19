import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type StockState = 'NORMAL' | 'BAJO_STOCK' | 'AGOTADO';
export interface InventoryReportFilters {
  id_sucursal?: number;
  id_categoria?: number;
  id_producto?: number;
  estado_stock?: StockState;
  page?: number;
  page_size?: number;
}
export interface InventoryKPIs {
  total_productos: number;
  total_variantes: number;
  total_registros_inventario: number;
  unidades_actuales: number;
  unidades_reservadas: number;
  unidades_disponibles: number;
  registros_agotados: number;
  registros_bajo_stock: number;
  productos_con_agotados: number;
  productos_con_bajo_stock: number;
  registros_con_stock_minimo_cero: number;
}
interface NamedState { nombre: string; estado: boolean }
export interface InventoryReportItem {
  id_inventario_sucursal: number;
  sucursal: NamedState & { id_sucursal: number };
  categoria: NamedState & { id_categoria: number };
  producto: NamedState & { id_producto: number };
  variante: { id_variante_producto: number; sku: string; talla: string; color: string; estado: boolean };
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
  stock_minimo: number;
  estado_stock: StockState | null;
  faltante_hasta_minimo: number;
}
export interface InventoryReportData {
  generado_en: string;
  filtros: { id_sucursal: number | null; id_categoria: number | null; id_producto: number | null; estado_stock: StockState | null; page: number; page_size: number };
  kpis: InventoryKPIs;
  por_sucursal: (InventoryKPIs & NamedState & { id_sucursal: number })[];
  por_categoria: (InventoryKPIs & NamedState & { id_categoria: number })[];
  detalle: { items: InventoryReportItem[]; pagination: { page: number; page_size: number; total: number; total_pages: number } };
  advertencias: { codigo: 'STOCK_DISPONIBLE_NEGATIVO'; mensaje: string; registros: number; alcance: 'FILTROS_SIN_ESTADO_STOCK' }[];
}
@Injectable({ providedIn: 'root' })
export class AdminInventoryReportService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  report(filters: InventoryReportFilters = {}) {
    let params = new HttpParams().set('page', filters.page ?? 1).set('page_size', filters.page_size ?? 20);
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null) params = params.set(key, value);
    }
    const token = this.session.getAccessToken();
    return this.http.get<{ success: true; data: InventoryReportData; message: string }>(
      `${environment.apiUrl}/api/admin/inventory-report`,
      { params, headers: token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders() },
    );
  }
}
