import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SaleReceipt } from '../../core/services/receipts.service';
import { SessionService } from '../../core/services/session.service';
import { routes } from '../../app.routes';
import { clientGuard } from '../../core/guards/client.guard';
import { staffGuard, staffChildGuard } from '../../core/guards/staff.guard';
import { ReceiptPage } from './receipt';

const receipt: SaleReceipt = {
  numero_venta: 'VTA-31', fecha_completada: '2026-09-17T12:00:00', canal: 'DIGITAL',
  sucursal: { nombre: 'Centro', direccion: 'Calle A' }, cliente: { nombre: 'Ana', apellido: 'Perez' },
  productos: [{ nombre: 'Camisa', talla: 'M', color: 'Blanco', cantidad: 2,
    precio_unitario: '200.00', descuento_unitario: '50.00', subtotal_linea: '300.00' }],
  subtotal: '400.00', descuento_total: '100.00', total: '300.00', moneda: 'BOB',
  pago: { medio: 'TARJETA', estado: 'APROBADO', monto: '300.00' },
};
describe('CU25 comprobante', () => {
  let fixture: ComponentFixture<ReceiptPage>;
  let http: HttpTestingController;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let url: string;
  function setup(staff = false, id = '31') {
    params = new BehaviorSubject(convertToParamMap({ id }));
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
      { provide: SessionService, useValue: { getAccessToken: () => 'test-token' } },
      { provide: ActivatedRoute, useValue: { paramMap: params, snapshot: { data: { audience: staff ? 'staff' : 'client' } } } },
    ] });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ReceiptPage);
    fixture.detectChanges();
    url = `${environment.apiUrl}/api/${staff ? 'staff/sales' : 'client/purchases'}/31/receipt`;
  }
  function flush(data = receipt) {
    const req = http.expectOne(url);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-token');
    req.flush({ success: true, data }); fixture.detectChanges();
  }
  const text = () => fixture.nativeElement.textContent as string;
  afterEach(() => { http?.verify(); fixture?.destroy(); });
  it('renders digital receipt with historical lines, totals and payment', () => {
    setup(); flush();
    for (const value of ['FashionStore', 'Comprobante de venta', 'VTA-31', 'COMPLETADA', 'Centro',
      'Calle A', 'Ana Perez', 'Camisa', 'Talla: M', 'Color: Blanco', 'Tarjeta', 'APROBADO']) expect(text()).toContain(value);
    expect(text()).toContain(fixture.componentInstance.money('300.00'));
    expect(fixture.nativeElement.querySelectorAll('tbody tr').length).toBe(1);
    expect(fixture.componentInstance.back()).toBe('/mis-compras/31');
    expect(text()).not.toContain('idempotencia');
  });
  it('shows loading and blocks printing until loaded', () => {
    setup(); const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    expect(text()).toContain('Cargando comprobante');
    expect(fixture.nativeElement.querySelector('.receipt-actions button').disabled).toBe(true);
    fixture.componentInstance.print(); expect(print).not.toHaveBeenCalled(); flush(); print.mockRestore();
  });
  it('loads staff endpoint and presencial receipt without client', () => {
    setup(true); flush({ ...receipt, canal: 'PRESENCIAL', cliente: null, pago: { ...receipt.pago, medio: 'EFECTIVO' } });
    expect(text()).toContain('Cliente no registrado'); expect(text()).toContain('Presencial'); expect(text()).toContain('Efectivo');
    expect(fixture.componentInstance.back()).toBe('/staff/ventas/nueva');
  });
  it('shows QR and refunded payment without changing original total', () => {
    setup(); flush({ ...receipt, pago: { ...receipt.pago, medio: 'QR', estado: 'REEMBOLSADO' } });
    expect(text()).toContain('QR'); expect(text()).toContain('REEMBOLSADO'); expect(fixture.componentInstance.receipt()?.total).toBe('300.00');
  });
  it('calls window.print from the print action', () => {
    setup(); flush(); const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    fixture.nativeElement.querySelector('.receipt-actions button').click(); expect(print).toHaveBeenCalledOnce(); print.mockRestore();
  });
  for (const status of [401, 403, 404, 409, 500]) it(`handles API ${status} without exposing internal errors`, () => {
    setup(); http.expectOne(url).flush({ message: 'secret PaymentIntent trace' }, { status, statusText: 'Error' }); fixture.detectChanges();
    expect(text()).toContain('Comprobante no disponible'); expect(text()).not.toContain('secret'); expect(fixture.componentInstance.receipt()).toBeNull();
    expect(fixture.nativeElement.querySelector('.receipt-actions button').disabled).toBe(true);
    if (status === 401) expect(text()).toContain('Iniciar sesión');
    if (status === 409) { expect(text()).toContain('PENDIENTES'); expect(text()).toContain('ANULADAS'); }
  });
  it('retries network error and prevents duplicate loading', () => {
    setup(); fixture.componentInstance.load(); http.expectOne(url).error(new ProgressEvent('error')); fixture.detectChanges();
    expect(text()).toContain('conexión'); fixture.componentInstance.load(); flush(); expect(fixture.componentInstance.error()).toBe('');
  });
  it('cancels stale requests when route changes', () => {
    setup(); const old = http.expectOne(url); params.next(convertToParamMap({ id: '32' })); expect(old.cancelled).toBe(true);
    http.expectOne(url.replace('/31/', '/32/')).flush({ success: true, data: { ...receipt, numero_venta: 'VTA-32' } });
    expect(fixture.componentInstance.receipt()?.numero_venta).toBe('VTA-32');
  });
  it('rejects invalid ids without calling API', () => { setup(false, '0'); expect(text()).toContain('Comprobante no encontrado'); http.expectNone(() => true); });
  it('protects client and staff routes with matching guards', () => {
    expect(routes.find(r => r.path === 'mis-compras/:id/comprobante')?.canActivate).toContain(clientGuard);
    const staff = routes.find(r => r.path === 'staff')!;
    expect(staff.canActivate).toContain(staffGuard); expect(staff.canActivateChild).toContain(staffChildGuard);
    expect(staff.children?.find(r => r.path === 'ventas/:id/comprobante')?.data?.['audience']).toBe('staff');
  });
});
