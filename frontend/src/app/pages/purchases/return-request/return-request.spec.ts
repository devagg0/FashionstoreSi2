import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { PurchaseDetail } from '../../../core/services/client-purchases.service';
import { ReturnDetail } from '../../../core/services/returns.service';
import { SessionService } from '../../../core/services/session.service';
import { PurchaseReturnRequest } from './return-request';

const base = `${environment.apiUrl}/api`;
const purchase: PurchaseDetail = {
  id_venta: 31,
  numero_venta: 'VTA-31',
  fecha: '2026-09-17T12:00:00',
  fecha_completada: null,
  canal: 'DIGITAL',
  estado: 'PENDIENTE',
  subtotal: '40',
  descuento_total: '0',
  total: '40',
  moneda: 'BOB',
  sucursal: { id_sucursal: 2, nombre: 'Centro' },
  pago: null,
  pagos: [],
  devoluciones: [],
  reembolsos: [],
  productos: [1, 2].map((id) => ({
    id_detalle_venta: id,
    id_variante_producto: id + 10,
    nombre: 'Camisa',
    talla: 'M',
    color: 'Blanco',
    cantidad: 2,
    precio_unitario: '10',
    descuento_unitario: '0',
    subtotal_linea: '20',
  })),
};
const returned: ReturnDetail = {
  id_devolucion: 7,
  id_venta: 31,
  tipo: 'DEVOLUCION',
  estado: 'SOLICITADA',
  motivo: 'Talla',
  id_usuario_solicitante: 12,
  created_at: '2026-09-17T12:00:00',
  lineas: [],
  reembolsos: [],
};

describe('CU24 cliente', () => {
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
            getAccessToken: () => 'token',
            getUser: () => ({ id_usuario: 12 }),
            logout: vi.fn(),
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PurchaseReturnRequest);
    page = fixture.componentInstance;
    fixture.componentRef.setInput('purchase', structuredClone(purchase));
    fixture.detectChanges();
  });
  afterEach(() => {
    fixture.destroy();
    http.verify();
    sessionStorage.clear();
  });
  function completed() {
    fixture.componentRef.setInput('purchase', {
      ...structuredClone(purchase),
      estado: 'COMPLETADA',
    });
    fixture.detectChanges();
  }
  function send(quantity = 1) {
    completed();
    page.open('DEVOLUCION');
    page.reason.set('Talla');
    page.quantity(purchase.productos[0], quantity);
    page.submit();
  }
  it('solicita cancelación pendiente con motivo y UUID', () => {
    expect(fixture.nativeElement.textContent).toContain('Cancelar compra');
    page.open('CANCELACION');
    page.reason.set(' Cambio de planes ');
    page.submit();
    const req = http.expectOne(`${base}/client/purchases/31/cancellation`);
    expect(req.request.body).toEqual({ motivo: 'Cambio de planes' });
    expect(req.request.headers.get('Authorization')).toBe('Bearer token');
    expect(req.request.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    req.flush({ success: true, data: { ...returned, tipo: 'CANCELACION' } });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('SOL-00007');
    expect(page.kind()).toBeNull();
  });
  it('no ofrece cancelación completada o con cancelación activa', () => {
    completed();
    expect(page.canCancel()).toBe(false);
    fixture.componentRef.setInput('purchase', {
      ...purchase,
      devoluciones: [{ ...returned, tipo: 'CANCELACION' }],
    });
    fixture.detectChanges();
    expect(page.canCancel()).toBe(false);
  });
  it('envía solo las líneas de devolución parcial seleccionadas', () => {
    send();
    const req = http.expectOne(`${base}/client/purchases/31/returns`);
    expect(req.request.body).toEqual({
      motivo: 'Talla',
      lineas: [{ id_detalle_venta: 1, cantidad: 1 }],
    });
    req.flush({ success: true, data: returned });
  });
  it('envía devolución total', () => {
    completed();
    page.open('DEVOLUCION');
    page.reason.set('Devolver');
    purchase.productos.forEach((item) => page.quantity(item, item.cantidad));
    page.submit();
    const req = http.expectOne(`${base}/client/purchases/31/returns`);
    expect(req.request.body.lineas).toEqual([
      { id_detalle_venta: 1, cantidad: 2 },
      { id_detalle_venta: 2, cantidad: 2 },
    ]);
    req.flush({ success: true, data: returned });
  });
  it('exige motivo y unidades seleccionadas', () => {
    completed();
    page.open('DEVOLUCION');
    page.submit();
    expect(page.error()).toContain('motivo');
    page.reason.set('Motivo');
    page.submit();
    expect(page.error()).toContain('al menos una');
    http.expectNone(`${base}/client/purchases/31/returns`);
  });
  it('rechaza cantidades negativas, fraccionarias o excesivas', () => {
    completed();
    page.open('DEVOLUCION');
    page.reason.set('Motivo');
    for (const qty of [-1, 0.5, 3, NaN]) {
      page.quantity(purchase.productos[0], qty);
      page.submit();
      expect(page.error()).toContain('cantidades');
    }
    http.expectNone(`${base}/client/purchases/31/returns`);
  });
  it('descuenta cantidades de solicitudes anteriores activas', () => {
    fixture.componentRef.setInput('purchase', {
      ...purchase,
      estado: 'COMPLETADA',
      devoluciones: [returned],
    });
    fixture.detectChanges();
    page.open('DEVOLUCION');
    http.expectOne(`${base}/client/returns/7`).flush({
      success: true,
      data: {
        ...returned,
        lineas: [
          {
            id_variante_producto: 11,
            cantidad: 1,
            cantidad_reintegrar: 0,
            importe_restitucion: '10',
          },
        ],
      },
    });
    expect(page.available(purchase.productos[0])).toBe(1);
    page.reason.set('Motivo');
    page.quantity(purchase.productos[0], 2);
    page.submit();
    http.expectNone(`${base}/client/purchases/31/returns`);
  });
  it('bloquea envío si no pudo verificar devoluciones anteriores', () => {
    fixture.componentRef.setInput('purchase', {
      ...purchase,
      estado: 'COMPLETADA',
      devoluciones: [returned],
    });
    fixture.detectChanges();
    page.open('DEVOLUCION');
    http.expectOne(`${base}/client/returns/7`).flush({}, { status: 500, statusText: 'Error' });
    page.reason.set('Motivo');
    page.quantity(purchase.productos[0], 1);
    page.submit();
    expect(page.verified()).toBe(false);
    http.expectNone(`${base}/client/purchases/31/returns`);
  });
  it('bloquea doble clic y conserva UUID tras error de red', () => {
    send();
    page.submit();
    const req = http.expectOne(`${base}/client/purchases/31/returns`);
    const key = req.request.headers.get('Idempotency-Key');
    req.error(new ProgressEvent('error'));
    expect(page.frozen()).toBe(true);
    page.submit();
    const retry = http.expectOne(`${base}/client/purchases/31/returns`);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    retry.flush({ success: true, data: returned });
  });
  it('reintenta la misma clave aunque el envío incierto aparezca en el historial', () => {
    send(2);
    const first = http.expectOne(`${base}/client/purchases/31/returns`);
    const key = first.request.headers.get('Idempotency-Key');
    first.error(new ProgressEvent('error'));
    page.close();
    fixture.componentRef.setInput('purchase', {
      ...purchase,
      estado: 'COMPLETADA',
      devoluciones: [returned],
    });
    fixture.detectChanges();
    page.open('DEVOLUCION');
    http.expectOne(`${base}/client/returns/7`).flush({
      success: true,
      data: {
        ...returned,
        lineas: [
          {
            id_variante_producto: 11,
            cantidad: 2,
            cantidad_reintegrar: 0,
            importe_restitucion: '20',
          },
        ],
      },
    });
    expect(page.available(purchase.productos[0])).toBe(0);
    page.submit();
    const retry = http.expectOne(`${base}/client/purchases/31/returns`);
    expect(retry.request.headers.get('Idempotency-Key')).toBe(key);
    expect(retry.request.body.lineas).toEqual([{ id_detalle_venta: 1, cantidad: 2 }]);
    retry.flush({ success: true, data: returned });
  });
  it('muestra error de duplicado del API y permite corregir', () => {
    send();
    http
      .expectOne(`${base}/client/purchases/31/returns`)
      .flush({ message: 'Solicitud duplicada' }, { status: 409, statusText: 'Conflict' });
    expect(page.error()).toBe('Solicitud duplicada');
    expect(page.busy()).toBe(false);
    expect(page.frozen()).toBe(false);
  });
  it('consulta estado propio y muestra reembolso pendiente/aprobado', () => {
    for (const state of ['PENDIENTE', 'APROBADO'] as const) {
      page.view(7);
      http.expectOne(`${base}/client/returns/7`).flush({
        success: true,
        data: {
          ...returned,
          reembolsos: [
            {
              id_reembolso: 1,
              id_pago: 2,
              estado: state,
              monto: '10',
              referencia_externa: 're_test',
            },
          ],
        },
      });
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain(state);
    }
  });
});
