import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  OfflineCartItemLocal,
  OfflinePurchaseDetailLocal,
  OfflinePurchaseLocal,
  OfflineSyncQueueItem,
} from '../../core/models/offline.model';
import { ClientCartService } from '../../core/services/client-cart.service';
import { ClientCheckoutService } from '../../core/services/client-checkout.service';
import { OfflineStorageService } from '../../core/services/offline-storage.service';
import { OfflineService } from '../../core/services/offline.service';
import { PaymentsService } from '../../core/services/payments.service';
import { ReceiptsService } from '../../core/services/receipts.service';
import { SessionService } from '../../core/services/session.service';
import { ReceiptPage } from '../receipt/receipt';

describe('PK08 - CU11: Compra digital offline del CLIENTE (Web Angular PWA)', () => {
  let user: {
    id_usuario: number;
    id_cliente: number;
    nombre: string;
    apellido: string;
    correo: string;
    rol: string;
    id_empresa: number;
  };

  let savedPurchases: OfflinePurchaseLocal[];
  let savedDetails: OfflinePurchaseDetailLocal[];
  let savedQueue: OfflineSyncQueueItem[];
  let cartItems: OfflineCartItemLocal[];

  let storageMock: Record<string, unknown>;
  let offlineService: OfflineService;
  let cartService: ClientCartService;
  let checkoutService: ClientCheckoutService;
  let paymentsService: PaymentsService;

  beforeEach(() => {
    sessionStorage.clear();
    user = {
      id_usuario: 50,
      id_cliente: 12,
      nombre: 'Valeria',
      apellido: 'Mendoza',
      correo: 'valeria@cliente.com',
      rol: 'CLIENTE',
      id_empresa: 1,
    };

    savedPurchases = [];
    savedDetails = [];
    savedQueue = [];
    cartItems = [];

    storageMock = {
      getStoredPackageSummary: async () => ({
        metadata: {
          id_empresa: 1,
          id_usuario: 50,
          version: 'v-test-1',
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
          nombre: 'Sucursal Central',
          direccion: 'Av. 6 de Agosto #100',
          hora_apertura: '09:00:00',
          hora_cierre: '20:00:00',
          estado: true,
        },
      ],
      getCatalogProducts: async () => [
        {
          id_producto: 10,
          nombre: 'Vestido Bohemio Floral',
          precio: '150.00',
          precio_final: '150.00',
          estado: true,
          imagen_principal: 'https://example.com/vestido.jpg',
        },
      ],
      getVariants: async () => [
        {
          id_variante_producto: 25,
          id_producto: 10,
          id_talla: 2,
          talla: 'M',
          id_color: 3,
          color: 'Azul',
          color_hex: '#0000ff',
          sku: 'VES-BOH-M-AZU',
          precio: '150.00',
          estado: true,
        },
      ],
      getInventory: async () => [
        {
          id_sucursal: 1,
          id_variante_producto: 25,
          stock_actual: 10,
          stock_reservado: 2,
          stock_disponible: 8,
          stock_minimo: 1,
        },
      ],
      getClients: async () => [
        {
          id_cliente: 12,
          id_usuario: 50,
          nombre: 'Valeria',
          apellido: 'Mendoza',
          correo: 'valeria@cliente.com',
        },
      ],
      getOfflineCartItems: async () => [...cartItems],
      saveOfflineCartItem: async (_e: number, _u: number, item: OfflineCartItemLocal) => {
        const idx = cartItems.findIndex(
          (c) => c.id_variante_producto === item.id_variante_producto,
        );
        if (idx >= 0) cartItems[idx] = item;
        else cartItems.push(item);
      },
      removeOfflineCartItem: async (_e: number, _u: number, idVar: number) => {
        cartItems = cartItems.filter((c) => c.id_variante_producto !== idVar);
      },
      clearOfflineCart: async () => {
        cartItems = [];
      },
      getOfflineReservations: async () => [],
      getOfflineReservationDetails: async () => [],
      getOfflinePurchases: async () => [...savedPurchases],
      getOfflinePurchaseDetails: async (_e: number, _u: number, uuid?: string) =>
        savedDetails.filter((d) => !uuid || d.uuid_venta_offline === uuid),
      getOfflinePurchaseByLocalId: async (_e: number, _u: number, idLocal: number) =>
        savedPurchases.find((p) => p.id_venta_local === idLocal) ?? null,
      getPendingReservedQuantities: async () => {
        const map = new Map<string, number>();
        for (const p of savedPurchases) {
          if (
            p.estado === 'REGISTRADA_LOCAL' ||
            p.estado === 'PENDIENTE_VALIDACION' ||
            p.estado === 'ENVIADA'
          ) {
            for (const d of savedDetails.filter(
              (x) => x.uuid_venta_offline === p.uuid_venta_offline,
            )) {
              const key = `${p.id_sucursal}_${d.id_variante_producto}`;
              map.set(key, (map.get(key) ?? 0) + d.cantidad);
            }
          }
        }
        return map;
      },
      saveOfflinePurchaseAtomic: vi.fn(
        async (
          _e: number,
          _u: number,
          purchase: OfflinePurchaseLocal,
          details: OfflinePurchaseDetailLocal[],
          queueItem: OfflineSyncQueueItem,
        ) => {
          savedPurchases.push(purchase);
          savedDetails.push(...details);
          savedQueue.push(queueItem);
          cartItems = [];
        },
      ),
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: OfflineStorageService, useValue: storageMock },
        {
          provide: SessionService,
          useValue: {
            getUser: () => user,
            getAccessToken: () => 'token-valeria',
          },
        },
      ],
    });

    offlineService = TestBed.inject(OfflineService);
    cartService = TestBed.inject(ClientCartService);
    checkoutService = TestBed.inject(ClientCheckoutService);
    paymentsService = TestBed.inject(PaymentsService);

    // Forzar entorno offline en el servicio
    vi.spyOn(offlineService, 'isOnline').mockReturnValue(false);
    vi.spyOn(offlineService, 'resolveEffectiveCompanyId').mockReturnValue(1);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('1. Permite al cliente añadir prendas al carrito offline y calcular subtotales correctamente', async () => {
    const res = await firstValueFrom(cartService.addItem(25, 2));

    expect(res.success).toBe(true);
    expect(res.data.items.length).toBe(1);
    expect(res.data.items[0].nombre_producto).toBe('Vestido Bohemio Floral');
    expect(res.data.items[0].cantidad).toBe(2);
    expect(res.data.items[0].precio_final).toBe('150.00');
    expect(res.data.items[0].subtotal_linea).toBe('300.00');
    expect(res.data.total).toBe('300.00');
    expect(cartItems.length).toBe(1);
  });

  it('2. Permite ajustar cantidades y eliminar artículos del carrito offline', async () => {
    await firstValueFrom(cartService.addItem(25, 1));
    expect(cartItems[0].cantidad).toBe(1);

    // Modificar cantidad a 3
    const updateRes = await firstValueFrom(cartService.updateQuantity(25, 3));
    expect(updateRes.data.items[0].cantidad).toBe(3);
    expect(updateRes.data.total).toBe('450.00');

    // Eliminar artículo
    const removeRes = await firstValueFrom(cartService.removeItem(25));
    expect(removeRes.data.items.length).toBe(0);
    expect(removeRes.data.total).toBe('0.00');
    expect(cartItems.length).toBe(0);
  });

  it('3. Checkout offline crea venta digital pendiente con ID local numérico y moneda BOB', async () => {
    await firstValueFrom(cartService.addItem(25, 2));

    const checkoutRes = await firstValueFrom(checkoutService.confirm(999999, 1));
    expect(checkoutRes.success).toBe(true);
    expect(checkoutRes.data.id_venta).toBeGreaterThan(90000000);
    expect(checkoutRes.data.numero_venta).toMatch(/^DIG-LOC-\d{4}$/);
    expect(checkoutRes.data.moneda).toBe('BOB');
    expect(checkoutRes.data.estado).toBe('PENDIENTE');
    expect(checkoutRes.data.stock_comprometido).toBe(true);
    expect(checkoutRes.data.total).toBe('300.00');
    expect(checkoutRes.data.items.length).toBe(1);
  });

  it('4. Registra compra offline con pago QR simulado, encolando en Outbox con UUID idempotente', async () => {
    const uuid = '6ba7b810-9dad-11d1-80b4-00c04fd430c8';
    const result = await offlineService.registerClientOfflinePurchase({
      uuid,
      idSucursal: 1,
      medioPago: 'QR',
      items: [{ id_variante_producto: 25, cantidad: 2, precio_unitario: 150 }],
    });

    expect(result.success).toBe(true);
    expect(result.uuid_venta_offline).toBe(uuid);
    expect(result.receipt).not.toBeNull();
    expect(result.receipt?.medio_pago).toBe('QR');
    expect(result.receipt?.pago_simulado).toBe(true);
    expect(result.receipt?.total).toBe(300);

    // Verificación de persistencia atómica
    expect(storageMock['saveOfflinePurchaseAtomic']).toHaveBeenCalledTimes(1);
    expect(savedPurchases.length).toBe(1);
    expect(savedPurchases[0].canal).toBe('DIGITAL');
    expect(savedPurchases[0].moneda).toBe('BOB');
    expect(savedPurchases[0].medio_pago).toBe('QR');
    expect(savedQueue.length).toBe(1);
    expect(savedQueue[0].tipo_operacion).toBe('COMPRA');
    expect(savedQueue[0].payload.uuid_venta_offline).toBe(uuid);
  });

  it('5. Registra compra offline con pago TARJETA simulado y comprobante provisional sin cobro real', async () => {
    const uuid = 'a2b3c4d5-1111-2222-3333-444455556666';
    const result = await offlineService.registerClientOfflinePurchase({
      uuid,
      idSucursal: 1,
      medioPago: 'TARJETA',
      items: [{ id_variante_producto: 25, cantidad: 1, precio_unitario: 150 }],
    });

    expect(result.success).toBe(true);
    expect(result.receipt?.medio_pago).toBe('TARJETA');
    expect(result.receipt?.comprobante_provisional).toBe(true);
    expect(result.receipt?.mensaje_advertencia).toContain('COMPROBANTE PROVISIONAL OFFLINE');
    expect(result.receipt?.mensaje_advertencia).toContain('NO representa un débito bancario real');
    expect(savedPurchases[0].referencia_pago_local).toMatch(/^SIM-TARJETA-/);
  });

  it('6. Descuenta disponibilidad local estimada tras compras digitales offline registradas', async () => {
    // Inicialmente disponible: 8 unidades
    const mapInitial = await (storageMock['getPendingReservedQuantities'] as Function)();
    expect(mapInitial.get('1_25') ?? 0).toBe(0);

    // Cliente compra 3 unidades offline
    const uuid = 'e1e2e3e4-5555-6666-7777-888899990000';
    await offlineService.registerClientOfflinePurchase({
      uuid,
      idSucursal: 1,
      medioPago: 'QR',
      items: [{ id_variante_producto: 25, cantidad: 3, precio_unitario: 150 }],
    });

    const mapAfter = await (storageMock['getPendingReservedQuantities'] as Function)();
    expect(mapAfter.get('1_25')).toBe(3);
  });

  it('7. Idempotencia: enviar el mismo UUID no duplica registros y retorna comprobante existente', async () => {
    const uuid = 'idempotent-uuid-1234-5678-90ab';
    const first = await offlineService.registerClientOfflinePurchase({
      uuid,
      idSucursal: 1,
      medioPago: 'QR',
      items: [{ id_variante_producto: 25, cantidad: 1, precio_unitario: 150 }],
    });
    expect(first.alreadyStored).toBe(false);
    expect(savedPurchases.length).toBe(1);

    // Segundo llamado con el mismo UUID (clic repetido o reintento)
    const second = await offlineService.registerClientOfflinePurchase({
      uuid,
      idSucursal: 1,
      medioPago: 'QR',
      items: [{ id_variante_producto: 25, cantidad: 1, precio_unitario: 150 }],
    });
    expect(second.alreadyStored).toBe(true);
    expect(second.numero_venta_local).toBe(first.numero_venta_local);
    // No se vuelve a llamar a la persistencia atómica
    expect(storageMock['saveOfflinePurchaseAtomic']).toHaveBeenCalledTimes(1);
    expect(savedPurchases.length).toBe(1);
  });

  it('8. Rechaza la compra si la cantidad solicitada supera el stock disponible offline', async () => {
    const uuid = 'stock-exceeded-uuid';
    // Stock disponible es 8, intentamos pedir 15
    const result = await offlineService.registerClientOfflinePurchase({
      uuid,
      idSucursal: 1,
      medioPago: 'QR',
      items: [{ id_variante_producto: 25, cantidad: 15, precio_unitario: 150 }],
    });

    expect(result.success).toBe(false);
    expect(result.errors?.[0]).toContain('Stock offline insuficiente');
    expect(savedPurchases.length).toBe(0);
  });
});
