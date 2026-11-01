import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflinePackageResponse,
  OfflineStatusResponse,
  OfflineStoredSummary,
} from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

describe('OfflineService (PK08 - CU08)', () => {
  let service: OfflineService;
  let httpMock: HttpTestingController;
  let storageMock: any;

  const mockUser = {
    id_usuario: 15,
    nombre: 'Ana',
    apellido: 'Cajera',
    correo: 'ana@fashionstore.com',
    rol: 'CAJERO',
    id_empresa: 2,
  };

  const mockSessionService = {
    getAccessToken: () => 'mock-jwt-token-cu08',
    getUser: () => mockUser,
    currentUser: () => mockUser,
  };

  const mockStoredSummary: OfflineStoredSummary = {
    metadata: {
      version: 'FS-OFFLINE-E2-abc12345',
      fecha_generacion: '2026-10-31T18:00:00Z',
      valido_hasta: '2026-11-01T18:00:00Z',
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
      total_clientes: 8,
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
      clientes: 8,
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
    colores: [{ id_color: 1, nombre: 'Blanco', estado: true }],
    productos: [
      {
        id_producto: 101,
        id_categoria: 1,
        nombre: 'Blusa Seda',
        seccion: 'MUJER',
        precio: '180.00',
        estado: true,
      },
    ],
    variantes: [
      {
        id_variante_producto: 201,
        id_producto: 101,
        id_talla: 1,
        id_color: 1,
        sku: 'BLU-SED-BLA-M',
        estado: true,
      },
    ],
    existencias: [
      {
        id_inventario_sucursal: 501,
        id_sucursal: 10,
        id_variante_producto: 201,
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
        id_usuario: 50,
        nombre: 'María',
        apellido: 'López',
        correo: 'maria@gmail.com',
        telefono: '71122334',
      },
    ],
  };

  beforeEach(() => {
    storageMock = {
      getStoredPackageSummary: () => Promise.resolve(mockStoredSummary),
      savePackageAtomic: () => Promise.resolve(),
      clearDatabase: () => Promise.resolve(),
    };

    TestBed.configureTestingModule({
      providers: [
        OfflineService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SessionService, useValue: mockSessionService },
        { provide: OfflineStorageService, useValue: storageMock },
      ],
    });

    service = TestBed.inject(OfflineService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('1. Debe recuperar la información local almacenada en IndexedDB al abrir la app', async () => {
    const summary = await service.loadLocalSummary();
    expect(summary).toEqual(mockStoredSummary);
    expect(service.localSummary()?.metadata.version).toBe('FS-OFFLINE-E2-abc12345');
    expect(service.localSummary()?.counts.productos).toBe(5);
  });

  it('2. Debe consultar el estado de vigencia mediante GET /api/offline/status con Bearer token', async () => {
    service.localSummary.set(mockStoredSummary);

    const mockStatusResponse: OfflineStatusResponse = {
      success: true,
      id_empresa: 2,
      version_actual: 'FS-OFFLINE-E2-abc12345',
      version_solicitada: 'FS-OFFLINE-E2-abc12345',
      vigente: true,
      requiere_actualizacion: false,
      fecha_generacion: '2026-10-31T18:00:00Z',
      valido_hasta: '2026-11-01T18:00:00Z',
      sucursales_autorizadas_ids: [10],
      suscripcion_activa: true,
      funcionalidad_offline: true,
      message: 'El paquete local está vigente y no requiere actualización.',
    };

    const statusPromise = firstValueFrom(service.checkStatus(10));

    const req = httpMock.expectOne(
      (request) =>
        request.url === `${environment.apiUrl}/api/offline/status` &&
        request.params.get('id_sucursal') === '10' &&
        request.params.get('version') === 'FS-OFFLINE-E2-abc12345',
    );
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer mock-jwt-token-cu08');
    expect(req.request.headers.get('If-None-Match')).toBe('"FS-OFFLINE-E2-abc12345"');
    expect(req.request.params.get('since_version')).toBe('FS-OFFLINE-E2-abc12345');
    req.flush(mockStatusResponse);

    const res = await statusPromise;
    expect(res.vigente).toBe(true);
    expect(res.requiere_actualizacion).toBe(false);
    expect(service.statusCheck()?.version_actual).toBe('FS-OFFLINE-E2-abc12345');
  });

  it('3. Debe descargar el paquete completo y almacenarlo atómicamente en IndexedDB', async () => {
    let savedCalled = false;
    storageMock.savePackageAtomic = (empId: number, uId: number, pkg: OfflinePackageResponse) => {
      savedCalled = true;
      expect(empId).toBe(2);
      expect(uId).toBe(15);
      expect(pkg.metadata.version).toBe('FS-OFFLINE-E2-abc12345');
      return Promise.resolve();
    };

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
    expect(savedCalled).toBe(true);
  });

  it('4. Debe soportar HTTP 304 Not Modified sin alterar ni duplicar datos en IndexedDB', async () => {
    service.localSummary.set(mockStoredSummary);
    let saveAttempted = false;
    storageMock.savePackageAtomic = () => {
      saveAttempted = true;
      return Promise.resolve();
    };

    const downloadPromise = firstValueFrom(service.downloadPackage(10));

    const req = httpMock.expectOne(
      (request) =>
        request.url === `${environment.apiUrl}/api/offline/package` &&
        request.headers.get('If-None-Match') === '"FS-OFFLINE-E2-abc12345"' &&
        request.params.get('since_version') === 'FS-OFFLINE-E2-abc12345',
    );
    req.flush(null, { status: 304, statusText: 'Not Modified' });

    const result = await downloadPromise;
    expect(result.notModified).toBe(true);
    expect(result.message).toContain('HTTP 304');
    expect(saveAttempted).toBe(false);
  });

  it('5. Una descarga fallida por red debe conservar los últimos datos válidos en IndexedDB', async () => {
    let saveAttempted = false;
    storageMock.savePackageAtomic = () => {
      saveAttempted = true;
      return Promise.resolve();
    };

    const downloadPromise = firstValueFrom(service.downloadPackage(10));

    const req = httpMock.expectOne(
      (request) => request.url === `${environment.apiUrl}/api/offline/package`,
    );
    req.flush(
      { message: 'Fallo de conexión con el servidor' },
      { status: 500, statusText: 'Server Error' },
    );

    await expect(downloadPromise).rejects.toThrow();
    expect(saveAttempted).toBe(false);
    expect(service.error()).toBeTruthy();
  });

  it('6. Debe reportar error claro ante suscripción SaaS inactiva o función OFFLINE deshabilitada (HTTP 403)', async () => {
    const downloadPromise = firstValueFrom(service.downloadPackage());

    const req = httpMock.expectOne(
      (request) => request.url === `${environment.apiUrl}/api/offline/package`,
    );
    req.flush(
      {
        success: false,
        message: 'La empresa no cuenta con una suscripción SaaS activa vigente.',
      },
      { status: 403, statusText: 'Forbidden' },
    );

    await expect(downloadPromise).rejects.toThrow();
    expect(service.error()).toContain('suscripción SaaS activa');
  });

  it('7. Debe permitir limpiar la base de datos local y reiniciar el estado', async () => {
    service.localSummary.set(mockStoredSummary);
    let clearCalled = false;
    storageMock.clearDatabase = (empId: number, uId: number) => {
      clearCalled = true;
      expect(empId).toBe(2);
      expect(uId).toBe(15);
      return Promise.resolve();
    };

    await service.clearLocalData();
    expect(clearCalled).toBe(true);
    expect(service.localSummary()).toBeNull();
    expect(service.statusCheck()).toBeNull();
  });
});
