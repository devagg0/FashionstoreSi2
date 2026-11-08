import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { PurchaseDetail } from '../../../core/services/client-purchases.service';
import { ExchangeOptionsData, ReturnDetail } from '../../../core/services/returns.service';
import { SessionService } from '../../../core/services/session.service';
import { PurchaseReturnRequest } from './return-request';

const base = `${environment.apiUrl}/api`;

const purchaseCompleted: PurchaseDetail = {
  id_venta: 31,
  numero_venta: 'VTA-31',
  fecha: '2026-11-07T10:00:00',
  fecha_completada: '2026-11-07T10:00:00',
  canal: 'PRESENCIAL',
  estado: 'COMPLETADA',
  subtotal: '200',
  descuento_total: '40',
  total: '160',
  moneda: 'BOB',
  sucursal: { id_sucursal: 2, nombre: 'Sucursal Centro' },
  pago: {
    id_pago: 1,
    medio: 'EFECTIVO',
    estado: 'APROBADO',
    monto: '160',
    moneda: 'BOB',
    fecha_aprobacion: '2026-11-07T10:00:00',
  },
  pagos: [],
  devoluciones: [],
  reembolsos: [],
  productos: [
    {
      id_detalle_venta: 1,
      id_variante_producto: 101,
      nombre: 'Chaqueta Denim',
      talla: 'S',
      color: 'Negro',
      cantidad: 2,
      precio_unitario: '100',
      descuento_unitario: '20',
      subtotal_linea: '160',
    },
  ],
};

const mockExchangeOptionsActive: ExchangeOptionsData = {
  id_venta: 31,
  numero_venta: 'VTA-31',
  estado_venta: 'COMPLETADA',
  moneda: 'BOB',
  id_sucursal: 2,
  sucursal: { id_sucursal: 2, nombre: 'Sucursal Centro' },
  fecha_completada: '2026-11-07T10:00:00',
  fecha_limite_solicitud: '2026-11-10T10:00:00',
  plazo_horas: 72,
  dentro_plazo_72h: true,
  elegible_cambio_devolucion: true,
  horas_restantes: 70.5,
  motivo_no_elegible: null,
  tipos_solicitud: ['CAMBIO', 'DEVOLUCION'],
  modalidades_entrega: ['ENTREGA_EN_TIENDA', 'DELIVERY_SIMULADO'],
  modalidad_entrega_pendiente: true,
  lineas_compra: [
    {
      id_detalle_venta: 1,
      id_variante_producto: 101,
      id_producto: 10,
      nombre_producto: 'Chaqueta Denim',
      sku: 'CHQ-S-NEG',
      id_talla: 1,
      talla: 'S',
      id_color: 1,
      color: 'Negro',
      codigo_hex: '#000000',
      cantidad_comprada: 2,
      cantidad_usada: 0,
      cantidad_disponible: 2,
      precio_unitario: '100.00',
      descuento_unitario: '20.00',
      subtotal_linea: '160.00',
      valor_unitario_reconocido: '80.00',
      valor_disponible_reconocido: '160.00',
    },
  ],
  variantes_reemplazo_disponibles: [
    {
      id_variante_producto: 102,
      id_producto: 10,
      nombre_producto: 'Chaqueta Denim',
      sku: 'CHQ-M-AZU',
      id_talla: 2,
      talla: 'M',
      id_color: 2,
      color: 'Azul',
      codigo_hex: '#0000FF',
      precio_unitario: '100.00',
      stock_disponible: 5,
    },
    {
      id_variante_producto: 201,
      id_producto: 11,
      nombre_producto: 'Abrigo Premium',
      sku: 'ABR-M-NEG',
      id_talla: 2,
      talla: 'M',
      id_color: 1,
      color: 'Negro',
      codigo_hex: '#000000',
      precio_unitario: '110.00',
      stock_disponible: 4,
    },
  ],
};

const mockExchangeOptionsExpired: ExchangeOptionsData = {
  ...mockExchangeOptionsActive,
  dentro_plazo_72h: false,
  elegible_cambio_devolucion: false,
  horas_restantes: 0,
  motivo_no_elegible:
    'El plazo máximo de 72 horas posteriores a la finalización de la compra ha expirado para solicitar cambios o devoluciones.',
};

describe('CU15 - Frontend Angular: Solicitar cambio o devolución de prenda', () => {
  let fixture: ComponentFixture<PurchaseReturnRequest>;
  let page: PurchaseReturnRequest;
  let http: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: SessionService,
          useValue: {
            getAccessToken: () => 'token-jwt-cliente',
            getUser: () => ({ id_usuario: 12 }),
            logout: vi.fn(),
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PurchaseReturnRequest);
    page = fixture.componentInstance;
  });

  afterEach(() => {
    fixture.destroy();
    http.verify();
    sessionStorage.clear();
    TestBed.resetTestingModule();
  });

  it('1. Valida plazo de 72 horas y registra CAMBIO sin modalidad inicial, con cálculo económico y estado Pendiente de revisión del cajero', () => {
    fixture.componentRef.setInput('purchase', structuredClone(purchaseCompleted));
    fixture.detectChanges();

    // 1. Simular carga de opciones con plazo vencido
    const req = http.expectOne(`${base}/client/purchases/31/exchange-options`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer token-jwt-cliente');
    req.flush({ success: true, data: mockExchangeOptionsExpired });
    fixture.detectChanges();

    // Plazo vencido -> muestra aviso y no permite solicitar
    expect(page.dentroPlazo72h()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('El plazo máximo de 72 horas');
    let buttons = Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
    expect(buttons.some((b) => b.textContent?.includes('Solicitar cambio'))).toBe(false);

    // 2. Plazo activo dentro de las 72 horas
    page.optionsData.set(mockExchangeOptionsActive);
    fixture.detectChanges();
    expect(page.dentroPlazo72h()).toBe(true);
    expect(page.horasRestantes()).toBe(70.5);
    expect(fixture.nativeElement.textContent).toContain('Plazo para cambios y devoluciones activo');

    // 3. Abrir modal de CAMBIO
    page.open('CAMBIO');
    fixture.detectChanges();
    expect(page.kind()).toBe('CAMBIO');

    // Verificar que NO existe selector de modalidad de entrega inicial (queda pendiente hasta CU16)
    expect(fixture.nativeElement.querySelector('.modality-fieldset')).toBeNull();

    // Seleccionar 1 unidad para cambio
    page.quantity(purchaseCompleted.productos[0], 1);
    expect(page.units()).toBe(1);

    // Seleccionar variante de reemplazo más cara (Abrigo 201 = 110.00 vs original 80.00 reconocido -> +30.00)
    page.setReplacement(1, 201);
    fixture.detectChanges();

    const summary = page.economicSummary();
    expect(summary).toBeTruthy();
    expect(summary?.totalOriginal).toBe(80);
    expect(summary?.totalReemplazo).toBe(110);
    expect(summary?.diferencia).toBe(30);
    expect(summary?.resultado).toBe('IMPORTE_ADICIONAL');
    expect(fixture.nativeElement.textContent).toContain('Importe adicional estimado a pagar');

    page.reason.set('Cambio por talla y modelo más abrigado');

    // 4. Enviar solicitud: body NO debe contener modalidad_entrega
    page.submit();
    const reqSubmit = http.expectOne(`${base}/client/purchases/31/exchanges`);
    expect(reqSubmit.request.method).toBe('POST');
    expect(reqSubmit.request.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    expect(reqSubmit.request.body).toEqual({
      tipo: 'CAMBIO',
      motivo: 'Cambio por talla y modelo más abrigado',
      lineas: [
        {
          id_detalle_venta: 1,
          cantidad: 1,
          id_variante_reemplazo: 201,
          cantidad_reemplazo: 1,
        },
      ],
    });

    const responseExchange: ReturnDetail = {
      id_devolucion: 8,
      id_venta: 31,
      tipo: 'CAMBIO',
      estado: 'SOLICITADA',
      modalidad_entrega: null,
      motivo: 'Cambio por talla y modelo más abrigado',
      id_usuario_solicitante: 12,
      created_at: '2026-11-07T11:00:00',
      diferencia_precio_estimada: '30.00',
      importe_adicional_estimado: '30.00',
      saldo_a_favor_estimado: '0.00',
      resumen_economico: {
        moneda: 'BOB',
        valor_original_reconocido: '80.00',
        valor_reemplazo_estimado: '110.00',
        diferencia_precio_estimada: '30.00',
        importe_adicional_estimado: '30.00',
        saldo_a_favor_estimado: '0.00',
        resultado_economico: 'IMPORTE_ADICIONAL',
      },
      lineas: [
        {
          id_variante_producto: 101,
          cantidad: 1,
          cantidad_reintegrar: 0,
          importe_restitucion: '0.00',
          id_variante_reemplazo: 201,
          cantidad_reemplazo: 1,
          precio_original_reconocido: '80.00',
          precio_reemplazo_estimado: '110.00',
          diferencia_precio_estimada: '30.00',
          prenda_original: {
            id_variante_producto: 101,
            nombre_producto: 'Chaqueta Denim',
            talla: 'S',
            color: 'Negro',
          },
          prenda_reemplazo: {
            id_variante_producto: 201,
            nombre_producto: 'Abrigo Premium',
            talla: 'M',
            color: 'Negro',
          },
        },
      ],
      reembolsos: [],
    };
    reqSubmit.flush({ success: true, data: responseExchange });
    fixture.detectChanges();

    // Confirma estado «Pendiente de revisión del cajero» y código SOL-00008
    expect(page.kind()).toBeNull();
    expect(page.success()).toContain('SOL-00008');
    expect(page.success()).toContain('Pendiente de revisión del cajero');
    expect(fixture.nativeElement.textContent).toContain('SOL-00008');
    expect(fixture.nativeElement.textContent).toContain('Pendiente de revisión del cajero');
    expect(fixture.nativeElement.textContent).toContain('Pendiente de aceptación del cajero');
  });

  it('2. Registra DEVOLUCIÓN inicial sin modalidad, con restitución estimada, idempotencia y seguimiento', () => {
    fixture.componentRef.setInput('purchase', structuredClone(purchaseCompleted));
    fixture.detectChanges();

    const reqOpt = http.expectOne(`${base}/client/purchases/31/exchange-options`);
    reqOpt.flush({ success: true, data: mockExchangeOptionsActive });
    fixture.detectChanges();

    // Abrir modal de DEVOLUCION
    page.open('DEVOLUCION');
    fixture.detectChanges();
    expect(page.kind()).toBe('DEVOLUCION');
    expect(fixture.nativeElement.querySelector('.modality-fieldset')).toBeNull();

    page.quantity(purchaseCompleted.productos[0], 2);
    expect(page.units()).toBe(2);

    const summary = page.economicSummary();
    expect(summary?.totalOriginal).toBe(160);
    expect(summary?.saldoAFavor).toBe(160);
    expect(summary?.resultado).toBe('SALDO_A_FAVOR');

    page.reason.set('Devolución completa de ambas prendas');
    page.submit();

    // Body enviado NO incluye modalidad_entrega
    const reqSubmit = http.expectOne(`${base}/client/purchases/31/returns`);
    expect(reqSubmit.request.method).toBe('POST');
    const key = reqSubmit.request.headers.get('Idempotency-Key');
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    expect(reqSubmit.request.body).toEqual({
      motivo: 'Devolución completa de ambas prendas',
      lineas: [{ id_detalle_venta: 1, cantidad: 2 }],
    });

    const responseDev: ReturnDetail = {
      id_devolucion: 9,
      id_venta: 31,
      tipo: 'DEVOLUCION',
      estado: 'SOLICITADA',
      modalidad_entrega: null,
      motivo: 'Devolución completa de ambas prendas',
      id_usuario_solicitante: 12,
      created_at: '2026-11-07T11:00:00',
      saldo_a_favor_estimado: '160.00',
      lineas: [
        {
          id_variante_producto: 101,
          cantidad: 2,
          cantidad_reintegrar: 0,
          importe_restitucion: '160.00',
        },
      ],
      reembolsos: [],
    };
    reqSubmit.flush({ success: true, data: responseDev });
    fixture.detectChanges();

    expect(page.success()).toContain('SOL-00009');
    expect(page.success()).toContain('Pendiente de revisión del cajero');
  });

  it('3. Limita la cantidad entre 0 y unidades disponibles, valida tipeo/pegado y muestra error 409 del servidor', () => {
    // Compra con 1 unidad comprada
    const purchaseSingleUnit = structuredClone(purchaseCompleted);
    purchaseSingleUnit.productos[0].cantidad = 1;
    purchaseSingleUnit.total = '80';

    const optionsSingleUnit: ExchangeOptionsData = {
      ...mockExchangeOptionsActive,
      lineas_compra: [
        {
          ...mockExchangeOptionsActive.lineas_compra[0],
          cantidad_comprada: 1,
          cantidad_disponible: 1,
          valor_disponible_reconocido: '80.00',
        },
      ],
    };

    fixture.componentRef.setInput('purchase', purchaseSingleUnit);
    fixture.detectChanges();

    const reqOpt = http.expectOne(`${base}/client/purchases/31/exchange-options`);
    reqOpt.flush({ success: true, data: optionsSingleUnit });
    fixture.detectChanges();

    // Abrir modal de DEVOLUCION
    page.open('DEVOLUCION');
    fixture.detectChanges();

    const prod = purchaseSingleUnit.productos[0];
    expect(page.available(prod)).toBe(1);

    // 1. Intentar seleccionar 5 unidades -> se limita a 1
    page.quantity(prod, 5);
    expect(page.quantities()[prod.id_detalle_venta]).toBe(1);
    expect(page.units()).toBe(1);

    // 2. Simular tipeo manual con input element intentando poner 10
    const mockInputEl = document.createElement('input');
    mockInputEl.value = '10';
    page.onQuantityInput(prod, { target: mockInputEl } as unknown as Event);
    expect(mockInputEl.value).toBe('1');
    expect(page.quantities()[prod.id_detalle_venta]).toBe(1);

    // 3. Simular pegado (paste) con valor 99
    mockInputEl.value = '99';
    page.onQuantityPaste(prod, { target: mockInputEl } as unknown as ClipboardEvent);
    // onQuantityPaste usa setTimeout 0
    expect(page.quantities()[prod.id_detalle_venta]).toBe(1);

    // 4. Resumen económico respeta la cantidad disponible (1 x 80 = 80) y no supera total pagado
    const summary = page.economicSummary();
    expect(summary?.totalOriginal).toBe(80);
    expect(summary?.saldoAFavor).toBe(80);

    // 5. Validar que si raw quantities supera available, submit() rechaza
    page.quantities.set({ [prod.id_detalle_venta]: 3 });
    page.reason.set('Motivo de prueba');
    page.submit();
    expect(page.error()).toBe('La cantidad solicitada supera las unidades disponibles para cambio o devolución.');

    // 6. Restaurar cantidad válida (1) y simular error HTTP 409 del backend
    page.quantity(prod, 1);
    page.submit();

    const reqSubmit = http.expectOne(`${base}/client/purchases/31/returns`);
    expect(reqSubmit.request.method).toBe('POST');
    expect(reqSubmit.request.body).toEqual({
      motivo: 'Motivo de prueba',
      lineas: [{ id_detalle_venta: 1, cantidad: 1 }],
    });

    reqSubmit.flush(
      {
        success: false,
        message: 'Conflicto de solicitud o idempotencia; consulte el estado de la compra antes de reintentar',
      },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();

    // Comprobar que muestra el mensaje exacto del servidor y no un mensaje de pago genérico
    expect(page.error()).toBe(
      'Conflicto de solicitud o idempotencia; consulte el estado de la compra antes de reintentar',
    );
  });
});
