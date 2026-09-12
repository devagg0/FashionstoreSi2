import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type ReservationState =
  | 'PENDIENTE'
  | 'CONFIRMADA'
  | 'ATENDIDA'
  | 'CANCELADA'
  | 'EXPIRADA';

export interface ReservationBranch {
  id_sucursal: number;
  nombre: string;
  direccion: string;
  ciudad: { id_ciudad: number; nombre: string };
}

export interface ReservationSummary {
  id_reserva: number;
  codigo: string;
  estado: ReservationState;
  created_at: string;
  fecha_atencion_programada: string;
  fecha_expiracion: string;
  sucursal: ReservationBranch;
  cantidad_prendas: number;
  total: string;
  cancelable: boolean;
}

export interface ReservationItem {
  id_variante_producto: number;
  sku: string;
  id_producto: number;
  producto: string;
  imagen_principal: string | null;
  talla: { id_talla: number; nombre: string };
  color: { id_color: number; nombre: string; codigo_hex: string | null };
  cantidad: number;
  precio_unitario: string;
  subtotal: string;
}

export interface ReservationDetail extends ReservationSummary {
  items: ReservationItem[];
}

export interface ReservationCreateRequest {
  id_sucursal: number;
  fecha_atencion_programada: string;
  items: Array<{ id_variante_producto: number; cantidad: number }>;
}

export interface ReservationResponse {
  success: true;
  data: ReservationDetail;
  message: string;
}

export interface ReservationListResponse {
  success: true;
  data: ReservationSummary[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
  message: string;
}

@Injectable({ providedIn: 'root' })
export class ClientReservationsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/client/reservations`;

  createReservation(body: ReservationCreateRequest): Observable<ReservationResponse> {
    return this.http.post<ReservationResponse>(this.url, body, { headers: this.headers() });
  }

  listReservations(filters: { estado?: ReservationState; page?: number; pageSize?: number } = {}) {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 10);
    if (filters.estado) params = params.set('estado', filters.estado);
    return this.http.get<ReservationListResponse>(this.url, {
      params,
      headers: this.headers(),
    });
  }

  getReservation(id: number): Observable<ReservationResponse> {
    return this.http.get<ReservationResponse>(`${this.url}/${id}`, {
      headers: this.headers(),
    });
  }

  cancelReservation(id: number): Observable<ReservationResponse> {
    return this.http.patch<ReservationResponse>(
      `${this.url}/${id}/cancel`,
      {},
      { headers: this.headers() },
    );
  }

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }
}
