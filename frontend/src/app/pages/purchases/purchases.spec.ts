import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { PurchaseDetail, PurchaseSummary } from '../../core/services/client-purchases.service';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { SessionService } from '../../core/services/session.service';
import { PurchasesPage } from './purchases';
import { routes } from '../../app.routes';
import { clientGuard } from '../../core/guards/client.guard';

const base = `${environment.apiUrl}/api/client/purchases`;
const summary: PurchaseSummary = {
  id_venta: 31,
  numero_venta: 'VTA-31',
  fecha: '2026-09-17T12:00:00',
  fecha_completada: null,
  canal: 'DIGITAL',
  estado: 'PENDIENTE',
  subtotal: '400.00',
  descuento_total: '100.00',
  total: '300.00',
  moneda: 'BOB',
  sucursal: { id_sucursal: 2, nombre: 'Centro' },
  pago: {
    id_pago: 9,
    medio: 'TARJETA',
    estado: 'PENDIENTE',
    monto: '300.00',
    moneda: 'BOB',
    fecha_aprobacion: null,
  },
};
const detail: PurchaseDetail = {
  ...summary,
  productos: [
    {
      id_detalle_venta: 1,
      id_variante_producto: 3,
      nombre: 'Camisa',
      talla: 'M',
      color: 'Blanco',
      cantidad: 2,
      precio_unitario: '200.00',
      descuento_unitario: '50.00',
      subtotal_linea: '300.00',
    },
  ],
  pagos: [summary.pago!],
  devoluciones: [],
  reembolsos: [],
};
function paymentResponse(id_pago: number, id_venta: number) {
  return {
    id_pago,
    id_venta,
    medio: 'TARJETA' as const,
    proveedor: 'STRIPE' as const,
    entorno: 'TEST' as const,
    estado: 'PENDIENTE' as const,
    estado_venta: 'PENDIENTE' as const,
    monto: '300.00',
    moneda: 'BOB' as const,
    referencia_externa: 'cs_test_123',
    clave_idempotencia: 'key',
    fecha_aprobacion: null,
    created_at: '2026-09-17T12:00:00',
    updated_at: '2026-09-17T12:00:00',
  };
}
function checkoutResponse(id_pago: number, id_venta: number) {
  return {
    success: true,
    data: {
      payment: paymentResponse(id_pago, id_venta),
      session_id: 'cs_test_123',
      url: 'https://checkout.stripe.com/c/pay/cs_test_123',
    },
  };
}

describe('CU23 Mis compras', () => {
  let fixture: ComponentFixture<PurchasesPage>;
  let page: PurchasesPage;
  let http: HttpTestingController;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let navigationUrl = '';
  function setup(id?: string) {
    navigationUrl = '';
    sessionStorage.clear();
    params = new BehaviorSubject(convertToParamMap(id === undefined ? {} : { id }));
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: params } },
        { provide: SessionService, useValue: { getAccessToken: () => 'fake-token', getUser: () => undefined } },
        { provide: CheckoutNavigationService, useValue: { go: (url: string) => navigationUrl = url } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PurchasesPage);
    page = fixture.componentInstance;
    fixture.detectChanges();
  }
  const text = () => fixture.nativeElement.textContent as string;
  function list(items: PurchaseSummary[] = [summary], total = items.length, offset = 0) {
    const req = http.expectOne((r) => r.url === base && r.params.get('offset') === String(offset));
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer fake-token');
    req.flush({ success: true, data: { items, total, limit: 12, offset } });
    fixture.detectChanges();
    return req;
  }
  function flushDetail(data: PurchaseDetail = detail) {
    http.expectOne(`${base}/31`).flush({ success: true, data });
    fixture.detectChanges();
  }
  afterEach(() => {
    http?.verify();
    fixture?.destroy();
  });
  it('protects both routes with CLIENTE guard', async () => {
    for (const path of ['mis-compras', 'mis-compras/:id']) {
      const route = routes.find((r) => r.path === path)!;
      expect(route.canActivate).toEqual([clientGuard]);
      expect(await (route.loadComponent as () => Promise<unknown>)()).toBe(PurchasesPage);
    }
  });
  it('renders history, total, branch, canal and pending badges', () => {
    setup();
    expect(text()).toContain('Cargando');
    list();
    for (const value of [
      'Mis compras',
      'VTA-31',
      'Centro',
      'COMPRA ONLINE',
      'PENDIENTE',
      'TARJETA',
      '300,00',
      'BOB',
    ])
      expect(text()).toContain(value);
    expect(fixture.nativeElement.querySelector('.detail-link').getAttribute('href')).toBe(
      '/mis-compras/31',
    );
    expect(fixture.nativeElement.querySelector('.continue-link')).toBeTruthy();
  });
  it('reuses the pending payment to reopen Stripe Checkout', () => {
    setup();
    list();
    const button = fixture.nativeElement.querySelector('.continue-link') as HTMLButtonElement;
    button.click();
    flushDetail();
    const request = http.expectOne(`${environment.apiUrl}/api/payments/9/stripe/checkout-session`);
    expect(request.request.method).toBe('POST');
    request.flush({
      success: true,
      data: {
        payment: {
          id_pago: 9,
          id_venta: 31,
          medio: 'TARJETA',
          proveedor: 'STRIPE',
          entorno: 'TEST',
          estado: 'PENDIENTE',
          estado_venta: 'PENDIENTE',
          monto: '300.00',
          moneda: 'BOB',
          referencia_externa: 'cs_test_123',
          clave_idempotencia: 'key',
          fecha_aprobacion: null,
          created_at: '2026-09-17T12:00:00',
          updated_at: '2026-09-17T12:00:00',
        },
        session_id: 'cs_test_123',
        url: 'https://checkout.stripe.com/c/pay/cs_test_123',
      },
    });
    expect(navigationUrl).toBe('https://checkout.stripe.com/c/pay/cs_test_123');
    expect(sessionStorage.getItem('fashionstore_cu22_undefined_31_attempt')).toContain('"idPago":9');
    expect(sessionStorage.getItem('fashionstore_cu22_undefined_31_sale')).not.toBeNull();
  });
  it('creates one pending card payment when the purchase has no payment', () => {
    setup();
    list([{ ...summary, pago: null }]);
    const button = fixture.nativeElement.querySelector('.continue-link') as HTMLButtonElement;
    button.click();
    button.click();
    http.expectOne(`${base}/31`).flush({ success: true, data: { ...detail, pago: null, pagos: [] } });
    const start = http.expectOne(`${environment.apiUrl}/api/sales/31/payments`);
    expect(start.request.method).toBe('POST');
    expect(start.request.headers.get('Idempotency-Key')).toMatch(/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i);
    start.flush({ success: true, data: { ...paymentResponse(9, 31), referencia_externa: null } });
    const checkout = http.expectOne(`${environment.apiUrl}/api/payments/9/stripe/checkout-session`);
    expect(checkout.request.method).toBe('POST');
    checkout.flush(checkoutResponse(9, 31));
    expect(navigationUrl).toBe('https://checkout.stripe.com/c/pay/cs_test_123');
    expect(sessionStorage.getItem('fashionstore_cu22_undefined_31_attempt')).toContain('"idPago":9');
  });
  it('shortens long card references without changing the purchase data', () => {
    setup();
    const numero_venta = 'DIG-696BFCA851E24A44AB1234567890ABCD';
    list([{ ...summary, numero_venta }]);
    const heading = fixture.nativeElement.querySelector('.purchase-card h2');
    expect(heading.textContent.trim()).toBe('DIG-696BFCA8');
    expect(heading.title).toBe(numero_venta);
    expect(page.items()[0].numero_venta).toBe(numero_venta);
  });
  it('uses short detail headings and preserves the full secondary reference', () => {
    setup('31');
    const numero_venta = 'VTA-12345678901243218888123456789012';
    flushDetail({ ...detail, numero_venta });
    for (const heading of fixture.nativeElement.querySelectorAll('.sale-reference')) {
      expect(heading.textContent.trim()).toBe('VTA-12345678');
    }
    expect(fixture.nativeElement.querySelector('.full-reference p').textContent).toContain(
      numero_venta,
    );
    expect(page.detail()?.numero_venta).toBe(numero_venta);
  });
  it('shows completed and refunded badges and presencial channel', () => {
    setup();
    list([
      {
        ...summary,
        estado: 'COMPLETADA',
        canal: 'PRESENCIAL',
        pago: { ...summary.pago!, estado: 'REEMBOLSADO' },
      },
    ]);
    expect(text()).toContain('COMPRA EN TIENDA');
    expect(text()).toContain('COMPLETADA');
    expect(text()).toContain('REEMBOLSADO');
    expect(fixture.nativeElement.querySelector('.continue-link')).toBeNull();
  });
  it('handles purchases without payment', () => {
    setup();
    list([{ ...summary, pago: null, estado: 'ANULADA' }]);
    expect(text()).toContain('Sin pago registrado');
    expect(text()).toContain('ANULADA');
  });
  it('shows empty history and catalog entry', () => {
    setup();
    list([]);
    expect(text()).toContain('Aún no tienes compras');
    expect(fixture.nativeElement.querySelector('a.solid').getAttribute('href')).toBe('/catalogo');
  });
  it('combines filters and resets pagination', () => {
    setup();
    list();
    page.filter('COMPLETADA', 'DIGITAL');
    const req = http.expectOne(
      (r) =>
        r.url === base &&
        r.params.get('estado') === 'COMPLETADA' &&
        r.params.get('canal') === 'DIGITAL' &&
        r.params.get('offset') === '0',
    );
    expect(req.request.params.get('limit')).toBe('12');
    req.flush({ data: { items: [], total: 0, limit: 12, offset: 0 } });
    fixture.detectChanges();
    expect(text()).toContain('Sin resultados para estos filtros');
    page.filter('', '');
    list();
  });
  it('cancels old filter request before accepting new results', () => {
    setup();
    const old = http.expectOne((r) => r.url === base);
    page.filter('ANULADA', '');
    expect(old.cancelled).toBe(true);
    list([]);
    expect(page.items()).toEqual([]);
  });
  it('load more keeps backend newest-first order and prevents double clicks', () => {
    setup();
    list([summary], 2);
    page.loadMore();
    page.loadMore();
    list(
      [{ ...summary, id_venta: 30, numero_venta: 'VTA-30', fecha: '2026-09-16T12:00:00' }],
      2,
      1,
    );
    expect(page.items().map((p) => p.id_venta)).toEqual([31, 30]);
    expect(page.more()).toBe(false);
  });
  it('preserves loaded cards and retries failed pagination at same offset', () => {
    setup();
    list([summary], 2);
    page.loadMore();
    http.expectOne((r) => r.url === base).error(new ProgressEvent('error'));
    expect(page.items()).toHaveLength(1);
    page.retry();
    list([{ ...summary, id_venta: 30 }], 2, 1);
  });
  it('renders historical detail and payment without internal references', () => {
    setup('31');
    flushDetail();
    for (const value of [
      'Camisa',
      'Talla M',
      'Blanco',
      'Cantidad: 2',
      'Precio unitario',
      'Descuento por unidad',
      'Subtotal',
      'Descuentos',
      'TARJETA',
      'Tu compra continúa pendiente',
    ])
      expect(text()).toContain(value);
    expect(text()).not.toMatch(/Stripe|clave_idempotencia|referencia_externa/);
    expect(text()).not.toContain('Devoluciones y cancelaciones');
    expect(text()).not.toContain('Reembolsos');
    expect(text()).toContain('Fecha de aprobación no disponible');
  });
  it('renders approved and rejected payment attempts', () => {
    setup('31');
    flushDetail({
      ...detail,
      estado: 'COMPLETADA',
      pagos: [
        { ...summary.pago!, estado: 'APROBADO', fecha_aprobacion: '2026-09-17T12:00:00' },
        { ...summary.pago!, id_pago: 8, estado: 'RECHAZADO' },
      ],
    });
    expect(text()).toContain('Compra completada');
    expect(text()).toContain('APROBADO');
    expect(text()).toContain('RECHAZADO');
    expect(text()).toContain('Aprobado:');
  });
  it('shows existing returns and refunds without inventing affected items', () => {
    setup('31');
    flushDetail({
      ...detail,
      devoluciones: [
        {
          id_devolucion: 2,
          tipo: 'DEVOLUCION',
          estado: 'PROCESADA',
          motivo: 'Talla incorrecta',
          fecha: summary.fecha,
          fecha_resolucion: summary.fecha,
          fecha_procesamiento: summary.fecha,
        },
      ],
      reembolsos: [
        {
          id_reembolso: 3,
          id_devolucion: 2,
          id_pago: 9,
          estado: 'APROBADO',
          monto: '150.00',
          fecha: summary.fecha,
          fecha_aprobacion: summary.fecha,
        },
      ],
    });
    for (const value of [
      'Devoluciones y cancelaciones',
      'PROCESADA',
      'Talla incorrecta',
      'Reembolsos',
      'Monto reembolsado',
      '150,00',
      'APROBADO',
      'Consulta la solicitud para ver sus prendas y cantidades.',
      'Consultar SOL-00002',
    ])
      expect(text()).toContain(value);
  });
  it('renders optional image and handles missing catalog/payment gracefully', () => {
    setup('31');
    flushDetail({
      ...detail,
      productos: [{ ...detail.productos[0], imagen: 'https://example.com/item.jpg', nombre: null }],
      pagos: [],
    });
    const image = fixture.nativeElement.querySelector('img');
    expect(image).not.toBeNull();
    image.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
    expect(text()).toContain('Producto no disponible');
    expect(text()).toContain('aún no tiene pagos');
  });
  it('clears old detail on navigation to another purchase', () => {
    setup('31');
    flushDetail();
    params.next(convertToParamMap({ id: '32' }));
    expect(page.detail()).toBeNull();
    http
      .expectOne(`${base}/32`)
      .flush({ data: { ...detail, id_venta: 32, numero_venta: 'VTA-32' } });
    expect(page.detail()?.id_venta).toBe(32);
  });
  it('rejects detail associated with wrong id', () => {
    setup('31');
    flushDetail({ ...detail, id_venta: 99 });
    expect(page.detail()).toBeNull();
    expect(page.error()).toBeTruthy();
  });
  it('rejects malformed detail id without request', () => {
    setup('-1');
    expect(page.missing()).toBe(true);
    http.expectNone(`${base}/-1`);
  });
  for (const status of [401, 403, 404, 500, 503])
    it(`handles API ${status} with safe message`, () => {
      setup('31');
      http
        .expectOne(`${base}/31`)
        .flush({ message: 'secret trace' }, { status, statusText: 'Error' });
      fixture.detectChanges();
      expect(page.error()).toBeTruthy();
      expect(text()).not.toContain('secret trace');
      if (status === 401) {
        expect(text()).toContain('Tu sesión expiró');
        expect(fixture.nativeElement.querySelector('a.solid').getAttribute('href')).toBe('/login');
        page.retry();
        http.expectNone(`${base}/31`);
      }
      if (status === 404) expect(text()).toContain('Compra no encontrada');
    });
  it('handles network failure and retry', () => {
    setup();
    http.expectOne((r) => r.url === base).error(new ProgressEvent('error'));
    page.retry();
    list();
    expect(page.error()).toBe('');
  });
  it('links to the receipt for a completed purchase with approved payment', () => {
    setup('31');
    flushDetail({ ...detail, estado: 'COMPLETADA', fecha_completada: '2026-09-17T12:00:00',
      pago: { ...summary.pago!, estado: 'APROBADO' } });
    const link = Array.from(fixture.nativeElement.querySelectorAll('a'))
      .find((node) => (node as HTMLAnchorElement).textContent?.includes('Ver comprobante')) as HTMLAnchorElement;
    expect(link?.getAttribute('href')).toBe('/mis-compras/31/comprobante');
  });
  it('does not offer a receipt for a pending purchase', () => {
    setup('31'); flushDetail(); expect(text()).not.toContain('Ver comprobante');
  });
});
