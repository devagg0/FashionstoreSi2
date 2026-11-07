import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { environment } from '../../../environments/environment';
import { OfflinePurchaseReceiptData } from '../../core/models/offline.model';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { PurchasesPage } from './purchases';

const base = `${environment.apiUrl}/api/client/purchases`;

const mockOfflinePurchase: OfflinePurchaseReceiptData = {
  uuid_venta_offline: 'uuid-offline-compra-1',
  numero_venta_local: 'DIG-LOC-ABCD1234',
  id_venta_local: 80001234,
  fecha_registro: '2026-11-03T10:00:00Z',
  canal: 'DIGITAL',
  sucursal: {
    id_sucursal: 2,
    nombre: 'Sucursal Centro',
    direccion: 'Av. 16 de Julio #100',
  },
  cliente: {
    nombre: 'Ana',
    apellido: 'Cliente',
    correo: 'ana@example.com',
  },
  detalles: [
    {
      id_detalle_local: 1,
      uuid_venta_offline: 'uuid-offline-compra-1',
      id_variante_producto: 301,
      id_producto: 101,
      producto_nombre: 'Vestido Bohemio',
      sku: 'VES-BOH-M-AZU',
      talla: 'M',
      color: 'Azul',
      cantidad: 1,
      precio_unitario: 280,
      descuento_unitario: 0,
      subtotal_linea: 280,
    },
  ],
  subtotal: 280,
  descuento_total: 0,
  total: 280,
  moneda: 'BOB',
  medio_pago: 'QR',
  pago_simulado: true,
  referencia_pago: 'SIM-QR-ABCD1234',
  estado_venta: 'PENDIENTE',
  estado_pago: 'PENDIENTE_VALIDACION',
  comprobante_provisional: true,
  mensaje_advertencia: 'COMPROBANTE PROVISIONAL DIGITAL OFFLINE',
};

describe('PK08 - CU11: Debugging Mis Compras Offline (FashionStore)', () => {
  let fixture: ComponentFixture<PurchasesPage>;
  let page: PurchasesPage;
  let http: HttpTestingController;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let offlineServiceMock: {
    isOnline: ReturnType<typeof vi.fn>;
    getPendingClientPurchases: ReturnType<typeof vi.fn>;
    getOfflinePurchaseReceipt: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    if (typeof sessionStorage !== 'undefined') sessionStorage.clear();
    params = new BehaviorSubject(convertToParamMap({}));

    offlineServiceMock = {
      isOnline: vi.fn().mockReturnValue(false),
      getPendingClientPurchases: vi.fn().mockResolvedValue([mockOfflinePurchase]),
      getOfflinePurchaseReceipt: vi.fn().mockResolvedValue(mockOfflinePurchase),
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: params } },
        {
          provide: SessionService,
          useValue: {
            getAccessToken: () => 'fake-token',
            getUser: () => ({ id_usuario: 5, rol: 'CLIENTE', id_empresa: 1 }),
          },
        },
        { provide: CheckoutNavigationService, useValue: { go: vi.fn() } },
        { provide: OfflineService, useValue: offlineServiceMock },
      ],
    });

    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    http?.verify();
    fixture?.destroy();
  });

  it('1. sin internet, muestra compras locales con importe, fecha, comprobante y estado "Compra simulada localmente — pendiente de sincronización" sin error de conexión y contador "1 compra"', async () => {
    offlineServiceMock.isOnline.mockReturnValue(false);
    fixture = TestBed.createComponent(PurchasesPage);
    page = fixture.componentInstance;
    fixture.detectChanges();

    // Esperar resolución de promesas locales de IndexedDB
    await fixture.whenStable();
    fixture.detectChanges();

    // No se deben realizar llamadas HTTP al backend estando offline
    http.expectNone((r) => r.url.startsWith(base));

    const text = fixture.nativeElement.textContent as string;

    // 1. Contador de compras debe ser "1 compra", NO "0 compras"
    expect(page.totalCount()).toBe(1);
    expect(text).toContain('1 compra · Más recientes primero');

    // 2. NO debe mostrar error de conexión ni mensaje de fallo
    expect(page.error()).toBe('');
    expect(text).not.toContain('No pudimos cargar tus compras');
    expect(text).not.toContain('No pudimos conectar');

    // 3. Debe mostrar el estado exacto requerido
    expect(text).toContain('Compra simulada localmente — pendiente de sincronización');

    // 4. Debe mostrar importe, fecha y datos de la compra local
    expect(text).toContain('280,00');
    expect(text).toContain('Sucursal Centro');
    expect(text).toContain('QR');

    // 5. Debe contener enlace al comprobante provisional
    const receiptLink = fixture.nativeElement.querySelector(
      'a[href="/mis-compras/80001234/comprobante"]',
    );
    expect(receiptLink).not.toBeNull();
    expect(receiptLink?.textContent).toContain('Ver comprobante');
  });

  it('2. sin internet, los filtros de estado y canal aplican correctamente sobre las compras locales y actualizan el contador', async () => {
    offlineServiceMock.isOnline.mockReturnValue(false);
    fixture = TestBed.createComponent(PurchasesPage);
    page = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    // Filtro PENDIENTE (la compra simulada está pendiente de sincronización)
    page.filter('PENDIENTE', '');
    fixture.detectChanges();
    expect(page.filteredPendingLocal().length).toBe(1);
    expect(page.totalCount()).toBe(1);

    // Filtro DIGITAL (coincide con el canal de la compra digital)
    page.filter('', 'DIGITAL');
    fixture.detectChanges();
    expect(page.filteredPendingLocal().length).toBe(1);
    expect(page.totalCount()).toBe(1);

    // Filtro PRESENCIAL (no coincide -> 0 compras)
    page.filter('', 'PRESENCIAL');
    fixture.detectChanges();
    expect(page.filteredPendingLocal().length).toBe(0);
    expect(page.totalCount()).toBe(0);

    // Filtro COMPLETADA (la compra simulada no está completada por el banco -> 0)
    page.filter('COMPLETADA', '');
    fixture.detectChanges();
    expect(page.filteredPendingLocal().length).toBe(0);
    expect(page.totalCount()).toBe(0);

    // Limpiar filtros -> vuelve a mostrar 1 compra
    page.filter('', '');
    fixture.detectChanges();
    expect(page.filteredPendingLocal().length).toBe(1);
    expect(page.totalCount()).toBe(1);
  });

  it('3. con internet, ante fallo de conexión en línea (status 0), no muestra error si existen compras locales pendientes', async () => {
    // Simulamos que el navegador reporta estar online inicialmente
    offlineServiceMock.isOnline.mockReturnValue(true);
    fixture = TestBed.createComponent(PurchasesPage);
    page = fixture.componentInstance;
    fixture.detectChanges();

    // El componente intenta consultar el backend
    const req = http.expectOne((r) => r.url === base);
    expect(req.request.method).toBe('GET');

    // La red falla (status 0: error de conexión)
    req.error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });

    await fixture.whenStable();
    fixture.detectChanges();

    // Al existir compras locales en IndexedDB, NO se muestra error de conexión
    expect(page.error()).toBe('');
    const text = fixture.nativeElement.textContent as string;
    expect(text).not.toContain('No pudimos cargar tus compras');
    expect(text).toContain('Compra simulada localmente — pendiente de sincronización');
    expect(page.totalCount()).toBe(1);
  });
});

