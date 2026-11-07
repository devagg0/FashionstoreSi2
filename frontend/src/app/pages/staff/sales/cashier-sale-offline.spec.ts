import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  OfflinePurchaseDetailLocal,
  OfflinePurchaseLocal,
  OfflineSyncQueueItem,
} from '../../../core/models/offline.model';
import { OfflineStorageService } from '../../../core/services/offline-storage.service';
import { OfflineService } from '../../../core/services/offline.service';
import { SessionService } from '../../../core/services/session.service';
import { StaffSalesService } from '../../../core/services/staff-sales.service';

describe('PK08 - CU11: Venta directa offline del CAJERO (POS FashionStore)', () => {
  let cashierUser: {
    id_usuario: number;
    nombre: string;
    apellido: string;
    rol: string;
    id_empresa: number;
  };

  let savedPurchases: OfflinePurchaseLocal[];
  let savedDetails: OfflinePurchaseDetailLocal[];
  let savedQueue: OfflineSyncQueueItem[];

  let storageMock: Record<string, unknown>;
  let salesService: StaffSalesService;
  let offlineService: OfflineService;

  beforeEach(() => {
    sessionStorage.clear();
    cashierUser = {
      id_usuario: 10,
      nombre: 'Carlos',
      apellido: 'Cajero',
      rol: 'CAJERO',
      id_empresa: 1,
    };

    savedPurchases = [];
    savedDetails = [];
    savedQueue = [];

    storageMock = {
      getStoredPackageSummary: async () => ({
        metadata: {
          id_empresa: 1,
          id_usuario: 10,
          version: 'pkg-cajero-v1',
          sucursales_autorizadas_ids: [1, 2],
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
        {
          id_sucursal: 2,
          id_ciudad: 2,
          ciudad: 'Cochabamba',
          nombre: 'Sucursal Prado',
          direccion: 'Av. Ballivián #500',
          estado: true,
        },
      ],
      getCatalogProducts: async () => [
        {
          id_producto: 101,
          id_categoria: 1,
          categoria: 'Camisas',
          nombre: 'Camisa Lino Premium',
          seccion: 'HOMBRE',
          precio: 250,
          precio_base: 250,
          precio_final: 250,
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
          color: 'Azul Marino',
          sku: 'CAM-LIN-M-AZU',
          precio: 250,
          estado: true,
        },
      ],
      getInventory: async () => [
        {
          id_inventario_sucursal: 501,
          id_sucursal: 1,
          id_variante_producto: 201,
          stock_actual: 5,
          stock_reservado: 0,
          stock_disponible: 5,
          stock_minimo: 1,
          updated_at: '2026-11-02T10:00:00Z',
        },
      ],
      getPendingReservedQuantities: async () => new Map<string, number>([['1_201', 1]]), // 1 unidad pendiente
      getOfflinePurchases: async () => savedPurchases,
      getOfflinePurchaseDetails: async () => savedDetails,
      saveOfflinePurchaseAtomic: async (
        _empresaId: number,
        _userId: number,
        purchase: OfflinePurchaseLocal,
        details: OfflinePurchaseDetailLocal[],
        queueItem: OfflineSyncQueueItem,
      ) => {
        savedPurchases.push(purchase);
        savedDetails.push(...details);
        savedQueue.push(queueItem);
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

    salesService = TestBed.inject(StaffSalesService);
    offlineService = TestBed.inject(OfflineService);

    vi.spyOn(offlineService, 'isOnline').mockReturnValue(false);
    vi.spyOn(offlineService, 'resolveEffectiveCompanyId').mockReturnValue(1);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('1. carga sucursales autorizadas de tienda desde almacenamiento local offline sin conexión', async () => {
    const branchesResp = await firstValueFrom(salesService.getBranches());

    expect(branchesResp.success).toBe(true);
    expect(branchesResp.data.length).toBe(2);
    expect(branchesResp.data[0].id_sucursal).toBe(1);
    expect(branchesResp.data[0].nombre).toBe('Sucursal Central POS');
    expect(branchesResp.data[1].id_sucursal).toBe(2);
  });

  it('2. cotiza la venta presencial con precios locales y rechaza cuando no hay stock suficiente', async () => {
    // 5 en stock - 1 pendiente = 4 disponibles
    const quoteValid = await firstValueFrom(
      salesService.quoteSale({
        id_sucursal: 1,
        items: [{ id_variante_producto: 201, cantidad: 2 }],
      }),
    );

    expect(quoteValid.success).toBe(true);
    expect(quoteValid.data.sucursal.id_sucursal).toBe(1);
    expect(quoteValid.data.detalles.length).toBe(1);
    expect(quoteValid.data.detalles[0].sku).toBe('CAM-LIN-M-AZU');
    expect(quoteValid.data.detalles[0].cantidad).toBe(2);
    expect(quoteValid.data.detalles[0].precio_unitario).toBe('250.00');
    expect(quoteValid.data.subtotal).toBe('500.00');
    expect(quoteValid.data.total).toBe('500.00');

    // Intentar cotizar 5 unidades (excede los 4 disponibles)
    await expect(
      firstValueFrom(
        salesService.quoteSale({
          id_sucursal: 1,
          items: [{ id_variante_producto: 201, cantidad: 5 }],
        }),
      ),
    ).rejects.toThrow();
  });

  it('3. registra venta presencial local con ID seguro, número de venta y estado PENDIENTE', async () => {
    const idempotencyKey = 'a1b2c3d4-e5f6-47a8-b9c0-112233445566';
    const saleResp = await firstValueFrom(
      salesService.createSale(
        {
          id_sucursal: 1,
          items: [{ id_variante_producto: 201, cantidad: 1 }],
        },
        idempotencyKey,
      ),
    );

    expect(saleResp.success).toBe(true);
    expect(saleResp.data.estado).toBe('PENDIENTE');
    expect(saleResp.data.id_venta).toBeGreaterThanOrEqual(80000000);
    expect(saleResp.data.numero_venta).toContain('VTA-LOC-');
    expect(saleResp.data.total).toBe('250.00');
    expect(saleResp.data.sucursal.nombre).toBe('Sucursal Central POS');
    expect(saleResp.data.cajero.nombre).toBe('Carlos');
  });

  it('4. guarda de forma atómica la venta, pago (efectivo/simulado) y comprobante provisional en la cola de sincronización', async () => {
    const saleUuid = '99887766-5544-4321-ba09-fedcba098765';

    const result = await offlineService.registerCashierOfflineSale({
      uuid: saleUuid,
      idSucursal: 1,
      medioPago: 'EFECTIVO',
      items: [
        {
          id_variante_producto: 201,
          cantidad: 1,
          precio_unitario: 250,
        },
      ],
      now: new Date('2026-11-02T16:00:00Z'),
    });

    expect(result.success).toBe(true);
    expect(result.receipt).not.toBeNull();
    expect(result.receipt?.canal).toBe('PRESENCIAL');
    expect(result.receipt?.medio_pago).toBe('EFECTIVO');
    expect(result.receipt?.pago_simulado).toBe(false);
    expect(result.receipt?.mensaje_advertencia).toContain('COMPROBANTE PROVISIONAL POS OFFLINE');

    // Verificar persistencia atómica en almacenes
    expect(savedPurchases.length).toBe(1);
    expect(savedPurchases[0].uuid_venta_offline).toBe(saleUuid);
    expect(savedPurchases[0].canal).toBe('PRESENCIAL');
    expect(savedPurchases[0].estado).toBe('REGISTRADA_LOCAL');
    expect(savedPurchases[0].estado_pago).toBe('APROBADO');

    expect(savedDetails.length).toBe(1);
    expect(savedDetails[0].sku).toBe('CAM-LIN-M-AZU');

    // Verificar Outbox de sincronización con tipo VENTA
    expect(savedQueue.length).toBe(1);
    expect(savedQueue[0].tipo_operacion).toBe('VENTA');
    expect(savedQueue[0].uuid_entidad).toBe(saleUuid);
    expect(savedQueue[0].payload.canal).toBe('PRESENCIAL');
    expect(savedQueue[0].payload.medio_pago).toBe('EFECTIVO');
  });
});

