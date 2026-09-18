import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { CartData } from '../../core/services/client-cart.service';
import { ClientCheckoutService, DigitalSale } from '../../core/services/client-checkout.service';
import { Checkout } from './checkout';
import { routes } from '../../app.routes';
import { clientGuard } from '../../core/guards/client.guard';

const cart: CartData = {
  id_carrito: 9, estado: 'ACTIVO', cantidad_items: 1, cantidad_unidades: 2,
  subtotal: '400.00', descuento_total: '80.00', total: '320.00', items: [{
    id_detalle_carrito: 1, id_producto: 7, id_variante_producto: 15, nombre_producto: 'Camisa Oxford', sku: 'CAM-M-BLA',
    talla: { id_talla: 1, nombre: 'M' }, color: { id_color: 2, nombre: 'Blanco', codigo_hex: null },
    cantidad: 2, imagen_principal: null, precio_base: '200.00', precio_final: '160.00', promocion: null,
    subtotal_linea: '320.00', disponibilidad_actual: 5, estado_producto: true, estado_variante: true,
  }],
};
const sale: DigitalSale = {
  id_venta: 31, numero_venta: 'DIG-31', id_carrito: 9, id_cliente: 7, id_sucursal: 2,
  estado: 'PENDIENTE', canal: 'DIGITAL', moneda: 'BOB', stock_comprometido: true,
  fecha_expiracion_pago: '2026-09-17T16:30:00', subtotal: '400.00', descuento_total: '100.00', total: '300.00',
  items: [{ id_variante_producto: 15, id_promocion: 8, cantidad: 2, precio_unitario: '200.00', descuento_unitario: '50.00', subtotal_linea: '300.00' }],
};
const availability = (id = 2, stock = 5, variant = 15) => ({
  variante: { id_variante_producto: variant, sku: 'CAM-M-BLA', talla: cart.items[0].talla, color: cart.items[0].color, estado: true },
  id_sucursal: id, nombre_sucursal: id === 2 ? 'Centro' : 'Sur', nombre_ciudad: 'La Paz', direccion: 'Av. 1', id_ciudad: 1,
  stock_actual: 10, stock_reservado: 5, stock_disponible: stock, hora_apertura: null, hora_cierre: null,
});

describe('Checkout web CU21', () => {
  let fixture: ComponentFixture<Checkout>;
  let page: Checkout;
  let http: HttpTestingController;
  const base = environment.apiUrl;
  const text = () => fixture.nativeElement.textContent as string;
  function setup(id: string | null = null) {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
      { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap(id === null ? {} : { id }) } } },
    ] });
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Checkout); page = fixture.componentInstance; fixture.detectChanges();
  }
  function load(value = cart, rows = [availability()]) {
    http.expectOne(`${base}/api/client/cart`).flush({ success: true, data: value });
    if (value.items.length && value.items.every(item => item.estado_producto && item.estado_variante)) {
      http.expectOne(req => req.url === `${base}/api/catalog/products/7/availability` && req.params.get('id_variante_producto') === '15')
        .flush({ success: true, data: { producto: { estado: true }, disponibilidad: rows } });
    }
    fixture.detectChanges();
  }
  function selectBranch(id = '2') {
    const select = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
    select.value = id; select.dispatchEvent(new Event('change')); fixture.detectChanges();
  }
  afterEach(() => { http?.verify(); fixture?.destroy(); sessionStorage.clear(); localStorage.clear(); });

  it('renders a valid cart, size/color, quantities and backend totals before confirmation', () => {
    setup(); load();
    for (const label of ['Camisa Oxford', 'Talla M', 'Blanco', 'Cantidad: 2', 'Descuentos']) expect(text()).toContain(label);
    expect(text()).toContain(page['money']('320.00')); expect(page['canConfirm']()).toBe(false);
    selectBranch(); expect(page['canConfirm']()).toBe(true);
  });
  it('offers only branches with complete stock and does not require reservation schedules', () => {
    setup(); load(cart, [availability(2, 1), availability(3, 2)]);
    expect(page['branches']().map(row => row.id_sucursal)).toEqual([3]);
    selectBranch('3'); expect(page['canConfirm']()).toBe(true);
  });
  it('requires availability at the same branch for every variant', () => {
    setup();
    const two = { ...cart, items: [...cart.items, { ...cart.items[0], id_variante_producto: 16, cantidad: 3 }] };
    http.expectOne(`${base}/api/client/cart`).flush({ success: true, data: two });
    const requests = http.match(req => req.url.endsWith('/7/availability'));
    expect(requests).toHaveLength(2);
    requests[0].flush({ data: { producto: { estado: true }, disponibilidad: [availability(2), availability(3)] } });
    requests[1].flush({ data: { producto: { estado: true }, disponibilidad: [availability(2, 2, 16), availability(3, 3, 16)] } });
    expect(page['branches']().map(row => row.id_sucursal)).toEqual([3]);
  });
  it('blocks checkout for an empty cart', () => {
    setup(); load({ ...cart, items: [], id_carrito: null, estado: null }); page['confirm']();
    expect(text()).toContain('Tu carrito está vacío'); expect(page['canConfirm']()).toBe(false);
    http.expectNone(`${base}/api/client/cart/checkout`);
  });
  it('blocks checkout for inactive variants', () => {
    setup(); load({ ...cart, items: [{ ...cart.items[0], estado_variante: false }] });
    expect(text()).toContain('variantes no disponibles'); expect(page['canConfirm']()).toBe(false);
  });
  it('reports insufficient availability without sending checkout', () => {
    setup(); load(cart, []); expect(text()).toContain('Ninguna sucursal'); expect(page['canConfirm']()).toBe(false);
  });
  it('rejects an invalid selection', () => {
    setup(); load(); page['chooseBranch']({ target: { value: '999' } } as unknown as Event);
    page['confirm'](); expect(page['branchId']()).toBeNull(); http.expectNone(`${base}/api/client/cart/checkout`);
  });
  it('sends only IDs, blocks double submission, and renders historical pending sale totals', () => {
    setup(); load(); selectBranch(); page['confirm'](); page['confirm'](); fixture.detectChanges();
    const requests = http.match(`${base}/api/client/cart/checkout`); expect(requests).toHaveLength(1);
    expect(requests[0].request.method).toBe('POST'); expect(requests[0].request.body).toEqual({ id_carrito: 9, id_sucursal: 2 });
    expect(text()).toContain('Preparando compra...'); expect(fixture.nativeElement.querySelector('select').disabled).toBe(true);
    requests[0].flush({ success: true, data: sale }); fixture.detectChanges();
    for (const label of ['DIG-31', 'PENDIENTE', 'Camisa Oxford', 'Centro', 'BOB', 'Continuar al pago', 'hora de Bolivia']) expect(text()).toContain(label);
    expect(text()).toContain(page['money']('300.00')); expect(page['saving']()).toBe(false);
    expect(page['canConfirm']()).toBe(false); page['confirm']();
    expect(TestBed.inject(Router).navigate).toHaveBeenCalledWith(['/compra', 31], { replaceUrl: true });
  });
  for (const status of [403, 404, 409, 422, 500]) {
    it(`handles API ${status} and releases processing state`, () => {
      setup(); load(); selectBranch(); page['confirm']();
      http.expectOne(`${base}/api/client/cart/checkout`).flush({ message: 'Stock o sucursal no disponible', detail: 'trace' }, { status, statusText: 'Error' });
      fixture.detectChanges(); expect(page['sale']()).toBeNull(); expect(page['saving']()).toBe(false);
      expect(text()).toContain(status === 500 ? 'No fue posible procesar la compra' : 'Stock o sucursal no disponible');
      expect(text()).not.toContain('trace');
    });
  }
  it('handles expired sessions and disables confirmation', () => {
    setup(); load(); selectBranch(); page['confirm']();
    http.expectOne(`${base}/api/client/cart/checkout`).flush({}, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges(); expect(text()).toContain('Tu sesión expiró'); expect(page['canConfirm']()).toBe(false);
    expect(fixture.nativeElement.querySelector('a[href="/login"]')).not.toBeNull();
  });
  it('retries a network failure with the same IDs without refreshing or changing branch', () => {
    setup(); load(); selectBranch(); page['confirm']();
    http.expectOne(`${base}/api/client/cart/checkout`).error(new ProgressEvent('error'));
    fixture.detectChanges(); expect(text()).toContain('No pudimos conectar'); expect(page['uncertain']()).toBe(true);
    page['chooseBranch']({ target: { value: '3' } } as unknown as Event); page['load']();
    expect(page['branchId']()).toBe(2); page['confirm']();
    const req = http.expectOne(`${base}/api/client/cart/checkout`); expect(req.request.body).toEqual({ id_carrito: 9, id_sucursal: 2 });
    req.flush({ success: true, data: sale });
  });
  it('loads pending sale through GET on refresh and preserves presentation labels', () => {
    setup('31');
    TestBed.inject(ClientCheckoutService).savePresentation(31, { id_sucursal: 2, sucursal: 'Centro · La Paz', items: [{ id_variante_producto: 15, nombre: 'Camisa Oxford', talla: 'M', color: 'Blanco' }] });
    const req = http.expectOne(`${base}/api/client/sales/31`); expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: sale }); fixture.detectChanges();
    expect(text()).toContain('Camisa Oxford'); expect(text()).toContain('Centro'); expect(text()).toContain('PENDIENTE');
    http.expectNone(`${base}/api/client/cart`);
  });
  it('shows variant and branch IDs if no presentation metadata is available', () => {
    setup('31'); http.expectOne(`${base}/api/client/sales/31`).flush({ data: { ...sale, fecha_expiracion_pago: null } });
    fixture.detectChanges(); expect(text()).toContain('Variante #15'); expect(text()).toContain('Sucursal #2');
    expect(text()).not.toContain('El plazo para pagar vence');
  });
  it('handles availability API failure and offers refresh', () => {
    setup(); http.expectOne(`${base}/api/client/cart`).flush({ data: cart });
    http.expectOne(req => req.url.endsWith('/availability')).flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges(); expect(page['loading']()).toBe(false); expect(page['canConfirm']()).toBe(false);
    expect(text()).toContain('Actualizar resumen');
  });
  it('guards both new routes with clientGuard', async () => {
    for (const path of ['compra', 'compra/:id']) {
      const route = routes.find(route => route.path === path)!;
      expect(route.canActivate).toEqual([clientGuard]);
      expect(await (route.loadComponent as () => Promise<unknown>)()).toBe(Checkout);
    }
  });
  it('opens CU22 with the existing sale summary without creating another sale', () => {
    setup('31'); http.expectOne(`${base}/api/client/sales/31`).flush({ data: sale });
    page['pay']();
    expect(TestBed.inject(Router).navigate).toHaveBeenCalledWith(['/compra', 31, 'pago']);
    expect(sessionStorage.getItem('fashionstore_cu22_undefined_31_sale')).toContain('DIG-31');
    http.expectNone(`${base}/api/client/cart/checkout`);
  });
});
