import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { Observable, map, of, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ReservationState } from './client-reservations.service';
import { SessionService } from './session.service';

export interface StaffReservationBranch {
  id_sucursal: number;
  nombre: string;
  direccion: string;
  ciudad: { id_ciudad: number; nombre: string };
}

export interface StaffReservationClient {
  id_cliente: number;
  nombre: string;
  apellido: string;
  correo: string;
  telefono: string | null;
}

export interface StaffReservationSummary {
  id_reserva: number;
  codigo: string;
  estado: ReservationState;
  created_at: string;
  fecha_atencion_programada: string;
  fecha_expiracion: string;
  fecha_atencion: string | null;
  cliente: StaffReservationClient;
  sucursal: StaffReservationBranch;
  cantidad_prendas: number;
  total: string;
}

export interface StaffReservationItem {
  id_variante_producto: number;
  sku: string;
  id_producto: number;
  producto: string;
  imagen_principal?: string | null;
  talla: { id_talla: number; nombre: string };
  color: { id_color: number; nombre: string; codigo_hex: string | null };
  cantidad: number;
  precio_reservado: string;
  subtotal: string;
}

export interface StaffReservationDetail extends StaffReservationSummary {
  prendas: StaffReservationItem[];
}

export interface StaffReservationFilters {
  estado?: ReservationState;
  fechaProgramada?: string;
  page?: number;
  pageSize?: number;
}

export interface StaffReservationResponse {
  success: true;
  data: StaffReservationDetail;
  message: string;
}

export interface StaffReservationListResponse {
  success: true;
  data: StaffReservationSummary[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
  message: string;
}

interface BranchContext {
  userId: number;
  branch: StaffReservationBranch;
}

@Injectable({ providedIn: 'root' })
export class StaffReservationsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/staff/reservations`;
  private readonly branchContext = signal<BranchContext | null>(null);

  readonly branch = computed(() => {
    const context = this.branchContext();
    if (!context || context.userId !== this.session.getUser()?.id_usuario) return null;
    return context.branch;
  });

  listReservations(filters: StaffReservationFilters = {}): Observable<StaffReservationListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 12);
    if (filters.estado) params = params.set('estado', filters.estado);
    if (filters.fechaProgramada) {
      params = params.set('fecha_programada', filters.fechaProgramada);
    }
    return this.http
      .get<StaffReservationListResponse>(this.url, { params, headers: this.headers() })
      .pipe(tap((response) => this.captureBranch(response.data[0]?.sucursal)));
  }

  getReservation(id: number): Observable<StaffReservationResponse> {
    return this.http
      .get<StaffReservationResponse>(`${this.url}/${id}`, { headers: this.headers() })
      .pipe(tap((response) => this.captureBranch(response.data.sucursal)));
  }

  getReservationByCode(code: string): Observable<StaffReservationResponse> {
    return this.http
      .get<StaffReservationResponse>(`${this.url}/code/${encodeURIComponent(code.trim())}`, {
        headers: this.headers(),
      })
      .pipe(tap((response) => this.captureBranch(response.data.sucursal)));
  }

  confirmReservation(id: number): Observable<StaffReservationResponse> {
    return this.transition(id, 'confirm');
  }

  attendReservation(id: number): Observable<StaffReservationResponse> {
    return this.transition(id, 'attend');
  }

  loadBranchContext(): Observable<StaffReservationBranch | null> {
    const current = this.branch();
    if (current) return of(current);
    return this.listReservations({ page: 1, pageSize: 1 }).pipe(
      map((response) => response.data[0]?.sucursal ?? null),
    );
  }

  clearContext(): void {
    this.branchContext.set(null);
  }

  private transition(id: number, action: 'confirm' | 'attend') {
    return this.http
      .patch<StaffReservationResponse>(
        `${this.url}/${id}/${action}`,
        {},
        { headers: this.headers() },
      )
      .pipe(tap((response) => this.captureBranch(response.data.sucursal)));
  }

  private captureBranch(branch: StaffReservationBranch | undefined): void {
    const userId = this.session.getUser()?.id_usuario;
    if (branch && userId !== undefined) this.branchContext.set({ userId, branch });
  }

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }
}
