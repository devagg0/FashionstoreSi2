import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface PatternModelMetrics {
  silhouette_score: number;
  inercia: number;
}

export interface PatternModelInfoResponse {
  algoritmo: string;
  tipo_aprendizaje: string;
  descripcion: string;
  variables: string[];
  n_clusters: number;
  metricas: PatternModelMetrics;
  es_experimental: boolean;
  nota_metodologica: string;
}

export interface PatternFilterOption {
  id: number;
  nombre: string;
  extra?: string | null;
}

export interface PatternFiltersResponse {
  sucursales: PatternFilterOption[];
  categorias: PatternFilterOption[];
  periodos_sugeridos_dias: number[];
}

export interface PatternAnalysisRequest {
  dias_periodo?: number;
  fecha_desde?: string | null;
  fecha_hasta?: string | null;
  id_sucursal?: number | null;
  id_categoria?: number | null;
}

export interface ClusterAverages {
  unidades_vendidas: number;
  ingresos_totales: number;
  frecuencia_ventas: number;
  precio_unitario: number;
  stock_actual: number;
  ratio_rotacion: number;
}

export interface PatternSegment {
  id_cluster: number;
  nombre: string;
  descripcion: string;
  estrategia: string;
  color: string;
  badge_class: string;
  total_productos: number;
  porcentaje_catalogo: number;
  promedios: ClusterAverages;
}

export interface ProductPatternItem {
  id_producto: number;
  nombre: string;
  categoria_nombre: string;
  seccion: string;
  precio_unitario: number;
  unidades_vendidas: number;
  ingresos_totales: number;
  frecuencia_ventas: number;
  stock_actual: number;
  ratio_rotacion: number;
  id_cluster: number;
  cluster_nombre: string;
  cluster_color: string;
  cluster_badge: string;
}

export interface PatternAnalysisResponse {
  success: boolean;
  datos_suficientes: boolean;
  mensaje: string;
  filtros_aplicados: Record<string, any>;
  total_productos_analizados: number;
  total_unidades_vendidas: number;
  total_ingresos_facturados: number;
  n_clusters: number;
  calidad_agrupamiento: string;
  metricas: PatternModelMetrics;
  segmentos: PatternSegment[];
  productos: ProductPatternItem[];
  modelo_referencial: PatternModelInfoResponse;
  disclaimer: string;
}

@Injectable({ providedIn: 'root' })
export class AdminPatternsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  private getHeaders(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  getModelInfo(): Observable<PatternModelInfoResponse> {
    return this.http.get<PatternModelInfoResponse>(
      `${environment.apiUrl}/api/admin/patterns/model-info`,
      { headers: this.getHeaders() },
    );
  }

  getFilters(): Observable<PatternFiltersResponse> {
    return this.http.get<PatternFiltersResponse>(
      `${environment.apiUrl}/api/admin/patterns/filters`,
      { headers: this.getHeaders() },
    );
  }

  analyze(payload: PatternAnalysisRequest): Observable<PatternAnalysisResponse> {
    return this.http.post<PatternAnalysisResponse>(
      `${environment.apiUrl}/api/admin/patterns/analyze`,
      payload,
      { headers: this.getHeaders() },
    );
  }
}

