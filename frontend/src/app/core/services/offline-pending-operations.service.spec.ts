import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { OfflinePendingOperationsService } from './offline-pending-operations.service';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';
import {
  OfflinePurchaseLocal,
  OfflineReservationLocal,
  OfflineSyncQueueItem,
} from '../models/offline.model';

describe('PK08 — CU12/CU13 Debugging: Consistencia de estados de sincronización de reservas offline', () => {
  let service: OfflinePendingOperationsService;
  let mockStorage: any;
  let mockSession: any;

  // 17 reservas descargadas del servidor en la caché local para atención offline
  const cachedDownloadedReservations: OfflineReservationLocal[] = Array.from(
    { length: 17 },
    (_, i) => ({
      uuid_reserva_offline: `RSV-SERVER-${i + 1}`,
      id_reserva: i + 1,
      codigo_local: `RSV-SERVER-${i + 1}`,
      id_empresa: 1,
      id_usuario: 100 + i,
      id_sucursal: 2,
      sucursal_nombre: 'Sucursal Central',
      cliente_nombre: `Cliente Online ${i + 1}`,
      estado: 'PENDIENTE' as const,
      total_referencial: 150.0,
      adelanto_efectivo: 0,
      saldo_pendiente: 150.0,
      fecha_reserva_offline: '2026-11-04T08:00:00.000Z',
      fecha_atencion_programada: '2026-11-05T12:00:00.000Z',
      observaciones: null,
      created_at: '2026-11-04T08:00:00.000Z',
      updated_at: '2026-11-04T08:00:00.000Z',
    }),
  );

  const realOfflineReservation: OfflineReservationLocal = {
    uuid_reserva_offline: 'uuid-offline-res-1',
    id_reserva: undefined,
    codigo_local: 'RSV-LOC-999',
    id_empresa: 1,
    id_usuario: 50,
    id_sucursal: 2,
    sucursal_nombre: 'Sucursal Central',
    cliente_nombre: 'Cliente Offline',
    estado: 'REGISTRADA_LOCAL' as const,
    total_referencial: 200.0,
    adelanto_efectivo: 0,
    saldo_pendiente: 200.0,
    fecha_reserva_offline: '2026-11-04T09:00:00.000Z',
    fecha_atencion_programada: '2026-11-05T15:00:00.000Z',
    observaciones: null,
    created_at: '2026-11-04T09:00:00.000Z',
    updated_at: '2026-11-04T09:00:00.000Z',
  };

  const realOfflineSales: OfflinePurchaseLocal[] = [1, 2, 3].map((num) => ({
    uuid_venta_offline: `uuid-pos-sale-${num}`,
    numero_venta_local: `POS-LOC-00${num}`,
    id_venta_local: 7000 + num,
    id_empresa: 1,
    id_usuario: 5,
    id_sucursal: 2,
    canal: 'PRESENCIAL',
    moneda: 'BOB',
    subtotal: 100.0 * num,
    descuento_total: 0,
    total: 100.0 * num,
    medio_pago: 'EFECTIVO',
    pago_simulado: false,
    referencia_pago_local: `EF-${num}`,
    estado_pago: 'APROBADO',
    estado: 'REGISTRADA_LOCAL',
    fecha_venta_offline: '2026-11-04T10:00:00.000Z',
    created_at: '2026-11-04T10:00:00.000Z',
    sucursal_nombre: 'Sucursal Central',
  }));

  const queueItems: OfflineSyncQueueItem[] = [
    {
      uuid_operacion: 'uuid-offline-res-1',
      tipo_operacion: 'RESERVA',
      uuid_entidad: 'uuid-offline-res-1',
      estado: 'REGISTRADA_LOCAL',
      payload: { uuid_reserva_offline: 'uuid-offline-res-1' },
      reintentos: 0,
      created_at: '2026-11-04T09:00:00.000Z',
      updated_at: '2026-11-04T09:00:00.000Z',
    },
    ...realOfflineSales.map((s) => ({
      uuid_operacion: s.uuid_venta_offline,
      tipo_operacion: 'VENTA' as const,
      uuid_entidad: s.uuid_venta_offline,
      estado: 'REGISTRADA_LOCAL' as const,
      payload: { uuid_venta_offline: s.uuid_venta_offline },
      reintentos: 0,
      created_at: s.fecha_venta_offline,
      updated_at: s.fecha_venta_offline,
    })),
    {
      uuid_operacion: 'trans-confirm-RSV-SERVER-1-1000',
      tipo_operacion: 'RESERVA',
      uuid_entidad: 'RSV-SERVER-1',
      estado: 'CONFIRMADA',
      payload: {
        accion: 'confirm',
        codigo_reserva: 'RSV-SERVER-1',
        id_sucursal: 2,
        fecha_transicion: '2026-11-04T10:30:00.000Z',
      },
      reintentos: 0,
      created_at: '2026-11-04T10:30:00.000Z',
      updated_at: '2026-11-04T10:30:00.000Z',
    },
    {
      uuid_operacion: 'trans-attend-RSV-SERVER-2-1001',
      tipo_operacion: 'RESERVA',
      uuid_entidad: 'RSV-SERVER-2',
      estado: 'ATENDIDA',
      payload: {
        accion: 'attend',
        codigo_reserva: 'RSV-SERVER-2',
        id_sucursal: 2,
        fecha_transicion: '2026-11-04T10:45:00.000Z',
      },
      reintentos: 0,
      created_at: '2026-11-04T10:45:00.000Z',
      updated_at: '2026-11-04T10:45:00.000Z',
    },
  ];

  beforeEach(() => {
    mockStorage = {
      getOfflineQueue: vi.fn().mockResolvedValue(queueItems),
      getOfflineReservations: vi
        .fn()
        .mockResolvedValue([...cachedDownloadedReservations, realOfflineReservation]),
      getOfflineReservationDetails: vi.fn().mockResolvedValue([]),
      getOfflinePurchases: vi.fn().mockResolvedValue(realOfflineSales),
      getOfflinePurchaseDetails: vi.fn().mockResolvedValue([]),
      getBranches: vi.fn().mockResolvedValue([
        { id_sucursal: 2, nombre: 'Sucursal Central', id_empresa: 1 },
      ]),
    };

    mockSession = {
      getUser: vi.fn().mockReturnValue({
        id_usuario: 5,
        id_empresa: 1,
        rol: 'CAJERO',
        nombre: 'Carlos',
        apellido: 'Perez',
      }),
      getAccessToken: () => 'valid-token',
    };

    TestBed.configureTestingModule({
      providers: [
        OfflinePendingOperationsService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: OfflineStorageService, useValue: mockStorage },
        {
          provide: OfflineService,
          useValue: { resolveEffectiveCompanyId: () => 1 },
        },
        {
          provide: SessionService,
          useValue: mockSession,
        },
      ],
    });

    service = TestBed.inject(OfflinePendingOperationsService);
  });

  it('1. Ignora reservas descargadas en caché y conserva las 6 operaciones reales como PENDIENTE', async () => {
    const ops = await service.loadLocalOperations();
    expect(ops.length).toBe(6);

    const serverReservationCodes = cachedDownloadedReservations.map((r) => r.codigo_local);
    const includedDownloaded = ops.filter(
      (op) => op.tipo === 'RESERVA' && serverReservationCodes.includes(op.codigo_provisional),
    );
    expect(includedDownloaded.length).toBe(0);

    const pendingOps = ops.filter((op) => op.estado_sincronizacion === 'PENDIENTE');
    expect(pendingOps.length).toBe(6);
    expect(ops.every((op) => op.confirmada_en_servidor === false)).toBe(true);
  });

  it('2. Reserva REINTENTABLE (RES-LOC-D231C891) nunca se clasifica como RECHAZADA; CONFIRMADA, RECHAZADA y EN_CONFLICTO mantienen estados coherentes', async () => {
    mockSession.getUser.mockReturnValue({
      id_usuario: 10,
      id_empresa: 1,
      rol: 'CLIENTE',
      nombre: 'Ana',
      apellido: 'Lopez',
    });

    const clientReservations: OfflineReservationLocal[] = [
      {
        uuid_reserva_offline: 'uuid-d231c891',
        codigo_local: 'RES-LOC-D231C891',
        id_empresa: 1,
        id_usuario: 10,
        id_sucursal: 2,
        sucursal_nombre: 'Sucursal Central',
        estado: 'REGISTRADA_LOCAL',
        total_referencial: 180,
        adelanto_efectivo: 0,
        saldo_pendiente: 180,
        fecha_reserva_offline: '2026-11-05T14:00:00.000Z',
        fecha_atencion_programada: '2026-11-06T15:00:00.000Z',
        motivo_servidor: 'Error interno temporal al procesar la operación; seguro para reintentar.',
        created_at: '2026-11-05T14:00:00.000Z',
        updated_at: '2026-11-05T14:05:00.000Z',
      },
      {
        uuid_reserva_offline: 'uuid-rejected-1',
        codigo_local: 'RES-LOC-REJ00001',
        id_empresa: 1,
        id_usuario: 10,
        id_sucursal: 2,
        sucursal_nombre: 'Sucursal Central',
        estado: 'RECHAZADA',
        total_referencial: 120,
        adelanto_efectivo: 0,
        saldo_pendiente: 120,
        fecha_reserva_offline: '2026-11-05T13:00:00.000Z',
        fecha_atencion_programada: '2026-11-05T23:30:00.000Z',
        motivo_servidor: 'La fecha programada está fuera del horario de atención de la sucursal.',
        created_at: '2026-11-05T13:00:00.000Z',
        updated_at: '2026-11-05T13:05:00.000Z',
      },
      {
        uuid_reserva_offline: 'uuid-synced-1',
        id_reserva: 88,
        codigo_local: 'RES-LOC-SYN00001',
        codigo_servidor: 'RSV-20261105-OFICIAL88',
        id_empresa: 1,
        id_usuario: 10,
        id_sucursal: 2,
        sucursal_nombre: 'Sucursal Central',
        estado: 'SINCRONIZADA',
        total_referencial: 250,
        adelanto_efectivo: 0,
        saldo_pendiente: 250,
        fecha_reserva_offline: '2026-11-05T12:00:00.000Z',
        fecha_atencion_programada: '2026-11-06T11:00:00.000Z',
        created_at: '2026-11-05T12:00:00.000Z',
        updated_at: '2026-11-05T12:10:00.000Z',
      },
    ];

    const clientQueue: OfflineSyncQueueItem[] = [
      {
        uuid_operacion: 'uuid-d231c891',
        tipo_operacion: 'RESERVA',
        uuid_entidad: 'uuid-d231c891',
        estado: 'PENDIENTE_SINCRONIZACION',
        payload: { uuid_reserva_offline: 'uuid-d231c891' },
        reintentos: 1,
        ultimo_error: 'Error interno temporal al procesar la operación; seguro para reintentar.',
        created_at: '2026-11-05T14:00:00.000Z',
        updated_at: '2026-11-05T14:05:00.000Z',
      },
      {
        uuid_operacion: 'uuid-rejected-1',
        tipo_operacion: 'RESERVA',
        uuid_entidad: 'uuid-rejected-1',
        estado: 'RECHAZADA',
        payload: { uuid_reserva_offline: 'uuid-rejected-1' },
        reintentos: 1,
        ultimo_error: 'La fecha programada está fuera del horario de atención de la sucursal.',
        created_at: '2026-11-05T13:00:00.000Z',
        updated_at: '2026-11-05T13:05:00.000Z',
      },
      {
        uuid_operacion: 'uuid-synced-1',
        tipo_operacion: 'RESERVA',
        uuid_entidad: 'uuid-synced-1',
        estado: 'SINCRONIZADA',
        payload: {
          uuid_reserva_offline: 'uuid-synced-1',
          id_servidor: 88,
          codigo_servidor: 'RSV-20261105-OFICIAL88',
        },
        reintentos: 0,
        created_at: '2026-11-05T12:00:00.000Z',
        updated_at: '2026-11-05T12:10:00.000Z',
      },
    ];

    mockStorage.getOfflineReservations.mockResolvedValue(clientReservations);
    mockStorage.getOfflineQueue.mockResolvedValue(clientQueue);
    mockStorage.getOfflinePurchases.mockResolvedValue([]);

    const ops = await service.loadLocalOperations();
    expect(ops.length).toBe(3);

    const retryOp = ops.find((o) => o.codigo_provisional === 'RES-LOC-D231C891')!;
    expect(retryOp).toBeDefined();
    expect(retryOp.estado_sincronizacion).toBe('PENDIENTE');
    expect(retryOp.estado_sincronizacion).not.toBe('RECHAZADA');
    expect(retryOp.motivo_servidor).toContain('seguro para reintentar');

    const rejectedOp = ops.find((o) => o.codigo_provisional === 'RES-LOC-REJ00001')!;
    expect(rejectedOp.estado_sincronizacion).toBe('RECHAZADA');
    expect(rejectedOp.motivo_servidor).toContain('fuera del horario');

    const syncedOp = ops.find((o) => o.codigo_provisional === 'RES-LOC-SYN00001')!;
    expect(syncedOp.estado_sincronizacion).toBe('SINCRONIZADA');
    expect(syncedOp.confirmada_en_servidor).toBe(true);
    expect(syncedOp.codigo_servidor).toBe('RSV-20261105-OFICIAL88');
  });
});
