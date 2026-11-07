import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { environment } from '../../../environments/environment';
import { registerFashionStoreServiceWorker } from '../../app.config';
import {
  OfflinePackageResponse,
  OfflineStatusResponse,
  OfflineStoredSummary,
} from '../models/offline.model';
import { CatalogService } from './catalog.service';
import { OfflineStorageService } from './offline-storage.service';
import { OFFLINE_IMAGES_CACHE_NAME, OfflineService } from './offline.service';
import { SessionService } from './session.service';

describe('OfflineService & OfflineStorageService (PK08 - CU08 Web Angular PWA)', () => {
  let service: OfflineService;
  let storageService: OfflineStorageService;
  let catalogService: CatalogService;
  let httpMock: HttpTestingController;
  let currentActiveUser: {
    id_usuario: number;
    nombre: string;
    apellido: string;
    correo: string;
    rol: string;
    id_empresa: number;
  };

  const mockCashierUser = {
    id_usuario: 15,
    nombre: 'Ana',
    apellido: 'Cajera',
    correo: 'ana@fashionstore.com',
    rol: 'CAJERO',
    id_empresa: 2,
  };

  const mockClientUser = {
    id_usuario: 88,
    nombre: 'Camila',
    apellido: 'Rojas',
    correo: 'camila.cliente@gmail.com',
    rol: 'CLIENTE',
    id_empresa: 2,
  };

  const mockSessionService = {
    getAccessToken: () => 'mock-jwt-token-cu08',
    getUser: () => currentActiveUser,
    currentUser: () => currentActiveUser,
  };

  const mockStoredSummary: OfflineStoredSummary = {
    metadata: {
      version: 'FS-OFFLINE-E2-abc12345',
      fecha_generacion: '2026-10-31T18:00:00Z',
      valido_hasta: '2027-11-01T18:00:00Z',
      vigencia_segundos: 86400,
      id_empresa: 2,
      empresa_codigo: 'moda-oriente',
      empresa_nombre: 'Moda Oriente',
      id_usuario: 15,
      usuario_rol: 'CAJERO',
      sucursales_autorizadas_ids: [10],
      suscripcion_activa: true,
      funcionalidad_offline: true,
      total_sucursales: 1,
      total_categorias: 2,
      total_productos: 5,
      total_variantes: 10,
      total_existencias: 25,
      total_clientes: 1,
    },
    savedAt: '2026-10-31T18:05:00Z',
    counts: {
      sucursales: 1,
      categorias: 2,
      tallas: 3,
      colores: 3,
      productos: 5,
      variantes: 10,
      existencias: 25,
      clientes: 1,
    },
    isExpired: false,
    timeRemainingText: '23h 55m restantes',
  };

  const mockPackageResponse: OfflinePackageResponse = {
    success: true,
    message: 'Paquete offline preparado exitosamente',
    metadata: mockStoredSummary.metadata,
    sucursales: [
      {
        id_sucursal: 10,
        id_ciudad: 1,
        ciudad: 'Santa Cruz',
        nombre: 'Sucursal Central',
        direccion: 'Calle Comercio 100',
        estado: true,
      },
    ],
    categorias: [{ id_categoria: 1, nombre: 'Ropa', estado: true }],
    tallas: [{ id_talla: 1, nombre: 'M', estado: true }],
    colores: [{ id_color: 1, nombre: 'Blanco', codigo_hex: '#FFFFFF', estado: true }],
    productos: [
      {
        id_producto: 101,
        id_categoria: 1,
        categoria: 'Ropa',
        nombre: 'Blusa Seda Imperial',
        seccion: 'MUJER',
        precio: '180.00',
        imagen_principal: 'https://cdn.fashionstore.bo/img/blusa-101.jpg',
        imagenes: [
          'https://cdn.fashionstore.bo/img/blusa-101.jpg',
          'https://cdn.fashionstore.bo/img/blusa-101-back.jpg',
        ],
        estado: true,
      },
    ],
    variantes: [
      {
        id_variante_producto: 201,
        id_producto: 101,
        id_talla: 1,
        talla: 'M',
        id_color: 1,
        color: 'Blanco',
        color_hex: '#FFFFFF',
        sku: 'BLU-SED-BLA-M',
        precio: '180.00',
        estado: true,
      },
    ],
    existencias: [
      {
        id_inventario_sucursal: 501,
        id_sucursal: 10,
        id_variante_producto: 201,
        id_producto: 101,
        stock_actual: 20,
        stock_reservado: 2,
        stock_disponible: 18,
        stock_minimo: 3,
        updated_at: '2026-10-31T18:00:00Z',
      },
    ],
    clientes: [
      {
        id_cliente: 1,
        id_usuario: 88,
        nombre: 'Camila',
        apellido: 'Rojas',
        correo: 'camila.cliente@gmail.com',
        telefono: '71122334',
      },
    ],
  };

  beforeEach(() => {
    TestBed.resetTestingModule();
    localStorage.clear();
    currentActiveUser = { ...mockCashierUser };

    TestBed.configureTestingModule({
      providers: [
        OfflineStorageService,
        OfflineService,
        CatalogService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SessionService, useValue: mockSessionService },
      ],
    });

    storageService = TestBed.inject(OfflineStorageService);
    service = TestBed.inject(OfflineService);
    catalogService = TestBed.inject(CatalogService);
    httpMock = TestBed.inject(HttpTestingController);
    service.isOnline.set(true);
  });

  afterEach(() => {
    httpMock.verify();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('1. conserva la preparación manual para personal operativo, descarga el paquete y persiste atómicamente en IndexedDB', async () => {
    vi.spyOn(storageService, 'getStoredPackageSummary').mockResolvedValue(mockStoredSummary);
    const saveSpy = vi.spyOn(storageService, 'savePackageAtomic').mockResolvedValue();
    vi.spyOn(service, 'cacheCatalogImages').mockResolvedValue({ cached: 2, total: 2 });

    const downloadPromise = firstValueFrom(service.downloadPackage(10));

    const req = httpMock.expectOne(
      (request) =>
        request.url === `${environment.apiUrl}/api/offline/package` &&
        request.params.get('id_sucursal') === '10',
    );
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer mock-jwt-token-cu08');
    req.flush(mockPackageResponse);

    const result = await downloadPromise;
    expect(result.notModified).toBe(false);
    expect(result.package?.metadata.total_productos).toBe(5);
    expect(saveSpy).toHaveBeenCalledWith(2, 15, mockPackageResponse);
  });

  it('2. permite que el CLIENTE autenticado prepare automáticamente los datos offline al usar FashionStore con internet sin menús administrativos', async () => {
    currentActiveUser = { ...mockClientUser };
    const clientSummary: OfflineStoredSummary = {
      ...mockStoredSummary,
      metadata: {
        ...mockStoredSummary.metadata,
        id_usuario: 88,
        usuario_rol: 'CLIENTE',
      },
    };

    vi.spyOn(storageService, 'getStoredPackageSummary')
      .mockResolvedValueOnce(null)
      .mockResolvedValue(clientSummary);
    const saveSpy = vi.spyOn(storageService, 'savePackageAtomic').mockResolvedValue();
    vi.spyOn(service, 'cacheCatalogImages').mockResolvedValue({ cached: 2, total: 2 });

    const autoPrepPromise = service.ensurePreparedAutomatically();
    await Promise.resolve();
    await Promise.resolve();

    const req = httpMock.expectOne(
      (request) => request.url === `${environment.apiUrl}/api/offline/package`,
    );
    expect(req.request.method).toBe('GET');
    req.flush({
      ...mockPackageResponse,
      metadata: clientSummary.metadata,
    });

    const prepared = await autoPrepPromise;
    expect(prepared).toBe(true);
    expect(saveSpy).toHaveBeenCalledWith(
      2,
      88,
      expect.objectContaining({
        metadata: expect.objectContaining({ id_usuario: 88, usuario_rol: 'CLIENTE' }),
      }),
    );

    // Una segunda llamada en la misma sesión con paquete vigente no vuelve a descargar
    const secondCall = await service.ensurePreparedAutomatically();
    expect(secondCall).toBe(true);
  });

  it('3. mantiene aislamiento estricto por empresa/usuario y rechaza paquetes de otro tenant', async () => {
    expect(storageService.getDatabaseName(2, 88)).toBe('fashionstore_offline_e2_u88');
    expect(storageService.getDatabaseName(1, 88)).toBe('fashionstore_offline_e1_u88');
    expect(storageService.getDatabaseName(2, 15)).not.toBe(storageService.getDatabaseName(2, 88));

    await expect(
      storageService.savePackageAtomic(1, 88, mockPackageResponse),
    ).rejects.toThrow(/no corresponde a la empresa activa/i);
  });

  it('4. prepara y almacena en caché local (Cache Storage) las imágenes del catálogo para mostrarlas sin internet', async () => {
    const putSpy = vi.fn().mockResolvedValue(undefined);
    const matchSpy = vi.fn().mockResolvedValue(undefined);
    const openSpy = vi.fn().mockResolvedValue({
      match: matchSpy,
      put: putSpy,
    });

    vi.stubGlobal('caches', { open: openSpy });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['fake-image-bytes']), { status: 200 }),
    );

    const result = await service.cacheCatalogImages(mockPackageResponse.productos, 2, 88);

    expect(openSpy).toHaveBeenCalledWith(OFFLINE_IMAGES_CACHE_NAME);
    expect(result.total).toBe(2);
    expect(result.cached).toBe(2);
    expect(putSpy).toHaveBeenCalledTimes(2);
    expect(service.cachedImagesCount()).toBe(2);
  });

  it('5. preserva intactas las reservas, detalles y operaciones pendientes de IndexedDB versión 2 al actualizar o limpiar el paquete', async () => {
    const clearedStores: string[] = [];
    const writtenStores: string[] = [];

    const fakeDb = {
      close: vi.fn(),
      transaction: vi.fn((_storeNames: string[], _mode: string) => {
        const txObj: Record<string, unknown> = {
          oncomplete: null as (() => void) | null,
          onerror: null,
          onabort: null,
          objectStore: (name: string) => ({
            clear: () => {
              clearedStores.push(name);
            },
            put: () => {
              writtenStores.push(name);
            },
          }),
        };
        setTimeout(() => {
          if (typeof txObj['oncomplete'] === 'function') {
            (txObj['oncomplete'] as () => void)();
          }
        }, 0);
        return txObj as unknown as IDBTransaction;
      }),
    } as unknown as IDBDatabase;

    vi.spyOn(storageService, 'openDatabase').mockResolvedValue(fakeDb);

    await storageService.savePackageAtomic(2, 88, mockPackageResponse);
    await storageService.clearDatabase(2, 88);

    // Verificar que NUNCA se abrieron ni limpiaron los almacenes de operaciones pendientes (CU10 v2)
    expect(clearedStores).not.toContain('reservas_offline');
    expect(clearedStores).not.toContain('detalles_reserva_offline');
    expect(clearedStores).not.toContain('cola_sincronizacion_offline');
    expect(writtenStores).not.toContain('reservas_offline');
    expect(writtenStores).not.toContain('detalles_reserva_offline');
    expect(writtenStores).not.toContain('cola_sincronizacion_offline');
    expect(clearedStores).toContain('productos');
    expect(clearedStores).toContain('existencias');
  });

  it('6. permite reabrir la PWA sin conexión (offline) y acceder al catálogo local en IndexedDB sin depender de FastAPI', async () => {
    currentActiveUser = { ...mockClientUser };
    vi.spyOn(storageService, 'getCatalogProducts').mockResolvedValue(mockPackageResponse.productos);
    vi.spyOn(storageService, 'getCategories').mockResolvedValue(mockPackageResponse.categorias);
    vi.spyOn(storageService, 'getSizes').mockResolvedValue(mockPackageResponse.tallas);
    vi.spyOn(storageService, 'getColors').mockResolvedValue(mockPackageResponse.colores);
    vi.spyOn(storageService, 'getVariants').mockResolvedValue(mockPackageResponse.variantes);
    vi.spyOn(storageService, 'getInventory').mockResolvedValue(mockPackageResponse.existencias);
    vi.spyOn(storageService, 'getBranches').mockResolvedValue(mockPackageResponse.sucursales);

    const listPromise = firstValueFrom(catalogService.listProducts({ seccion: 'MUJER' }));

    // Simular fallo de red (FastAPI apagado / dispositivo sin internet: status 0)
    const req = httpMock.expectOne((r) => r.url === `${environment.apiUrl}/api/catalog/products`);
    req.error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });

    const catalogResp = await listPromise;
    expect(catalogResp.success).toBe(true);
    expect(catalogResp.data.length).toBe(1);
    expect(catalogResp.data[0].nombre).toBe('Blusa Seda Imperial');
    expect(catalogResp.data[0].precio_final).toBe('180.00');
    expect(catalogResp.data[0].tallas_disponibles[0].nombre).toBe('M');
  });

  it('7. soporta HTTP 304 Not Modified y registra el Service Worker de la PWA', async () => {
    const registerSpy = vi.fn().mockResolvedValue({ scope: '/' });
    const swReg = await registerFashionStoreServiceWorker({
      serviceWorker: { register: registerSpy } as unknown as ServiceWorkerContainer,
    });
    expect(registerSpy).toHaveBeenCalledWith('/sw.js', { scope: '/' });
    expect(swReg).toEqual({ scope: '/' });

    service.localSummary.set(mockStoredSummary);
    const saveSpy = vi.spyOn(storageService, 'savePackageAtomic').mockResolvedValue();

    const downloadPromise = firstValueFrom(service.downloadPackage(10));

    const req = httpMock.expectOne(
      (request) =>
        request.url === `${environment.apiUrl}/api/offline/package` &&
        request.headers.get('If-None-Match') === '"FS-OFFLINE-E2-abc12345"',
    );
    req.flush(null, { status: 304, statusText: 'Not Modified' });

    const result = await downloadPromise;
    expect(result.notModified).toBe(true);
    expect(result.message).toContain('HTTP 304');
    expect(saveSpy).not.toHaveBeenCalled();
  });
});
