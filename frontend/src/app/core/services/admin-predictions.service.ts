import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface ModelEvaluationMetrics {
  mae: number;
  rmse: number;
  r2: number;
}

export interface ModelInfoResponse {
  algoritmo: string;
  descripcion: string;
  variables: string[];
  total_variables: number;
  dataset_size: number;
  train_size: number;
  test_size: number;
  metricas: ModelEvaluationMetrics;
  es_experimental: boolean;
  nota_metodologica: string;
  entrenado_en?: string | null;
}

export interface PredictionFilterItem {
  id: number;
  nombre: string;
  codigo?: string | null;
  extra?: string | null;
}

export interface PredictionFiltersResponse {
  productos: PredictionFilterItem[];
  sucursales: PredictionFilterItem[];
  horizontes_disponibles: number[];
}

export interface PredictionRequest {
  id_producto: number;
  id_sucursal: number;
  horizonte_dias: number;
}

export interface HistoricalContext {
  ventas_ultimos_7d: number;
  ventas_ultimos_14d: number;
  ventas_ultimos_30d: number;
  stock_actual: number;
  stock_minimo: number;
  precio_unitario: number;
  seccion: string;
  datos_suficientes: boolean;
  mensaje_suficiencia: string;
}

export interface DailyTrendPoint {
  fecha: string;
  dia_etiqueta: string;
  tipo: 'REAL' | 'PROYECTADO';
  unidades: number;
}

export interface PredictionResult {
  demanda_estimada: number;
  demanda_estimada_raw: number;
  rango_minimo: number;
  rango_maximo: number;
  unidades_diarias_promedio: number;
  cobertura_stock_dias?: number | null;
  riesgo_desabastecimiento: boolean;
  nivel_riesgo: 'BAJO' | 'MEDIO' | 'ALTO' | 'CRITICO';
  confianza_estimacion: 'ALTA' | 'MEDIA' | 'EXPERIMENTAL';
  explicacion: string;
}

export interface PredictionResponse {
  success: boolean;
  id_producto: number;
  producto_nombre: string;
  id_sucursal: number;
  sucursal_nombre: string;
  horizonte_dias: number;
  prediccion: PredictionResult;
  historico: HistoricalContext;
  serie_temporal: DailyTrendPoint[];
  modelo: ModelInfoResponse;
  disclaimer: string;
}

@Injectable({ providedIn: 'root' })
export class AdminPredictionsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  private getHeaders(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  getModelInfo(): Observable<ModelInfoResponse> {
    return this.http.get<ModelInfoResponse>(
      `${environment.apiUrl}/api/admin/predictions/model-info`,
      { headers: this.getHeaders() },
    );
  }

  getFilters(): Observable<PredictionFiltersResponse> {
    return this.http.get<PredictionFiltersResponse>(
      `${environment.apiUrl}/api/admin/predictions/filters`,
      { headers: this.getHeaders() },
    );
  }

  predict(payload: PredictionRequest): Observable<PredictionResponse> {
    return this.http.post<PredictionResponse>(
      `${environment.apiUrl}/api/admin/predictions/predict`,
      payload,
      { headers: this.getHeaders() },
    );
  }
}

