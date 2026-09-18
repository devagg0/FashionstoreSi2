import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { Payment, PaymentSale, PaymentsService } from '../../core/services/payments.service';
import { CheckoutNavigationService } from '../../core/services/checkout-navigation.service';
import { SessionService } from '../../core/services/session.service';
import { PaymentPage } from './payment';
import { routes } from '../../app.routes';
import { clientGuard } from '../../core/guards/client.guard';
import { cashierGuard } from '../../core/guards/cashier.guard';

const sale: PaymentSale = {
  id: 31,
  numero: 'VTA-31',
  sucursal: 'Centro · La Paz',
  canal: 'PRESENCIAL',
  estado: 'PENDIENTE',
  fecha: '2026-09-17T18:00:00',
  subtotal: '400.00',
  descuento: '100.00',
  total: '300.00',
  items: [
    {
      id: 15,
      nombre: 'Camisa Oxford',
      talla: 'M',
      color: 'Blanco',
      cantidad: 2,
      precio: '200.00',
      subtotal: '300.00',
    },
  ],
};
const base = `${environment.apiUrl}/api`;
const key = '11111111-2222-4333-8444-555555555555';
function payment(overrides: Partial<Payment> = {}): Payment {
  return {
    id_pago: 9,
    id_venta: 31,
    medio: 'EFECTIVO',
    proveedor: 'MANUAL',
    entorno: 'LOCAL',
    estado: 'PENDIENTE',
    estado_venta: 'PENDIENTE',
    monto: '300.00',
    moneda: 'BOB',
    referencia_externa: null,
    clave_idempotencia: key,
    fecha_aprobacion: null,
    created_at: '2026-09-17T18:01:00',
    updated_at: '2026-09-17T18:01:00',
    ...overrides,
  };
}
const card = () => payment({ medio: 'TARJETA', proveedor: 'STRIPE', entorno: 'TEST' });

describe('CU22 QR y Checkout web', () => {
  let fixture: ComponentFixture<PaymentPage>;
  let page: PaymentPage;
  let http: HttpTestingController;
  let api: PaymentsService;
  const go = vi.fn();
  function setup(
    value: PaymentSale | null = sale,
    saved = false,
    query: Record<string, string> = {},
  ) {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: convertToParamMap({ id: '31' }),
              queryParamMap: convertToParamMap(query),
            },
          },
        },
        { provide: CheckoutNavigationService, useValue: { go } },
        {
          provide: SessionService,
          useValue: {
            getUser: () => ({
              id_usuario: 1,
              rol: value?.canal === 'DIGITAL' ? 'CLIENTE' : 'CAJERO',
            }),
            getAccessToken: () => 'fake-token',
          },
        },
      ],
    });
    api = TestBed.inject(PaymentsService);
    http = TestBed.inject(HttpTestingController);
    if (value) api.saveSale(value);
    if (saved) api.saveAttempt(31, { key, medio: 'TARJETA', idPago: 9 });
    fixture = TestBed.createComponent(PaymentPage);
    page = fixture.componentInstance;
    fixture.detectChanges();
  }
  const text = () => fixture.nativeElement.textContent as string;
  function start(method: 'EFECTIVO' | 'QR' | 'TARJETA', prepareOnly = false) {
    page.choose(method);
    if (prepareOnly) page.prepareQr();
    else page.confirm();
    const req = http.expectOne(`${base}/sales/31/payments`);
    expect(req.request.body).toEqual({ medio: method });
    expect(req.request.headers.get('Authorization')).toBe('Bearer fake-token');
    expect(req.request.headers.get('Idempotency-Key')).toBeTruthy();
    const pending = method === 'TARJETA' ? card() : payment({ medio: method });
    req.flush({ success: true, data: pending });
    return pending;
  }
  function finish(pending: Payment, approved = true) {
    const route = pending.medio === 'QR' ? 'qr/confirm' : 'manual/confirm';
    const req = http.expectOne(`${base}/payments/9/${route}`);
    expect(req.request.body).toEqual(pending.medio === 'QR' ? {} : { resultado: 'APROBADO' });
    req.flush({
      success: true,
      data: {
        ...pending,
        estado: approved ? 'APROBADO' : 'RECHAZADO',
        estado_venta: approved ? 'COMPLETADA' : 'PENDIENTE',
      },
    });
    fixture.detectChanges();
  }
  function checkout(pending = card()) {
    const req = http.expectOne(`${base}/payments/9/stripe/checkout-session`);
    expect(req.request.body).toEqual({});
    req.flush({
      success: true,
      data: {
        payment: { ...pending, referencia_externa: 'cs_test_demo' },
        session_id: 'cs_test_demo',
        url: 'https://checkout.stripe.com/c/pay/cs_test_demo',
      },
    });
    fixture.detectChanges();
  }
  afterEach(() => {
    http?.verify();
    fixture?.destroy();
    sessionStorage.clear();
    vi.restoreAllMocks();
    go.mockReset();
  });
  it('preserves guarded routes and shared payment component', async () => {
    setup();
    const client = routes.find((route) => route.path === 'compra/:id/pago')!;
    const staff = routes
      .find((route) => route.path === 'staff')!
      .children!.find((route) => route.path === 'ventas/:id/pago')!;
    expect(client.canActivate).toEqual([clientGuard]);
    expect(staff.canActivate).toEqual([cashierGuard]);
    expect(await (client.loadComponent as () => Promise<unknown>)()).toBe(PaymentPage);
    expect(await (staff.loadComponent as () => Promise<unknown>)()).toBe(PaymentPage);
  });
  it('renders products, sidebar totals and three cashier methods', () => {
    setup();
    for (const value of [
      'VTA-31',
      'Centro',
      'Camisa Oxford',
      'Talla M',
      'Blanco',
      'Cantidad: 2',
      'BOB',
      'Subtotal',
      'Descuento',
      'Total final',
    ])
      expect(text()).toContain(value);
    expect(page.methods()).toEqual(['EFECTIVO', 'QR', 'TARJETA']);
    expect(fixture.nativeElement.querySelectorAll('.method')).toHaveLength(3);
  });
  it('digital shows QR and TARJETA without card fields or fixture UI', () => {
    setup({ ...sale, canal: 'DIGITAL' });
    expect(page.methods()).toEqual(['QR', 'TARJETA']);
    expect(fixture.nativeElement.querySelectorAll('.method')).toHaveLength(2);
    expect(text()).toContain('Pagar con tarjeta');
    expect(text()).not.toMatch(/Simular pago|pm_card_|rechazado/);
    expect(fixture.nativeElement.querySelector('input')).toBeNull();
  });
  it('cash asks confirmation in modal and approves the completed receipt', () => {
    setup();
    page.choose('EFECTIVO');
    page.open('APROBADO');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('dialog').hasAttribute('open')).toBe(true);
    http.expectNone(`${base}/sales/31/payments`);
    page.close();
    finish(start('EFECTIVO'));
    expect(page.completed()).toBe(true);
    expect(text()).toContain('Pago realizado correctamente');
    expect(text()).toContain('COMPLETADA');
    page.confirm();
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('generates QR with non-sensitive reference then asks server to confirm', () => {
    setup({ ...sale, canal: 'DIGITAL' });
    const pending = start('QR', true);
    fixture.detectChanges();
    expect(page.qrCells().length).toBeGreaterThan(100);
    expect(text()).toContain('Escanea el QR para realizar el pago.');
    expect(text()).toContain('Pago #9');
    expect(text()).toContain(key);
    expect(text()).toContain('Ya realicé el pago');
    http.expectNone(`${base}/payments/9/qr/confirm`);
    page.open('APROBADO');
    page.confirm();
    http.expectOne(`${base}/payments/9`).flush({ data: pending });
    finish(pending);
    expect(page.completed()).toBe(true);
  });
  it('QR rejection preserves pending sale and permits a new attempt', () => {
    setup({ ...sale, canal: 'DIGITAL' });
    finish(start('QR'), false);
    expect(page.status()).toBe('PENDIENTE');
    expect(text()).toContain('El pago fue rechazado');
    page.newAttempt();
    expect(page.attempt()).toBeNull();
    expect(page.canPay()).toBe(true);
  });
  it('card opens hosted Checkout, retaining payment and blocking clicks while redirecting', () => {
    setup({ ...sale, canal: 'DIGITAL' });
    checkout(start('TARJETA'));
    expect(go).toHaveBeenCalledWith('https://checkout.stripe.com/c/pay/cs_test_demo');
    expect(api.attempt(31)?.idPago).toBe(9);
    expect(api.attempt(31)?.key).toBe(key);
    expect(page.busy()).toBe(true);
    expect(text()).toContain('Redirigiendo a Stripe Checkout');
    page.confirm();
    page.retry();
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('success return validates persisted sale association then syncs without assuming approval', () => {
    setup({ ...sale, canal: 'DIGITAL' }, true, {
      checkout: 'success',
      payment_id: '9',
      session_id: 'untrusted',
    });
    expect(page.completed()).toBe(false);
    http.expectOne(`${base}/payments/9`).flush({ data: card() });
    const req = http.expectOne(`${base}/payments/9/stripe/sync`);
    expect(req.request.body).toEqual({});
    req.flush({ data: card() });
    fixture.detectChanges();
    expect(page.completed()).toBe(false);
    expect(page.status()).toBe('PENDIENTE');
    expect(text()).not.toContain('Pago realizado correctamente');
  });
  it('backend approved sync shows receipt with sale number, total and card method', () => {
    setup({ ...sale, canal: 'DIGITAL' }, false, { checkout: 'success', payment_id: '9' });
    http.expectOne(`${base}/payments/9`).flush({ data: card() });
    http
      .expectOne(`${base}/payments/9/stripe/sync`)
      .flush({ data: { ...card(), estado: 'APROBADO', estado_venta: 'COMPLETADA' } });
    fixture.detectChanges();
    expect(page.completed()).toBe(true);
    for (const value of [
      'Pago realizado correctamente',
      'Venta COMPLETADA',
      'VTA-31',
      'TARJETA',
      '300,00',
    ])
      expect(text()).toContain(value);
  });
  it('cancel return syncs, preserves pending sale and reuses Checkout to retry', () => {
    setup({ ...sale, canal: 'DIGITAL' }, true, { checkout: 'cancel', payment_id: '9' });
    http.expectOne(`${base}/payments/9`).flush({ data: card() });
    http.expectOne(`${base}/payments/9/stripe/sync`).flush({ data: card() });
    fixture.detectChanges();
    expect(text()).toContain('Pago cancelado. Tu compra continúa pendiente.');
    expect(page.completed()).toBe(false);
    page.confirm();
    http.expectOne(`${base}/payments/9`).flush({ data: card() });
    checkout();
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('rejects return id conflicting with saved attempt', () => {
    setup({ ...sale, canal: 'DIGITAL' }, true, { checkout: 'success', payment_id: '12' });
    expect(page.error()).toContain('no corresponde');
    http.expectNone(`${base}/payments/12`);
  });
  it('rejects return payment belonging to another sale before sync', () => {
    setup({ ...sale, canal: 'DIGITAL' }, false, { checkout: 'success', payment_id: '9' });
    http.expectOne(`${base}/payments/9`).flush({ data: { ...card(), id_venta: 99 } });
    expect(page.payment()).toBeNull();
    http.expectNone(`${base}/payments/9/stripe/sync`);
  });
  it('blocks invalid return identifiers', () => {
    setup({ ...sale, canal: 'DIGITAL' }, false, { checkout: 'success', payment_id: '-1' });
    expect(page.error()).toBeTruthy();
    http.expectNone(`${base}/payments/-1`);
  });
  it('blocks an already completed sale', () => {
    setup({ ...sale, estado: 'COMPLETADA' });
    page.confirm();
    expect(page.canPay()).toBe(false);
    expect(text()).toContain('Esta venta ya está completada');
    expect(fixture.nativeElement.querySelector('.method-grid')).toBeNull();
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('blocks double submissions and method changes during requests', () => {
    setup();
    page.choose('EFECTIVO');
    page.confirm();
    page.confirm();
    page.choose('QR');
    expect(page.busy()).toBe(true);
    expect(page.method()).toBe('EFECTIVO');
    const reqs = http.match(`${base}/sales/31/payments`);
    expect(reqs).toHaveLength(1);
    reqs[0].flush({}, { status: 503, statusText: 'Unavailable' });
  });
  it('retries unknown start with the same UUID and method', () => {
    setup();
    page.choose('QR');
    page.confirm();
    const req = http.expectOne(`${base}/sales/31/payments`);
    const original = req.request.headers.get('Idempotency-Key');
    req.error(new ProgressEvent('error'));
    page.retry();
    const retry = http.expectOne(`${base}/sales/31/payments`);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(original);
    expect(retry.request.body).toEqual({ medio: 'QR' });
    retry.flush({}, { status: 503, statusText: 'Unavailable' });
  });
  it('recovers saved pending payment without creating another attempt', () => {
    setup({ ...sale, canal: 'DIGITAL' }, true);
    http.expectOne(`${base}/payments/9`).flush({ data: card() });
    page.newAttempt();
    expect(page.attempt()?.idPago).toBe(9);
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('retries uncertain Checkout creation with the same persisted payment', () => {
    setup({ ...sale, canal: 'DIGITAL' });
    start('TARJETA');
    http
      .expectOne(`${base}/payments/9/stripe/checkout-session`)
      .flush({}, { status: 503, statusText: 'Unavailable' });
    page.retry();
    http.expectOne(`${base}/payments/9`).flush({ data: card() });
    checkout();
    expect(api.attempt(31)?.idPago).toBe(9);
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('recovers an uncertain persisted session through sync', () => {
    setup({ ...sale, canal: 'DIGITAL' }, true);
    const pending = { ...card(), referencia_externa: 'cs_test_demo' };
    http.expectOne(`${base}/payments/9`).flush({ data: pending });
    page.refresh(true);
    http
      .expectOne(`${base}/payments/9/stripe/sync`)
      .flush({}, { status: 503, statusText: 'Unavailable' });
    page.retry();
    http.expectOne(`${base}/payments/9/stripe/sync`).flush({ data: pending });
    expect(page.uncertain()).toBe(false);
    http.expectNone(`${base}/payments/9/stripe/checkout-session`);
  });
  it('navigation failure releases loading while preserving recovery', () => {
    setup();
    go.mockImplementationOnce(() => {
      throw new Error('navigation');
    });
    checkout(start('TARJETA'));
    expect(page.busy()).toBe(false);
    expect(page.error()).toBeTruthy();
    expect(page.attempt()?.idPago).toBe(9);
  });
  for (const status of [401, 403, 404, 409, 422, 500, 503])
    it(`handles API ${status} without exposing details`, () => {
      setup();
      page.confirm();
      http
        .expectOne(`${base}/sales/31/payments`)
        .flush({ message: 'secret trace' }, { status, statusText: 'Error' });
      fixture.detectChanges();
      expect(page.error()).toBeTruthy();
      expect(text()).not.toContain('secret trace');
      if (status === 401) {
        expect(page.canPay()).toBe(false);
        expect(text()).toContain('Iniciar sesión');
      }
      if (status === 409) {
        page.newAttempt();
        expect(page.attempt()).not.toBeNull();
      }
    });
  it('does not pay without a sale snapshot', () => {
    setup(null);
    page.confirm();
    expect(page.error()).toContain('resumen');
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('does not create a payment if persistence fails', () => {
    setup();
    vi.spyOn(api, 'saveAttempt').mockImplementation(() => {
      throw new Error('storage');
    });
    page.confirm();
    page.retry();
    expect(page.error()).toContain('almacenamiento');
    http.expectNone(`${base}/sales/31/payments`);
  });
  it('rejects recovery of a payment from another sale', () => {
    setup();
    page.recover('9');
    http.expectOne(`${base}/payments/9`).flush({ data: payment({ id_venta: 99 }) });
    expect(page.payment()).toBeNull();
    expect(page.error()).toBeTruthy();
  });
});

describe('Checkout URL security', () => {
  it('blocks untrusted URLs before browser navigation', () => {
    const navigation = new CheckoutNavigationService();
    for (const url of [
      'http://checkout.stripe.com/c/pay/demo',
      'https://evil.example',
      'https://checkout.stripe.com.evil.example',
      'javascript:alert(1)',
      'https://user:pass@checkout.stripe.com/c/pay/demo',
      'https://checkout.stripe.com:444/c/pay/demo',
    ])
      expect(() => navigation.go(url)).toThrow();
  });
});
