import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface DashboardFilterItem {
  id: number;
  nombre: string;
  extra?: string | null;
}

export interface DashboardFiltersResponse {
  sucursales: DashboardFilterItem[];
  categorias: DashboardFilterItem[];
  periodos_disponibles: number[];
}

export interface DashboardAnalyticsRequest {
  dias_periodo?: number;
  fecha_desde?: string | null;
  fecha_hasta?: string | null;
  id_sucursal?: number | null;
  id_categoria?: number | null;
}

export interface KpiOverview {
  total_ventas: number;
  ingresos_totales: number;
  ticket_promedio: number;
  unidades_vendidas: number;
  stock_disponible: number;
  total_reservas: number;
  reservas_atendidas: number;
  total_devoluciones: number;
  tasa_devolucion_pct: number;
}

export interface DailyMetricPoint {
  fecha: string;
  dia_etiqueta: string;
  unidades: number;
  ingresos: number;
}

export interface CategoryDistributionItem {
  categoria: string;
  unidades: number;
  ingresos: number;
  porcentaje: number;
}

export interface ChannelDistributionItem {
  canal: string;
  unidades: number;
  ingresos: number;
  porcentaje: number;
}

export interface SectionDistributionItem {
  seccion: string;
  unidades: number;
  ingresos: number;
  porcentaje: number;
}

export interface PredictionRiskItem {
  id_producto: number;
  producto_nombre: string;
  stock_actual: number;
  demanda_estimada_15d: number;
  cobertura_dias?: number | null;
  nivel_riesgo: string;
}

export interface PredictionsSummary {
  algoritmo: string;
  mae: number;
  rmse: number;
  r2: number;
  productos_con_riesgo_stock: number;
  items_riesgo: PredictionRiskItem[];
  disclaimer: string;
}

export interface PatternSegmentSummary {
  id_cluster: number;
  nombre: string;
  color: string;
  total_productos: number;
  porcentaje_catalogo: number;
  unidades_promedio: number;
}

export interface PatternsSummary {
  algoritmo: string;
  silhouette_score: number;
  calidad_agrupamiento: string;
  n_clusters: number;
  segmentos: PatternSegmentSummary[];
  disclaimer: string;
}

export interface RecentReportItem {
  id_reporte: number;
  tipo: string;
  titulo: string;
  creado_en: string;
  consulta: string;
}

export interface AiReportsSummary {
  total_reportes_guardados: number;
  ultimos_reportes: RecentReportItem[];
}

export interface DashboardAnalyticsResponse {
  success: boolean;
  filtros_aplicados: Record<string, any>;
  kpis: KpiOverview;
  tendencia_diaria: DailyMetricPoint[];
  distribucion_categorias: CategoryDistributionItem[];
  distribucion_canales: ChannelDistributionItem[];
  distribucion_secciones: SectionDistributionItem[];
  ml_predicciones: PredictionsSummary;
  ml_patrones: PatternsSummary;
  reportes_ia: AiReportsSummary;
}

@Injectable({ providedIn: 'root' })
export class AdminDashboardService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  private getHeaders(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  getFilters(): Observable<DashboardFiltersResponse> {
    return this.http.get<DashboardFiltersResponse>(
      `${environment.apiUrl}/api/admin/dashboard/filters`,
      { headers: this.getHeaders() },
    );
  }

  getAnalytics(payload: DashboardAnalyticsRequest): Observable<DashboardAnalyticsResponse> {
    return this.http.post<DashboardAnalyticsResponse>(
      `${environment.apiUrl}/api/admin/dashboard/analytics`,
      payload,
      { headers: this.getHeaders() },
    );
  }
}

