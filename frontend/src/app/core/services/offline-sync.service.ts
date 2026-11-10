import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { firstValueFrom, timeout } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflineCodeLinkItem,
  OfflineQueueSyncOperationInputDto,
  OfflineQueueSyncRequest,
  OfflineQueueSyncResponse,
  OfflineSyncOperationResult,
  OfflineSyncOperationType,
  OfflineSyncQueueItem,
} from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

export interface SyncPendingOptions {
  manual?: boolean;
  auto?: boolean;
}

@Injectable({ providedIn: 'root' })
export class OfflineSyncService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly storage = inject(OfflineStorageService);
  private readonly offlineService = inject(OfflineService);

  readonly isSyncing = signal<boolean>(false);
  readonly lastSyncResponse = signal<OfflineQueueSyncResponse | null>(null);
  readonly lastSyncError = signal<string | null>(null);

  private activeSyncPromise: Promise<OfflineQueueSyncResponse> | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        void this.handleOnlineRecovery();
      });
    }
  }

  /**
   * Encabezados con JWT para autenticación y aislamiento multitenant.
   */
  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  /**
   * Verifica conectividad real con el backend FastAPI antes de lanzar sincronizaciones automáticas.
   */
  async checkRealConnection(): Promise<boolean> {
    try {
      await firstValueFrom(
        this.http
          .get(`${environment.apiUrl}/health`, { responseType: 'text' })
          .pipe(timeout(3500)),
      );
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Disparador automático al recuperar la conexión a internet.
   * Valida conectividad real y evita ejecuciones duplicadas.
   */
  async handleOnlineRecovery(): Promise<void> {
    const user = this.session.getUser();
    if (!user) return;

    if (this.isSyncing()) {
      return;
    }

    const hasRealConnection = await this.checkRealConnection();
    if (!hasRealConnection) {
      return;
    }

    try {
      await this.syncPendingOperations({ auto: true });
    } catch {
      // Fallo silencioso en sincronización automática para no interrumpir al usuario
    }
  }

  /**
   * Determina la prioridad de ordenamiento para garantizar la secuencia estricta:
   * 1. RESERVA (creación de cliente)
   * 2. CONFIRMAR (transición personal: PENDIENTE -> CONFIRMADA)
   * 3. ATENDER (transición personal: CONFIRMADA -> ATENDIDA)
   * 4. VENTA (venta por reserva o venta directa POS) / COMPRA (digital)
   */
  private getOperationPriority(item: OfflineSyncQueueItem): number {
    const type = (item.tipo_operacion || '').toUpperCase();
    const action = String(item.payload?.accion || '').toLowerCase();

    if (type === 'RESERVA' && !action) {
      return 1;
    }
    if (type === 'TRANSICION_RESERVA' || (type === 'RESERVA' && action)) {
      if (action.includes('confirm')) return 2;
      if (action.includes('attend') || action.includes('atend')) return 3;
      return 2;
    }
    if (type === 'VENTA' || type === 'COMPRA') {
      return 4;
    }
    return 5;
  }

  /**
   * Sincroniza el lote de operaciones pendientes en IndexedDB con el backend central (POST /api/offline/sincronizar).
   * - Control de concurrencia: nunca ejecuta dos sincronizaciones simultáneas (mutex/lock).
   * - Envía únicamente operaciones del usuario y empresa autorizados según rol.
   * - Respeta orden estricto de dependencias: RESERVA -> CONFIRMAR -> ATENDER -> VENTA.
   * - Procesa resultados individuales (CONFIRMADA, REINTENTABLE, RECHAZADA, EN_CONFLICTO).
   * - Ante caída de red, conserva íntegra la cola en IndexedDB sin duplicados ni pérdidas.
   */
  async syncPendingOperations(
    options: SyncPendingOptions = {},
  ): Promise<OfflineQueueSyncResponse> {
    // 1. Evitar dos sincronizaciones simultáneas
    if (this.isSyncing()) {
      if (this.activeSyncPromise) {
        return this.activeSyncPromise;
      }
      throw new Error('Ya existe un proceso de sincronización en ejecución.');
    }

    const user = this.session.getUser();
    const empresaId = await this.offlineService.resolveCompanyIdAsync(user?.id_usuario);

    if (!user || !empresaId) {
      const msg = 'Sesión no válida o sin empresa asignada para sincronizar.';
      this.lastSyncError.set(msg);
      throw new Error(msg);
    }

    this.isSyncing.set(true);
    this.lastSyncError.set(null);

    const syncTask = (async (): Promise<OfflineQueueSyncResponse> => {
      // 2. Obtener cola local desde IndexedDB
      const queue = await this.storage.getOfflineQueue(empresaId, user.id_usuario);

      const isClient = user.rol.toUpperCase() === 'CLIENTE';
      const isStaff =
        user.rol.toUpperCase() === 'CAJERO' ||
        user.rol.toUpperCase() === 'ENCARGADO_SUCURSAL';

      // 3. Filtrar únicamente operaciones pendientes correspondientes al rol y actor
      const pendingItems = queue.filter((item) => {
        // Excluir operaciones ya sincronizadas con éxito
        if (item.estado === 'SINCRONIZADA') return false;

        const opType = (item.tipo_operacion || '').toUpperCase();
        const hasAction = Boolean(item.payload?.accion);

        if (isClient) {
          // CLIENTE solo puede sincronizar sus reservas y compras digitales
          if (hasAction) return false;
          if (opType === 'VENTA' && item.payload?.canal === 'PRESENCIAL') return false;
        } else if (isStaff) {
          // PERSONAL solo sincroniza transiciones y ventas presenciales
          if (opType === 'COMPRA') return false;
          if (opType === 'RESERVA' && !hasAction) return false;
        }

        return true;
      });

      // Si no hay operaciones pendientes, retornar respuesta vacía sin llamada HTTP
      if (pendingItems.length === 0) {
        const emptyResponse: OfflineQueueSyncResponse = {
          success: true,
          empresa_id: empresaId,
          id_usuario: user.id_usuario,
          rol: user.rol,
          total_operaciones: 0,
          confirmadas: 0,
          rechazadas: 0,
          en_conflicto: 0,
          reintentables: 0,
          resultados: [],
          resultados_por_uuid: {},
          vinculaciones_codigos: {},
          fecha_sincronizacion: new Date().toISOString(),
          mensaje: 'No hay operaciones pendientes de sincronización.',
        };
        this.lastSyncResponse.set(emptyResponse);
        return emptyResponse;
      }

      // 4. Ordenar respetando dependencias y secuencia:
      // RESERVA (1) -> CONFIRMAR (2) -> ATENDER (3) -> VENTA/COMPRA (4)
      const sortedItems = [...pendingItems].sort((a, b) => {
        const prioA = this.getOperationPriority(a);
        const prioB = this.getOperationPriority(b);
        if (prioA !== prioB) {
          return prioA - prioB;
        }

        // Si b depende de a, a debe ir antes
        if (b.payload?.depende_de_uuid === a.uuid_operacion) return -1;
        if (a.payload?.depende_de_uuid === b.uuid_operacion) return 1;

        // Por defecto, orden cronológico de registro local
        return (a.created_at || '').localeCompare(b.created_at || '');
      });

      let resolvedClientId: number | null = null;
      if (isClient && typeof this.storage.getClients === 'function') {
        try {
          const clients = await this.storage.getClients(empresaId, user.id_usuario);
          const matchedClient = clients?.find((c) => c.id_usuario === user.id_usuario);
          resolvedClientId = matchedClient ? matchedClient.id_cliente : null;
        } catch {
          resolvedClientId = null;
        }
      }

      // 5. Construir lote normalizado con secuencia y datos originales
      const operationsDto: OfflineQueueSyncOperationInputDto[] = sortedItems.map(
        (item, idx) => {
          let tipoOp: OfflineSyncOperationType = item.tipo_operacion as any;
          let payload = item.payload ? { ...item.payload } : {};
          if (tipoOp === 'RESERVA' && payload.accion) {
            tipoOp = 'TRANSICION_RESERVA';
          } else if (tipoOp === 'VENTA' && payload.canal === 'DIGITAL') {
            tipoOp = 'COMPRA';
          }

          if (isClient && tipoOp === 'COMPRA') {
            payload = { ...payload, id_cliente: resolvedClientId ?? null };
          }

          const codigoLocal =
            payload.codigo_reserva ||
            payload.numero_venta_local ||
            payload.codigo_local ||
            item.uuid_entidad;

          const fechaOp =
            payload.fecha_reserva_offline ||
            payload.fecha_venta_offline ||
            payload.fecha_transicion ||
            item.created_at;

          return {
            uuid_operacion: item.uuid_operacion,
            uuid_entidad: item.uuid_entidad || item.uuid_operacion,
            tipo_operacion: tipoOp,
            secuencia: idx + 1,
            depende_de_uuid: payload.depende_de_uuid || null,
            codigo_local: codigoLocal,
            fecha_operacion_offline: fechaOp,
            payload: payload,
          };
        },
      );

      const requestPayload: OfflineQueueSyncRequest = {
        operaciones: operationsDto,
      };

      // 6. Enviar lote a FastAPI con manejo de fallos de red
      let response: OfflineQueueSyncResponse;
      try {
        response = await firstValueFrom(
          this.http.post<OfflineQueueSyncResponse>(
            `${environment.apiUrl}/api/offline/sincronizar`,
            requestPayload,
            { headers: this.headers() },
          ),
        );
      } catch (err: unknown) {
        // Ante caída de red o error de conexión, se conserva íntegra la cola y no se borra nada
        const isNetworkErr =
          err instanceof HttpErrorResponse &&
          (err.status === 0 || !navigator.onLine);
        const errorMsg = isNetworkErr
          ? 'Caída de conexión durante la sincronización: se conservaron todas las operaciones pendientes intactas.'
          : (err as any)?.error?.message ||
            (err instanceof Error
              ? err.message
              : 'Error inesperado al sincronizar con el servidor.');

        this.lastSyncError.set(errorMsg);
        throw new Error(errorMsg);
      }

      // 7. Aplicar resultados de forma atómica en IndexedDB (cola, reservas, compras)
      await this.storage.applyBatchSyncResults(
        empresaId,
        user.id_usuario,
        response.resultados,
        response.vinculaciones_codigos,
      );

      this.lastSyncResponse.set(response);
      return response;
    })();

    this.activeSyncPromise = syncTask;
    try {
      return await syncTask;
    } finally {
      this.isSyncing.set(false);
      this.activeSyncPromise = null;
    }
  }
}

