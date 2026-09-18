import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { ReturnDetail } from '../../../core/services/returns.service';
import { SessionService } from '../../../core/services/session.service';
import { StaffReturnsPage } from './staff-returns';

const base = `${environment.apiUrl}/api/staff/returns`;
const row: ReturnDetail = {
  id_devolucion: 7,
  id_venta: 31,
  tipo: 'DEVOLUCION',
  estado: 'SOLICITADA',
  motivo: 'Talla',
  id_usuario_solicitante: 12,
  created_at: '2026-09-17T12:00:00',
  lineas: [
    { id_variante_producto: 11, cantidad: 2, cantidad_reintegrar: 0, importe_restitucion: '20.00' },
  ],
  reembolsos: [],
};
const refund = {
  id_reembolso: 9,
  id_pago: 3,
  estado: 'PENDIENTE' as const,
  monto: '20.00',
  referencia_externa: null,
};

const stripePayment = {
  id_pago: 3,
  medio: 'TARJETA' as const,
  proveedor: 'STRIPE' as const,
  entorno: 'TEST' as const,
  estado: 'APROBADO',
  monto: '20.00',
  moneda: 'BOB',
};
const qrPayment = {
  ...stripePayment,
  medio: 'QR' as const,
  proveedor: 'MANUAL' as const,
  entorno: 'LOCAL' as const,
};
describe('CU24 personal', () => {
  let fixture: ComponentFixture<StaffReturnsPage>;
  let page: StaffReturnsPage;
  let http: HttpTestingController;
  function setup(id: string | null = '7', data: ReturnDetail = row) {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(convertToParamMap(id === null ? {} : { id })) },
        },
        {
          provide: SessionService,
          useValue: {
            getAccessToken: () => 'token',
            getUser: () => ({ id_usuario: 5 }),
            logout: vi.fn(),
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffReturnsPage);
    page = fixture.componentInstance;
    http
      .expectOne(id === null ? (r) => r.url === base : `${base}/${id}`)
      .flush({ success: true, data: id === null ? [data] : data });
    fixture.detectChanges();
  }
  afterEach(() => {
    fixture?.destroy();
    http?.verify();
  });
  it('lista referencias, venta, motivo y filtra estado con paginación', () => {
    setup(null);
    expect(fixture.nativeElement.textContent).toContain('SOL-00007');
    page.filter('APROBADA');
    const req = http.expectOne((r) => r.url === base && r.params.get('estado') === 'APROBADA');
    expect(req.request.params.get('limit')).toBe('20');
    expect(req.request.params.get('offset')).toBe('0');
    req.flush({ success: true, data: [] });
  });
  it('aprueba todas las líneas con importes y reintegro autorizado', () => {
    setup();
    page.open('APROBADA');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('dialog')).toBeTruthy();
    page.edit(11, 'cantidad_reintegrar', 1);
    page.edit(11, 'importe_restitucion', '15.00');
    page.confirm();
    const req = http.expectOne(`${base}/7/review`);
    expect(req.request.body).toEqual({
      resultado: 'APROBADA',
      lineas: [{ id_variante_producto: 11, cantidad_reintegrar: 1, importe_restitucion: '15.00' }],
    });
    req.flush({ success: true, data: { ...row, estado: 'APROBADA' } });
    http
      .expectOne(`${base}/7`)
      .flush({ success: true, data: { ...row, estado: 'APROBADA', pago: stripePayment } });
    expect(page.detail()?.estado).toBe('APROBADA');
  });
  it('rechaza sin enviar líneas', () => {
    setup();
    page.open('RECHAZADA');
    page.confirm();
    const req = http.expectOne(`${base}/7/review`);
    expect(req.request.body).toEqual({ resultado: 'RECHAZADA' });
    req.flush({ success: true, data: { ...row, estado: 'RECHAZADA' } });
    expect(page.success()).toContain('rechazada');
  });
  it('aprueba cancelación sin líneas', () => {
    setup('7', { ...row, tipo: 'CANCELACION', lineas: [] });
    page.open('APROBADA');
    page.confirm();
    const req = http.expectOne(`${base}/7/review`);
    expect(req.request.body).toEqual({ resultado: 'APROBADA' });
    req.flush({
      success: true,
      data: { ...row, tipo: 'CANCELACION', estado: 'APROBADA', lineas: [] },
    });
    http
      .expectOne(`${base}/7`)
      .flush({
        success: true,
        data: { ...row, tipo: 'CANCELACION', estado: 'APROBADA', lineas: [] },
      });
  });
  it('no permite reintegrar más que lo solicitado ni exceder importe', () => {
    setup();
    page.open('APROBADA');
    for (const [quantity, amount] of [
      [3, '20'],
      [-1, '20'],
      [0.5, '20'],
      [1, '21'],
      [1, '-1'],
      [1, '1.001'],
    ] as const) {
      page.edit(11, 'cantidad_reintegrar', quantity);
      page.edit(11, 'importe_restitucion', amount);
      page.confirm();
      expect(page.modalError()).toContain('Revisa');
    }
    http.expectNone(`${base}/7/review`);
  });
  it('procesa devolución sin reembolso', () => {
    setup('7', { ...row, estado: 'APROBADA' });
    page.open('PROCESAR');
    page.confirm();
    const req = http.expectOne(`${base}/7/process`);
    expect(req.request.body).toEqual({});
    req.flush({ success: true, data: { ...row, estado: 'PROCESADA' } });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('DEVOLUCIÓN PROCESADA');
  });
  it('exige medio original cuando no lo entrega el contrato', () => {
    setup('7', { ...row, estado: 'APROBADA', reembolsos: [refund] });
    page.open('PROCESAR');
    page.confirm();
    expect(page.modalError()).toContain('pago original aprobado');
    http.expectNone(`${base}/7/process`);
  });
  it('reembolso manual requiere comprobante y envía solo referencia', () => {
    setup('7', { ...row, estado: 'APROBADA', reembolsos: [refund], pago: qrPayment });
    page.open('PROCESAR');
    page.confirm();
    expect(page.modalError()).toContain('comprobante');
    page.receipt.set(' REC-100 ');
    page.confirm();
    const req = http.expectOne(`${base}/7/process`);
    expect(req.request.body).toEqual({ referencia_manual: 'REC-100' });
    req.flush({
      success: true,
      data: { ...row, estado: 'PROCESADA', reembolsos: [{ ...refund, estado: 'APROBADO' }] },
    });
  });
  it('Stripe no pide tarjeta; pendiente permite reconsultar con process', () => {
    setup('7', { ...row, estado: 'APROBADA', reembolsos: [refund], pago: stripePayment });
    page.open('PROCESAR');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('select[name=method]')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Tarjeta');
    expect(fixture.nativeElement.querySelector('input[name=receipt]')).toBeNull();
    page.confirm();
    const req = http.expectOne(`${base}/7/process`);
    expect(req.request.body).toEqual({});
    const pending = {
      ...row,
      pago: stripePayment,
      estado: 'APROBADA' as const,
      reembolsos: [{ ...refund, referencia_externa: 're_test' }],
    };
    req.flush({ success: true, data: pending });
    fixture.detectChanges();
    expect(page.success()).toContain('pendiente');
    expect(fixture.nativeElement.textContent).toContain('Reconsultar reembolso');
    page.open('PROCESAR');
    expect(page.method()).toBe('STRIPE');
    page.confirm();
    http.expectOne(`${base}/7/process`).flush({
      success: true,
      data: {
        ...pending,
        estado: 'PROCESADA',
        reembolsos: [{ ...pending.reembolsos[0], estado: 'APROBADO' }],
      },
    });
    expect(page.detail()?.reembolsos[0].estado).toBe('APROBADO');
  });
  it('reembolso fallido impide crear otro intento', () => {
    setup('7', { ...row, estado: 'APROBADA', reembolsos: [{ ...refund, estado: 'RECHAZADO' }] });
    page.open('PROCESAR');
    expect(page.action()).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('Reembolso fallido');
  });
  it('bloquea doble confirmación', () => {
    setup();
    page.open('RECHAZADA');
    page.confirm();
    page.confirm();
    http
      .expectOne(`${base}/7/review`)
      .flush({ success: true, data: { ...row, estado: 'RECHAZADA' } });
  });
  it('muestra error de solicitud ya resuelta y permite actualizar', () => {
    setup();
    page.open('APROBADA');
    page.confirm();
    http
      .expectOne(`${base}/7/review`)
      .flush({ message: 'Solicitud ya resuelta' }, { status: 409, statusText: 'Conflict' });
    expect(page.modalError()).toBe('Solicitud ya resuelta');
    expect(page.busy()).toBe(false);
    page.close();
    page.load();
    http.expectOne(`${base}/7`).flush({ success: true, data: { ...row, estado: 'PROCESADA' } });
    expect(page.detail()?.estado).toBe('PROCESADA');
  });
  it('impide resolver solicitudes propias y estados finales', () => {
    setup('7', { ...row, id_usuario_solicitante: 5 });
    page.open('APROBADA');
    expect(page.action()).toBeNull();
    page.detail.set({ ...row, estado: 'PROCESADA' });
    page.open('PROCESAR');
    expect(page.action()).toBeNull();
  });
  it('efectivo se detecta sin selector y requiere comprobante', () => {
    setup('7', {
      ...row,
      estado: 'APROBADA',
      reembolsos: [refund],
      pago: { ...qrPayment, medio: 'EFECTIVO' },
    });
    page.open('PROCESAR');
    fixture.detectChanges();
    expect(page.method()).toBe('MANUAL');
    expect(fixture.nativeElement.querySelector('select[name=method]')).toBeNull();
    expect(fixture.nativeElement.querySelector('input[name=receipt]')).toBeTruthy();
    page.confirm();
    http.expectNone(`${base}/7/process`);
  });
  it('aprobar refresca antes de permitir procesar el pago original', () => {
    setup();
    page.open('APROBADA');
    page.confirm();
    http
      .expectOne(`${base}/7/review`)
      .flush({ success: true, data: { ...row, estado: 'APROBADA' } });
    page.open('PROCESAR');
    expect(page.action()).toBeNull();
    expect(page.busy()).toBe(true);
    http
      .expectOne(`${base}/7`)
      .flush({
        success: true,
        data: { ...row, estado: 'APROBADA', pago: stripePayment, reembolsos: [refund] },
      });
    page.open('PROCESAR');
    page.confirm();
    const req = http.expectOne(`${base}/7/process`);
    expect(req.request.body).toEqual({});
    req.flush({ success: true, data: { ...row, estado: 'PROCESADA', pago: stripePayment } });
  });
  it('fallo de refresco mantiene bloqueado el procesamiento hasta actualizar', () => {
    setup();
    page.open('APROBADA');
    page.confirm();
    http
      .expectOne(`${base}/7/review`)
      .flush({ success: true, data: { ...row, estado: 'APROBADA' } });
    http.expectOne(`${base}/7`).error(new ProgressEvent('error'));
    page.open('PROCESAR');
    expect(page.action()).toBeNull();
    expect(page.refreshRequired()).toBe(true);
    page.load();
    http
      .expectOne(`${base}/7`)
      .flush({ success: true, data: { ...row, estado: 'APROBADA', pago: stripePayment } });
    expect(page.refreshRequired()).toBe(false);
    page.open('PROCESAR');
    expect(page.action()).toBe('PROCESAR');
  });
});
