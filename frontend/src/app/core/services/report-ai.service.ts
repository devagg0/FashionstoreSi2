import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface ReportAIAnalysis {
  analisis: string;
  modelo: string;
  generado_en: string;
}

/**
 * Analisis con IA compartido por los reportes administrativos (CU28, CU29 y CU30).
 * Envia los datos ya cargados en el dashboard; no vuelve a consultar el reporte.
 */
@Injectable({ providedIn: 'root' })
export class ReportAIService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  /**
   * `pregunta` es opcional: la consulta que el administrador dicto por voz,
   * ya convertida a texto en el navegador (ver SpeechRecognitionService).
   */
  analyze<T>(path: string, data: T, pregunta?: string) {
    const token = this.session.getAccessToken();
    const params = pregunta ? new HttpParams().set('pregunta', pregunta) : new HttpParams();
    return this.http.post<{ success: true; data: ReportAIAnalysis; message: string }>(
      `${environment.apiUrl}${path}/ai-analysis`,
      data,
      { params, headers: token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders() },
    );
  }
}
