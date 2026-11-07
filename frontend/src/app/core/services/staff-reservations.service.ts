import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { from, Observable, map, of, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflineReservationDetailLocal,
  OfflineReservationLocal,
  OfflineReservationState,
  OfflineSyncQueueItem,
  hashReservationUuidToId,
} from '../models/offline.model';
import { ReservationState } from './client-reservations.service';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
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
  private readonly offlineService = inject(OfflineService);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly url = `${environment.apiUrl}/api/staff/reservations`;
  private readonly branchStoragePrefix = 'fashionstore_staff_branch_';
  private readonly branchContext = signal<BranchContext | null>(this.readStoredBranchContext());

  readonly branch = computed(() => {
    const context = this.branchContext();
    if (!context || context.userId !== this.session.getUser()?.id_usuario) return null;
    return context.branch;
  });

  private isOffline(): boolean {
    return (
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine)
    );
  }

  listReservations(filters: StaffReservationFilters = {}): Observable<StaffReservationListResponse> {
    if (this.isOffline()) {
      return from(this.listReservationsOffline(filters)).pipe(
        tap((response) => this.captureBranch(response.data[0]?.sucursal)),
      );
    }
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 12);
    if (filters.estado) params = params.set('estado', filters.estado);
    if (filters.fechaProgramada) {
      params = params.set('fecha_programada', filters.fechaProgramada);
    }
    return this.http
      .get<StaffReservationListResponse>(this.url, { params, headers: this.headers() })
      .pipe(
        tap((response) => {
          this.captureBranch(response.data[0]?.sucursal);
          this.saveReservationsListOnline(response.data);
        }),
      );
  }

  getReservation(id: number): Observable<StaffReservationResponse> {
    if (this.isOffline()) {
      return from(this.getReservationOffline(id)).pipe(
        tap((response) => this.captureBranch(response.data.sucursal)),
      );
    }
    return this.http
      .get<StaffReservationResponse>(`${this.url}/${id}`, { headers: this.headers() })
      .pipe(
        tap((response) => {
          this.captureBranch(response.data.sucursal);
          this.saveReservationDetailOnline(response.data);
        }),
      );
  }

  getReservationByCode(code: string): Observable<StaffReservationResponse> {
    if (this.isOffline()) {
      return from(this.getReservationByCodeOffline(code)).pipe(
        tap((response) => this.captureBranch(response.data.sucursal)),
      );
    }
    return this.http
      .get<StaffReservationResponse>(`${this.url}/code/${encodeURIComponent(code.trim())}`, {
        headers: this.headers(),
      })
      .pipe(
        tap((response) => {
          this.captureBranch(response.data.sucursal);
          this.saveReservationDetailOnline(response.data);
        }),
      );
  }

  confirmReservation(id: number): Observable<StaffReservationResponse> {
    if (this.isOffline()) {
      return from(this.transitionOffline(id, 'confirm')).pipe(
        tap((response) => this.captureBranch(response.data.sucursal)),
      );
    }
    return this.transition(id, 'confirm');
  }

  attendReservation(id: number): Observable<StaffReservationResponse> {
    if (this.isOffline()) {
      return from(this.transitionOffline(id, 'attend')).pipe(
        tap((response) => this.captureBranch(response.data.sucursal)),
      );
    }
    return this.transition(id, 'attend');
  }

  loadBranchContext(): Observable<StaffReservationBranch | null> {
    const current = this.branch();
    if (current) return of(current);
    const stored = this.readStoredBranchContext();
    if (stored) {
      this.branchContext.set(stored);
      return of(stored.branch);
    }
    if (this.isOffline()) {
      return from(this.resolveFallbackBranchOffline());
    }
    return this.listReservations({ page: 1, pageSize: 1 }).pipe(
      map((response) => response.data[0]?.sucursal ?? null),
    );
  }

  clearContext(): void {
    this.branchContext.set(null);
    try {
      const userId = this.session.getUser()?.id_usuario;
      if (typeof localStorage !== 'undefined' && userId !== undefined) {
        localStorage.removeItem(`${this.branchStoragePrefix}${userId}`);
      }
    } catch {
      // ignore storage errors
    }
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
    if (branch && userId !== undefined) {
      const context: BranchContext = { userId, branch };
      this.branchContext.set(context);
      try {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem(`${this.branchStoragePrefix}${userId}`, JSON.stringify(context));
        }
      } catch {
        // ignore storage errors
      }
    }
  }

  private readStoredBranchContext(): BranchContext | null {
    if (typeof localStorage === 'undefined') return null;
    try {
      const user = this.session.getUser();
      if (!user) return null;
      const raw = localStorage.getItem(`${this.branchStoragePrefix}${user.id_usuario}`);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as BranchContext;
      if (parsed && parsed.userId === user.id_usuario && parsed.branch) {
        return parsed;
      }
    } catch {
      // ignore JSON parse error
    }
    return null;
  }

  private async resolveFallbackBranchOffline(): Promise<StaffReservationBranch | null> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return null;
    try {
      const branches = await this.offlineStorage.getBranches(empresaId, user.id_usuario);
      if (branches.length === 0) return null;
      const b = branches[0];
      const fallback: StaffReservationBranch = {
        id_sucursal: b.id_sucursal,
        nombre: b.nombre,
        direccion: b.direccion,
        ciudad: { id_ciudad: b.id_ciudad, nombre: b.ciudad ?? '' },
      };
      this.captureBranch(fallback);
      return fallback;
    } catch {
      return null;
    }
  }

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  private hashToId(uuid: string): number {
    return hashReservationUuidToId(uuid);
  }

  private async listReservationsOffline(
    filters: StaffReservationFilters = {},
  ): Promise<StaffReservationListResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const [reservations, details, branches] = await Promise.all([
      this.offlineStorage.getOfflineReservations(empresaId, user.id_usuario),
      this.offlineStorage.getOfflineReservationDetails(empresaId, user.id_usuario),
      this.offlineStorage.getBranches(empresaId, user.id_usuario),
    ]);

    const branchMap = new Map(branches.map((b) => [b.id_sucursal, b]));
    const authorizedBranch = this.branch() ?? this.readStoredBranchContext()?.branch;
    const authorizedBranchId = authorizedBranch?.id_sucursal;

    let filtered = reservations.filter((r) => {
      // 1. Excluir reservas borrador no sincronizadas del cliente (no confundir con reservas oficiales)
      if (r.estado === 'REGISTRADA_LOCAL' && !r.id_reserva) {
        return false;
      }

      // 2. Si la sucursal autorizada está establecida, restringir estrictamente a dicha sucursal
      if (authorizedBranchId && r.id_sucursal !== authorizedBranchId) {
        return false;
      }

      // 3. Filtro por estado
      if (filters.estado) {
        const rState = r.estado === 'REGISTRADA_LOCAL' ? 'PENDIENTE' : r.estado;
        if (rState !== filters.estado) return false;
      }

      // 4. Filtro por fecha programada
      if (filters.fechaProgramada) {
        const datePart = (r.fecha_atencion_programada ?? '').slice(0, 10);
        if (datePart !== filters.fechaProgramada) return false;
      }

      return true;
    });

    filtered.sort((a, b) => b.created_at.localeCompare(a.created_at));

    const page = filters.page ?? 1;
    const pageSize = filters.pageSize ?? 12;
    const total = filtered.length;
    const totalPages = Math.ceil(total / pageSize) || 1;
    const start = (page - 1) * pageSize;
    const pagedRows = filtered.slice(start, start + pageSize);

    const summaries: StaffReservationSummary[] = pagedRows.map((r) => {
      const branch = branchMap.get(r.id_sucursal) ?? authorizedBranch ?? {
        id_sucursal: r.id_sucursal,
        nombre: r.sucursal_nombre ?? `Sucursal #${r.id_sucursal}`,
        direccion: '',
        ciudad: { id_ciudad: 1, nombre: '' },
      };
      const rDetails = details.filter((d) => d.uuid_reserva_offline === r.uuid_reserva_offline);
      const numItems =
        rDetails.length > 0
          ? rDetails.reduce((acc, d) => acc + d.cantidad, 0)
          : (r.cantidad_prendas ?? 0);
      const state =
        r.estado === 'REGISTRADA_LOCAL' ? 'PENDIENTE' : (r.estado as ReservationState);

      return {
        id_reserva: r.id_reserva ?? this.hashToId(r.uuid_reserva_offline),
        codigo: r.codigo_local,
        estado: state,
        created_at: r.created_at,
        fecha_atencion_programada: r.fecha_atencion_programada,
        fecha_expiracion: r.fecha_expiracion ?? r.fecha_atencion_programada,
        fecha_atencion: r.fecha_atencion ?? null,
        cliente: {
          id_cliente: r.id_cliente ?? 1,
          nombre: r.cliente_nombre ?? 'Cliente',
          apellido: r.cliente_apellido ?? '',
          correo: r.cliente_correo ?? 'cliente@fashionstore.com',
          telefono: r.cliente_telefono ?? null,
        },
        sucursal: {
          id_sucursal: branch.id_sucursal,
          nombre: branch.nombre,
          direccion: branch.direccion,
          ciudad:
            typeof branch.ciudad === 'object' && branch.ciudad !== null
              ? branch.ciudad
              : { id_ciudad: 1, nombre: String(branch.ciudad ?? '') },
        },
        cantidad_prendas: numItems,
        total: (r.total_referencial ?? 0).toFixed(2),
      };
    });

    return {
      success: true,
      data: summaries,
      pagination: {
        page,
        page_size: pageSize,
        total,
        total_pages: totalPages,
      },
      message: 'OK',
    };
  }

  private async getReservationOffline(id: number): Promise<StaffReservationResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const reservations = await this.offlineStorage.getOfflineReservations(empresaId, user.id_usuario);
    const reservation = reservations.find(
      (r) => r.id_reserva === id || this.hashToId(r.uuid_reserva_offline) === id,
    );

    if (!reservation) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: 'No se encontró la reserva solicitada en almacenamiento offline.' },
      });
    }

    const authorizedBranch = this.branch() ?? this.readStoredBranchContext()?.branch;
    if (authorizedBranch && reservation.id_sucursal !== authorizedBranch.id_sucursal) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: 'Reserva no encontrada en la sucursal asignada.' },
      });
    }

    const detail = await this.buildReservationDetail(reservation, empresaId, user.id_usuario);
    return { success: true, data: detail, message: 'OK' };
  }

  private async getReservationByCodeOffline(code: string): Promise<StaffReservationResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const clean = code.trim().toUpperCase();
    const reservations = await this.offlineStorage.getOfflineReservations(empresaId, user.id_usuario);
    const reservation = reservations.find(
      (r) =>
        r.codigo_local?.toUpperCase() === clean ||
        r.uuid_reserva_offline?.toUpperCase() === clean,
    );

    if (!reservation) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: `No se encontró ninguna reserva con el código "${code}".` },
      });
    }

    const authorizedBranch = this.branch() ?? this.readStoredBranchContext()?.branch;
    if (authorizedBranch && reservation.id_sucursal !== authorizedBranch.id_sucursal) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: `La reserva "${code}" no pertenece a tu sucursal asignada.` },
      });
    }

    const detail = await this.buildReservationDetail(reservation, empresaId, user.id_usuario);
    return { success: true, data: detail, message: 'OK' };
  }

  private async transitionOffline(
    id: number,
    action: 'confirm' | 'attend',
  ): Promise<StaffReservationResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const reservations = await this.offlineStorage.getOfflineReservations(empresaId, user.id_usuario);
    const reservation = reservations.find(
      (r) => r.id_reserva === id || this.hashToId(r.uuid_reserva_offline) === id,
    );

    if (!reservation) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: 'No se encontró la reserva solicitada en almacenamiento offline.' },
      });
    }

    const currentState =
      reservation.estado === 'REGISTRADA_LOCAL' ? 'PENDIENTE' : reservation.estado;

    if (action === 'confirm') {
      if (currentState !== 'PENDIENTE') {
        throw new HttpErrorResponse({
          status: 409,
          error: {
            message: `Solo se pueden confirmar reservas en estado PENDIENTE. Estado actual: ${currentState}.`,
          },
        });
      }
      reservation.estado = 'CONFIRMADA';
    } else if (action === 'attend') {
      if (currentState !== 'CONFIRMADA') {
        throw new HttpErrorResponse({
          status: 409,
          error: {
            message: `Solo se pueden marcar como atendidas reservas en estado CONFIRMADA. Estado actual: ${currentState}.`,
          },
        });
      }
      reservation.estado = 'ATENDIDA';
      reservation.fecha_atencion = new Date().toISOString();
    }

    reservation.updated_at = new Date().toISOString();

    const queueItem: OfflineSyncQueueItem = {
      uuid_operacion: `trans-${action}-${reservation.uuid_reserva_offline}-${Date.now()}`,
      tipo_operacion: 'RESERVA',
      uuid_entidad: reservation.uuid_reserva_offline,
      estado: reservation.estado,
      payload: {
        uuid_reserva_offline: reservation.uuid_reserva_offline,
        id_reserva: reservation.id_reserva ?? id,
        codigo_reserva: reservation.codigo_local,
        accion: action,
        estado_anterior: currentState,
        estado_nuevo: reservation.estado,
        fecha_transicion: new Date().toISOString(),
      },
      reintentos: 0,
      ultimo_error: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    await this.offlineStorage.updateOfflineReservationState(
      empresaId,
      user.id_usuario,
      reservation,
      queueItem,
    );

    const detail = await this.buildReservationDetail(reservation, empresaId, user.id_usuario);
    return {
      success: true,
      data: detail,
      message:
        action === 'confirm'
          ? 'Reserva confirmada localmente.'
          : 'Reserva marcada como atendida localmente.',
    };
  }

  private async buildReservationDetail(
    r: OfflineReservationLocal,
    empresaId: number,
    userId: number,
  ): Promise<StaffReservationDetail> {
    const [details, branches, products, variants] = await Promise.all([
      this.offlineStorage.getOfflineReservationDetails(empresaId, userId, r.uuid_reserva_offline),
      this.offlineStorage.getBranches(empresaId, userId),
      this.offlineStorage.getCatalogProducts(empresaId, userId),
      this.offlineStorage.getVariants(empresaId, userId),
    ]);

    const authorizedBranch = this.branch() ?? this.readStoredBranchContext()?.branch;
    const branch = branches.find((b) => b.id_sucursal === r.id_sucursal) ?? authorizedBranch ?? {
      id_sucursal: r.id_sucursal,
      nombre: r.sucursal_nombre ?? `Sucursal #${r.id_sucursal}`,
      direccion: '',
      ciudad: { id_ciudad: 1, nombre: '' },
    };

    const prendas: StaffReservationItem[] = details.map((d) => {
      const v = variants.find((variant) => variant.id_variante_producto === d.id_variante_producto);
      const p = products.find((prod) => prod.id_producto === (v?.id_producto ?? d.id_producto));
      return {
        id_variante_producto: d.id_variante_producto,
        sku: d.sku,
        id_producto: d.id_producto,
        producto: d.producto_nombre || p?.nombre || `Prenda #${d.id_variante_producto}`,
        imagen_principal: d.imagen_principal ?? p?.imagen_principal ?? null,
        talla: { id_talla: v?.id_talla ?? 1, nombre: d.talla || 'Única' },
        color: { id_color: v?.id_color ?? 1, nombre: d.color || 'Único', codigo_hex: null },
        cantidad: d.cantidad,
        precio_reservado: (d.precio_referencial ?? 0).toFixed(2),
        subtotal: (d.subtotal ?? d.precio_referencial * d.cantidad).toFixed(2),
      };
    });

    const state =
      r.estado === 'REGISTRADA_LOCAL' ? 'PENDIENTE' : (r.estado as ReservationState);

    const numItems =
      prendas.length > 0
        ? prendas.reduce((acc, p) => acc + p.cantidad, 0)
        : (r.cantidad_prendas ?? 0);

    return {
      id_reserva: r.id_reserva ?? this.hashToId(r.uuid_reserva_offline),
      codigo: r.codigo_local,
      estado: state,
      created_at: r.created_at,
      fecha_atencion_programada: r.fecha_atencion_programada,
      fecha_expiracion: r.fecha_expiracion ?? r.fecha_atencion_programada,
      fecha_atencion: r.fecha_atencion ?? null,
      cliente: {
        id_cliente: r.id_cliente ?? 1,
        nombre: r.cliente_nombre ?? 'Cliente',
        apellido: r.cliente_apellido ?? '',
        correo: r.cliente_correo ?? 'cliente@fashionstore.com',
        telefono: r.cliente_telefono ?? null,
      },
      sucursal: {
        id_sucursal: branch.id_sucursal,
        nombre: branch.nombre,
        direccion: branch.direccion,
        ciudad:
          typeof branch.ciudad === 'object' && branch.ciudad !== null
            ? branch.ciudad
            : { id_ciudad: 1, nombre: String(branch.ciudad ?? '') },
      },
      cantidad_prendas: numItems,
      total: (r.total_referencial ?? 0).toFixed(2),
      prendas,
    };
  }

  private saveReservationsListOnline(summaries: StaffReservationSummary[]): void {
    if (!summaries || summaries.length === 0) return;
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return;
    if (typeof this.offlineStorage?.saveStaffReservations !== 'function') return;

    (async () => {
      try {
        const reservationsToSave: OfflineReservationLocal[] = summaries.map((s) => ({
          uuid_reserva_offline: s.codigo,
          codigo_local: s.codigo,
          id_reserva: s.id_reserva,
          id_empresa: empresaId,
          id_usuario: user.id_usuario,
          id_sucursal: s.sucursal.id_sucursal,
          id_cliente: s.cliente.id_cliente,
          cliente_nombre: s.cliente.nombre,
          cliente_apellido: s.cliente.apellido,
          cliente_correo: s.cliente.correo,
          cliente_telefono: s.cliente.telefono ?? undefined,
          sucursal_nombre: s.sucursal.nombre,
          fecha_reserva_offline: s.created_at,
          fecha_atencion_programada: s.fecha_atencion_programada,
          fecha_expiracion: s.fecha_expiracion,
          fecha_atencion: s.fecha_atencion,
          total_referencial: Number(s.total) || 0,
          saldo_pendiente: Number(s.total) || 0,
          estado: s.estado as OfflineReservationState,
          cantidad_prendas: s.cantidad_prendas,
          created_at: s.created_at,
          updated_at: new Date().toISOString(),
        }));

        const detailsToSave: OfflineReservationDetailLocal[] = [];

        for (const s of summaries) {
          const detailData = s as StaffReservationDetail;
          if (Array.isArray(detailData.prendas) && detailData.prendas.length > 0) {
            for (const p of detailData.prendas) {
              detailsToSave.push({
                uuid_reserva_offline: s.codigo,
                id_variante_producto: p.id_variante_producto,
                id_producto: p.id_producto,
                producto_nombre: p.producto,
                sku: p.sku,
                talla: p.talla.nombre,
                color: p.color.nombre,
                cantidad: p.cantidad,
                precio_referencial: Number(p.precio_reservado) || 0,
                subtotal: Number(p.subtotal) || 0,
                imagen_principal: p.imagen_principal ?? null,
              });
            }
          }
        }

        await this.offlineStorage.saveStaffReservations(
          empresaId,
          user.id_usuario,
          reservationsToSave,
          detailsToSave,
        );

        // Pre-fetch missing details in browser environment using native fetch
        const missingDetails = summaries.filter(
          (s) => !Array.isArray((s as StaffReservationDetail).prendas) || (s as StaffReservationDetail).prendas.length === 0,
        );

        if (missingDetails.length > 0 && typeof fetch === 'function' && typeof window !== 'undefined') {
          const token = this.session.getAccessToken();
          if (token) {
            const fetchedDetails: OfflineReservationDetailLocal[] = [];
            await Promise.allSettled(
              missingDetails.map(async (s) => {
                try {
                  const resp = await fetch(`${this.url}/${s.id_reserva}`, {
                    headers: {
                      Authorization: `Bearer ${token}`,
                      Accept: 'application/json',
                    },
                  });
                  if (resp.ok) {
                    const json = (await resp.json()) as StaffReservationResponse;
                    if (json?.data?.prendas) {
                      for (const p of json.data.prendas) {
                        fetchedDetails.push({
                          uuid_reserva_offline: s.codigo,
                          id_variante_producto: p.id_variante_producto,
                          id_producto: p.id_producto,
                          producto_nombre: p.producto,
                          sku: p.sku,
                          talla: p.talla.nombre,
                          color: p.color.nombre,
                          cantidad: p.cantidad,
                          precio_referencial: Number(p.precio_reservado) || 0,
                          subtotal: Number(p.subtotal) || 0,
                          imagen_principal: p.imagen_principal ?? null,
                        });
                      }
                    }
                  }
                } catch {
                  // Ignore fetch errors during background prefetch
                }
              }),
            );

            if (fetchedDetails.length > 0) {
              await this.offlineStorage.saveStaffReservations(
                empresaId,
                user.id_usuario,
                reservationsToSave,
                fetchedDetails,
              );
            }
          }
        }
      } catch {
        // Safe fail: caching is best effort and must never break online experience
      }
    })();
  }

  private saveReservationDetailOnline(detail: StaffReservationDetail): void {
    if (!detail) return;
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return;
    if (typeof this.offlineStorage?.saveStaffReservations !== 'function') return;

    (async () => {
      try {
        const reservationLocal: OfflineReservationLocal = {
          uuid_reserva_offline: detail.codigo,
          codigo_local: detail.codigo,
          id_reserva: detail.id_reserva,
          id_empresa: empresaId,
          id_usuario: user.id_usuario,
          id_sucursal: detail.sucursal.id_sucursal,
          id_cliente: detail.cliente.id_cliente,
          cliente_nombre: detail.cliente.nombre,
          cliente_apellido: detail.cliente.apellido,
          cliente_correo: detail.cliente.correo,
          cliente_telefono: detail.cliente.telefono ?? undefined,
          sucursal_nombre: detail.sucursal.nombre,
          fecha_reserva_offline: detail.created_at,
          fecha_atencion_programada: detail.fecha_atencion_programada,
          fecha_expiracion: detail.fecha_expiracion,
          fecha_atencion: detail.fecha_atencion,
          total_referencial: Number(detail.total) || 0,
          saldo_pendiente: Number(detail.total) || 0,
          estado: detail.estado as OfflineReservationState,
          cantidad_prendas: detail.cantidad_prendas,
          created_at: detail.created_at,
          updated_at: new Date().toISOString(),
        };

        const detailsLocal: OfflineReservationDetailLocal[] = (detail.prendas || []).map((p) => ({
          uuid_reserva_offline: detail.codigo,
          id_variante_producto: p.id_variante_producto,
          id_producto: p.id_producto,
          producto_nombre: p.producto,
          sku: p.sku,
          talla: p.talla.nombre,
          color: p.color.nombre,
          cantidad: p.cantidad,
          precio_referencial: Number(p.precio_reservado) || 0,
          subtotal: Number(p.subtotal) || 0,
          imagen_principal: p.imagen_principal ?? null,
        }));

        await this.offlineStorage.saveStaffReservations(
          empresaId,
          user.id_usuario,
          [reservationLocal],
          detailsLocal,
        );
      } catch {
        // Safe fail
      }
    })();
  }
}
