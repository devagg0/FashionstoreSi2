import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type ReservationState = 'PENDIENTE' | 'CONFIRMADA' | 'ATENDIDA' | 'CANCELADA' | 'EXPIRADA';
export type ReservationDateKind = 'CREACION' | 'PROGRAMADA' | 'ATENCION';
export type ReservationPeriod = 'DIA' | 'SEMANA' | 'MES';

export interface ReservationsReportFilters {
  fecha_desde?: string;
  fecha_hasta?: string;
  tipo_fecha?: ReservationDateKind;
  periodo?: ReservationPeriod;
  id_sucursal?: number;
  estado?: ReservationState;
  id_categoria?: number;
  id_producto?: number;
}
interface ReservationTotals {
  total_reservas: number;
  unidades_reservadas: number;
}
export interface ReservationsKPIs extends ReservationTotals {
  reservas_pendientes: number;
  reservas_confirmadas: number;
  reservas_atendidas: number;
  reservas_canceladas: number;
  reservas_expiradas: number;
  clientes_con_reservas: number;
}
export interface ReservationsReportData {
  zona_horaria: 'America/La_Paz';
  generado_en: string;
  criterio_estado: 'PERSISTIDO';
  filtros: Required<Pick<ReservationsReportFilters, 'tipo_fecha' | 'periodo'>> & ReservationsReportFilters;
  kpis: ReservationsKPIs;
  por_estado: (ReservationTotals & { estado: ReservationState })[];
  por_sucursal: (ReservationTotals & { id_sucursal: number; nombre_sucursal: string; clientes_con_reservas: number })[];
  serie_periodica: (ReservationTotals & { inicio_periodo: string })[];
  productos_mas_reservados: (ReservationTotals & { id_producto: number; nombre_producto: string })[];
  categorias_mas_reservadas: (ReservationTotals & { id_categoria: number; nombre_categoria: string })[];
  advertencias: { reservas_vencidas_sin_actualizar: number };
}

@Injectable({ providedIn: 'root' })
export class AdminReservationsReportService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  report(filters: ReservationsReportFilters = {}) {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') params = params.set(key, value);
    }
    const token = this.session.getAccessToken();
    return this.http.get<{ success: true; data: ReservationsReportData; message: string }>(
      `${environment.apiUrl}/api/admin/reservations-report`,
      { params, headers: token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders() },
    );
  }
}
