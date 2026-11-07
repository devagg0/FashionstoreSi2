import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  OfflinePurchaseDetailLocal,
  OfflinePurchaseLocal,
  OfflineReservationDetailLocal,
  OfflineReservationLocal,
  OfflineSyncQueueItem,
} from '../../../core/models/offline.model';
import { OfflineStorageService } from '../../../core/services/offline-storage.service';
import { OfflineService } from '../../../core/services/offline.service';
import { SessionService } from '../../../core/services/session.service';
import { StaffReservationsService } from '../../../core/services/staff-reservations.service';
import { StaffSalesService } from '../../../core/services/staff-sales.service';

describe('PK08 - CU11: Cajero - Atención y Venta por Reserva Offline (FashionStore)', () => {
  let cashierUser: {
    id_usuario: number;
    nombre: string;
    apellido: string;
    rol: string;
    id_empresa: number;
  };

  let localReservations: OfflineReservationLocal[];
  let localReservationDetails: OfflineReservationDetailLocal[];
  let localPurchases: OfflinePurchaseLocal[];
  let localPurchaseDetails: OfflinePurchaseDetailLocal[];
  let localSyncQueue: OfflineSyncQueueItem[];

  let storageMock: Record<string, unknown>;
  let reservationsService: StaffReservationsService;
  let salesService: StaffSalesService;
  let offlineService: OfflineService;

  beforeEach(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.clear();
    cashierUser = {
      id_usuario: 10,
      nombre: 'Carlos',
      apellido: 'Cajero',
      rol: 'CAJERO',
      id_empresa: 1,
    };

    localReservations = [
      {
        uuid_reserva_offline: 'res-uuid-001',
        codigo_local: 'RES-001',
        id_reserva: 7001,
        id_empresa: 1,
        id_usuario: 20,
        id_cliente: 20,
        cliente_nombre: 'Maria',
        cliente_apellido: 'Gomez',
        cliente_correo: 'maria@example.com',
        id_sucursal: 1,
        fecha_reserva_offline: '2026-11-02T10:00:00Z',
        fecha_atencion_programada: '2026-11-03T15:00:00Z',
        fecha_expiracion: '2026-11-03T18:00:00Z',
        estado: 'PENDIENTE',
        total_referencial: 500,
        saldo_pendiente: 500,
        created_at: '2026-11-02T10:00:00Z',
        updated_at: '2026-11-02T10:00:00Z',
      },
      {
        uuid_reserva_offline: 'res-uuid-002',
        codigo_local: 'RES-002',
        id_reserva: 7002,
        id_empresa: 1,
        id_usuario: 21,
        id_cliente: 21,
        cliente_nombre: 'Juan',
        cliente_apellido: 'Perez',
        cliente_correo: 'juan@example.com',
        id_sucursal: 1,
        fecha_reserva_offline: '2026-11-02T11:00:00Z',
        fecha_atencion_programada: '2026-11-03T16:00:00Z',
        fecha_expiracion: '2026-11-03T19:00:00Z',
        estado: 'CONFIRMADA',
        total_referencial: 300,
        saldo_pendiente: 300,
        created_at: '2026-11-02T11:00:00Z',
        updated_at: '2026-11-02T11:00:00Z',
      },
    ];

    localReservationDetails = [
      {
        id_detalle_local: 1,
        uuid_reserva_offline: 'res-uuid-001',
        id_variante_producto: 201,
        id_producto: 101,
        producto_nombre: 'Vestido Seda Floral',
        sku: 'VES-SED-M-FLO',
        talla: 'M',
        color: 'Floral',
        cantidad: 2,
        precio_referencial: 250,
        subtotal: 500,
      },
      {
        id_detalle_local: 2,
        uuid_reserva_offline: 'res-uuid-002',
        id_variante_producto: 202,
        id_producto: 102,
        producto_nombre: 'Blusa Satín',
        sku: 'BLU-SAT-S-BLA',
        talla: 'S',
        color: 'Blanco',
        cantidad: 1,
        precio_referencial: 300,
        subtotal: 300,
      },
    ];

    localPurchases = [];
    localPurchaseDetails = [];
    localSyncQueue = [];

    storageMock = {
      getStoredPackageSummary: async () => ({
        metadata: {
          id_empresa: 1,
          id_usuario: 10,
          version: 'pkg-cajero-v1',
          sucursales_autorizadas_ids: [1],
        },
        isExpired: false,
        savedAt: '2026-11-02T10:00:00Z',
      }),
      getBranches: async () => [
        {
          id_sucursal: 1,
          id_ciudad: 1,
          ciudad: 'La Paz',
          nombre: 'Sucursal Central POS',
          direccion: 'Av. Arce #2000',
          estado: true,
        },
      ],
      getCatalogProducts: async () => [
        {
          id_producto: 101,
          id_categoria: 1,
          categoria: 'Vestidos',
          nombre: 'Vestido Seda Floral',
          seccion: 'MUJER',
          precio: 250,
          precio_base: 250,
          precio_final: 250,
          estado: true,
        },
        {
          id_producto: 102,
          id_categoria: 1,
          categoria: 'Blusas',
          nombre: 'Blusa Satín',
          seccion: 'MUJER',
          precio: 300,
          precio_base: 300,
          precio_final: 300,
          estado: true,
        },
      ],
      getVariants: async () => [
        {
          id_variante_producto: 201,
          id_producto: 101,
          id_talla: 2,
          talla: 'M',
          id_color: 3,
          color: 'Floral',
          sku: 'VES-SED-M-FLO',
          precio: 250,
          estado: true,
        },
        {
          id_variante_producto: 202,
          id_producto: 102,
          id_talla: 1,
          talla: 'S',
          id_color: 1,
          color: 'Blanco',
          sku: 'BLU-SAT-S-BLA',
          precio: 300,
          estado: true,
        },
      ],
      getInventory: async () => [
        {
          id_inventario_sucursal: 501,
          id_sucursal: 1,
          id_variante_producto: 201,
          stock_actual: 5,
          stock_reservado: 2,
          stock_disponible: 3,
          stock_minimo: 1,
          updated_at: '2026-11-02T10:00:00Z',
        },
      ],
      getPendingReservedQuantities: async () => new Map<string, number>(),
      getOfflineReservations: async () => localReservations,
      getOfflineReservationDetails: async (
        _empresaId: number,
        _userId: number,
        uuid?: string,
      ) => {
        if (uuid) {
          return localReservationDetails.filter((d) => d.uuid_reserva_offline === uuid);
        }
        return localReservationDetails;
      },
      updateOfflineReservationState: async (
        _empresaId: number,
        _userId: number,
        reservation: OfflineReservationLocal,
        queueItem?: OfflineSyncQueueItem,
      ) => {
        const idx = localReservations.findIndex(
          (r) => r.uuid_reserva_offline === reservation.uuid_reserva_offline,
        );
        if (idx >= 0) {
          localReservations[idx] = reservation;
        }
        if (queueItem) {
          localSyncQueue.push(queueItem);
        }
      },
      getOfflinePurchases: async () => localPurchases,
      getOfflinePurchaseDetails: async () => localPurchaseDetails,
      saveOfflinePurchaseAtomic: async (
        _empresaId: number,
        _userId: number,
        purchase: OfflinePurchaseLocal,
        details: OfflinePurchaseDetailLocal[],
        queueItem: OfflineSyncQueueItem,
      ) => {
        localPurchases.push(purchase);
        localPurchaseDetails.push(...details);
        localSyncQueue.push(queueItem);
      },
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: SessionService,
          useValue: {
            getUser: () => cashierUser,
            getAccessToken: () => 'fake-cashier-token',
          },
        },
        {
          provide: OfflineStorageService,
          useValue: storageMock,
        },
      ],
    });

    reservationsService = TestBed.inject(StaffReservationsService);
    salesService = TestBed.inject(StaffSalesService);
    offlineService = TestBed.inject(OfflineService);

    vi.spyOn(offlineService, 'isOnline').mockReturnValue(false);
    vi.spyOn(offlineService, 'resolveEffectiveCompanyId').mockReturnValue(1);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (typeof sessionStorage !== 'undefined') sessionStorage.clear();
  });

  it('1. consulta reservas offline previamente almacenadas y filtra por estado y sucursal', async () => {
    const listResp = await firstValueFrom(reservationsService.listReservations({ estado: 'PENDIENTE' }));

    expect(listResp.success).toBe(true);
    expect(listResp.data.length).toBe(1);
    expect(listResp.data[0].id_reserva).toBe(7001);
    expect(listResp.data[0].codigo).toBe('RES-001');
    expect(listResp.data[0].estado).toBe('PENDIENTE');
    expect(listResp.data[0].cliente.nombre).toBe('Maria');
    expect(listResp.data[0].sucursal.id_sucursal).toBe(1);

    const codeResp = await firstValueFrom(reservationsService.getReservationByCode('RES-002'));
    expect(codeResp.success).toBe(true);
    expect(codeResp.data.codigo).toBe('RES-002');
    expect(codeResp.data.estado).toBe('CONFIRMADA');
  });

  it('2. ejecuta transiciones PENDIENTE -> CONFIRMADA -> ATENDIDA offline y registra eventos en cola de sincronización', async () => {
    // 1. Confirmar preparación (PENDIENTE -> CONFIRMADA)
    const confirmResp = await firstValueFrom(reservationsService.confirmReservation(7001));
    expect(confirmResp.success).toBe(true);
    expect(confirmResp.data.estado).toBe('CONFIRMADA');

    const confirmedItem = localReservations.find((r) => r.id_reserva === 7001);
    expect(confirmedItem?.estado).toBe('CONFIRMADA');

    expect(localSyncQueue.length).toBe(1);
    expect(localSyncQueue[0].tipo_operacion).toBe('RESERVA');
    expect(localSyncQueue[0].payload.accion).toBe('confirm');
    expect(localSyncQueue[0].payload.estado_nuevo).toBe('CONFIRMADA');

    // 2. Marcar como atendida (CONFIRMADA -> ATENDIDA)
    const attendResp = await firstValueFrom(reservationsService.attendReservation(7001));
    expect(attendResp.success).toBe(true);
    expect(attendResp.data.estado).toBe('ATENDIDA');

    const attendedItem = localReservations.find((r) => r.id_reserva === 7001);
    expect(attendedItem?.estado).toBe('ATENDIDA');
    expect(attendedItem?.fecha_atencion).toBeDefined();

    expect(localSyncQueue.length).toBe(2);
    expect(localSyncQueue[1].payload.accion).toBe('attend');
    expect(localSyncQueue[1].payload.estado_nuevo).toBe('ATENDIDA');
  });

  it('3. cotiza venta desde reserva ATENDIDA, calcula liberaciones por venta parcial y rechaza si no está ATENDIDA o excede reserva', async () => {
    // 1. Rechaza cotización si la reserva está en PENDIENTE
    await expect(
      firstValueFrom(
        salesService.quoteSale({
          id_sucursal: 1,
          id_reserva: 7001,
          items: [{ id_variante_producto: 201, cantidad: 1 }],
        }),
      ),
    ).rejects.toThrow();

    // Marcamos la reserva 7001 como ATENDIDA
    localReservations[0].estado = 'ATENDIDA';

    // 2. Rechaza si la cantidad solicitada (3) supera la reservada (2)
    await expect(
      firstValueFrom(
        salesService.quoteSale({
          id_sucursal: 1,
          id_reserva: 7001,
          items: [{ id_variante_producto: 201, cantidad: 3 }],
        }),
      ),
    ).rejects.toThrow();

    // 3. Cotiza venta parcial: compra 1 de las 2 prendas reservadas -> 1 liberada
    const quote = await firstValueFrom(
      salesService.quoteSale({
        id_sucursal: 1,
        id_reserva: 7001,
        items: [{ id_variante_producto: 201, cantidad: 1 }],
      }),
    );

    expect(quote.success).toBe(true);
    expect(quote.data.id_reserva).toBe(7001);
    expect(quote.data.id_cliente).toBe(20);
    expect(quote.data.detalles.length).toBe(1);
    expect(quote.data.detalles[0].cantidad).toBe(1);
    expect(quote.data.detalles[0].precio_unitario).toBe('250.00');
    expect(quote.data.total).toBe('250.00');

    // Verificar cálculo de liberaciones
    expect(quote.data.liberaciones.length).toBe(1);
    expect(quote.data.liberaciones[0].id_variante_producto).toBe(201);
    expect(quote.data.liberaciones[0].cantidad_reservada).toBe(2);
    expect(quote.data.liberaciones[0].cantidad_compra).toBe(1);
    expect(quote.data.liberaciones[0].cantidad_liberar).toBe(1);
  });

  it('4. registra cobro (efectivo/simulado) de venta por reserva con UUID, comprobante provisional y evita duplicados', async () => {
    localReservations[0].estado = 'ATENDIDA';
    const saleUuid = '11223344-5566-4777-8888-99990000aaaa';

    // 1. Registrar venta por reserva cobrada con TARJETA simulada
    const result = await offlineService.registerCashierOfflineSale({
      uuid: saleUuid,
      idSucursal: 1,
      idReserva: 7001,
      medioPago: 'TARJETA',
      items: [
        {
          id_variante_producto: 201,
          cantidad: 2,
          precio_unitario: 250,
        },
      ],
      now: new Date('2026-11-03T16:30:00Z'),
    });

    expect(result.success).toBe(true);
    expect(result.receipt).not.toBeNull();
    expect(result.receipt?.canal).toBe('PRESENCIAL');
    expect(result.receipt?.medio_pago).toBe('TARJETA');
    expect(result.receipt?.pago_simulado).toBe(true);
    expect(result.receipt?.comprobante_provisional).toBe(true);
    expect(result.receipt?.total).toBe(500);

    // Verificar guardado en almacenamiento local
    expect(localPurchases.length).toBe(1);
    expect(localPurchases[0].id_reserva).toBe(7001);
    expect(localPurchases[0].cliente_nombre).toContain('Maria');
    expect(localPurchases[0].estado_pago).toBe('PENDIENTE_VALIDACION');

    // Verificar encolado de sincronización dependiente de la reserva
    expect(localSyncQueue.length).toBe(1);
    expect(localSyncQueue[0].tipo_operacion).toBe('VENTA');
    expect(localSyncQueue[0].payload.id_reserva).toBe(7001);
    expect(localSyncQueue[0].payload.codigo_reserva).toBe('RES-001');

    // 2. Prevenir venta duplicada para la misma reserva
    const duplicateUuid = 'bbbbcccc-dddd-4eee-8fff-111122223333';
    const dupResult = await offlineService.registerCashierOfflineSale({
      uuid: duplicateUuid,
      idSucursal: 1,
      idReserva: 7001,
      medioPago: 'EFECTIVO',
      items: [
        {
          id_variante_producto: 201,
          cantidad: 2,
        },
      ],
    });

    expect(dupResult.success).toBe(false);
    expect(dupResult.message).toContain('ya tiene una venta registrada');
    expect(localPurchases.length).toBe(1);
  });
});
