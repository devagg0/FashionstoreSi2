import { HttpClient, HttpErrorResponse, HttpHeaders, HttpResponse } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import {
  catchError,
  concatMap,
  firstValueFrom,
  map,
  Observable,
  of,
  tap,
  throwError,
} from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflineBranchData,
  OfflinePackageResponse,
  OfflineProductData,
  OfflineReceiptData,
  OfflineReservationDetailLocal,
  OfflineReservationLocal,
  OfflinePurchaseDetailLocal,
  OfflinePurchaseLocal,
  OfflinePurchaseReceiptData,
  hashReservationUuidToId,
  CashierOfflineSaleInput,
  CashierOfflineSaleResult,
  ClientOfflinePurchaseResult,
  OfflineStatusResponse,
  OfflineStoredSummary,
  OfflineSyncQueueItem,
} from '../models/offline.model';
import { isReservationDateAllowed, reservationTimeSlots, reservationTimestamp } from '../utils/reservation-schedule';
import { OfflineStorageService } from './offline-storage.service';
import { ReservationContext, ReservationSelectionItem } from './reservation-selection.service';
import { SessionService } from './session.service';

export const OFFLINE_IMAGES_CACHE_NAME = 'fashionstore-offline-images-v1';

const ALLOWED_AUTO_PREP_ROLES = new Set([
  'CLIENTE',
  'ADMINISTRADOR',
  'ADMIN',
  'CAJERO',
  'ENCARGADO_SUCURSAL',
]);

export interface ClientOfflineReservationResult {
  receipt: OfflineReceiptData | null;
  errors: string[];
  /** true cuando el UUID ya estaba guardado localmente (reintento idempotente). */
  alreadyStored: boolean;
}

export interface DownloadResult {
  notModified: boolean;
  package?: OfflinePackageResponse;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class OfflineService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly storage = inject(OfflineStorageService);
  private readonly autoPreparedSessionKeys = new Set<string>();

  readonly isOnline = signal<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  readonly isLoading = signal<boolean>(false);
  readonly isAutoPreparing = signal<boolean>(false);
  readonly cachedImagesCount = signal<number>(0);
  readonly error = signal<string | null>(null);
  readonly lastActionMessage = signal<string | null>(null);
  readonly localSummary = signal<OfflineStoredSummary | null>(null);
  readonly statusCheck = signal<OfflineStatusResponse | null>(null);

  readonly offlinePreparationDate = computed<string | null>(() => {
    const summary = this.localSummary();
    if (!summary) return null;
    const raw = summary.metadata?.fecha_generacion || summary.savedAt;
    if (!raw) return null;
    const date = new Date(raw);
    if (isNaN(date.getTime())) return null;
    return date.toLocaleString('es-BO', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  });

  readonly offlineExpiryDate = computed<string | null>(() => {
    const summary = this.localSummary();
    if (!summary || !summary.metadata?.valido_hasta) return null;
    const date = new Date(summary.metadata.valido_hasta);
    if (isNaN(date.getTime())) return null;
    return date.toLocaleString('es-BO', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  });

  readonly isPackageExpired = computed<boolean>(() => {
    const summary = this.localSummary();
    if (!summary) return false;
    if (summary.isExpired) return true;
    if (!summary.metadata?.valido_hasta) return false;
    const expiry = new Date(summary.metadata.valido_hasta).getTime();
    return !isNaN(expiry) && Date.now() > expiry;
  });

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => {
        this.isOnline.set(true);
        const user = this.session.getUser();
        if (user && user.rol.toUpperCase() === 'CLIENTE') {
          void this.ensurePreparedAutomatically();
        }
      });
      window.addEventListener('offline', () => {
        this.isOnline.set(false);
        void this.loadLocalSummary();
      });
      void this.loadLocalSummary();
    }
  }

  /**
   * Resuelve el id_empresa efectivo del usuario actual (usando el token o el último contexto preparado para ese usuario).
   */
  resolveEffectiveCompanyId(): number | null {
    const user = this.session.getUser();
    if (!user) return null;
    if (typeof user.id_empresa === 'number' && user.id_empresa > 0) {
      return user.id_empresa;
    }
    return this.readUserCompanyFallback(user.id_usuario);
  }

  /**
   * Carga el resumen local desde IndexedDB sin requerir conexión a internet.
   */
  async loadLocalSummary(): Promise<OfflineStoredSummary | null> {
    const user = this.session.getUser();
    if (!user) {
      this.localSummary.set(null);
      return null;
    }

    let empresaId = this.resolveEffectiveCompanyId();
    if (!empresaId) {
      empresaId = await this.findCompanyIdFromDatabases(user.id_usuario);
      if (empresaId) {
        this.saveUserCompanyFallback(user.id_usuario, empresaId);
      }
    }

    if (!empresaId) {
      this.localSummary.set(null);
      return null;
    }

    try {
      const summary = await this.storage.getStoredPackageSummary(
        empresaId,
        user.id_usuario,
      );
      this.localSummary.set(summary);
      return summary;
    } catch {
      this.localSummary.set(null);
      return null;
    }
  }

  async findCompanyIdFromDatabases(userId: number): Promise<number | null> {
    try {
      if (typeof indexedDB !== 'undefined' && typeof indexedDB.databases === 'function') {
        const dbs = await indexedDB.databases();
        const prefix = 'fashionstore_offline_e';
        const suffix = `_u${userId}`;
        for (const db of dbs) {
          if (db.name && db.name.startsWith(prefix) && db.name.endsWith(suffix)) {
            const mid = db.name.slice(prefix.length, db.name.length - suffix.length);
            const parsed = Number(mid);
            if (Number.isInteger(parsed) && parsed > 0) {
              return parsed;
            }
          }
        }
      }
    } catch {
      // Ignorar en entornos donde no esté disponible indexedDB.databases
    }
    return null;
  }

  async resolveCompanyIdAsync(userId?: number): Promise<number | null> {
    let empresaId = this.resolveEffectiveCompanyId();
    const uid = userId ?? this.session.getUser()?.id_usuario;
    if (!empresaId && uid) {
      empresaId = await this.findCompanyIdFromDatabases(uid);
      if (empresaId) {
        this.saveUserCompanyFallback(uid, empresaId);
      }
    }
    return empresaId;
  }

  /**
   * Consulta liviana al endpoint GET /api/offline/status para verificar
   * vigencia y si existen cambios en el servidor antes de descargar.
   */
  checkStatus(branchId?: number, version?: string): Observable<OfflineStatusResponse> {
    const token = this.session.getAccessToken();
    const user = this.session.getUser();

    if (!token || !user) {
      const msg = 'Sesión no válida o no autenticada.';
      this.error.set(msg);
      return throwError(() => new Error(msg));
    }

    this.isLoading.set(true);
    this.error.set(null);

    let headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    const params: Record<string, string | number> = {};
    if (branchId) params['id_sucursal'] = branchId;
    const targetVersion = version || this.localSummary()?.metadata.version;
    if (targetVersion) {
      params['version'] = targetVersion;
      params['since_version'] = targetVersion;
      headers = headers.set('If-None-Match', `"${targetVersion}"`);
    }

    return this.http
      .get<OfflineStatusResponse>(`${environment.apiUrl}/api/offline/status`, {
        headers,
        params,
      })
      .pipe(
        tap({
          next: (res) => {
            this.statusCheck.set(res);
            this.isLoading.set(false);
            this.lastActionMessage.set(res.message);
          },
          error: (err) => {
            this.isLoading.set(false);
            const msg =
              err.error?.message ||
              'No fue posible verificar el estado del paquete en el servidor.';
            this.error.set(msg);
          },
        }),
      );
  }

  /**
   * Descarga o actualiza el paquete de datos offline mediante GET /api/offline/package.
   * - Soporta HTTP 304 condicional (mediante If-None-Match y since_version).
   * - Guarda en IndexedDB de forma atómica y espera su finalización antes de emitir.
   * - Prepara las imágenes del catálogo en Cache Storage para visualización sin internet.
   * - Una descarga fallida conserva intactos los últimos datos válidos.
   */
  downloadPackage(branchId?: number): Observable<DownloadResult> {
    const token = this.session.getAccessToken();
    const user = this.session.getUser();

    if (!token || !user) {
      const msg = 'Sesión no válida o no autenticada.';
      this.error.set(msg);
      return throwError(() => new Error(msg));
    }

    const initialEmpresaId = this.resolveEffectiveCompanyId();
    if (!initialEmpresaId && user.rol.toUpperCase() !== 'CLIENTE') {
      const msg = 'El usuario no tiene una empresa asociada para sincronizar offline.';
      this.error.set(msg);
      return throwError(() => new Error(msg));
    }

    this.isLoading.set(true);
    this.error.set(null);

    const currentVersion = this.localSummary()?.metadata.version;
    let headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    const params: Record<string, string | number> = {};
    if (branchId) params['id_sucursal'] = branchId;
    if (currentVersion) {
      headers = headers.set('If-None-Match', `"${currentVersion}"`);
      params['since_version'] = currentVersion;
      params['version'] = currentVersion;
    }

    return this.http
      .get<OfflinePackageResponse>(`${environment.apiUrl}/api/offline/package`, {
        headers,
        params,
        observe: 'response',
      })
      .pipe(
        map((response: HttpResponse<OfflinePackageResponse>): DownloadResult => {
          if (response.status === 304) {
            const message =
              'El paquete offline local se encuentra actualizado (HTTP 304). No hubo cambios.';
            this.lastActionMessage.set(message);
            this.isLoading.set(false);
            return { notModified: true, message };
          }

          const pkg = response.body;
          if (!pkg || !pkg.metadata) {
            throw new Error('Respuesta inválida del servidor al descargar paquete offline.');
          }

          return {
            notModified: false,
            package: pkg,
            message: pkg.message || 'Paquete offline descargado exitosamente.',
          };
        }),
        catchError((err: unknown) => {
          if (err instanceof HttpErrorResponse && err.status === 304) {
            const message =
              'El paquete offline local se encuentra actualizado (HTTP 304). No hubo cambios.';
            this.lastActionMessage.set(message);
            this.isLoading.set(false);
            return of<DownloadResult>({ notModified: true, message });
          }
          this.isLoading.set(false);
          const msg =
            (err as any)?.error?.message ||
            'Error de conexión o permisos al descargar el paquete offline. Los datos previos se conservan intactos.';
          this.error.set(msg);
          return throwError(() => err);
        }),
        concatMap(async (result: DownloadResult) => {
          if (!result.notModified && result.package) {
            const targetEmpresaId =
              user.id_empresa || result.package.metadata.id_empresa || initialEmpresaId;
            if (targetEmpresaId) {
              this.saveUserCompanyFallback(user.id_usuario, targetEmpresaId);
              await this.storage.savePackageAtomic(
                targetEmpresaId,
                user.id_usuario,
                result.package,
              );
              await this.cacheCatalogImages(
                result.package.productos ?? [],
                targetEmpresaId,
                user.id_usuario,
              );
              await this.loadLocalSummary();
              const countInfo = `${result.package.metadata.total_productos} productos, ${result.package.metadata.total_variantes} variantes y ${result.package.metadata.total_existencias} existencias guardadas en IndexedDB.`;
              this.lastActionMessage.set(`Paquete preparado: ${countInfo}`);
            }
          }
          this.isLoading.set(false);
          return result;
        }),
      );
  }

  /**
   * Prepara y almacena en caché local (Cache Storage API) las imágenes del catálogo
   * para mostrarlas sin conexión a internet.
   */
  async cacheCatalogImages(
    productos: OfflineProductData[],
    _empresaId?: number,
    _userId?: number,
  ): Promise<{ cached: number; total: number }> {
    const urls = new Set<string>();
    for (const prod of productos ?? []) {
      if (prod.imagen_principal && prod.imagen_principal.trim()) {
        urls.add(prod.imagen_principal.trim());
      }
      for (const img of prod.imagenes ?? []) {
        if (img && img.trim()) {
          urls.add(img.trim());
        }
      }
      if (prod.galeria && Array.isArray(prod.galeria)) {
        for (const g of prod.galeria) {
          if (g.url_imagen && g.url_imagen.trim()) {
            urls.add(g.url_imagen.trim());
          }
        }
      }
    }

    const uniqueUrls = [...urls];
    if (
      uniqueUrls.length === 0 ||
      typeof globalThis === 'undefined' ||
      typeof globalThis.caches === 'undefined' ||
      typeof globalThis.fetch !== 'function'
    ) {
      this.cachedImagesCount.set(0);
      return { cached: 0, total: uniqueUrls.length };
    }

    let cachedCount = 0;
    try {
      const cache = await globalThis.caches.open(OFFLINE_IMAGES_CACHE_NAME);
      await Promise.all(
        uniqueUrls.map(async (url) => {
          try {
            const existing = await cache.match(url);
            if (existing) {
              cachedCount++;
              return;
            }
            let response: Response;
            try {
              response = await globalThis.fetch(url, { mode: 'cors', credentials: 'omit' });
            } catch {
              response = await globalThis.fetch(url, { mode: 'no-cors' });
            }
            if (response && (response.ok || response.type === 'opaque')) {
              await cache.put(url, response.clone());
              cachedCount++;
            }
          } catch {
            // Una imagen inaccesible no interrumpe la persistencia del catálogo.
          }
        }),
      );
    } catch {
      // Continuar de forma segura si Cache Storage no está disponible
    }

    this.cachedImagesCount.set(cachedCount);
    return { cached: cachedCount, total: uniqueUrls.length };
  }

  /**
   * Permite que el CLIENTE autenticado prepare automáticamente los datos offline
   * al utilizar FashionStore con internet, sin entrar en menús administrativos.
   */
  async ensurePreparedAutomatically(
    options: { branchId?: number; force?: boolean } = {},
  ): Promise<boolean> {
    const token = this.session.getAccessToken();
    const user = this.session.getUser();
    if (!token || !user || !ALLOWED_AUTO_PREP_ROLES.has(user.rol.toUpperCase())) {
      return false;
    }

    const summary = await this.loadLocalSummary();
    if (!this.isOnline()) {
      return Boolean(summary && !summary.isExpired);
    }

    if (this.isAutoPreparing() || this.isLoading()) {
      return Boolean(summary && !summary.isExpired);
    }

    const empresaId = this.resolveEffectiveCompanyId() ?? 0;
    const sessionKey = `${empresaId}:${user.id_usuario}:${options.branchId ?? 'ALL'}`;

    if (
      !options.force &&
      summary &&
      !summary.isExpired &&
      this.autoPreparedSessionKeys.has(sessionKey)
    ) {
      return true;
    }

    this.isAutoPreparing.set(true);
    try {
      if (!summary || summary.isExpired || options.force) {
        const res = await firstValueFrom(this.downloadPackage(options.branchId));
        if (res.package || res.notModified) {
          this.autoPreparedSessionKeys.add(sessionKey);
          return true;
        }
        return false;
      }

      const status = await firstValueFrom(
        this.checkStatus(options.branchId, summary.metadata.version),
      );
      if (status.requiere_actualizacion) {
        await firstValueFrom(this.downloadPackage(options.branchId));
      }
      this.autoPreparedSessionKeys.add(sessionKey);
      return true;
    } catch {
      // Fallo silencioso para no bloquear la navegación normal del cliente si el plan no incluye OFFLINE
      return Boolean(summary && !summary.isExpired);
    } finally {
      this.isAutoPreparing.set(false);
    }
  }

  /**
   * Elimina los datos locales de catálogo almacenados en IndexedDB (preservando reservas v2).
   */
  async clearLocalData(): Promise<void> {
    const user = this.session.getUser();
    const empresaId = this.resolveEffectiveCompanyId();
    if (user && empresaId) {
      await this.storage.clearDatabase(empresaId, user.id_usuario);
      this.localSummary.set(null);
      this.statusCheck.set(null);
      this.lastActionMessage.set('Los datos locales offline han sido eliminados de IndexedDB.');
    }
  }

  /**
   * CU10: registra localmente (sin HTTP) la reserva del CLIENTE hecha en el flujo original CU17.
   * Valida contra el paquete IndexedDB y guarda reserva, detalles y cola pendiente en una única
   * transacción. El resultado es siempre «pendiente de sincronización», nunca confirmada.
   * El UUID recibido hace la operación idempotente ante clics repetidos o reintentos.
   */
  async registerClientOfflineReservation(input: {
    uuid: string;
    context: ReservationContext;
    items: ReservationSelectionItem[];
    now?: Date;
  }): Promise<ClientOfflineReservationResult> {
    const fail = (...errors: string[]): ClientOfflineReservationResult => ({
      receipt: null,
      errors,
      alreadyStored: false,
    });
    const user = this.session.getUser();
    const empresaId = this.resolveEffectiveCompanyId();
    if (!user || !empresaId) return fail('Sesión no válida. Inicia sesión nuevamente.');
    if (user.rol.toUpperCase() !== 'CLIENTE') {
      return fail('Solo el cliente puede registrar reservas desde el catálogo.');
    }

    const userId = user.id_usuario;
    const now = input.now ?? new Date();
    const { uuid, context, items } = input;

    try {
      const existing = (await this.storage.getOfflineReservations(empresaId, userId)).find(
        (row) => row.uuid_reserva_offline === uuid,
      );
      if (existing) {
        const details = await this.storage.getOfflineReservationDetails(empresaId, userId, uuid);
        return { receipt: this.toReceipt(existing, details), errors: [], alreadyStored: true };
      }

      const [summary, branches, products, variants, stock, pendingMap] = await Promise.all([
        this.storage.getStoredPackageSummary(empresaId, userId),
        this.storage.getBranches(empresaId, userId),
        this.storage.getCatalogProducts(empresaId, userId),
        this.storage.getVariants(empresaId, userId),
        this.storage.getInventory(empresaId, userId),
        this.storage.getPendingReservedQuantities(empresaId, userId),
      ]);

      const errors: string[] = [];
      if (!summary) {
        return fail('No hay datos offline preparados. Conéctate a internet para preparar el catálogo.');
      }
      const branch = branches.find((row) => row.id_sucursal === context.id_sucursal);
      if (!branch || !branch.estado) {
        errors.push('La sucursal elegida no está disponible en los datos offline.');
      } else if (
        !isReservationDateAllowed(context.fecha, now) ||
        !reservationTimeSlots(
          branch.hora_apertura ?? '',
          branch.hora_cierre ?? '',
          context.fecha,
          now,
        ).includes(context.horario)
      ) {
        errors.push(
          'La fecha u horario de recogida no es válido para el horario de la sucursal. Elige otro.',
        );
      }
      if (!items.length) errors.push('Selecciona al menos una prenda.');
      if (new Set(items.map((item) => item.id_variante_producto)).size !== items.length) {
        errors.push('Hay prendas repetidas en la reserva.');
      }

      const lines: OfflineReservationDetailLocal[] = [];
      for (const item of items) {
        const variant = variants.find((row) => row.id_variante_producto === item.id_variante_producto);
        const product = products.find((row) => row.id_producto === variant?.id_producto);
        if (!variant || !variant.estado || !product || !product.estado) {
          errors.push(`${item.producto} (${item.sku}) ya no está disponible offline.`);
          continue;
        }
        if (!Number.isInteger(item.cantidad) || item.cantidad < 1) {
          errors.push(`Cantidad inválida para ${item.producto}.`);
          continue;
        }
        const entry = stock.find(
          (row) =>
            row.id_sucursal === context.id_sucursal &&
            row.id_variante_producto === item.id_variante_producto,
        );
        const pending = pendingMap.get(`${context.id_sucursal}_${item.id_variante_producto}`) ?? 0;
        const available = Math.max(0, (entry?.stock_disponible ?? 0) - pending);
        if (item.cantidad > available) {
          errors.push(
            `Stock offline insuficiente para ${item.producto} (${item.talla} / ${item.color}). Disponible estimado: ${available}.`,
          );
          continue;
        }
        const unitPrice = Number(
          variant.precio ?? product.precio_final ?? product.precio ?? item.precio_referencia,
        );
        lines.push({
          uuid_reserva_offline: uuid,
          id_variante_producto: variant.id_variante_producto,
          id_producto: product.id_producto,
          producto_nombre: product.nombre,
          sku: variant.sku,
          talla: variant.talla || item.talla,
          color: variant.color || item.color,
          cantidad: item.cantidad,
          precio_referencial: unitPrice,
          subtotal: unitPrice * item.cantidad,
        });
      }
      if (errors.length) return fail(...errors);

      const nowIso = now.toISOString();

      const scheduled = reservationTimestamp(context.fecha, context.horario);
      const total = lines.reduce((acc, line) => acc + line.subtotal, 0);
      const reservation: OfflineReservationLocal = {
        uuid_reserva_offline: uuid,
        codigo_local: `RES-LOC-${uuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`,
        id_empresa: empresaId,
        id_usuario: userId,
        id_sucursal: context.id_sucursal,
        fecha_reserva_offline: nowIso,
        fecha_atencion_programada: scheduled,
        observaciones: null,
        total_referencial: total,
        saldo_pendiente: total,
        estado: 'REGISTRADA_LOCAL',
        created_at: nowIso,
        sucursal_nombre: branch!.nombre,
      };
      const queueItem: OfflineSyncQueueItem = {
        uuid_operacion: `op-${uuid}`,
        tipo_operacion: 'RESERVA',
        uuid_entidad: uuid,
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_reserva_offline: uuid,
          id_sucursal: context.id_sucursal,
          fecha_reserva_offline: nowIso,
          fecha_atencion_programada: scheduled,
          detalles: lines.map((line) => ({
            id_variante_producto: line.id_variante_producto,
            id_producto: line.id_producto,
            cantidad: line.cantidad,
            precio_referencial: line.precio_referencial,
          })),
          observaciones: null,
        },
        reintentos: 0,
        ultimo_error: null,
        created_at: nowIso,
        updated_at: nowIso,
      };
      await this.storage.saveOfflineReservationAtomic(empresaId, userId, reservation, lines, queueItem);
      return { receipt: this.toReceipt(reservation, lines, branch!.direccion), errors: [], alreadyStored: false };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'error desconocido';
      return fail(`No se pudo guardar la reserva en este dispositivo: ${msg}`);
    }
  }

  /**
   * CU10: reservas del cliente guardadas localmente que aún no fueron confirmadas por el servidor.
   * Persisten en IndexedDB tras recargar o cerrar el navegador.
   */
  async getPendingClientReservations(): Promise<OfflineReceiptData[]> {
    const user = this.session.getUser();
    const empresaId = this.resolveEffectiveCompanyId();
    if (!user || !empresaId) return [];
    try {
      const [reservations, details, queue] = await Promise.all([
        this.storage.getOfflineReservations(empresaId, user.id_usuario),
        this.storage.getOfflineReservationDetails(empresaId, user.id_usuario),
        typeof this.storage.getOfflineQueue === 'function'
          ? this.storage.getOfflineQueue(empresaId, user.id_usuario)
          : Promise.resolve([]),
      ]);
      const queueByEntity = new Map(
        (queue || []).map((q) => [q.uuid_entidad || q.uuid_operacion, q]),
      );

      return reservations
        .filter((row) => {
          const qItem = queueByEntity.get(row.uuid_reserva_offline);
          if (row.estado === 'SINCRONIZADA' || qItem?.estado === 'SINCRONIZADA') {
            return Boolean(qItem) || Boolean(row.codigo_local?.startsWith('RES-LOC-'));
          }
          return (
            row.estado === 'REGISTRADA_LOCAL' ||
            row.estado === 'ENVIADA' ||
            row.estado === 'RECHAZADA' ||
            row.estado === 'EN_CONFLICTO'
          );
        })
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((row) => {
          const qItem = queueByEntity.get(row.uuid_reserva_offline);
          const isRetryable =
            qItem?.estado === 'PENDIENTE_SINCRONIZACION' ||
            qItem?.estado === 'REGISTRADA_LOCAL' ||
            qItem?.estado === 'ENVIADA';
          let effectiveState = row.estado;
          if (qItem?.estado === 'SINCRONIZADA' || row.estado === 'SINCRONIZADA') {
            effectiveState = 'SINCRONIZADA';
          } else if (isRetryable) {
            effectiveState = 'REGISTRADA_LOCAL';
          } else if (qItem?.estado === 'CONFLICTO') {
            effectiveState = 'EN_CONFLICTO';
          } else if (qItem?.estado === 'RECHAZADA') {
            effectiveState = 'RECHAZADA';
          }

          return this.toReceipt(
            {
              ...row,
              estado: effectiveState,
              codigo_servidor:
                row.codigo_servidor ?? qItem?.payload?.codigo_servidor ?? null,
              motivo_servidor:
                row.motivo_servidor ?? qItem?.ultimo_error ?? null,
            },
            details.filter((d) => d.uuid_reserva_offline === row.uuid_reserva_offline),
          );
        });
    } catch {
      return [];
    }
  }

  private toReceipt(
    reservation: OfflineReservationLocal,
    details: OfflineReservationDetailLocal[],
    branchAddress?: string,
  ): OfflineReceiptData {
    return {
      uuid_reserva_offline: reservation.uuid_reserva_offline,
      codigo_local: reservation.codigo_local,
      id_reserva: reservation.id_reserva,
      codigo_servidor: reservation.codigo_servidor ?? null,
      motivo_servidor: reservation.motivo_servidor ?? null,
      fecha_registro: reservation.fecha_reserva_offline,
      fecha_limite: reservation.fecha_atencion_programada,
      sucursal_nombre: reservation.sucursal_nombre ?? ('Sucursal #' + reservation.id_sucursal),
      sucursal_direccion: branchAddress,
      detalles: details,
      total_referencial: reservation.total_referencial,
      adelanto_efectivo: 0,
      saldo_pendiente: reservation.total_referencial,
      observaciones: reservation.observaciones,
      estado: reservation.estado,
    };
  }

  /**
   * PK08 - CU11: Registra localmente (sin HTTP) la compra digital del CLIENTE desde el flujo original.
   * Valida disponibilidad contra IndexedDB, descuenta la disponibilidad local estimada de forma atómica,
   * genera UUID idempotente, guarda la compra y pago simulado (QR o TARJETA) en la cola de sincronización,
   * y vacía el carrito offline.
   * IMPORTANTE: No afirma cobro bancario real; el estado siempre es PENDIENTE_VALIDACION.
   */
  async registerClientOfflinePurchase(input: {
    uuid: string;
    idVentaLocal?: number;
    numeroVentaLocal?: string;
    idSucursal: number;
    medioPago: 'QR' | 'TARJETA';
    items: {
      id_variante_producto: number;
      cantidad: number;
      precio_unitario?: number;
      id_producto?: number;
      sku?: string;
    }[];
    now?: Date;
    observaciones?: string | null;
  }): Promise<ClientOfflinePurchaseResult> {
    const fail = (message: string, errors: string[] = []): ClientOfflinePurchaseResult => ({
      success: false,
      uuid_venta_offline: input.uuid,
      id_venta_local: 0,
      numero_venta_local: '',
      receipt: null,
      message,
      errors: errors.length ? errors : [message],
      alreadyStored: false,
    });

    const user = this.session.getUser();
    const empresaId = await this.resolveCompanyIdAsync(user?.id_usuario);
    if (!user || !empresaId) {
      return fail('Sesión no válida. Inicia sesión nuevamente.');
    }
    if (user.rol.toUpperCase() !== 'CLIENTE') {
      return fail('Solo el cliente puede registrar compras digitales desde el catálogo.');
    }

    const userId = user.id_usuario;
    const now = input.now ?? new Date();
    const { uuid, idSucursal, medioPago, items } = input;

    try {
      // Idempotencia: si ya existe una compra con este UUID o idVentaLocal, retornar el comprobante existente
      const existing = (await this.storage.getOfflinePurchases(empresaId, userId)).find(
        (row) =>
          row.uuid_venta_offline === uuid ||
          (input.idVentaLocal !== undefined && row.id_venta_local === input.idVentaLocal),
      );
      if (existing) {
        const details = await this.storage.getOfflinePurchaseDetails(
          empresaId,
          userId,
          existing.uuid_venta_offline,
        );
        const branches = await this.storage.getBranches(empresaId, userId);
        const branch = branches.find((b) => b.id_sucursal === existing.id_sucursal);
        return {
          success: true,
          uuid_venta_offline: existing.uuid_venta_offline,
          id_venta_local: existing.id_venta_local,
          numero_venta_local: existing.numero_venta_local,
          receipt: this.toPurchaseReceipt(existing, details, branch),
          message: 'Compra recuperada de almacenamiento local (operación idempotente).',
          alreadyStored: true,
        };
      }

      const [summary, branches, products, variants, stock, pendingMap] = await Promise.all([
        this.storage.getStoredPackageSummary(empresaId, userId),
        this.storage.getBranches(empresaId, userId),
        this.storage.getCatalogProducts(empresaId, userId),
        this.storage.getVariants(empresaId, userId),
        this.storage.getInventory(empresaId, userId),
        this.storage.getPendingReservedQuantities(empresaId, userId),
      ]);

      const errors: string[] = [];
      if (!summary) {
        return fail('No hay datos offline preparados en este dispositivo.');
      }
      const branch = branches.find((b) => b.id_sucursal === idSucursal);
      if (!branch || !branch.estado) {
        errors.push('La sucursal seleccionada no está disponible offline.');
      }
      if (!items || items.length === 0) {
        errors.push('El carrito no contiene artículos para comprar.');
      }

      const lines: OfflinePurchaseDetailLocal[] = [];
      let totalAmount = 0;

      for (const item of items) {
        const variant = variants.find((v) => v.id_variante_producto === item.id_variante_producto);
        const product = products.find((p) => p.id_producto === variant?.id_producto);
        if (!variant || !variant.estado || !product || !product.estado) {
          errors.push(`El producto o variante #${item.id_variante_producto} no está disponible offline.`);
          continue;
        }
        if (!Number.isInteger(item.cantidad) || item.cantidad < 1) {
          errors.push(`Cantidad inválida para ${product.nombre}.`);
          continue;
        }
        const entry = stock.find(
          (s) => s.id_sucursal === idSucursal && s.id_variante_producto === item.id_variante_producto,
        );
        const pending = pendingMap.get(`${idSucursal}_${item.id_variante_producto}`) ?? 0;
        const available = Math.max(0, (entry?.stock_disponible ?? 0) - pending);

        if (item.cantidad > available) {
          errors.push(
            `Stock offline insuficiente para ${product.nombre} (Talla: ${variant.talla ?? 'Única'}, Color: ${variant.color ?? 'Único'}). Disponible estimado: ${available}.`,
          );
          continue;
        }

        const unitPrice = item.precio_unitario ?? Number(variant.precio ?? product.precio_final ?? product.precio ?? 0);
        const subtotalLine = unitPrice * item.cantidad;
        totalAmount += subtotalLine;

        lines.push({
          uuid_venta_offline: uuid,
          id_variante_producto: variant.id_variante_producto,
          id_producto: product.id_producto,
          producto_nombre: product.nombre,
          sku: variant.sku,
          id_talla: variant.id_talla,
          talla: variant.talla || 'Única',
          id_color: variant.id_color,
          color: variant.color || 'Único',
          cantidad: item.cantidad,
          precio_unitario: unitPrice,
          descuento_unitario: 0,
          subtotal_linea: subtotalLine,
        });
      }

      if (errors.length > 0) {
        return fail('No se pudo registrar la compra offline por errores de validación.', errors);
      }

      const clients = await this.storage.getClients(empresaId, userId);
      const matchedClient = clients.find((c) => c.id_usuario === userId);
      const resolvedClientId = matchedClient ? matchedClient.id_cliente : null;

      // Generar ID de venta local entero en rango seguro (90000000 - 99999999)
      let hash = 0;
      for (let i = 0; i < uuid.length; i++) {
        hash = (Math.imul(31, hash) + uuid.charCodeAt(i)) | 0;
      }
      const localSaleId = input.idVentaLocal ?? (90000000 + (Math.abs(hash) % 9999999));
      const saleNumber = input.numeroVentaLocal ?? `DIG-LOC-${uuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`;
      const nowIso = now.toISOString();


      const purchase: OfflinePurchaseLocal = {
        uuid_venta_offline: uuid,
        numero_venta_local: saleNumber,
        id_venta_local: localSaleId,
        id_empresa: empresaId,
        id_usuario: userId,
        id_cliente: resolvedClientId,
        id_sucursal: idSucursal,
        canal: 'DIGITAL',
        moneda: 'BOB',
        subtotal: totalAmount,
        descuento_total: 0,
        total: totalAmount,
        medio_pago: medioPago,
        pago_simulado: true,
        referencia_pago_local: `SIM-${medioPago}-${uuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`,
        estado_pago: 'PENDIENTE_VALIDACION',
        estado: 'REGISTRADA_LOCAL',
        fecha_venta_offline: nowIso,
        created_at: nowIso,
        sucursal_nombre: branch?.nombre ?? `Sucursal #${idSucursal}`,
        sucursal_direccion: branch?.direccion,
        cliente_nombre: `${user.nombre ?? ''} ${user.apellido ?? ''}`.trim() || 'Cliente',
        cliente_correo: user.correo ?? null,
        observaciones: input.observaciones ?? null,
      };

      const queueItem: OfflineSyncQueueItem = {
        uuid_operacion: `op-compra-${uuid}`,
        tipo_operacion: 'COMPRA',
        uuid_entidad: uuid,
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_venta_offline: uuid,
          canal: 'DIGITAL',
          id_sucursal: idSucursal,
          id_cliente: resolvedClientId,
          detalles: lines.map((line) => ({
            id_variante_producto: line.id_variante_producto,
            id_producto: line.id_producto,
            sku: line.sku,
            cantidad: line.cantidad,
            precio_unitario: line.precio_unitario,
            descuento_unitario: 0,
            subtotal_linea: line.subtotal_linea,
          })),
          subtotal: totalAmount,
          descuento_total: 0,
          total: totalAmount,
          moneda: 'BOB',
          medio_pago: medioPago,
          pago_simulado: true,
          referencia_pago_local: purchase.referencia_pago_local,
          fecha_venta_offline: nowIso,
          observaciones: input.observaciones ?? null,
        },
        reintentos: 0,
        ultimo_error: null,
        created_at: nowIso,
        updated_at: nowIso,
      };

      await this.storage.saveOfflinePurchaseAtomic(empresaId, userId, purchase, lines, queueItem);

      const receipt = this.toPurchaseReceipt(purchase, lines, branch);
      return {
        success: true,
        uuid_venta_offline: uuid,
        id_venta_local: localSaleId,
        numero_venta_local: saleNumber,
        receipt,
        message: 'Compra y pago electrónico simulado guardados en modo offline.',
        alreadyStored: false,
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido';
      return fail(`No se pudo guardar la compra en este dispositivo: ${msg}`);
    }
  }

  /**
   * Obtiene el comprobante provisional de una compra digital registrada offline por su ID o UUID.
   */
  async getOfflinePurchaseReceipt(
    idOrUuid: number | string,
    options?: { onlyConfirmedPayment?: boolean },
  ): Promise<OfflinePurchaseReceiptData | null> {
    const user = this.session.getUser();
    if (!user) return null;
    let empresaId = this.resolveEffectiveCompanyId();
    if (!empresaId) {
      empresaId = await this.findCompanyIdFromDatabases(user.id_usuario);
      if (empresaId) {
        this.saveUserCompanyFallback(user.id_usuario, empresaId);
      }
    }
    if (!empresaId) return null;

    try {
      const purchases = await this.storage.getOfflinePurchases(empresaId, user.id_usuario);
      const isNum = typeof idOrUuid === 'number' || /^[1-9]\d*$/.test(String(idOrUuid));
      const targetNum = isNum ? Number(idOrUuid) : NaN;
      const targetStr = String(idOrUuid);

      const purchase = purchases.find((p) =>
        isNum
          ? p.id_venta_local === targetNum || p.uuid_venta_offline === targetStr
          : p.uuid_venta_offline === targetStr || p.numero_venta_local === targetStr,
      );

      if (!purchase) return null;
      if (options?.onlyConfirmedPayment && purchase.pago_confirmado_local === false) {
        return null;
      }

      const [details, branches] = await Promise.all([
        this.storage.getOfflinePurchaseDetails(empresaId, user.id_usuario, purchase.uuid_venta_offline),
        this.storage.getBranches(empresaId, user.id_usuario),
      ]);
      const branch = branches.find((b) => b.id_sucursal === purchase.id_sucursal);
      return this.toPurchaseReceipt(purchase, details, branch);
    } catch {
      return null;
    }
  }

  /**
   * Obtiene la lista de compras del cliente pendientes de sincronización.
   */
  async getPendingClientPurchases(): Promise<OfflinePurchaseReceiptData[]> {
    const user = this.session.getUser();
    const empresaId = await this.resolveCompanyIdAsync(user?.id_usuario);
    if (!user || !empresaId) return [];

    try {
      const [purchases, details, branches] = await Promise.all([
        this.storage.getOfflinePurchases(empresaId, user.id_usuario),
        this.storage.getOfflinePurchaseDetails(empresaId, user.id_usuario),
        this.storage.getBranches(empresaId, user.id_usuario),
      ]);

      const branchMap = new Map(branches.map((b) => [b.id_sucursal, b]));
      return purchases
        .filter((p) => p.estado === 'REGISTRADA_LOCAL' || p.estado === 'PENDIENTE_VALIDACION' || p.estado === 'ENVIADA')
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((p) => {
          const pDetails = details.filter((d) => d.uuid_venta_offline === p.uuid_venta_offline);
          return this.toPurchaseReceipt(p, pDetails, branchMap.get(p.id_sucursal));
        });
    } catch {
      return [];
    }
  }

  /**
   * PK08 - CU11: Registra localmente (sin HTTP) la venta directa del CAJERO en el POS (/staff/ventas/nueva).
   * Valida disponibilidad de stock local en la sucursal seleccionada deduciendo reservas y ventas offline previas,
   * calcula importes y descuentos locales, genera UUID idempotente, guarda cabecera, líneas, pago y operación
   * pendiente ('VENTA') de forma atómica en IndexedDB.
   * Admite medios de pago EFECTIVO, QR y TARJETA (estos dos últimos simulados con disclaimer explícito).
   */
  async registerCashierOfflineSale(
    input: CashierOfflineSaleInput,
  ): Promise<CashierOfflineSaleResult> {
    const fail = (message: string, errors: string[] = []): CashierOfflineSaleResult => ({
      success: false,
      uuid_venta_offline: input.uuid,
      id_venta_local: 0,
      numero_venta_local: '',
      receipt: null,
      message,
      errors: errors.length ? errors : [message],
      alreadyStored: false,
    });

    const user = this.session.getUser();
    let empresaId = this.resolveEffectiveCompanyId();
    if (user && !empresaId) {
      empresaId = await this.findCompanyIdFromDatabases(user.id_usuario);
      if (empresaId) {
        this.saveUserCompanyFallback(user.id_usuario, empresaId);
      }
    }
    if (!user || !empresaId) {
      return fail('Sesión no válida. Inicia sesión nuevamente.');
    }
    const staffRoles = new Set(['CAJERO', 'ADMINISTRADOR', 'ADMIN', 'ENCARGADO']);
    if (!staffRoles.has(user.rol.toUpperCase())) {
      return fail('Solo el personal autorizado de tienda puede registrar ventas desde el POS.');
    }

    const userId = user.id_usuario;
    const now = input.now ?? new Date();
    const { uuid, idSucursal, medioPago, items } = input;

    try {
      // Idempotencia: si ya existe una venta con este UUID o idVentaLocal, actualizar su medio de pago si se está confirmando el cobro o retornar el comprobante existente
      const existing = (await this.storage.getOfflinePurchases(empresaId, userId)).find(
        (row) =>
          row.uuid_venta_offline === uuid ||
          (input.idVentaLocal !== undefined && row.id_venta_local === input.idVentaLocal),
      );
      if (existing) {
        const details = await this.storage.getOfflinePurchaseDetails(
          empresaId,
          userId,
          existing.uuid_venta_offline,
        );
        const branches = await this.storage.getBranches(empresaId, userId);
        const branch = branches.find((b) => b.id_sucursal === existing.id_sucursal);

        if (
          input.confirmPayment &&
          (existing.medio_pago !== medioPago || existing.pago_confirmado_local === false)
        ) {
          const existingUuid = existing.uuid_venta_offline;
          const isSimulated = medioPago !== 'EFECTIVO';
          const refPago = isSimulated
            ? `SIM-${medioPago}-${existingUuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`
            : `LOC-EFECTIVO-${existingUuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`;
          const estadoPago = medioPago === 'EFECTIVO' ? 'APROBADO' : 'PENDIENTE_VALIDACION';
          const nowIso = now.toISOString();

          const updatedSale: OfflinePurchaseLocal = {
            ...existing,
            medio_pago: medioPago,
            pago_simulado: isSimulated,
            referencia_pago_local: refPago,
            estado_pago: estadoPago,
            pago_confirmado_local: true,
            updated_at: nowIso,
          };

          const queueItems = await this.storage.getOfflineQueue(empresaId, userId);
          const existingQueue = queueItems.find((q) => q.uuid_entidad === existingUuid);
          const updatedQueueItem: OfflineSyncQueueItem = existingQueue
            ? {
                ...existingQueue,
                payload: {
                  ...(existingQueue.payload ?? {}),
                  medio_pago: medioPago,
                  pago_simulado: isSimulated,
                  referencia_pago_local: refPago,
                },
                updated_at: nowIso,
              }
            : {
                uuid_operacion: `op-${existingUuid}`,
                tipo_operacion: 'VENTA',
                uuid_entidad: existingUuid,
                estado: 'REGISTRADA_LOCAL',
                payload: {
                  uuid_venta_offline: existingUuid,
                  canal: 'PRESENCIAL',
                  id_sucursal: existing.id_sucursal,
                  id_cliente: existing.id_cliente ?? null,
                  id_reserva: existing.id_reserva ?? null,
                  detalles: details.map((line) => ({
                    id_variante_producto: line.id_variante_producto,
                    id_producto: line.id_producto,
                    sku: line.sku,
                    cantidad: line.cantidad,
                    precio_unitario: line.precio_unitario,
                    descuento_unitario: line.descuento_unitario,
                    subtotal_linea: line.subtotal_linea,
                  })),
                  subtotal: existing.subtotal,
                  descuento_total: existing.descuento_total,
                  total: existing.total,
                  moneda: 'BOB',
                  medio_pago: medioPago,
                  pago_simulado: isSimulated,
                  referencia_pago_local: refPago,
                  fecha_venta_offline: existing.fecha_venta_offline,
                  observaciones: existing.observaciones ?? null,
                },
                reintentos: 0,
                ultimo_error: null,
                created_at: existing.created_at,
                updated_at: nowIso,
              };

          await this.storage.saveOfflinePurchaseAtomic(
            empresaId,
            userId,
            updatedSale,
            details,
            updatedQueueItem,
            false,
          );

          return {
            success: true,
            uuid_venta_offline: updatedSale.uuid_venta_offline,
            id_venta_local: updatedSale.id_venta_local,
            numero_venta_local: updatedSale.numero_venta_local,
            receipt: this.toPurchaseReceipt(updatedSale, details, branch),
            message: 'Venta presencial registrada de forma atómica en modo offline.',
            alreadyStored: false,
          };
        }

        return {
          success: true,
          uuid_venta_offline: existing.uuid_venta_offline,
          id_venta_local: existing.id_venta_local,
          numero_venta_local: existing.numero_venta_local,
          receipt: this.toPurchaseReceipt(existing, details, branch),
          message: 'Venta presencial recuperada de almacenamiento local (operación idempotente).',
          alreadyStored: true,
        };
      }

      let reservation: OfflineReservationLocal | null = null;
      let resDetails: OfflineReservationDetailLocal[] = [];

      if (input.idReserva) {
        const purchases = await this.storage.getOfflinePurchases(empresaId, userId);
        const dup = purchases.find(
          (p) => p.id_reserva === input.idReserva && p.uuid_venta_offline !== uuid,
        );
        if (dup) {
          return fail('Esta reserva ya tiene una venta registrada.');
        }

        const reservations = await this.storage.getOfflineReservations(empresaId, userId);
        reservation =
          reservations.find(
            (r) =>
              r.id_reserva === input.idReserva ||
              hashReservationUuidToId(r.uuid_reserva_offline) === input.idReserva,
          ) ?? null;

        if (!reservation) {
          return fail('La reserva asociada no fue encontrada en almacenamiento offline.');
        }

        const resState = reservation.estado === 'REGISTRADA_LOCAL' ? 'PENDIENTE' : reservation.estado;
        if (resState !== 'ATENDIDA') {
          return fail(`La reserva debe estar ATENDIDA para procesar su venta. Estado actual: ${resState}.`);
        }

        if (reservation.id_sucursal !== idSucursal) {
          return fail('La reserva no pertenece a la sucursal de la venta.');
        }

        resDetails = await this.storage.getOfflineReservationDetails(
          empresaId,
          userId,
          reservation.uuid_reserva_offline,
        );
      }

      const [summary, branches, products, variants, stock, pendingMap] = await Promise.all([
        this.storage.getStoredPackageSummary(empresaId, userId),
        this.storage.getBranches(empresaId, userId),
        this.storage.getCatalogProducts(empresaId, userId),
        this.storage.getVariants(empresaId, userId),
        this.storage.getInventory(empresaId, userId),
        this.storage.getPendingReservedQuantities(empresaId, userId),
      ]);

      const errors: string[] = [];
      if (!summary) {
        return fail('No hay datos offline preparados en este dispositivo.');
      }
      const branch = branches.find((b) => b.id_sucursal === idSucursal);
      if (!branch || !branch.estado) {
        errors.push('La sucursal seleccionada no está disponible offline.');
      }
      if (!items || items.length === 0) {
        errors.push('No hay prendas seleccionadas para la venta.');
      }

      const lines: OfflinePurchaseDetailLocal[] = [];
      let subtotalTotal = 0;
      let totalDiscount = 0;

      for (const item of items) {
        const variant = variants.find((v) => v.id_variante_producto === item.id_variante_producto);
        const product = products.find((p) => p.id_producto === variant?.id_producto);
        if (!variant || !variant.estado || !product || !product.estado) {
          errors.push(`El producto o variante #${item.id_variante_producto} no está disponible offline.`);
          continue;
        }
        if (!Number.isInteger(item.cantidad) || item.cantidad < 1) {
          errors.push(`Cantidad inválida para ${product.nombre}.`);
          continue;
        }

        if (input.idReserva && reservation) {
          const resItem = resDetails.find((d) => d.id_variante_producto === item.id_variante_producto);
          if (!resItem) {
            errors.push(`La variante #${item.id_variante_producto} no pertenece a la reserva.`);
            continue;
          }
          if (item.cantidad > resItem.cantidad) {
            errors.push(
              `La cantidad solicitada para ${product.nombre} (${item.cantidad}) supera la cantidad reservada (${resItem.cantidad}).`,
            );
            continue;
          }
        } else {
          const entry = stock.find(
            (s) => s.id_sucursal === idSucursal && s.id_variante_producto === item.id_variante_producto,
          );
          const pending = pendingMap.get(`${idSucursal}_${item.id_variante_producto}`) ?? 0;
          const available = Math.max(0, (entry?.stock_disponible ?? 0) - pending);

          if (item.cantidad > available) {
            errors.push(
              `Stock offline insuficiente para ${product.nombre} (Talla: ${variant.talla ?? 'Única'}, Color: ${variant.color ?? 'Único'}). Disponible estimado: ${available}.`,
            );
            continue;
          }
        }

        const resItem =
          input.idReserva && reservation
            ? resDetails.find((d) => d.id_variante_producto === item.id_variante_producto)
            : null;
        const unitPrice =
          item.precio_unitario ??
          Number(resItem?.precio_referencial ?? variant.precio ?? product.precio_final ?? product.precio ?? 0);
        const discountUnit = item.descuento_unitario ?? 0;
        const subtotalLine = (unitPrice - discountUnit) * item.cantidad;

        subtotalTotal += unitPrice * item.cantidad;
        totalDiscount += discountUnit * item.cantidad;

        lines.push({
          uuid_venta_offline: uuid,
          id_variante_producto: variant.id_variante_producto,
          id_producto: product.id_producto,
          producto_nombre: product.nombre,
          sku: variant.sku,
          id_talla: variant.id_talla,
          talla: variant.talla || 'Única',
          id_color: variant.id_color,
          color: variant.color || 'Único',
          cantidad: item.cantidad,
          precio_unitario: unitPrice,
          descuento_unitario: discountUnit,
          subtotal_linea: subtotalLine,
        });
      }

      if (errors.length > 0) {
        return fail('No se pudo registrar la venta presencial por errores de validación.', errors);
      }

      const totalAmount = subtotalTotal - totalDiscount;

      // Generar ID de venta local entero en rango seguro (80000000 - 89999999)
      let hash = 0;
      for (let i = 0; i < uuid.length; i++) {
        hash = (Math.imul(31, hash) + uuid.charCodeAt(i)) | 0;
      }
      const localSaleId = 80000000 + (Math.abs(hash) % 9999999);
      const saleNumber = `VTA-LOC-${uuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`;
      const nowIso = now.toISOString();

      const isSimulated = medioPago !== 'EFECTIVO';
      const refPago = isSimulated
        ? `SIM-${medioPago}-${uuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`
        : `LOC-EFECTIVO-${uuid.replace(/-/g, '').slice(0, 8).toUpperCase()}`;
      const estadoPago = medioPago === 'EFECTIVO' ? 'APROBADO' : 'PENDIENTE_VALIDACION';

      const clientName =
        input.idCliente && input.idCliente > 0
          ? undefined
          : reservation?.cliente_nombre
            ? `${reservation.cliente_nombre} ${reservation.cliente_apellido ?? ''}`.trim()
            : undefined;
      const clientEmail = reservation?.cliente_correo ?? undefined;

      const sale: OfflinePurchaseLocal = {
        uuid_venta_offline: uuid,
        numero_venta_local: saleNumber,
        id_venta_local: localSaleId,
        id_empresa: empresaId,
        id_usuario: userId,
        id_cliente: input.idCliente ?? reservation?.id_cliente ?? null,
        id_reserva: input.idReserva ?? null,
        id_sucursal: idSucursal,
        canal: 'PRESENCIAL',
        moneda: 'BOB',
        subtotal: subtotalTotal,
        descuento_total: totalDiscount,
        total: totalAmount,
        medio_pago: medioPago,
        pago_simulado: isSimulated,
        referencia_pago_local: refPago,
        estado_pago: estadoPago,
        pago_confirmado_local: input.confirmPayment ?? true,
        estado: 'REGISTRADA_LOCAL',
        fecha_venta_offline: nowIso,
        created_at: nowIso,
        sucursal_nombre: branch!.nombre,
        sucursal_direccion: branch!.direccion,
        cliente_nombre: clientName,
        cliente_correo: clientEmail,
        cajero_nombre: `${user.nombre ?? ''} ${user.apellido ?? ''}`.trim() || 'Cajero',
        observaciones: input.observaciones ?? null,
      };

      const queueItem: OfflineSyncQueueItem = {
        uuid_operacion: `op-${uuid}`,
        tipo_operacion: 'VENTA',
        uuid_entidad: uuid,
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_venta_offline: uuid,
          canal: 'PRESENCIAL',
          id_sucursal: idSucursal,
          id_cliente: input.idCliente ?? reservation?.id_cliente ?? null,
          id_reserva: input.idReserva ?? null,
          codigo_reserva: reservation?.codigo_local ?? null,
          uuid_reserva_offline: reservation?.uuid_reserva_offline ?? null,
          detalles: lines.map((line) => ({
            id_variante_producto: line.id_variante_producto,
            id_producto: line.id_producto,
            sku: line.sku,
            cantidad: line.cantidad,
            precio_unitario: line.precio_unitario,
            descuento_unitario: line.descuento_unitario,
            subtotal_linea: line.subtotal_linea,
          })),
          subtotal: subtotalTotal,
          descuento_total: totalDiscount,
          total: totalAmount,
          moneda: 'BOB',
          medio_pago: medioPago,
          pago_simulado: isSimulated,
          referencia_pago_local: refPago,
          fecha_venta_offline: nowIso,
          observaciones: input.observaciones ?? null,
        },
        reintentos: 0,
        ultimo_error: null,
        created_at: nowIso,
        updated_at: nowIso,
      };

      await this.storage.saveOfflinePurchaseAtomic(empresaId, userId, sale, lines, queueItem, false);

      const receipt = this.toPurchaseReceipt(sale, lines, branch);
      return {
        success: true,
        uuid_venta_offline: uuid,
        id_venta_local: localSaleId,
        numero_venta_local: saleNumber,
        receipt,
        message: 'Venta presencial registrada de forma atómica en modo offline.',
        alreadyStored: false,
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error desconocido';
      return fail(`No se pudo guardar la venta presencial en este dispositivo: ${msg}`);
    }
  }

  private toPurchaseReceipt(
    purchase: OfflinePurchaseLocal,
    details: OfflinePurchaseDetailLocal[],
    branch?: OfflineBranchData,
  ): OfflinePurchaseReceiptData {
    const isPresencial = purchase.canal === 'PRESENCIAL';
    const isEfectivo = purchase.medio_pago === 'EFECTIVO';
    let advertencia =
      'COMPROBANTE PROVISIONAL OFFLINE: Esta compra digital fue guardada en el dispositivo y se encuentra pendiente de sincronización. El pago electrónico fue simulado y NO representa un débito bancario real hasta su confirmación.';

    if (isPresencial) {
      if (isEfectivo) {
        advertencia =
          'COMPROBANTE PROVISIONAL POS OFFLINE: Venta presencial registrada sin conexión. El cobro en efectivo fue recibido en caja y la venta se consolidará en el servidor al sincronizar.';
      } else {
        advertencia =
          'COMPROBANTE PROVISIONAL POS OFFLINE: Venta presencial con pago electrónico SIMULADO en modo offline. No constituye confirmación bancaria externa y se encuentra pendiente de validación y sincronización.';
      }
    }

    return {
      uuid_venta_offline: purchase.uuid_venta_offline,
      numero_venta_local: purchase.numero_venta_local,
      id_venta_local: purchase.id_venta_local,
      fecha_registro: purchase.fecha_venta_offline,
      canal: purchase.canal,
      sucursal: {
        id_sucursal: purchase.id_sucursal,
        nombre: purchase.sucursal_nombre ?? branch?.nombre ?? `Sucursal #${purchase.id_sucursal}`,
        direccion: purchase.sucursal_direccion ?? branch?.direccion,
      },
      cliente: purchase.cliente_nombre
        ? {
            nombre: purchase.cliente_nombre,
            correo: purchase.cliente_correo ?? undefined,
          }
        : null,
      cajero: purchase.cajero_nombre
        ? {
            id_usuario: purchase.id_usuario,
            nombre: purchase.cajero_nombre,
          }
        : null,
      detalles: details,
      subtotal: purchase.subtotal,
      descuento_total: purchase.descuento_total,
      total: purchase.total,
      moneda: 'BOB',
      medio_pago: purchase.medio_pago,
      pago_simulado: purchase.pago_simulado,
      referencia_pago: purchase.referencia_pago_local,
      estado_venta: purchase.estado_pago === 'APROBADO' ? 'COMPLETADA' : 'PENDIENTE',
      estado_pago: purchase.estado_pago,
      comprobante_provisional: true,
      mensaje_advertencia: advertencia,
    };
  }

  saveUserCompanyFallback(userId: number, empresaId: number): void {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(`fashionstore_offline_company_u${userId}`, String(empresaId));
      }
    } catch {
      // Ignorar si localStorage no está disponible
    }
  }

  private readUserCompanyFallback(userId: number): number | null {
    try {
      if (typeof localStorage === 'undefined') return null;
      const raw = localStorage.getItem(`fashionstore_offline_company_u${userId}`);
      const parsed = Number(raw);
      return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
    } catch {
      return null;
    }
  }
}
