import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, Observable, of } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflineConflictDetail,
  OfflineOperationConflictDiagnosis,
  OfflineSyncQueueItem,
} from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

export type OfflineOperationUiType =
  | 'RESERVA'
  | 'COMPRA'
  | 'VENTA'
  | 'TRANSICION_RESERVA';

export type OfflineOperationSyncStatus =
  | 'PENDIENTE'
  | 'SINCRONIZADA'
  | 'RECHAZADA'
  | 'CONFLICTO';

export interface OfflinePendingLineItem {
  id_variante_producto: number;
  producto_nombre: string;
  sku?: string;
  talla?: string;
  color?: string;
  cantidad: number;
  precio: number;
  subtotal: number;
}

export interface OfflinePendingOperationItem {
  uuid_operacion: string;
  uuid_entidad: string;
  tipo: OfflineOperationUiType;
  codigo_provisional: string;
  codigo_servidor?: string | null;
  fecha: string;
  id_sucursal: number;
  sucursal_nombre: string;
  id_usuario: number;
  actor_nombre?: string;
  rol: 'CLIENTE' | 'CAJERO' | 'ENCARGADO_SUCURSAL' | 'ADMINISTRADOR';
  importe?: number | null;
  moneda: string;
  metodo_pago?: string | null;
  pago_simulado?: boolean;
  estado_comercial: string;
  estado_sincronizacion: OfflineOperationSyncStatus;
  confirmada_en_servidor: boolean;
  motivo_servidor?: string | null;
  detalles: OfflinePendingLineItem[];
  ruta_comprobante?: string | any[];
  id_local_comprobante?: number | string;
  accion_transicion?: string;
  conflictos?: OfflineConflictDetail[];
  diagnostico_cu14?: OfflineOperationConflictDiagnosis | null;
  bloqueada_por_dependencia?: boolean;
  depende_de_uuid?: string | null;
  payload?: any;
}

export interface ServerBatchStatusResponse {
  success: boolean;
  operaciones: Record<
    string,
    {
      confirmada: boolean;
      estado_sincronizacion: string;
      codigo_servidor?: string | null;
      motivo?: string | null;
      id_servidor?: number | null;
      estado_servidor?: string | null;
    }
  >;
  total_consultados: number;
  total_sincronizados: number;
  mensaje: string;
}

@Injectable({ providedIn: 'root' })
export class OfflinePendingOperationsService {
  private readonly http = inject(HttpClient);
  private readonly storage = inject(OfflineStorageService);
  private readonly offlineService = inject(OfflineService);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/offline/operaciones`;

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  /**
   * Consulta desde IndexedDB las operaciones locales pendientes respetando
   * empresa, usuario, rol y sucursal autorizada.
   */
  async loadLocalOperations(filters?: {
    tipo?: string;
    estadoSync?: string;
  }): Promise<OfflinePendingOperationItem[]> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return [];

    const isClient = user.rol.toUpperCase() === 'CLIENTE';
    const isStaff =
      user.rol.toUpperCase() === 'CAJERO' ||
      user.rol.toUpperCase() === 'ENCARGADO_SUCURSAL';

    // 1. Obtener datos de IndexedDB
    const [queue, reservations, resDetails, purchases, purDetails, branches] =
      await Promise.all([
        this.storage.getOfflineQueue(empresaId, user.id_usuario),
        this.storage.getOfflineReservations(empresaId, user.id_usuario),
        this.storage.getOfflineReservationDetails(empresaId, user.id_usuario),
        this.storage.getOfflinePurchases(empresaId, user.id_usuario),
        this.storage.getOfflinePurchaseDetails(empresaId, user.id_usuario),
        this.storage.getBranches(empresaId, user.id_usuario),
      ]);

    const branchMap = new Map(branches.map((b) => [b.id_sucursal, b.nombre]));

    // Para personal de sucursal, identificar su sucursal autorizada
    let authorizedBranchId: number | null = null;
    if (isStaff) {
      if (typeof localStorage !== 'undefined') {
        try {
          const raw = localStorage.getItem(`fashionstore_staff_branch_${user.id_usuario}`);
          if (raw) {
            const parsed = JSON.parse(raw);
            authorizedBranchId = parsed?.branch?.id_sucursal ?? null;
          }
        } catch {
          // ignore
        }
      }
      if (!authorizedBranchId && branches.length > 0) {
        authorizedBranchId = branches[0].id_sucursal;
      }
    }

    const items: OfflinePendingOperationItem[] = [];

    // Mapa para asociar cola con entidad
    const queueByEntity = new Map<string, OfflineSyncQueueItem>();
    const queueByOperation = new Map<string, OfflineSyncQueueItem>();
    for (const q of queue) {
      queueByEntity.set(q.uuid_entidad, q);
      queueByOperation.set(q.uuid_operacion, q);
    }

    // 2. Procesar Compras y Ventas (compras_offline)
    for (const p of purchases) {
      // Aislamiento: CLIENTE solo ve sus compras digitales; CAJERO solo ve ventas de su sucursal
      if (isClient) {
        if (p.id_usuario !== user.id_usuario && p.canal !== 'DIGITAL') continue;
      } else if (isStaff) {
        if (authorizedBranchId && p.id_sucursal !== authorizedBranchId) continue;
      }

      const qItem =
        queueByEntity.get(p.uuid_venta_offline) ||
        queueByOperation.get(p.uuid_venta_offline);

      let syncStatus: OfflineOperationSyncStatus = 'PENDIENTE';
      const isSynced =
        qItem?.estado === 'SINCRONIZADA' ||
        p.estado === 'CONFIRMADA' ||
        Boolean(p.id_venta_servidor);
      const isQueueRetryable =
        qItem?.estado === 'PENDIENTE_SINCRONIZACION' ||
        qItem?.estado === 'REGISTRADA_LOCAL' ||
        qItem?.estado === 'ENVIADA';

      if (isSynced) {
        syncStatus = 'SINCRONIZADA';
      } else if (
        qItem?.estado === 'CONFLICTO' ||
        (!isQueueRetryable && p.estado === 'EN_CONFLICTO')
      ) {
        syncStatus = 'CONFLICTO';
      } else if (
        qItem?.estado === 'RECHAZADA' ||
        (!isQueueRetryable && p.estado === 'RECHAZADA')
      ) {
        syncStatus = 'RECHAZADA';
      }

      const pDetails = purDetails
        .filter((d) => d.uuid_venta_offline === p.uuid_venta_offline)
        .map((d) => ({
          id_variante_producto: d.id_variante_producto,
          producto_nombre: d.producto_nombre,
          sku: d.sku,
          talla: d.talla,
          color: d.color,
          cantidad: d.cantidad,
          precio: d.precio_unitario,
          subtotal: d.subtotal_linea,
        }));

      const isDigital = p.canal === 'DIGITAL';
      const uiType: OfflineOperationUiType = isDigital ? 'COMPRA' : 'VENTA';
      const role: 'CLIENTE' | 'CAJERO' = isDigital ? 'CLIENTE' : 'CAJERO';

      const sucursalNombre =
        p.sucursal_nombre ||
        branchMap.get(p.id_sucursal) ||
        `Sucursal #${p.id_sucursal}`;

      items.push({
        uuid_operacion: p.uuid_venta_offline,
        uuid_entidad: p.uuid_venta_offline,
        tipo: uiType,
        codigo_provisional: p.numero_venta_local,
        fecha: p.fecha_venta_offline || p.created_at,
        id_sucursal: p.id_sucursal,
        sucursal_nombre: sucursalNombre,
        id_usuario: p.id_usuario,
        actor_nombre: p.cliente_nombre || `${user.nombre} ${user.apellido}`,
        rol: role,
        importe: p.total,
        moneda: p.moneda || 'BOB',
        metodo_pago: p.medio_pago,
        pago_simulado: p.pago_simulado,
        estado_comercial: p.estado || 'REGISTRADA_LOCAL',
        estado_sincronizacion: syncStatus,
        confirmada_en_servidor: isSynced,
        codigo_servidor: p.numero_venta_servidor || qItem?.payload?.codigo_servidor || null,
        motivo_servidor: qItem?.ultimo_error || p.motivo_servidor || null,
        detalles: pDetails,
        ruta_comprobante: isDigital
          ? ['/mis-compras', p.id_venta_local, 'comprobante']
          : ['/staff/ventas', p.id_venta_local, 'comprobante'],
        id_local_comprobante: p.id_venta_local,
        conflictos: qItem?.conflictos || p.conflictos || [],
        depende_de_uuid: qItem?.payload?.depende_de_uuid || p.uuid_reserva_offline || null,
        payload: qItem?.payload || {
          uuid_venta_offline: p.uuid_venta_offline,
          numero_venta_local: p.numero_venta_local,
          id_sucursal: p.id_sucursal,
          canal: p.canal,
          medio_pago: p.medio_pago,
          items: pDetails.map((d) => ({
            id_variante_producto: d.id_variante_producto,
            cantidad: d.cantidad,
            precio_unitario: d.precio,
          })),
        },
      });
    }

    // 3. Procesar Reservas (reservas_offline)
    for (const r of reservations) {
      if (isClient) {
        if (r.id_usuario !== user.id_usuario) continue;
      } else if (isStaff) {
        if (authorizedBranchId && r.id_sucursal !== authorizedBranchId) continue;
      }

      // Regla CU12/CU13: Contar únicamente operaciones realmente registradas en la cola offline
      // o con trazabilidad verificable de registro offline local ('RES-LOC-...').
      // Las reservas descargadas de PostgreSQL para la caché de staff tienen id_reserva > 0
      // sin entrada de creación en cola y NO deben contarse como operaciones offline.
      const creationQueueItem = queue.find(
        (q) =>
          q.tipo_operacion === 'RESERVA' &&
          !q.payload?.accion &&
          (q.uuid_entidad === r.uuid_reserva_offline || q.uuid_operacion === r.uuid_reserva_offline),
      );

      const isOfflineCreated =
        Boolean(creationQueueItem) ||
        r.estado === 'REGISTRADA_LOCAL' ||
        r.estado === 'ENVIADA' ||
        r.estado === 'RECHAZADA' ||
        r.estado === 'EN_CONFLICTO' ||
        Boolean(r.codigo_local?.startsWith('RES-LOC-'));

      // Si no fue creada offline (es una reserva descargada del backend para caché local), NO se cuenta en CU12
      if (
        !isOfflineCreated ||
        (r.id_reserva && r.id_reserva > 0 && !creationQueueItem && !r.codigo_local?.startsWith('RES-LOC-'))
      ) {
        continue;
      }

      // Para operaciones offline legítimas:
      // Las operaciones REINTENTABLES permanecen PENDIENTES hasta que CU13 las confirme o determine un rechazo/conflicto real.
      let syncStatus: OfflineOperationSyncStatus = 'PENDIENTE';
      const qItem = creationQueueItem || queueByEntity.get(r.uuid_reserva_offline);
      const isResSynced =
        qItem?.estado === 'SINCRONIZADA' ||
        r.estado === 'SINCRONIZADA' ||
        Boolean(r.codigo_servidor);
      const isResQueueRetryable =
        qItem?.estado === 'PENDIENTE_SINCRONIZACION' ||
        qItem?.estado === 'REGISTRADA_LOCAL' ||
        qItem?.estado === 'ENVIADA';

      if (isResSynced) {
        syncStatus = 'SINCRONIZADA';
      } else if (
        qItem?.estado === 'CONFLICTO' ||
        (!isResQueueRetryable && r.estado === 'EN_CONFLICTO')
      ) {
        syncStatus = 'CONFLICTO';
      } else if (
        qItem?.estado === 'RECHAZADA' ||
        (!isResQueueRetryable && r.estado === 'RECHAZADA')
      ) {
        syncStatus = 'RECHAZADA';
      }

      const rDetails = resDetails
        .filter((d) => d.uuid_reserva_offline === r.uuid_reserva_offline)
        .map((d) => ({
          id_variante_producto: d.id_variante_producto,
          producto_nombre: d.producto_nombre,
          sku: d.sku,
          talla: d.talla,
          color: d.color,
          cantidad: d.cantidad,
          precio: d.precio_referencial,
          subtotal: d.subtotal,
        }));

      const sucursalNombre =
        r.sucursal_nombre ||
        branchMap.get(r.id_sucursal) ||
        `Sucursal #${r.id_sucursal}`;

      items.push({
        uuid_operacion: r.uuid_reserva_offline,
        uuid_entidad: r.uuid_reserva_offline,
        tipo: 'RESERVA',
        codigo_provisional: r.codigo_local,
        fecha: r.fecha_reserva_offline || r.created_at,
        id_sucursal: r.id_sucursal,
        sucursal_nombre: sucursalNombre,
        id_usuario: r.id_usuario,
        actor_nombre: r.cliente_nombre || 'Cliente',
        rol: 'CLIENTE',
        importe: r.total_referencial,
        moneda: 'BOB',
        metodo_pago: r.adelanto_efectivo ? 'EFECTIVO' : 'POR_COBRAR',
        pago_simulado: false,
        estado_comercial: r.estado,
        estado_sincronizacion: syncStatus,
        confirmada_en_servidor: isResSynced,
        codigo_servidor: r.codigo_servidor || qItem?.payload?.codigo_servidor || null,
        motivo_servidor: qItem?.ultimo_error || r.motivo_servidor || null,
        detalles: rDetails,
        ruta_comprobante: isClient
          ? ['/mis-reservas', r.uuid_reserva_offline]
          : ['/staff/reservas', r.uuid_reserva_offline],
        id_local_comprobante: r.uuid_reserva_offline,
        conflictos: qItem?.conflictos || r.conflictos || [],
        depende_de_uuid: qItem?.payload?.depende_de_uuid || null,
        payload: qItem?.payload || {
          uuid_reserva_offline: r.uuid_reserva_offline,
          codigo_local: r.codigo_local,
          id_sucursal: r.id_sucursal,
          fecha_atencion_programada: r.fecha_atencion_programada,
          detalles: rDetails.map((d) => ({
            id_variante_producto: d.id_variante_producto,
            cantidad: d.cantidad,
            precio_referencial: d.precio,
          })),
        },
      });
    }

    // 4. Procesar Transiciones de reserva registradas en cola por el personal
    if (isStaff) {
      for (const q of queue) {
        if (q.tipo_operacion === 'RESERVA' && q.payload?.accion) {
          const action = q.payload.accion;
          const sucursalId = q.payload?.id_sucursal || authorizedBranchId || 1;
          const sucursalNombre =
            branchMap.get(sucursalId) || 'Sucursal Asignada';

          let syncStatus: OfflineOperationSyncStatus = 'PENDIENTE';
          const isTransSynced =
            q.estado === 'SINCRONIZADA' || Boolean(q.payload?.codigo_servidor);

          if (isTransSynced) {
            syncStatus = 'SINCRONIZADA';
          } else if (q.estado === 'CONFLICTO') {
            syncStatus = 'CONFLICTO';
          } else if (q.estado === 'RECHAZADA') {
            syncStatus = 'RECHAZADA';
          }

          items.push({
            uuid_operacion: q.uuid_operacion,
            uuid_entidad: q.uuid_entidad,
            tipo: 'TRANSICION_RESERVA',
            codigo_provisional: q.payload.codigo_reserva || q.uuid_entidad,
            codigo_servidor: q.payload?.codigo_servidor ?? null,
            fecha: q.payload.fecha_transicion || q.created_at,
            id_sucursal: sucursalId,
            sucursal_nombre: sucursalNombre,
            id_usuario: user.id_usuario,
            actor_nombre: `${user.nombre} ${user.apellido}`,
            rol: 'CAJERO',
            importe: null,
            moneda: 'BOB',
            metodo_pago: null,
            pago_simulado: false,
            estado_comercial: q.payload.estado_nuevo || q.estado,
            estado_sincronizacion: syncStatus,
            confirmada_en_servidor: isTransSynced,
            motivo_servidor: q.ultimo_error || null,
            detalles: [],
            accion_transicion:
              action === 'confirm'
                ? 'Confirmación de preparación'
                : 'Marcada como atendida',
            conflictos: q.conflictos || [],
            depende_de_uuid: q.payload?.depende_de_uuid || q.uuid_entidad || null,
            payload: q.payload,
          });
        }
      }
    }

    // Ordenar de más reciente a más antigua
    items.sort((a, b) => b.fecha.localeCompare(a.fecha));

    // Aplicar filtros opcionales
    return items.filter((item) => {
      if (filters?.tipo && filters.tipo !== 'TODOS') {
        if (item.tipo !== filters.tipo) return false;
      }
      if (filters?.estadoSync && filters.estadoSync !== 'TODOS') {
        if (item.estado_sincronizacion !== filters.estadoSync) return false;
      }
      return true;
    });
  }

  /**
   * Consulta el endpoint batch CU12 en el servidor para contrastar los UUIDs locales.
   * IMPORTANTE (Regla CU12): No marca como sincronizada una operación que el servidor no encuentre.
   */
  verifyBatchStatuses(uuids: string[]): Observable<ServerBatchStatusResponse | null> {
    if (!uuids || uuids.length === 0) {
      return of({
        success: true,
        operaciones: {},
        total_consultados: 0,
        total_sincronizados: 0,
        mensaje: 'Sin operaciones para consultar',
      });
    }

    return this.http
      .post<ServerBatchStatusResponse>(
        `${this.url}/status/batch`,
        { uuids },
        { headers: this.headers() },
      )
      .pipe(
        catchError(() =>
          of(null), // En caso de fallo de red o error del servidor, se ignora silenciosamente
        ),
      );
  }
}
