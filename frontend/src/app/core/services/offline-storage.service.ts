import { Injectable } from '@angular/core';
import {
  OfflineBranchData,
  OfflineBranchStockItem,
  OfflineCategoryData,
  OfflineClientData,
  OfflineColorData,
  OfflinePackageMetadata,
  OfflinePackageResponse,
  OfflineProductData,
  OfflineProductDetail,
  OfflineReservationDetailLocal,
  OfflineReservationLocal,
  OfflineSizeData,
  OfflineStockData,
  OfflineStoredSummary,
  OfflineSyncQueueItem,
  OfflineVariantData,
  OfflineVariantDetailItem,
  OfflineCartItemLocal,
  OfflinePurchaseLocal,
  OfflinePurchaseDetailLocal,
  OfflineCodeLinkItem,
  OfflineOperationResolutionResult,
  OfflineSyncOperationResult,
} from '../models/offline.model';

const DB_VERSION = 3;

const PACKAGE_STORE_NAMES = [
  'metadata',
  'sucursales',
  'categorias',
  'tallas',
  'colores',
  'productos',
  'variantes',
  'existencias',
  'clientes',
] as const;

const CU10_STORE_NAMES = [
  'reservas_offline',
  'detalles_reserva_offline',
  'cola_sincronizacion_offline',
] as const;

const CU11_STORE_NAMES = [
  'carrito_offline',
  'compras_offline',
  'detalles_compra_offline',
] as const;

const STORE_NAMES = [...PACKAGE_STORE_NAMES, ...CU10_STORE_NAMES, ...CU11_STORE_NAMES] as const;

type StoreName = (typeof STORE_NAMES)[number];
type PackageStoreName = (typeof PACKAGE_STORE_NAMES)[number];

@Injectable({ providedIn: 'root' })
export class OfflineStorageService {
  /**
   * Genera el nombre de la base de datos IndexedDB garantizando aislamiento
   * estricto por empresa y usuario sin mezclar datos multi-tenant.
   */
  getDatabaseName(empresaId: number, userId: number): string {
    return `fashionstore_offline_e${empresaId}_u${userId}`;
  }

  /**
   * Abre o inicializa la base de datos IndexedDB con sus almacenes tipados.
   */
  openDatabase(empresaId: number, userId: number): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('IndexedDB no está disponible en este entorno.'));
        return;
      }

      const dbName = this.getDatabaseName(empresaId, userId);
      const request = indexedDB.open(dbName, DB_VERSION);

      request.onupgradeneeded = () => {
        const db = request.result;

        // Stores CU08 / CU09
        if (!db.objectStoreNames.contains('metadata')) {
          db.createObjectStore('metadata', { keyPath: 'key' });
        }
        if (!db.objectStoreNames.contains('sucursales')) {
          db.createObjectStore('sucursales', { keyPath: 'id_sucursal' });
        }
        if (!db.objectStoreNames.contains('categorias')) {
          db.createObjectStore('categorias', { keyPath: 'id_categoria' });
        }
        if (!db.objectStoreNames.contains('tallas')) {
          db.createObjectStore('tallas', { keyPath: 'id_talla' });
        }
        if (!db.objectStoreNames.contains('colores')) {
          db.createObjectStore('colores', { keyPath: 'id_color' });
        }
        if (!db.objectStoreNames.contains('productos')) {
          db.createObjectStore('productos', { keyPath: 'id_producto' });
        }
        if (!db.objectStoreNames.contains('variantes')) {
          const varStore = db.createObjectStore('variantes', {
            keyPath: 'id_variante_producto',
          });
          varStore.createIndex('id_producto', 'id_producto', { unique: false });
        }
        if (!db.objectStoreNames.contains('existencias')) {
          const stockStore = db.createObjectStore('existencias', {
            keyPath: 'id_inventario_sucursal',
          });
          stockStore.createIndex('id_sucursal', 'id_sucursal', { unique: false });
          stockStore.createIndex('id_variante_producto', 'id_variante_producto', {
            unique: false,
          });
        }
        if (!db.objectStoreNames.contains('clientes')) {
          db.createObjectStore('clientes', { keyPath: 'id_cliente' });
        }

        // Stores CU10: Reservas Offline y Cola de Sincronización
        if (!db.objectStoreNames.contains('reservas_offline')) {
          const resStore = db.createObjectStore('reservas_offline', {
            keyPath: 'uuid_reserva_offline',
          });
          resStore.createIndex('id_sucursal', 'id_sucursal', { unique: false });
          resStore.createIndex('id_cliente', 'id_cliente', { unique: false });
          resStore.createIndex('estado', 'estado', { unique: false });
          resStore.createIndex('created_at', 'created_at', { unique: false });
        }
        if (!db.objectStoreNames.contains('detalles_reserva_offline')) {
          const detStore = db.createObjectStore('detalles_reserva_offline', {
            keyPath: 'id_detalle_local',
            autoIncrement: true,
          });
          detStore.createIndex('uuid_reserva_offline', 'uuid_reserva_offline', { unique: false });
          detStore.createIndex('id_variante_producto', 'id_variante_producto', { unique: false });
        }
        if (!db.objectStoreNames.contains('cola_sincronizacion_offline')) {
          const colaStore = db.createObjectStore('cola_sincronizacion_offline', {
            keyPath: 'uuid_operacion',
          });
          colaStore.createIndex('tipo_operacion', 'tipo_operacion', { unique: false });
          colaStore.createIndex('estado', 'estado', { unique: false });
          colaStore.createIndex('created_at', 'created_at', { unique: false });
        }

        // Stores CU11: Carrito Offline y Compras Digitales Offline
        if (!db.objectStoreNames.contains('carrito_offline')) {
          db.createObjectStore('carrito_offline', {
            keyPath: 'id_variante_producto',
          });
        }
        if (!db.objectStoreNames.contains('compras_offline')) {
          const buyStore = db.createObjectStore('compras_offline', {
            keyPath: 'uuid_venta_offline',
          });
          buyStore.createIndex('id_sucursal', 'id_sucursal', { unique: false });
          buyStore.createIndex('id_cliente', 'id_cliente', { unique: false });
          buyStore.createIndex('id_venta_local', 'id_venta_local', { unique: false });
          buyStore.createIndex('estado', 'estado', { unique: false });
          buyStore.createIndex('created_at', 'created_at', { unique: false });
        }
        if (!db.objectStoreNames.contains('detalles_compra_offline')) {
          const buyDetStore = db.createObjectStore('detalles_compra_offline', {
            keyPath: 'id_detalle_local',
            autoIncrement: true,
          });
          buyDetStore.createIndex('uuid_venta_offline', 'uuid_venta_offline', { unique: false });
          buyDetStore.createIndex('id_variante_producto', 'id_variante_producto', { unique: false });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error('Error al abrir IndexedDB.'));
    });
  }

  /**
   * Guarda de forma atómica el paquete offline completo dentro de una única transacción
   * de lectura/escritura en los almacenes del catálogo. Si ocurre un fallo en cualquier almacén,
   * IndexedDB revierte automáticamente toda la transacción, preservando los datos previos válidos
   * y sin afectar las reservas locales registradas en CU10.
   */
  async savePackageAtomic(
    empresaId: number,
    userId: number,
    pkg: OfflinePackageResponse,
  ): Promise<void> {
    if (!pkg || !pkg.metadata || pkg.metadata.id_empresa !== empresaId) {
      throw new Error('El paquete recibido es inválido o no corresponde a la empresa activa.');
    }

    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const tx = db.transaction(PACKAGE_STORE_NAMES as unknown as string[], 'readwrite');

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Fallo en transacción atómica de IndexedDB');
        db.close();
        reject(error);
      };

      tx.onabort = () => {
        const error = tx.error ?? new Error('Transacción abortada: se conservaron datos anteriores.');
        db.close();
        reject(error);
      };

      // 1. Metadata
      const metaStore = tx.objectStore('metadata');
      metaStore.clear();
      metaStore.put({
        key: 'current_package',
        metadata: pkg.metadata,
        savedAt: new Date().toISOString(),
      });

      // 2. Sucursales
      const branchStore = tx.objectStore('sucursales');
      branchStore.clear();
      for (const item of pkg.sucursales) {
        branchStore.put(item);
      }

      // 3. Categorías
      const catStore = tx.objectStore('categorias');
      catStore.clear();
      for (const item of pkg.categorias) {
        catStore.put(item);
      }

      // 4. Tallas
      const sizeStore = tx.objectStore('tallas');
      sizeStore.clear();
      for (const item of pkg.tallas) {
        sizeStore.put(item);
      }

      // 5. Colores
      const colorStore = tx.objectStore('colores');
      colorStore.clear();
      for (const item of pkg.colores) {
        colorStore.put(item);
      }

      // 6. Productos
      const prodStore = tx.objectStore('productos');
      prodStore.clear();
      for (const item of pkg.productos) {
        prodStore.put(item);
      }

      // 7. Variantes
      const varStore = tx.objectStore('variantes');
      varStore.clear();
      for (const item of pkg.variantes) {
        varStore.put(item);
      }

      // 8. Existencias
      const stockStore = tx.objectStore('existencias');
      stockStore.clear();
      for (const item of pkg.existencias) {
        stockStore.put(item);
      }

      // 9. Clientes (mínimos, sin contraseñas ni tokens)
      const clientStore = tx.objectStore('clientes');
      clientStore.clear();
      for (const item of pkg.clientes) {
        const sanitizedClient = {
          id_cliente: item.id_cliente,
          id_usuario: item.id_usuario,
          nombre: item.nombre,
          apellido: item.apellido,
          correo: item.correo ?? null,
          telefono: item.telefono ?? null,
        };
        clientStore.put(sanitizedClient);
      }
    });
  }

  /**
   * Lee el resumen del paquete almacenado localmente en IndexedDB.
   * Funciona 100% offline sin necesidad de conexión de red ni llamadas HTTP.
   */
  async getStoredPackageSummary(
    empresaId: number,
    userId: number,
  ): Promise<OfflineStoredSummary | null> {
    try {
      const db = await this.openDatabase(empresaId, userId);

      const metadataEntry = await new Promise<{
        key: string;
        metadata: OfflinePackageMetadata;
        savedAt: string;
      } | null>((resolve, reject) => {
        const tx = db.transaction('metadata', 'readonly');
        const store = tx.objectStore('metadata');
        const req = store.get('current_package');
        req.onsuccess = () => resolve(req.result ?? null);
        req.onerror = () => reject(req.error);
      });

      if (!metadataEntry || !metadataEntry.metadata) {
        db.close();
        return null;
      }

      const countStore = (name: StoreName): Promise<number> =>
        new Promise((resolve, reject) => {
          const tx = db.transaction(name, 'readonly');
          const store = tx.objectStore(name);
          const req = store.count();
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
        });

      const [
        sucursales,
        categorias,
        tallas,
        colores,
        productos,
        variantes,
        existencias,
        clientes,
      ] = await Promise.all([
        countStore('sucursales'),
        countStore('categorias'),
        countStore('tallas'),
        countStore('colores'),
        countStore('productos'),
        countStore('variantes'),
        countStore('existencias'),
        countStore('clientes'),
      ]);

      db.close();

      const now = new Date();
      const expirationDate = new Date(metadataEntry.metadata.valido_hasta);
      const isExpired = now.getTime() > expirationDate.getTime();

      let timeRemainingText = 'Expirado';
      if (!isExpired) {
        const diffMs = expirationDate.getTime() - now.getTime();
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
        timeRemainingText = `${diffHours}h ${diffMinutes}m restantes`;
      }

      return {
        metadata: metadataEntry.metadata,
        savedAt: metadataEntry.savedAt,
        counts: {
          sucursales,
          categorias,
          tallas,
          colores,
          productos,
          variantes,
          existencias,
          clientes,
        },
        isExpired,
        timeRemainingText,
      };
    } catch {
      return null;
    }
  }

  /**
   * Limpia únicamente los almacenes del paquete de catálogo (metadata, sucursales, categorías,
   * tallas, colores, productos, variantes, existencias y clientes), preservando intactas
   * las reservas, detalles y operaciones pendientes de IndexedDB versión 2.
   */
  async clearDatabase(empresaId: number, userId: number): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);
    return new Promise((resolve, reject) => {
      const tx = db.transaction(PACKAGE_STORE_NAMES as unknown as string[], 'readwrite');
      for (const storeName of PACKAGE_STORE_NAMES) {
        tx.objectStore(storeName).clear();
      }
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        const err = tx.error ?? new Error('No fue posible limpiar los datos de catálogo offline.');
        db.close();
        reject(err);
      };
    });
  }

  /**
   * Consulta genérica de todos los registros de un object store tipado.
   * Funciona 100% offline desde IndexedDB sin realizar solicitudes HTTP.
   */
  async getAllFromStore<T>(
    empresaId: number,
    userId: number,
    storeName: StoreName,
  ): Promise<T[]> {
    try {
      const db = await this.openDatabase(empresaId, userId);
      return new Promise((resolve, reject) => {
        const tx = db.transaction(storeName, 'readonly');
        const store = tx.objectStore(storeName);
        const req = store.getAll();
        req.onsuccess = () => {
          db.close();
          resolve((req.result ?? []) as T[]);
        };
        req.onerror = () => {
          db.close();
          reject(req.error);
        };
      });
    } catch {
      return [];
    }
  }

  /**
   * Obtiene todos los productos del catálogo local en IndexedDB.
   */
  async getCatalogProducts(empresaId: number, userId: number): Promise<OfflineProductData[]> {
    return this.getAllFromStore<OfflineProductData>(empresaId, userId, 'productos');
  }

  /**
   * Obtiene todas las categorías locales en IndexedDB.
   */
  async getCategories(empresaId: number, userId: number): Promise<OfflineCategoryData[]> {
    return this.getAllFromStore<OfflineCategoryData>(empresaId, userId, 'categorias');
  }

  /**
   * Obtiene todas las tallas locales en IndexedDB.
   */
  async getSizes(empresaId: number, userId: number): Promise<OfflineSizeData[]> {
    return this.getAllFromStore<OfflineSizeData>(empresaId, userId, 'tallas');
  }

  /**
   * Obtiene todos los colores locales en IndexedDB.
   */
  async getColors(empresaId: number, userId: number): Promise<OfflineColorData[]> {
    return this.getAllFromStore<OfflineColorData>(empresaId, userId, 'colores');
  }

  /**
   * Obtiene las sucursales autorizadas en IndexedDB.
   */
  async getBranches(empresaId: number, userId: number): Promise<OfflineBranchData[]> {
    return this.getAllFromStore<OfflineBranchData>(empresaId, userId, 'sucursales');
  }

  /**
   * Obtiene todas las variantes locales en IndexedDB.
   */
  async getVariants(empresaId: number, userId: number): Promise<OfflineVariantData[]> {
    return this.getAllFromStore<OfflineVariantData>(empresaId, userId, 'variantes');
  }

  /**
   * Obtiene todas las existencias locales en IndexedDB.
   */
  async getInventory(empresaId: number, userId: number): Promise<OfflineStockData[]> {
    return this.getAllFromStore<OfflineStockData>(empresaId, userId, 'existencias');
  }

  /**
   * Obtiene todos los clientes mínimos locales en IndexedDB.
   */
  async getClients(empresaId: number, userId: number): Promise<OfflineClientData[]> {
    return this.getAllFromStore<OfflineClientData>(empresaId, userId, 'clientes');
  }

  /**
   * Obtiene todas las reservas registradas localmente en IndexedDB.
   */
  async getOfflineReservations(
    empresaId: number,
    userId: number,
  ): Promise<OfflineReservationLocal[]> {
    return this.getAllFromStore<OfflineReservationLocal>(empresaId, userId, 'reservas_offline');
  }

  /**
   * Obtiene los detalles de reservas locales, opcionalmente filtrados por UUID.
   */
  async getOfflineReservationDetails(
    empresaId: number,
    userId: number,
    uuidReserva?: string,
  ): Promise<OfflineReservationDetailLocal[]> {
    const all = await this.getAllFromStore<OfflineReservationDetailLocal>(
      empresaId,
      userId,
      'detalles_reserva_offline',
    );
    if (!uuidReserva) return all;
    return all.filter((d) => d.uuid_reserva_offline === uuidReserva);
  }

  /**
   * Obtiene la cola de sincronización offline local.
   */
  async getOfflineQueue(
    empresaId: number,
    userId: number,
  ): Promise<OfflineSyncQueueItem[]> {
    return this.getAllFromStore<OfflineSyncQueueItem>(
      empresaId,
      userId,
      'cola_sincronizacion_offline',
    );
  }

  /**
   * Guarda de forma atómica una reserva offline, sus líneas de detalle y el registro
   * en la cola de sincronización (Outbox) dentro de una única transacción IndexedDB.
   * Si ocurre un fallo en cualquier almacén o la cuota se agota, se revierte por completo.
   */
  async saveOfflineReservationAtomic(
    empresaId: number,
    userId: number,
    reservation: OfflineReservationLocal,
    details: OfflineReservationDetailLocal[],
    queueItem: OfflineSyncQueueItem,
  ): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        ['reservas_offline', 'detalles_reserva_offline', 'cola_sincronizacion_offline'],
        'readwrite',
      );

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Fallo en transacción atómica de reserva offline');
        db.close();
        reject(error);
      };

      tx.onabort = () => {
        const error =
          tx.error ?? new Error('Transacción abortada: se revirtió el registro de reserva.');
        db.close();
        reject(error);
      };

      // 1. Guardar cabecera de la reserva
      const resStore = tx.objectStore('reservas_offline');
      resStore.put(reservation);

      // 2. Guardar líneas de detalle
      const detStore = tx.objectStore('detalles_reserva_offline');
      for (const item of details) {
        detStore.put(item);
      }

      // 3. Guardar en la cola de sincronización (Outbox)
      const queueStore = tx.objectStore('cola_sincronizacion_offline');
      queueStore.put(queueItem);
    });
  }

  /**
   * Guarda o actualiza un lote de reservas autorizadas del personal y sus líneas de detalle
   * en IndexedDB para disponibilidad offline.
   * Respeta transiciones locales pendientes de sincronización para no sobrescribir estados modificados offline.
   */
  async saveStaffReservations(
    empresaId: number,
    userId: number,
    reservations: OfflineReservationLocal[],
    details: OfflineReservationDetailLocal[] = [],
  ): Promise<void> {
    if (!reservations || reservations.length === 0) return;
    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        ['reservas_offline', 'detalles_reserva_offline', 'cola_sincronizacion_offline'],
        'readwrite',
      );

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Error al guardar reservas de sucursal en IndexedDB');
        db.close();
        reject(error);
      };

      // 1. Leer cola de sincronización para identificar reservas con transiciones locales pendientes
      const queueStore = tx.objectStore('cola_sincronizacion_offline');
      const queueReq = queueStore.getAll();

      queueReq.onsuccess = () => {
        const queueItems = (queueReq.result as OfflineSyncQueueItem[]) || [];
        const pendingEntities = new Set(
          queueItems
            .filter((item) => item.tipo_operacion === 'RESERVA')
            .map((item) => item.uuid_entidad),
        );

        // 2. Guardar reservas que no tengan cambios locales pendientes
        const resStore = tx.objectStore('reservas_offline');
        for (const res of reservations) {
          if (!pendingEntities.has(res.uuid_reserva_offline)) {
            resStore.put(res);
          }
        }

        // 3. Guardar o reemplazar detalles
        if (details.length > 0) {
          const detStore = tx.objectStore('detalles_reserva_offline');
          const detReq = detStore.getAll();
          detReq.onsuccess = () => {
            const existingDetails = (detReq.result as OfflineReservationDetailLocal[]) || [];
            const uuidsToUpdate = new Set(reservations.map((r) => r.uuid_reserva_offline));

            for (const ed of existingDetails) {
              if (uuidsToUpdate.has(ed.uuid_reserva_offline) && ed.id_detalle_local !== undefined) {
                detStore.delete(ed.id_detalle_local);
              }
            }

            for (const d of details) {
              const toInsert = { ...d };
              delete toInsert.id_detalle_local;
              detStore.put(toInsert);
            }
          };
        }
      };
    });
  }

  /**
   * Retorna un mapa con las cantidades reservadas pendientes por sucursal y variante:
   * Clave: `${id_sucursal}_${id_variante_producto}` -> Cantidad total reservada localmente.
   * Considera exclusivamente reservas en estado 'REGISTRADA_LOCAL' o 'ENVIADA'.
   */
  /**
   * Obtiene todos los artículos del carrito offline del cliente almacenados en IndexedDB.
   */
  async getOfflineCartItems(
    empresaId: number,
    userId: number,
  ): Promise<OfflineCartItemLocal[]> {
    return this.getAllFromStore<OfflineCartItemLocal>(empresaId, userId, 'carrito_offline');
  }

  /**
   * Guarda o actualiza un artículo en el carrito offline en IndexedDB.
   */
  async saveOfflineCartItem(
    empresaId: number,
    userId: number,
    item: OfflineCartItemLocal,
  ): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);
    return new Promise((resolve, reject) => {
      const tx = db.transaction('carrito_offline', 'readwrite');
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        const error = tx.error ?? new Error('Error al guardar artículo en carrito offline');
        db.close();
        reject(error);
      };
      tx.objectStore('carrito_offline').put(item);
    });
  }

  async updateOfflineReservationState(
    empresaId: number,
    userId: number,
    reservation: OfflineReservationLocal,
    queueItem?: OfflineSyncQueueItem,
  ): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const stores = queueItem
        ? ['reservas_offline', 'cola_sincronizacion_offline']
        : ['reservas_offline'];
      const tx = db.transaction(stores, 'readwrite');

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Fallo al actualizar estado de reserva offline');
        db.close();
        reject(error);
      };

      const resStore = tx.objectStore('reservas_offline');
      resStore.put(reservation);

      if (queueItem) {
        const queueStore = tx.objectStore('cola_sincronizacion_offline');
        queueStore.put(queueItem);
      }
    });
  }

  /**
   * Elimina un artículo del carrito offline por ID de variante de producto.
   */
  async removeOfflineCartItem(
    empresaId: number,
    userId: number,
    idVarianteProducto: number,
  ): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);
    return new Promise((resolve, reject) => {
      const tx = db.transaction('carrito_offline', 'readwrite');
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        const error = tx.error ?? new Error('Error al eliminar artículo del carrito offline');
        db.close();
        reject(error);
      };
      tx.objectStore('carrito_offline').delete(idVarianteProducto);
    });
  }

  /**
   * Vacía por completo el carrito offline local del cliente.
   */
  async clearOfflineCart(empresaId: number, userId: number): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);
    return new Promise((resolve, reject) => {
      const tx = db.transaction('carrito_offline', 'readwrite');
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        const error = tx.error ?? new Error('Error al vaciar carrito offline');
        db.close();
        reject(error);
      };
      tx.objectStore('carrito_offline').clear();
    });
  }

  /**
   * Obtiene todas las compras digitales registradas localmente en IndexedDB.
   */
  async getOfflinePurchases(
    empresaId: number,
    userId: number,
  ): Promise<OfflinePurchaseLocal[]> {
    return this.getAllFromStore<OfflinePurchaseLocal>(empresaId, userId, 'compras_offline');
  }

  /**
   * Obtiene una compra digital offline por su UUID local.
   */
  async getOfflinePurchaseByUuid(
    empresaId: number,
    userId: number,
    uuid: string,
  ): Promise<OfflinePurchaseLocal | null> {
    const purchases = await this.getOfflinePurchases(empresaId, userId);
    return purchases.find((p) => p.uuid_venta_offline === uuid) ?? null;
  }

  /**
   * Obtiene una compra digital offline por su ID numérico local (para rutas /compra/:id).
   */
  async getOfflinePurchaseByLocalId(
    empresaId: number,
    userId: number,
    idVentaLocal: number,
  ): Promise<OfflinePurchaseLocal | null> {
    const purchases = await this.getOfflinePurchases(empresaId, userId);
    return purchases.find((p) => p.id_venta_local === idVentaLocal) ?? null;
  }

  /**
   * Obtiene los detalles de compras digitales locales, opcionalmente filtrados por UUID.
   */
  async getOfflinePurchaseDetails(
    empresaId: number,
    userId: number,
    uuid?: string,
  ): Promise<OfflinePurchaseDetailLocal[]> {
    const details = await this.getAllFromStore<OfflinePurchaseDetailLocal>(
      empresaId,
      userId,
      'detalles_compra_offline',
    );
    if (!uuid) return details;
    return details.filter((d) => d.uuid_venta_offline === uuid);
  }

  /**
   * Guarda de forma atómica una venta presencial o compra digital offline, sus líneas de detalle,
   * la operación en la cola de sincronización (Outbox) y opcionalmente limpia el carrito offline
   * dentro de una única transacción en IndexedDB.
   */
  async saveOfflinePurchaseAtomic(
    empresaId: number,
    userId: number,
    purchase: OfflinePurchaseLocal,
    details: OfflinePurchaseDetailLocal[],
    queueItem: OfflineSyncQueueItem,
    clearCart = true,
  ): Promise<void> {
    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        [
          'compras_offline',
          'detalles_compra_offline',
          'cola_sincronizacion_offline',
          'carrito_offline',
        ],
        'readwrite',
      );

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Fallo en transacción atómica de compra offline');
        db.close();
        reject(error);
      };

      tx.onabort = () => {
        const error =
          tx.error ?? new Error('Transacción abortada: se revirtió el registro de compra offline.');
        db.close();
        reject(error);
      };

      // 1. Guardar cabecera de la compra / venta presencial
      const buyStore = tx.objectStore('compras_offline');
      buyStore.put(purchase);

      // 2. Guardar líneas de detalle
      const detStore = tx.objectStore('detalles_compra_offline');
      for (const item of details) {
        detStore.put(item);
      }

      // 3. Guardar en la cola de sincronización (Outbox)
      const queueStore = tx.objectStore('cola_sincronizacion_offline');
      queueStore.put(queueItem);

      // 4. Limpiar el carrito offline tras la compra si corresponde (solo cliente digital)
      if (clearCart) {
        const cartStore = tx.objectStore('carrito_offline');
        cartStore.clear();
      }
    });
  }

  async getPendingReservedQuantities(
    empresaId: number,
    userId: number,
  ): Promise<Map<string, number>> {
    try {
      const [reservas, detallesReserva, compras, detallesCompra] = await Promise.all([
        this.getOfflineReservations(empresaId, userId),
        this.getOfflineReservationDetails(empresaId, userId),
        this.getOfflinePurchases(empresaId, userId),
        this.getOfflinePurchaseDetails(empresaId, userId),
      ]);

      const pendingMap = new Map<string, number>(); // uuid -> id_sucursal
      for (const r of reservas) {
        if (r.estado === 'REGISTRADA_LOCAL' || r.estado === 'ENVIADA') {
          pendingMap.set(r.uuid_reserva_offline, r.id_sucursal);
        }
      }

      for (const c of compras) {
        if (
          c.estado === 'REGISTRADA_LOCAL' ||
          c.estado === 'PENDIENTE_VALIDACION' ||
          c.estado === 'ENVIADA'
        ) {
          pendingMap.set(c.uuid_venta_offline, c.id_sucursal);
        }
      }

      const branchVariantQuantities = new Map<string, number>();
      for (const d of detallesReserva) {
        const branchId = pendingMap.get(d.uuid_reserva_offline);
        if (branchId !== undefined) {
          const key = `${branchId}_${d.id_variante_producto}`;
          const current = branchVariantQuantities.get(key) || 0;
          branchVariantQuantities.set(key, current + d.cantidad);
        }
      }

      for (const d of detallesCompra) {
        const branchId = pendingMap.get(d.uuid_venta_offline);
        if (branchId !== undefined) {
          const key = `${branchId}_${d.id_variante_producto}`;
          const current = branchVariantQuantities.get(key) || 0;
          branchVariantQuantities.set(key, current + d.cantidad);
        }
      }

      return branchVariantQuantities;
    } catch {
      return new Map<string, number>();
    }
  }

  /**
   * Construye el detalle integral de un producto offline con sus variantes,
   * precios, imágenes y desglose de existencias por sucursal autorizada,
   * deduciendo de manera transparente las reservas locales pendientes.
   */
  async getProductDetail(
    empresaId: number,
    userId: number,
    productId: number,
  ): Promise<OfflineProductDetail | null> {
    const [products, categories, sizes, colors, variants, allStock, branches, pendingMap] =
      await Promise.all([
        this.getCatalogProducts(empresaId, userId),
        this.getCategories(empresaId, userId),
        this.getSizes(empresaId, userId),
        this.getColors(empresaId, userId),
        this.getVariants(empresaId, userId),
        this.getInventory(empresaId, userId),
        this.getBranches(empresaId, userId),
        this.getPendingReservedQuantities(empresaId, userId),
      ]);

    const product = products.find((p) => p.id_producto === productId);
    if (!product) return null;

    const catMap = new Map(categories.map((c) => [c.id_categoria, c.nombre]));
    const sizeMap = new Map(sizes.map((s) => [s.id_talla, s.nombre]));
    const colorMap = new Map(colors.map((c) => [c.id_color, c]));

    const productVariants = variants.filter((v) => v.id_producto === productId);
    const variantIds = new Set(productVariants.map((v) => v.id_variante_producto));
    const productStock = allStock.filter((s) => variantIds.has(s.id_variante_producto));

    // Desglose de disponibilidad por sucursal para el producto
    const branchStockMap = new Map<number, OfflineBranchStockItem>();
    for (const b of branches) {
      branchStockMap.set(b.id_sucursal, {
        id_sucursal: b.id_sucursal,
        nombre_sucursal: b.nombre,
        ciudad: b.ciudad,
        stock_actual: 0,
        stock_reservado: 0,
        stock_disponible: 0,
      });
    }

    const variantDetails: OfflineVariantDetailItem[] = productVariants.map((v) => {
      const vStock = productStock.filter((s) => s.id_variante_producto === v.id_variante_producto);
      const vBranchMap = new Map<number, OfflineBranchStockItem>();
      for (const b of branches) {
        vBranchMap.set(b.id_sucursal, {
          id_sucursal: b.id_sucursal,
          nombre_sucursal: b.nombre,
          ciudad: b.ciudad,
          stock_actual: 0,
          stock_reservado: 0,
          stock_disponible: 0,
        });
      }

      let variantTotalDisponible = 0;
      for (const s of vStock) {
        const key = `${s.id_sucursal}_${s.id_variante_producto}`;
        const pendingReserved = pendingMap.get(key) || 0;
        const availableEstimated = Math.max(0, s.stock_disponible - pendingReserved);
        const reservedEstimated = s.stock_reservado + pendingReserved;

        const item = vBranchMap.get(s.id_sucursal);
        if (item) {
          item.stock_actual += s.stock_actual;
          item.stock_reservado += reservedEstimated;
          item.stock_disponible += availableEstimated;
        }
        variantTotalDisponible += availableEstimated;

        const globalBranch = branchStockMap.get(s.id_sucursal);
        if (globalBranch) {
          globalBranch.stock_actual += s.stock_actual;
          globalBranch.stock_reservado += reservedEstimated;
          globalBranch.stock_disponible += availableEstimated;
        }
      }

      const colorObj = colorMap.get(v.id_color);
      const variantPrice = v.precio ? Number(v.precio) : Number(product.precio);

      return {
        id_variante_producto: v.id_variante_producto,
        id_producto: v.id_producto,
        sku: v.sku,
        id_talla: v.id_talla,
        id_color: v.id_color,
        talla: v.talla || sizeMap.get(v.id_talla) || 'Talla única',
        color: v.color || colorObj?.nombre || 'Color único',
        color_hex: v.color_hex || colorObj?.codigo_hex || null,
        precio: variantPrice,
        estado: v.estado,
        stockTotalDisponible: variantTotalDisponible,
        disponibilidadPorSucursal: Array.from(vBranchMap.values()),
      };
    });

    const branchList = Array.from(branchStockMap.values());
    const totalProductStock = branchList.reduce((acc, curr) => acc + curr.stock_disponible, 0);
    const branchesWithStock = branchList.filter((b) => b.stock_disponible > 0).length;

    return {
      producto: product,
      categoriaNombre: product.categoria || catMap.get(product.id_categoria) || 'Sin categoría',
      variantes: variantDetails,
      totalStockDisponible: totalProductStock,
      sucursalesConStock: branchesWithStock,
      disponibilidadPorSucursal: branchList,
    };
  }

  /**
   * PK08 - CU13: Aplica los resultados de sincronizacion atomicamente sobre IndexedDB:
   * - Operaciones CONFIRMADAS: marca en cola como SINCRONIZADA, actualiza ID/codigo oficial del servidor
   *   en reservas_offline y compras_offline.
   * - Operaciones REINTENTABLES: conserva pendientes e incrementa contador de reintentos con ultimo error.
   * - Operaciones RECHAZADAS / EN_CONFLICTO: actualiza estado y registra motivo/conflictos para CU14.
   * - Resuelve vinculaciones_codigos en referencias cruzadas (e.g. reservas asociadas a ventas).
   * - NUNCA elimina comprobantes provisionales ni registros historicos.
   */
  async applyBatchSyncResults(
    empresaId: number,
    userId: number,
    results: OfflineSyncOperationResult[],
    codeLinks: Record<string, OfflineCodeLinkItem> = {},
  ): Promise<void> {
    if (!results || results.length === 0) return;

    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        ['cola_sincronizacion_offline', 'reservas_offline', 'compras_offline'],
        'readwrite',
      );

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Fallo al aplicar resultados de sincronizacion en IndexedDB');
        db.close();
        reject(error);
      };

      tx.onabort = () => {
        const error = tx.error ?? new Error('Transaccion abortada al aplicar sincronizacion');
        db.close();
        reject(error);
      };

      const queueStore = tx.objectStore('cola_sincronizacion_offline');
      const resStore = tx.objectStore('reservas_offline');
      const buyStore = tx.objectStore('compras_offline');

      const qReq = queueStore.getAll();
      const rReq = resStore.getAll();
      const bReq = buyStore.getAll();

      qReq.onsuccess = () => {
        rReq.onsuccess = () => {
          bReq.onsuccess = () => {
            const queueItems = (qReq.result as OfflineSyncQueueItem[]) || [];
            const reservations = (rReq.result as OfflineReservationLocal[]) || [];
            const purchases = (bReq.result as OfflinePurchaseLocal[]) || [];

            const queueMap = new Map<string, OfflineSyncQueueItem>();
            for (const q of queueItems) {
              queueMap.set(q.uuid_operacion, q);
              if (q.uuid_entidad) queueMap.set(q.uuid_entidad, q);
            }

            const resMap = new Map<string, OfflineReservationLocal>();
            for (const r of reservations) {
              resMap.set(r.uuid_reserva_offline, r);
              if (r.codigo_local) resMap.set(r.codigo_local, r);
            }

            const buyMap = new Map<string, OfflinePurchaseLocal>();
            for (const b of purchases) {
              buyMap.set(b.uuid_venta_offline, b);
            }

            const nowIso = new Date().toISOString();

            for (const res of results) {
              const qItem =
                queueMap.get(res.uuid_operacion) ||
                (res.uuid_entidad ? queueMap.get(res.uuid_entidad) : undefined);

              if (res.estado_resultado === 'CONFIRMADA') {
                if (qItem) {
                  qItem.estado = 'SINCRONIZADA';
                  qItem.payload = {
                    ...qItem.payload,
                    id_servidor: res.id_servidor,
                    codigo_servidor: res.codigo_servidor,
                    estado_servidor: res.estado_entidad_servidor,
                  };
                  qItem.ultimo_error = null;
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }

                if (res.tipo_operacion === 'RESERVA') {
                  const targetRes = res.uuid_entidad
                    ? resMap.get(res.uuid_entidad)
                    : resMap.get(res.uuid_operacion);
                  if (targetRes) {
                    targetRes.id_reserva = res.id_servidor ?? targetRes.id_reserva;
                    targetRes.codigo_servidor = res.codigo_servidor ?? targetRes.codigo_servidor;
                    targetRes.estado = 'SINCRONIZADA';
                    targetRes.motivo_servidor = null;
                    targetRes.conflictos = [];
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'TRANSICION_RESERVA') {
                  const targetRes =
                    (res.uuid_entidad ? resMap.get(res.uuid_entidad) : undefined) ||
                    (res.codigo_reserva_asociada ? resMap.get(res.codigo_reserva_asociada) : undefined) ||
                    (res.codigo_local ? resMap.get(res.codigo_local) : undefined);
                  if (targetRes) {
                    targetRes.id_reserva = res.id_servidor ?? targetRes.id_reserva;
                    targetRes.codigo_servidor = res.codigo_servidor ?? targetRes.codigo_servidor;
                    targetRes.estado =
                      (res.estado_entidad_servidor as any) ||
                      (qItem?.payload?.accion === 'attend' ? 'ATENDIDA' : 'CONFIRMADA');
                    targetRes.motivo_servidor = null;
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'COMPRA' || res.tipo_operacion === 'VENTA') {
                  const targetBuy = res.uuid_entidad
                    ? buyMap.get(res.uuid_entidad)
                    : buyMap.get(res.uuid_operacion);
                  if (targetBuy) {
                    targetBuy.id_venta_servidor = res.id_servidor ?? targetBuy.id_venta_servidor;
                    targetBuy.numero_venta_servidor = res.codigo_servidor ?? targetBuy.numero_venta_servidor;
                    targetBuy.pago_simulado = res.pago_simulado ?? targetBuy.pago_simulado;
                    targetBuy.estado_pago =
                      res.estado_pago === 'APROBADO' && !targetBuy.pago_simulado
                        ? 'APROBADO'
                        : 'PENDIENTE_VALIDACION';
                    targetBuy.estado =
                      res.estado_entidad_servidor === 'COMPLETADA'
                        ? 'CONFIRMADA'
                        : ((res.estado_entidad_servidor as any) || 'CONFIRMADA');
                    targetBuy.motivo_servidor = null;
                    targetBuy.conflictos = [];
                    targetBuy.updated_at = nowIso;
                    buyStore.put(targetBuy);
                  }
                }
              } else if (res.estado_resultado === 'REINTENTABLE') {
                const retryNotice =
                  res.motivo || res.mensaje || 'Error temporal; reintento automatico programado';
                if (qItem) {
                  qItem.estado = 'PENDIENTE_SINCRONIZACION';
                  qItem.reintentos = (qItem.reintentos || 0) + 1;
                  qItem.ultimo_error = retryNotice;
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }

                if (res.tipo_operacion === 'RESERVA') {
                  const targetRes = res.uuid_entidad
                    ? resMap.get(res.uuid_entidad)
                    : resMap.get(res.uuid_operacion);
                  if (targetRes) {
                    if (targetRes.estado === 'RECHAZADA' || targetRes.estado === 'EN_CONFLICTO') {
                      targetRes.estado = 'REGISTRADA_LOCAL';
                    }
                    targetRes.motivo_servidor = retryNotice;
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'COMPRA' || res.tipo_operacion === 'VENTA') {
                  const targetBuy = res.uuid_entidad
                    ? buyMap.get(res.uuid_entidad)
                    : buyMap.get(res.uuid_operacion);
                  if (targetBuy) {
                    if (targetBuy.estado === 'RECHAZADA' || targetBuy.estado === 'EN_CONFLICTO') {
                      targetBuy.estado = 'REGISTRADA_LOCAL';
                    }
                    targetBuy.motivo_servidor = retryNotice;
                    targetBuy.updated_at = nowIso;
                    buyStore.put(targetBuy);
                  }
                }
              } else if (res.estado_resultado === 'EN_CONFLICTO' || res.estado_resultado === 'RECHAZADA') {
                const isConflict = res.estado_resultado === 'EN_CONFLICTO';
                if (qItem) {
                  qItem.estado = isConflict ? 'CONFLICTO' : 'RECHAZADA';
                  qItem.ultimo_error = res.motivo || res.mensaje;
                  qItem.conflictos = res.conflictos || [];
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }

                if (res.tipo_operacion === 'RESERVA' || res.tipo_operacion === 'TRANSICION_RESERVA') {
                  const targetRes = res.uuid_entidad
                    ? resMap.get(res.uuid_entidad)
                    : resMap.get(res.uuid_operacion);
                  if (targetRes) {
                    targetRes.estado = isConflict ? 'EN_CONFLICTO' : 'RECHAZADA';
                    targetRes.motivo_servidor = res.motivo || res.mensaje;
                    targetRes.conflictos = res.conflictos || [];
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'COMPRA' || res.tipo_operacion === 'VENTA') {
                  const targetBuy = res.uuid_entidad
                    ? buyMap.get(res.uuid_entidad)
                    : buyMap.get(res.uuid_operacion);
                  if (targetBuy) {
                    targetBuy.estado = isConflict ? 'EN_CONFLICTO' : 'RECHAZADA';
                    targetBuy.motivo_servidor = res.motivo || res.mensaje;
                    targetBuy.conflictos = res.conflictos || [];
                    targetBuy.updated_at = nowIso;
                    buyStore.put(targetBuy);
                  }
                }
              }
            }

            if (codeLinks && Object.keys(codeLinks).length > 0) {
              for (const [refKey, link] of Object.entries(codeLinks)) {
                if (link.tipo_operacion === 'RESERVA') {
                  for (const buy of purchases) {
                    if (buy.uuid_reserva_offline === refKey || (buy as any).codigo_reserva === refKey) {
                      buy.id_reserva = link.id_servidor;
                      buy.updated_at = nowIso;
                      buyStore.put(buy);
                    }
                  }
                }
              }
            }
          };
        };
      };
    });
  }

  /**
   * PK08 - CU14: Aplica resultados de resolución de conflictos en IndexedDB.
   * - Conserva UUID, comprobantes e historial local sin borrados silenciosos.
   * - Actualiza códigos oficiales (RSV-..., VTA-...) cuando el servidor los confirma.
   * - Actualiza estados de sincronización y estado comercial.
   * - Si se descarta por usuario, marca estado cancelado/descartado sin borrar el comprobante.
   * - Propaga vinculación de códigos a operaciones dependientes.
   */
  async applyConflictResolutionResults(
    empresaId: number,
    userId: number,
    results: OfflineOperationResolutionResult[],
    codeLinks: Record<string, OfflineCodeLinkItem> = {},
  ): Promise<void> {
    if (!results || results.length === 0) return;

    const db = await this.openDatabase(empresaId, userId);

    return new Promise((resolve, reject) => {
      const tx = db.transaction(
        ['cola_sincronizacion_offline', 'reservas_offline', 'compras_offline'],
        'readwrite',
      );

      tx.oncomplete = () => {
        db.close();
        resolve();
      };

      tx.onerror = () => {
        const error = tx.error ?? new Error('Fallo al aplicar resultados de resolución en IndexedDB');
        db.close();
        reject(error);
      };

      tx.onabort = () => {
        const error = tx.error ?? new Error('Transacción abortada al resolver conflictos');
        db.close();
        reject(error);
      };

      const queueStore = tx.objectStore('cola_sincronizacion_offline');
      const resStore = tx.objectStore('reservas_offline');
      const buyStore = tx.objectStore('compras_offline');

      const qReq = queueStore.getAll();
      const rReq = resStore.getAll();
      const bReq = buyStore.getAll();

      qReq.onsuccess = () => {
        rReq.onsuccess = () => {
          bReq.onsuccess = () => {
            const queueItems = (qReq.result as OfflineSyncQueueItem[]) || [];
            const reservations = (rReq.result as OfflineReservationLocal[]) || [];
            const purchases = (bReq.result as OfflinePurchaseLocal[]) || [];

            const queueMap = new Map<string, OfflineSyncQueueItem>();
            for (const q of queueItems) {
              queueMap.set(q.uuid_operacion, q);
              if (q.uuid_entidad) queueMap.set(q.uuid_entidad, q);
            }

            const resMap = new Map<string, OfflineReservationLocal>();
            for (const r of reservations) {
              resMap.set(r.uuid_reserva_offline, r);
              if (r.codigo_local) resMap.set(r.codigo_local, r);
            }

            const buyMap = new Map<string, OfflinePurchaseLocal>();
            for (const b of purchases) {
              buyMap.set(b.uuid_venta_offline, b);
            }

            const nowIso = new Date().toISOString();

            for (const res of results) {
              const qItem =
                queueMap.get(res.uuid_operacion) ||
                (res.uuid_entidad ? queueMap.get(res.uuid_entidad) : undefined);

              if (res.descartada_por_usuario || res.accion_aplicada === 'DESCARTAR_OPERACION') {
                // Descartada voluntariamente: se retira de la cola de sincronización activa
                // y se preserva el registro histórico con comprobante marcado como CANCELADA / RECHAZADA
                if (qItem) {
                  qItem.estado = 'RECHAZADA';
                  qItem.ultimo_error = 'Operación descartada por decisión del usuario';
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }

                if (res.tipo_operacion === 'RESERVA' || res.tipo_operacion === 'TRANSICION_RESERVA') {
                  const targetRes = res.uuid_entidad
                    ? resMap.get(res.uuid_entidad)
                    : resMap.get(res.uuid_operacion);
                  if (targetRes) {
                    targetRes.estado = 'CANCELADA';
                    targetRes.motivo_servidor = 'Descartada por el usuario';
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'COMPRA' || res.tipo_operacion === 'VENTA') {
                  const targetBuy = res.uuid_entidad
                    ? buyMap.get(res.uuid_entidad)
                    : buyMap.get(res.uuid_operacion);
                  if (targetBuy) {
                    targetBuy.estado = 'RECHAZADA';
                    targetBuy.motivo_servidor = 'Descartada por el usuario';
                    targetBuy.updated_at = nowIso;
                    buyStore.put(targetBuy);
                  }
                }
              } else if (res.confirmada || res.estado_resultado === 'CONFIRMADA') {
                if (qItem) {
                  qItem.estado = 'SINCRONIZADA';
                  qItem.payload = {
                    ...qItem.payload,
                    id_servidor: res.id_servidor,
                    codigo_servidor: res.codigo_servidor,
                    estado_servidor: res.estado_entidad_servidor,
                  };
                  qItem.ultimo_error = null;
                  qItem.conflictos = [];
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }

                if (res.tipo_operacion === 'RESERVA') {
                  const targetRes = res.uuid_entidad
                    ? resMap.get(res.uuid_entidad)
                    : resMap.get(res.uuid_operacion);
                  if (targetRes) {
                    targetRes.id_reserva = res.id_servidor ?? targetRes.id_reserva;
                    targetRes.codigo_servidor = res.codigo_servidor ?? targetRes.codigo_servidor;
                    targetRes.estado = 'SINCRONIZADA';
                    targetRes.motivo_servidor = null;
                    targetRes.conflictos = [];
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'TRANSICION_RESERVA') {
                  const targetRes =
                    (res.uuid_entidad ? resMap.get(res.uuid_entidad) : undefined) ||
                    (res.codigo_reserva_asociada ? resMap.get(res.codigo_reserva_asociada) : undefined) ||
                    (res.codigo_local ? resMap.get(res.codigo_local) : undefined);
                  if (targetRes) {
                    targetRes.id_reserva = res.id_servidor ?? targetRes.id_reserva;
                    targetRes.codigo_servidor = res.codigo_servidor ?? targetRes.codigo_servidor;
                    targetRes.estado =
                      (res.estado_entidad_servidor as any) ||
                      (qItem?.payload?.accion === 'attend' ? 'ATENDIDA' : 'CONFIRMADA');
                    targetRes.motivo_servidor = null;
                    targetRes.conflictos = [];
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'COMPRA' || res.tipo_operacion === 'VENTA') {
                  const targetBuy = res.uuid_entidad
                    ? buyMap.get(res.uuid_entidad)
                    : buyMap.get(res.uuid_operacion);
                  if (targetBuy) {
                    targetBuy.id_venta_servidor = res.id_servidor ?? targetBuy.id_venta_servidor;
                    targetBuy.numero_venta_servidor = res.codigo_servidor ?? targetBuy.numero_venta_servidor;
                    targetBuy.pago_simulado = res.pago_simulado ?? targetBuy.pago_simulado;
                    targetBuy.estado_pago =
                      res.estado_pago === 'APROBADO' && !targetBuy.pago_simulado
                        ? 'APROBADO'
                        : 'PENDIENTE_VALIDACION';
                    targetBuy.estado =
                      res.estado_entidad_servidor === 'COMPLETADA'
                        ? 'CONFIRMADA'
                        : ((res.estado_entidad_servidor as any) || 'CONFIRMADA');
                    if (res.total !== null && res.total !== undefined) {
                      targetBuy.total = Number(res.total);
                    }
                    if (res.subtotal !== null && res.subtotal !== undefined) {
                      targetBuy.subtotal = Number(res.subtotal);
                    }
                    targetBuy.motivo_servidor = null;
                    targetBuy.conflictos = [];
                    targetBuy.updated_at = nowIso;
                    buyStore.put(targetBuy);
                  }
                }
              } else if (res.estado_resultado === 'REINTENTABLE') {
                const retryNotice = res.motivo || res.mensaje || 'Error temporal; reintentable';
                if (qItem) {
                  qItem.estado = 'PENDIENTE_SINCRONIZACION';
                  qItem.reintentos = (qItem.reintentos || 0) + 1;
                  qItem.ultimo_error = retryNotice;
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }
              } else if (res.estado_resultado === 'EN_CONFLICTO' || res.estado_resultado === 'RECHAZADA') {
                const isConflict = res.estado_resultado === 'EN_CONFLICTO';
                if (qItem) {
                  qItem.estado = isConflict ? 'CONFLICTO' : 'RECHAZADA';
                  qItem.ultimo_error = res.motivo || res.mensaje;
                  qItem.conflictos = res.conflictos || [];
                  qItem.updated_at = nowIso;
                  queueStore.put(qItem);
                }

                if (res.tipo_operacion === 'RESERVA' || res.tipo_operacion === 'TRANSICION_RESERVA') {
                  const targetRes = res.uuid_entidad
                    ? resMap.get(res.uuid_entidad)
                    : resMap.get(res.uuid_operacion);
                  if (targetRes) {
                    targetRes.estado = isConflict ? 'EN_CONFLICTO' : 'RECHAZADA';
                    targetRes.motivo_servidor = res.motivo || res.mensaje;
                    targetRes.conflictos = res.conflictos || [];
                    targetRes.updated_at = nowIso;
                    resStore.put(targetRes);
                  }
                } else if (res.tipo_operacion === 'COMPRA' || res.tipo_operacion === 'VENTA') {
                  const targetBuy = res.uuid_entidad
                    ? buyMap.get(res.uuid_entidad)
                    : buyMap.get(res.uuid_operacion);
                  if (targetBuy) {
                    targetBuy.estado = isConflict ? 'EN_CONFLICTO' : 'RECHAZADA';
                    targetBuy.motivo_servidor = res.motivo || res.mensaje;
                    targetBuy.conflictos = res.conflictos || [];
                    targetBuy.updated_at = nowIso;
                    buyStore.put(targetBuy);
                  }
                }
              }
            }

            if (codeLinks && Object.keys(codeLinks).length > 0) {
              for (const [refKey, link] of Object.entries(codeLinks)) {
                if (link.tipo_operacion === 'RESERVA') {
                  for (const buy of purchases) {
                    if (buy.uuid_reserva_offline === refKey || (buy as any).codigo_reserva === refKey) {
                      buy.id_reserva = link.id_servidor;
                      if (link.codigo_servidor) {
                        (buy as any).codigo_reserva = link.codigo_servidor;
                      }
                      buy.updated_at = nowIso;
                      buyStore.put(buy);
                    }
                  }
                }
              }
            }
          };
        };
      };
    });
  }
}
