import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface SalesReportFilters {
  fecha_desde?: string;
  fecha_hasta?: string;
  id_sucursal?: number;
  canal?: 'PRESENCIAL' | 'DIGITAL';
  id_categoria?: number;
}
export interface SalesKPIs {
  cantidad_ventas: number;
  importe_antes_descuentos: string;
  descuentos: string;
  importe_vendido: string;
  ticket_promedio: string | null;
  unidades_vendidas: number;
  clientes_identificados: number;
  ventas_sin_cliente: number;
}
export interface SalesReportData {
  moneda: 'BOB';
  zona_horaria: 'America/La_Paz';
  kpis: SalesKPIs;
  por_canal: (SalesKPIs & { canal: 'PRESENCIAL' | 'DIGITAL' })[];
  por_sucursal: (SalesKPIs & { id_sucursal: number; nombre_sucursal: string })[];
  serie_diaria: (SalesKPIs & { fecha: string })[];
  productos_mas_vendidos: {
    id_producto: number; nombre_producto: string; unidades_vendidas: number;
    importe_antes_descuentos: string; descuentos: string; importe_vendido: string;
  }[];
}
@Injectable({ providedIn: 'root' })
export class AdminSalesReportService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  report(filters: SalesReportFilters = {}) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params = params.set(key, value);
    }
    const token = this.session.getAccessToken();
    return this.http.get<{ success: true; data: SalesReportData; message: string }>(
      `${environment.apiUrl}/api/admin/sales-report`,
      { params, headers: token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders() },
    );
  }
}
