import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { OfflinePurchaseReceiptData } from '../../core/models/offline.model';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { ClientCheckoutService } from '../../core/services/client-checkout.service';
import { OfflineService } from '../../core/services/offline.service';
import { Payment, PaymentSale, PaymentsService } from '../../core/services/payments.service';
import { SessionService } from '../../core/services/session.service';
import { PaymentPage } from './payment';

const base = `${environment.apiUrl}/api`;
const key = '11111111-2222-4333-8444-555555555555';

const mockPresencialSale: PaymentSale = {
  id: 31,
  numero: 'VTA-DRAFT-31',
  sucursal: 'Sucursal Central',
  canal: 'PRESENCIAL',
  estado: 'PENDIENTE',
  fecha: '2026-09-17T18:00:00',
  subtotal: '350.00',
  descuento: '0.00',
  total: '350.00',
  items: [
    {
      id: 15,
      nombre: 'Vestido Seda',
      talla: 'M',
      color: 'Negro',
      cantidad: 1,
      precio: '350.00',
      subtotal: '350.00',
    },
  ],
};

const mockDigitalSale: PaymentSale = {
  id: 42,
  numero: 'DIG-DRAFT-42',
  sucursal: 'Sucursal Miraflores',
  canal: 'DIGITAL',
  estado: 'PENDIENTE',
  fecha: '2026-09-17T18:00:00',
  subtotal: '220.00',
  descuento: '0.00',
  total: '220.00',
  items: [
    {
      id: 20,
      nombre: 'Camisa Lino',
      talla: 'L',
      color: 'Blanco',
      cantidad: 1,
      precio: '220.00',
      subtotal: '220.00',
    },
  ],
};

describe('PaymentPage - Coherencia de confirmación offline vs online (CU11 Debugging)', () => {
  let fixture: ComponentFixture<PaymentPage>;
  let page: PaymentPage;
  let http: HttpTestingController;
  let paymentsApi: PaymentsService;
  let offlineServiceMock: {
    isOnline: ReturnType<typeof vi.fn>;
    getOfflinePurchaseReceipt: ReturnType<typeof vi.fn>;
    registerClientOfflinePurchase: ReturnType<typeof vi.fn>;
    registerCashierOfflineSale: ReturnType<typeof vi.fn>;
  };

  function setup(
    saleToLoad: PaymentSale,
    isOnline: boolean,
    userRole: 'CLIENTE' | 'CAJERO',
  ) {
    offlineServiceMock = {
      isOnline: vi.fn().mockReturnValue(isOnline),
      getOfflinePurchaseReceipt: vi.fn().mockResolvedValue(null),
      registerClientOfflinePurchase: vi.fn(),
      registerCashierOfflineSale: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ id: String(saleToLoad.id) }),
              queryParamMap: convertToParamMap({}),
            },
          },
        },
        { provide: CheckoutNavigationService, useValue: { go: vi.fn() } },
        { provide: OfflineService, useValue: offlineServiceMock },
        {
          provide: ClientCheckoutService,
          useValue: {
            presentation: () => null,
            offlineSale: () => null,
          },
        },
        {
          provide: SessionService,
          useValue: {
            getUser: () => ({ id_usuario: 1, rol: userRole }),
            getAccessToken: () => 'token-test',
          },
        },
      ],
    });

    paymentsApi = TestBed.inject(PaymentsService);
    http = TestBed.inject(HttpTestingController);

    paymentsApi.saveSale(saleToLoad);
    fixture = TestBed.createComponent(PaymentPage);
    page = fixture.componentInstance;
    fixture.detectChanges();
  }

  afterEach(() => {
    sessionStorage.clear();
  });

  it('1. Cliente offline (TARJETA/QR): muestra una sola confirmación coherente de simulación local pendiente de validación bancaria, sin el bloque online "PAGO APROBADO / Venta COMPLETADA" y con código reconciliado', async () => {
    setup(mockDigitalSale, false, 'CLIENTE');

    const receiptData: OfflinePurchaseReceiptData = {
      uuid_venta_offline: key,
      id_venta_local: 501,
      numero_venta_local: 'DIG-LOCAL-501',
      fecha_registro: new Date().toISOString(),
      canal: 'DIGITAL',
      sucursal: { id_sucursal: 1, nombre: 'Sucursal Miraflores' },
      cliente: null,
      cajero: null,
      medio_pago: 'TARJETA',
      pago_simulado: true,
      referencia_pago: 'REF-CARD-501',
      estado_venta: 'PENDIENTE',
      estado_pago: 'PENDIENTE_VALIDACION',
      comprobante_provisional: true,
      mensaje_advertencia: 'Operación simulada offline',
      subtotal: 220,
      descuento_total: 0,
      total: 220,
      moneda: 'BOB',
      detalles: [
        {
          uuid_venta_offline: key,
          id_variante_producto: 20,
          id_producto: 1,
          producto_nombre: 'Camisa Lino',
          sku: 'SKU-20',
          talla: 'L',
          color: 'Blanco',
          cantidad: 1,
          precio_unitario: 220,
          descuento_unitario: 0,
          subtotal_linea: 220,
        },
      ],
    };

    offlineServiceMock.registerClientOfflinePurchase.mockResolvedValue({
      success: true,
      id_venta_local: 501,
      numero_venta_local: 'DIG-LOCAL-501',
      receipt: receiptData,
    });

    page.choose('TARJETA');
    page.confirm();

    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;

    // 1. Debe mostrar confirmación coherente offline
    expect(text).toContain('SIMULACIÓN LOCAL EXITOSA');
    expect(text).toContain('Comprobante provisional de compra');
    expect(text).toContain('Simulación de pago local exitosa');
    expect(text).toContain('DIG-LOCAL-501');
    expect(text).toContain('pendiente de sincronización y validación bancaria');

    // 2. NO debe mostrar simultáneamente el bloque online ni afirmar venta COMPLETADA / PAGO APROBADO
    expect(text).not.toContain('PAGO APROBADO');
    expect(text).not.toContain('Pago realizado correctamente');
    expect(text).not.toContain('Venta COMPLETADA');

    // 3. Códigos reconciliados y consistentes en resumen y comprobante
    const summaryHeading = fixture.nativeElement.querySelector('.summary h2')?.textContent;
    expect(summaryHeading).toBe('DIG-LOCAL-501');
  });

  it('2. Cajero offline (EFECTIVO): indica cobro presencial registrado en caja, sin mensaje de pago bancario simulado y con códigos consistentes', async () => {
    setup(mockPresencialSale, false, 'CAJERO');

    const receiptData: OfflinePurchaseReceiptData = {
      uuid_venta_offline: key,
      id_venta_local: 601,
      numero_venta_local: 'VTA-LOCAL-601',
      fecha_registro: new Date().toISOString(),
      canal: 'PRESENCIAL',
      sucursal: { id_sucursal: 1, nombre: 'Sucursal Central' },
      cliente: null,
      cajero: null,
      medio_pago: 'EFECTIVO',
      pago_simulado: false,
      referencia_pago: 'REF-CASH-601',
      estado_venta: 'PENDIENTE',
      estado_pago: 'APROBADO',
      comprobante_provisional: true,
      mensaje_advertencia: 'Cobro en efectivo registrado en caja',
      subtotal: 350,
      descuento_total: 0,
      total: 350,
      moneda: 'BOB',
      detalles: [
        {
          uuid_venta_offline: key,
          id_variante_producto: 15,
          id_producto: 2,
          producto_nombre: 'Vestido Seda',
          sku: 'SKU-15',
          talla: 'M',
          color: 'Negro',
          cantidad: 1,
          precio_unitario: 350,
          descuento_unitario: 0,
          subtotal_linea: 350,
        },
      ],
    };

    offlineServiceMock.registerCashierOfflineSale.mockResolvedValue({
      success: true,
      id_venta_local: 601,
      numero_venta_local: 'VTA-LOCAL-601',
      receipt: receiptData,
    });

    page.choose('EFECTIVO');
    page.confirm();

    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;

    // 1. Debe indicar cobro en caja presencial y guardado local
    expect(text).toContain('COBRO PRESENCIAL REGISTRADO');
    expect(text).toContain('Cobro en efectivo registrado en caja');
    expect(text).toContain('Cobro presencial en caja: Se registró el cobro en efectivo');
    expect(text).toContain('Efectivo (en caja)');

    // 2. NO debe afirmar simulación de pago bancario
    expect(text).not.toContain('simulado sin conexión a internet y no constituye confirmación');

    // 3. NO debe mostrar bloque online "PAGO APROBADO / Venta COMPLETADA"
    expect(text).not.toContain('PAGO APROBADO');
    expect(text).not.toContain('Pago realizado correctamente');
    expect(text).not.toContain('Venta COMPLETADA');

    // 4. Códigos consistentes
    const summaryHeading = fixture.nativeElement.querySelector('.summary h2')?.textContent;
    expect(summaryHeading).toBe('VTA-LOCAL-601');
  });

  it('3. Flujo online original: conserva exactamente la confirmación online de PAGO APROBADO / Venta COMPLETADA sin avisos offline', () => {
    setup(mockPresencialSale, true, 'CAJERO');

    page.choose('EFECTIVO');
    page.confirm();

    const req = http.expectOne(`${base}/sales/31/payments`);
    expect(req.request.body).toEqual({ medio: 'EFECTIVO' });

    const pendingPayment: Payment = {
      id_pago: 99,
      id_venta: 31,
      medio: 'EFECTIVO',
      proveedor: 'MANUAL',
      entorno: 'LOCAL',
      estado: 'PENDIENTE',
      estado_venta: 'PENDIENTE',
      monto: '350.00',
      moneda: 'BOB',
      referencia_externa: null,
      clave_idempotencia: key,
      fecha_aprobacion: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    req.flush({ success: true, data: pendingPayment });

    const confirmReq = http.expectOne(`${base}/payments/99/manual/confirm`);
    confirmReq.flush({
      success: true,
      data: {
        ...pendingPayment,
        estado: 'APROBADO',
        estado_venta: 'COMPLETADA',
        fecha_aprobacion: new Date().toISOString(),
      },
    });

    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;

    // 1. Debe mostrar bloque online original
    expect(text).toContain('PAGO APROBADO');
    expect(text).toContain('Pago realizado correctamente');
    expect(text).toContain('Venta COMPLETADA · VTA-DRAFT-31');

    // 2. NO debe mostrar avisos ni comprobantes provisionales offline
    expect(text).not.toContain('SIMULACIÓN LOCAL EXITOSA');
    expect(text).not.toContain('Comprobante provisional');
    expect(text).not.toContain('VENTA REGISTRADA OFFLINE EN CAJA');
    expect(text).not.toContain('PAGO SIMULADO OFFLINE');
  });
});