import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  OfflineQueueSyncResponse,
  OfflineSyncOperationResult,
  OfflineSyncQueueItem,
} from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineSyncService } from './offline-sync.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

describe('PK08 — CU13 Frontend: Sincronizar operaciones pendientes de FashionStore', () => {
  let service: OfflineSyncService;
  let httpMock: HttpTestingController;
  let mockStorage: any;
  let mockSession: any;
  let mockOffline: any;

  const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 10));

  beforeEach(() => {
    TestBed.resetTestingModule();

    mockStorage = {
      getOfflineQueue: vi.fn(),
      applyBatchSyncResults: vi.fn().mockResolvedValue(undefined),
    };
    mockSession = {
      getUser: vi.fn(),
      getAccessToken: vi.fn().mockReturnValue('mock-jwt-token'),
    };
    mockOffline = {
      resolveEffectiveCompanyId: vi.fn().mockReturnValue(1),
      isOnline: vi.fn().mockReturnValue(true),
    };

    TestBed.configureTestingModule({
      providers: [
        OfflineSyncService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: OfflineStorageService, useValue: mockStorage },
        { provide: SessionService, useValue: mockSession },
        { provide: OfflineService, useValue: mockOffline },
      ],
    });

    service = TestBed.inject(OfflineSyncService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    TestBed.resetTestingModule();
  });

  it('1. Sincronización de cliente (RESERVA y COMPRA) actualiza IndexedDB con IDs oficiales sin borrar registros históricos', async () => {
    mockSession.getUser.mockReturnValue({
      id_usuario: 10,
      id_empresa: 1,
      rol: 'CLIENTE',
      nombre: 'Ana',
      apellido: 'Lopez',
      correo: 'ana@test.com',
    });

    const clientQueue: OfflineSyncQueueItem[] = [
      {
        uuid_operacion: 'op-res-1',
        tipo_operacion: 'RESERVA',
        uuid_entidad: 'uuid-res-1',
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_reserva_offline: 'uuid-res-1',
          codigo_reserva: 'RSV-LOC-001',
          id_sucursal: 2,
          detalles: [{ id_variante_producto: 101, cantidad: 1 }],
        },
        reintentos: 0,
        created_at: '2026-11-05T10:00:00.000Z',
        updated_at: '2026-11-05T10:00:00.000Z',
      },
      {
        uuid_operacion: 'op-buy-2',
        tipo_operacion: 'COMPRA',
        uuid_entidad: 'uuid-buy-2',
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_venta_offline: 'uuid-buy-2',
          numero_venta_local: 'DIG-LOC-002',
          canal: 'DIGITAL',
          id_sucursal: 2,
          medio_pago: 'TARJETA',
          total: 250,
          detalles: [{ id_variante_producto: 202, cantidad: 1 }],
        },
        reintentos: 0,
        created_at: '2026-11-05T10:05:00.000Z',
        updated_at: '2026-11-05T10:05:00.000Z',
      },
    ];

    mockStorage.getOfflineQueue.mockResolvedValue(clientQueue);

    const mockBackendResponse: OfflineQueueSyncResponse = {
      success: true,
      empresa_id: 1,
      id_usuario: 10,
      rol: 'CLIENTE',
      total_operaciones: 2,
      confirmadas: 2,
      rechazadas: 0,
      en_conflicto: 0,
      reintentables: 0,
      resultados: [
        {
          uuid_operacion: 'op-res-1',
          uuid_entidad: 'uuid-res-1',
          tipo_operacion: 'RESERVA',
          secuencia: 1,
          confirmada: true,
          estado_resultado: 'CONFIRMADA',
          estado_sincronizacion: 'SINCRONIZADA',
          id_servidor: 77,
          codigo_servidor: 'RSV-20261105-OFICIAL77',
          reintentable: false,
          conservar_en_cola: false,
          fecha_sincronizacion: '2026-11-05T10:10:00.000Z',
        },
        {
          uuid_operacion: 'op-buy-2',
          uuid_entidad: 'uuid-buy-2',
          tipo_operacion: 'COMPRA',
          secuencia: 2,
          confirmada: true,
          estado_resultado: 'CONFIRMADA',
          estado_sincronizacion: 'SINCRONIZADA',
          id_servidor: 301,
          codigo_servidor: 'DIG-OFICIAL-301',
          estado_entidad_servidor: 'PENDIENTE',
          estado_pago: 'PENDIENTE',
          pago_simulado: true,
          reintentable: false,
          conservar_en_cola: false,
          fecha_sincronizacion: '2026-11-05T10:10:00.000Z',
        },
      ],
      resultados_por_uuid: {},
      vinculaciones_codigos: {
        'uuid-res-1': {
          referencia_local: 'uuid-res-1',
          tipo_operacion: 'RESERVA',
          id_servidor: 77,
          codigo_servidor: 'RSV-20261105-OFICIAL77',
        },
      },
      fecha_sincronizacion: '2026-11-05T10:10:00.000Z',
      mensaje: 'Sincronización completada: 2 de 2 operaciones confirmadas.',
    };

    const syncPromise = service.syncPendingOperations({ manual: true });
    await flushPromises();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/offline/sincronizar`);
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('Authorization')).toBe('Bearer mock-jwt-token');
    expect(req.request.body.operaciones.length).toBe(2);
    expect(req.request.body.operaciones[0].tipo_operacion).toBe('RESERVA');
    expect(req.request.body.operaciones[1].tipo_operacion).toBe('COMPRA');

    req.flush(mockBackendResponse);

    const result = await syncPromise;
    expect(result.success).toBe(true);
    expect(result.confirmadas).toBe(2);
    expect(mockStorage.applyBatchSyncResults).toHaveBeenCalledWith(
      1,
      10,
      mockBackendResponse.resultados,
      mockBackendResponse.vinculaciones_codigos,
    );
  });

  it('2. Secuencia estricta y dependencias del cajero: CONFIRMAR -> ATENDER -> VENTA por reserva -> VENTA directa', async () => {
    mockSession.getUser.mockReturnValue({
      id_usuario: 25,
      id_empresa: 1,
      rol: 'CAJERO',
      nombre: 'Carlos',
      apellido: 'Perez',
      correo: 'carlos@test.com',
    });

    // Cola desordenada localmente
    const staffQueue: OfflineSyncQueueItem[] = [
      {
        uuid_operacion: 'op-sale-res-3',
        tipo_operacion: 'VENTA',
        uuid_entidad: 'uuid-sale-res-3',
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_venta_offline: 'uuid-sale-res-3',
          canal: 'PRESENCIAL',
          id_reserva: 74500123,
          depende_de_uuid: 'op-trans-attend-2',
          medio_pago: 'EFECTIVO',
          total: 150,
        },
        reintentos: 0,
        created_at: '2026-11-05T11:03:00.000Z',
        updated_at: '2026-11-05T11:03:00.000Z',
      },
      {
        uuid_operacion: 'op-direct-sale-4',
        tipo_operacion: 'VENTA',
        uuid_entidad: 'uuid-direct-sale-4',
        estado: 'REGISTRADA_LOCAL',
        payload: {
          uuid_venta_offline: 'uuid-direct-sale-4',
          canal: 'PRESENCIAL',
          medio_pago: 'EFECTIVO',
          total: 300,
        },
        reintentos: 0,
        created_at: '2026-11-05T11:04:00.000Z',
        updated_at: '2026-11-05T11:04:00.000Z',
      },
      {
        uuid_operacion: 'op-trans-attend-2',
        tipo_operacion: 'TRANSICION_RESERVA',
        uuid_entidad: 'uuid-res-55',
        estado: 'ATENDIDA' as any,
        payload: {
          uuid_operacion_offline: 'op-trans-attend-2',
          uuid_reserva_offline: 'uuid-res-55',
          accion: 'attend',
        },
        reintentos: 0,
        created_at: '2026-11-05T11:02:00.000Z',
        updated_at: '2026-11-05T11:02:00.000Z',
      },
      {
        uuid_operacion: 'op-trans-confirm-1',
        tipo_operacion: 'TRANSICION_RESERVA',
        uuid_entidad: 'uuid-res-55',
        estado: 'CONFIRMADA' as any,
        payload: {
          uuid_operacion_offline: 'op-trans-confirm-1',
          uuid_reserva_offline: 'uuid-res-55',
          accion: 'confirm',
        },
        reintentos: 0,
        created_at: '2026-11-05T11:01:00.000Z',
        updated_at: '2026-11-05T11:01:00.000Z',
      },
    ];

    mockStorage.getOfflineQueue.mockResolvedValue(staffQueue);

    const syncPromise = service.syncPendingOperations({ manual: true });
    await flushPromises();

    const req = httpMock.expectOne(`${environment.apiUrl}/api/offline/sincronizar`);
    const sentOps = req.request.body.operaciones;

    expect(sentOps.length).toBe(4);
    // 1: CONFIRMAR
    expect(sentOps[0].uuid_operacion).toBe('op-trans-confirm-1');
    expect(sentOps[0].secuencia).toBe(1);
    expect(sentOps[0].payload.accion).toBe('confirm');

    // 2: ATENDER
    expect(sentOps[1].uuid_operacion).toBe('op-trans-attend-2');
    expect(sentOps[1].secuencia).toBe(2);
    expect(sentOps[1].payload.accion).toBe('attend');

    // 3: VENTA por reserva (dependiente)
    expect(sentOps[2].uuid_operacion).toBe('op-sale-res-3');
    expect(sentOps[2].secuencia).toBe(3);
    expect(sentOps[2].depende_de_uuid).toBe('op-trans-attend-2');

    // 4: VENTA directa independiente
    expect(sentOps[3].uuid_operacion).toBe('op-direct-sale-4');
    expect(sentOps[3].secuencia).toBe(4);

    req.flush({
      success: true,
      empresa_id: 1,
      id_usuario: 25,
      rol: 'CAJERO',
      total_operaciones: 4,
      confirmadas: 4,
      rechazadas: 0,
      en_conflicto: 0,
      reintentables: 0,
      resultados: [],
      resultados_por_uuid: {},
      vinculaciones_codigos: {},
      fecha_sincronizacion: new Date().toISOString(),
      mensaje: 'Sincronizado',
    });

    await syncPromise;
  });

  it('3. Mutex de concurrencia: bloquea ejecuciones simultáneas y reutiliza la promesa en vuelo sin peticiones duplicadas', async () => {
    mockSession.getUser.mockReturnValue({
      id_usuario: 25,
      id_empresa: 1,
      rol: 'CAJERO',
    });

    mockStorage.getOfflineQueue.mockResolvedValue([
      {
        uuid_operacion: 'op-1',
        tipo_operacion: 'VENTA',
        uuid_entidad: 'uuid-1',
        estado: 'REGISTRADA_LOCAL',
        payload: { canal: 'PRESENCIAL', total: 100 },
        reintentos: 0,
        created_at: '2026-11-05T12:00:00.000Z',
        updated_at: '2026-11-05T12:00:00.000Z',
      },
    ]);

    // Lanzar primera sincronización
    const firstCall = service.syncPendingOperations({ manual: true });
    expect(service.isSyncing()).toBe(true);

    // Intentar segunda sincronización mientras la primera está en curso
    const secondCall = service.syncPendingOperations({ auto: true });
    await flushPromises();

    // Debe existir EXACTAMENTE 1 petición HTTP en vuelo
    const requests = httpMock.match(`${environment.apiUrl}/api/offline/sincronizar`);
    expect(requests.length).toBe(1);

    requests[0].flush({
      success: true,
      total_operaciones: 1,
      confirmadas: 1,
      rechazadas: 0,
      en_conflicto: 0,
      reintentables: 0,
      resultados: [],
      resultados_por_uuid: {},
      vinculaciones_codigos: {},
      fecha_sincronizacion: new Date().toISOString(),
      mensaje: 'OK',
    });

    const [res1, res2] = await Promise.all([firstCall, secondCall]);
    expect(res1.success).toBe(true);
    expect(res2.success).toBe(true);
    expect(service.isSyncing()).toBe(false);
  });

  it('4. Caída de red conserva intacta la cola y conflictos individuales se procesan para CU14 sin abortar el lote', async () => {
    mockSession.getUser.mockReturnValue({
      id_usuario: 25,
      id_empresa: 1,
      rol: 'CAJERO',
    });

    const testQueue: OfflineSyncQueueItem[] = [
      {
        uuid_operacion: 'op-conflicto-stock',
        tipo_operacion: 'VENTA',
        uuid_entidad: 'uuid-sale-conflicto',
        estado: 'REGISTRADA_LOCAL',
        payload: { canal: 'PRESENCIAL', total: 400 },
        reintentos: 0,
        created_at: '2026-11-05T12:00:00.000Z',
        updated_at: '2026-11-05T12:00:00.000Z',
      },
      {
        uuid_operacion: 'op-confirmada',
        tipo_operacion: 'VENTA',
        uuid_entidad: 'uuid-sale-ok',
        estado: 'REGISTRADA_LOCAL',
        payload: { canal: 'PRESENCIAL', total: 200 },
        reintentos: 0,
        created_at: '2026-11-05T12:01:00.000Z',
        updated_at: '2026-11-05T12:01:00.000Z',
      },
    ];

    mockStorage.getOfflineQueue.mockResolvedValue(testQueue);

    // 4.A: Caída de red preserva la cola
    const networkFailPromise = service.syncPendingOperations({ manual: true });
    await flushPromises();
    const req1 = httpMock.expectOne(`${environment.apiUrl}/api/offline/sincronizar`);
    req1.error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });

    let networkErrorCaught = false;
    try {
      await networkFailPromise;
    } catch (err: any) {
      networkErrorCaught = true;
      expect(err.message).toContain('Caída de conexión');
      // No debe llamar applyBatchSyncResults para preservar la cola intacta
      expect(mockStorage.applyBatchSyncResults).not.toHaveBeenCalled();
    }
    expect(networkErrorCaught).toBe(true);
    expect(service.isSyncing()).toBe(false);

    // 4.B: Manejo de lote con conflicto y operación confirmada
    const mixedResults: OfflineSyncOperationResult[] = [
      {
        uuid_operacion: 'op-conflicto-stock',
        uuid_entidad: 'uuid-sale-conflicto',
        tipo_operacion: 'VENTA',
        secuencia: 1,
        confirmada: false,
        estado_resultado: 'EN_CONFLICTO',
        estado_sincronizacion: 'CONFLICTO',
        motivo: 'Stock disponible insuficiente para prenda',
        conflictos: [
          {
            tipo_conflicto: 'STOCK_INSUFICIENTE',
            detalle: 'Stock disponible 0, solicitado 2',
          },
        ],
        reintentable: false,
        conservar_en_cola: true,
        fecha_sincronizacion: new Date().toISOString(),
      },
      {
        uuid_operacion: 'op-confirmada',
        uuid_entidad: 'uuid-sale-ok',
        tipo_operacion: 'VENTA',
        secuencia: 2,
        confirmada: true,
        estado_resultado: 'CONFIRMADA',
        estado_sincronizacion: 'SINCRONIZADA',
        id_servidor: 888,
        codigo_servidor: 'VTA-OFICIAL-888',
        reintentable: false,
        conservar_en_cola: false,
        fecha_sincronizacion: new Date().toISOString(),
      },
    ];

    const mixedPromise = service.syncPendingOperations({ manual: true });
    await flushPromises();
    const req2 = httpMock.expectOne(`${environment.apiUrl}/api/offline/sincronizar`);
    req2.flush({
      success: false,
      empresa_id: 1,
      id_usuario: 25,
      rol: 'CAJERO',
      total_operaciones: 2,
      confirmadas: 1,
      en_conflicto: 1,
      rechazadas: 0,
      reintentables: 0,
      resultados: mixedResults,
      resultados_por_uuid: {},
      vinculaciones_codigos: {},
      fecha_sincronizacion: new Date().toISOString(),
      mensaje: 'Procesada parcialmente',
    });

    const mixedResp = await mixedPromise;
    expect(mixedResp.confirmadas).toBe(1);
    expect(mixedResp.en_conflicto).toBe(1);
    expect(mockStorage.applyBatchSyncResults).toHaveBeenCalledWith(
      1,
      25,
      mixedResults,
      expect.any(Object),
    );
  });
});
