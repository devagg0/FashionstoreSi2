import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type ReportType = 'VENTAS' | 'STOCK' | 'DEVOLUCIONES' | 'RESERVAS' | 'NO_SOPORTADO' | 'AMBIGUO';
export type Visualization = 'bar' | 'line' | 'pie' | 'table';
export type ResultStatus = 'OK' | 'VACIO' | 'AMBIGUO' | 'NO_SOPORTADO';

export interface ReportKpi {
  etiqueta: string;
  valor: string;
  unidad?: string | null;
}

export interface ReportColumn {
  clave: string;
  etiqueta: string;
  tipo: 'texto' | 'numero' | 'moneda';
}

export interface ReportTable {
  columnas: ReportColumn[];
  filas: Record<string, any>[];
  total_filas: number;
  truncada?: boolean;
}

export interface ReportChartPoint {
  etiqueta: string;
  valor: number;
}

export interface ReportChart {
  tipo: Visualization;
  titulo: string;
  unidad?: string | null;
  puntos: ReportChartPoint[];
}

export interface NaturalLanguageReportData {
  estado: ResultStatus;
  tipo: ReportType;
  titulo: string;
  mensaje?: string | null;
  filtros_aplicados: Record<string, string>;
  kpis: ReportKpi[];
  tabla?: ReportTable | null;
  grafico?: ReportChart | null;
  resumen?: string | null;
  modelo?: string | null;
  generado_en: string;
}

export interface NaturalLanguageReportResponse {
  success: boolean;
  data: NaturalLanguageReportData;
  id_reporte?: number | null;
  message: string;
}

export interface GeneratedReportSummary {
  id_reporte: number;
  tipo: ReportType;
  titulo: string;
  consulta: string;
  filtros_aplicados: Record<string, string>;
  creado_en: string;
  nombre_usuario?: string | null;
}

export interface GeneratedReportDetail {
  id_reporte: number;
  tipo: ReportType;
  titulo: string;
  consulta: string;
  filtros_aplicados: Record<string, string>;
  creado_en: string;
  nombre_usuario?: string | null;
  resultado: NaturalLanguageReportData;
}

export interface GeneratedReportHistoryResponse {
  success: boolean;
  data: GeneratedReportSummary[];
  total: number;
}

export interface GeneratedReportDetailResponse {
  success: boolean;
  data: GeneratedReportDetail;
}

@Injectable({ providedIn: 'root' })
export class NaturalLanguageReportService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  private getHeaders(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  query(consulta: string): Observable<NaturalLanguageReportResponse> {
    return this.http.post<NaturalLanguageReportResponse>(
      `${environment.apiUrl}/api/admin/reports/natural-language`,
      { consulta: consulta.trim() },
      { headers: this.getHeaders() },
    );
  }

  getHistory(limit = 50): Observable<GeneratedReportHistoryResponse> {
    return this.http.get<GeneratedReportHistoryResponse>(
      `${environment.apiUrl}/api/admin/reports/history?limit=${limit}`,
      { headers: this.getHeaders() },
    );
  }

  getSavedReport(reportId: number): Observable<GeneratedReportDetailResponse> {
    return this.http.get<GeneratedReportDetailResponse>(
      `${environment.apiUrl}/api/admin/reports/history/${reportId}`,
      { headers: this.getHeaders() },
    );
  }

  exportSavedExcel(reportId: number): Observable<Blob> {
    return this.http.get(
      `${environment.apiUrl}/api/admin/reports/history/${reportId}/export/excel`,
      { headers: this.getHeaders(), responseType: 'blob' },
    );
  }

  exportDirectExcel(payload: {
    titulo: string;
    consulta?: string;
    resumen?: string | null;
    kpis?: ReportKpi[];
    tabla?: ReportTable | null;
    filtros?: Record<string, string>;
  }): Observable<Blob> {
    return this.http.post(
      `${environment.apiUrl}/api/admin/reports/export/excel`,
      payload,
      { headers: this.getHeaders(), responseType: 'blob' },
    );
  }
}

