import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { CartData, CartItem } from '../../core/services/client-cart.service';
import { Cart } from './cart';

const item: CartItem = {
  id_detalle_carrito: 3, id_variante_producto: 15, id_producto: 7, nombre_producto: 'Camisa Oxford',
  sku: 'CAM-M-BLA', talla: { id_talla: 1, nombre: 'M' }, color: { id_color: 2, nombre: 'Blanco', codigo_hex: '#fff' },
  imagen_principal: '/camisa.jpg', cantidad: 2, precio_base: '200.00', precio_final: '160.00',
  promocion: null, subtotal_linea: '320.00', disponibilidad_actual: 5, estado_producto: true, estado_variante: true,
};
const data: CartData = { id_carrito: 1, estado: 'ACTIVO', items: [item], cantidad_items: 1, cantidad_unidades: 2, subtotal: '400.00', descuento_total: '80.00', total: '320.00' };
const empty: CartData = { id_carrito: null, estado: null, items: [], cantidad_items: 0, cantidad_unidades: 0, subtotal: '0.00', descuento_total: '0.00', total: '0.00' };

describe('Cart CU19', () => {
  let fixture: ComponentFixture<Cart>;
  let page: Cart;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/client/cart`;
  const text = () => fixture.nativeElement.textContent as string;
  const buttons = () => Array.from(fixture.nativeElement.querySelectorAll('.quantity-controls button')) as HTMLButtonElement[];
  function load(value = data) {
    http.expectOne(url).flush({ success: true, data: value, message: 'OK' }); fixture.detectChanges();
  }
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController); fixture = TestBed.createComponent(Cart); page = fixture.componentInstance;
    fixture.detectChanges();
    const dialog = fixture.nativeElement.querySelector('dialog') as HTMLDialogElement;
    // jsdom has no top-layer implementation; browser handles focus trapping and Escape.
    dialog.showModal = () => { dialog.open = true; };
    dialog.close = () => { dialog.open = false; };
  });
  afterEach(() => { http.verify(); fixture.destroy(); });
  it('shows initial loading without an empty-cart flash', () => {
    expect(text()).toContain('Cargando carrito'); expect(text()).not.toContain('Tu carrito está vacío'); load();
  });
  it('shows the empty state and catalog link without list or summary', () => {
    load(empty); expect(text()).toContain('Tu carrito está vacío');
    expect(text()).toContain('Explora nuestro catálogo y agrega tus prendas favoritas.');
    expect(fixture.nativeElement.querySelector('.cart-empty a').getAttribute('href')).toBe('/catalogo');
    expect(fixture.nativeElement.querySelector('.cart-layout')).toBeNull();
  });
  it('renders identity, size, color, SKU and image alt', () => {
    load(); for (const value of ['Camisa Oxford', 'Talla M', 'Blanco', 'CAM-M-BLA']) expect(text()).toContain(value);
    expect(fixture.nativeElement.querySelector('img').alt).toBe(item.nombre_producto);
  });
  it('renders discounted prices, line subtotal and exact backend summary', () => {
    load({ ...data, subtotal: '999.01', descuento_total: '123.45', total: '875.56', cantidad_items: 7, cantidad_unidades: 9 });
    expect(fixture.nativeElement.querySelector('s').textContent).toBe(page['money']('200.00'));
    const summary = fixture.nativeElement.querySelector('.cart-summary').textContent;
    for (const value of ['999.01', '123.45', '875.56']) expect(summary).toContain(page['money'](value));
    expect(text()).toContain(page['money']('320.00'));
    expect(Array.from(fixture.nativeElement.querySelectorAll('dd')).slice(0, 2).map((node: any) => node.textContent)).toEqual(['7', '9']);
  });
  it('does not show an old price when equal numerically', () => {
    load({ ...data, items: [{ ...item, precio_base: '160' }] }); expect(fixture.nativeElement.querySelector('s')).toBeNull();
  });
  for (const [name, index, quantity] of [['increase', 1, 3], ['decrease', 0, 1]] as const) {
    it(`${name} sends the final quantity and waits for server response`, () => {
      load(); buttons()[index].click(); fixture.detectChanges();
      const req = http.expectOne(`${url}/items/15`); expect(req.request.method).toBe('PATCH'); expect(req.request.body).toEqual({ cantidad: quantity });
      expect(page['cart']()?.items[0].cantidad).toBe(2); expect(text()).toContain('Actualizando...');
      req.flush({ success: true, data: { ...data, items: [{ ...item, cantidad: quantity }] }, message: '' }); fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('input').value).toBe(String(quantity)); expect(page['busy']()).toBe(false);
    });
  }
  it('disables decrement at one and never sends zero', () => {
    const single = { ...item, cantidad: 1 }; load({ ...data, items: [single] });
    expect(buttons()[0].disabled).toBe(true); buttons()[0].click(); page['updateQuantity'](single, 0); http.expectNone(`${url}/items/15`);
  });
  it('accepts a typed final quantity and resets the input until confirmed', () => {
    load(); const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = '5'; input.dispatchEvent(new Event('change'));
    expect(input.value).toBe('2'); const req = http.expectOne(`${url}/items/15`); expect(req.request.body).toEqual({ cantidad: 5 });
    req.flush({ success: true, data: { ...data, items: [{ ...item, cantidad: 5 }] }, message: '' }); fixture.detectChanges(); expect(input.value).toBe('5');
  });
  for (const quantity of ['', '0', '-1', '1.5', '2147483648']) {
    it(`rejects invalid input ${quantity} without changing the persisted value`, () => {
      load(); const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
      input.value = quantity; input.dispatchEvent(new Event('change')); fixture.detectChanges();
      expect(input.value).toBe('2'); expect(text()).toContain('cantidad entera'); http.expectNone(`${url}/items/15`);
    });
  }
  it('prevents duplicate updates and removes while updating', () => {
    load(); buttons()[1].click(); page['updateQuantity'](item, 3); page['removeItem'](item); fixture.detectChanges();
    expect(buttons()[1].disabled).toBe(true);
    const requests = http.match(`${url}/items/15`); expect(requests).toHaveLength(1); requests[0].flush({ success: true, data, message: '' });
  });
  it('removes using DELETE and adopts the returned empty cart, preventing double click', () => {
    load(); fixture.nativeElement.querySelector('.cart-remove').click(); page['removeItem'](item); fixture.detectChanges(); expect(text()).toContain('Eliminando...');
    const req = http.expectOne(`${url}/items/15`); expect(req.request.method).toBe('DELETE');
    req.flush({ success: true, data: empty, message: '' }); fixture.detectChanges(); expect(text()).toContain('Tu carrito está vacío');
  });
  it('asks confirmation and cancel does not delete anything', () => {
    load(); page['askClear'](); expect(page['dialog']().nativeElement.open).toBe(true);
    expect(text()).toContain('¿Deseas eliminar todos los productos del carrito?'); page['closeDialog']();
    expect(page['dialog']().nativeElement.open).toBe(false); page['clearCart'](); http.expectNone(`${url}/items`);
  });
  it('clears only after confirmation, prevents duplicates and closes dialog', () => {
    load(); page['askClear'](); page['clearCart'](); page['clearCart'](); fixture.detectChanges(); expect(text()).toContain('Vaciando...');
    const req = http.expectOne(`${url}/items`); expect(req.request.method).toBe('DELETE');
    req.flush({ success: true, data: empty, message: '' }); fixture.detectChanges();
    expect(page['clearing']()).toBe(false); expect(page['dialog']().nativeElement.open).toBe(false); expect(text()).toContain('Tu carrito está vacío');
  });
  it('preserves cart and shows an error if clearing fails', () => {
    load(); page['askClear'](); page['clearCart'](); http.expectOne(`${url}/items`).flush({}, { status: 500, statusText: 'Error' }); fixture.detectChanges();
    expect(page['cart']()).toEqual(data); expect(text()).toContain('No fue posible procesar'); expect(page['clearing']()).toBe(false);
  });
  for (const [stock, label] of [[0, 'Sin stock actualmente'], [1, 'Solo quedan 1 unidades disponibles']] as const) {
    it(`shows stock ${stock} without removing the item`, () => {
      load({ ...data, items: [{ ...item, disponibilidad_actual: stock }] }); expect(text()).toContain(label); expect(page['cart']()?.items).toHaveLength(1);
    });
  }
  for (const field of ['estado_producto', 'estado_variante'] as const) {
    it(`disables quantity for inactive ${field}, keeping remove enabled`, () => {
      const inactive = { ...item, [field]: false }; load({ ...data, items: [inactive] }); expect(text()).toContain('No disponible');
      expect(buttons().every(button => button.disabled)).toBe(true); expect(fixture.nativeElement.querySelector('input').disabled).toBe(true);
      expect(fixture.nativeElement.querySelector('.cart-remove').disabled).toBe(false); page['updateQuantity'](inactive, 3); http.expectNone(`${url}/items/15`);
    });
  }
  for (const status of [401, 403, 404, 409, 422, 500]) {
    it(`handles ${status}, preserving quantity and releasing updating state`, () => {
      load(); page['updateQuantity'](item, 3); http.expectOne(`${url}/items/15`).flush({ message: 'Mensaje del servidor', detail: 'private trace' }, { status, statusText: 'Error' }); fixture.detectChanges();
      expect(page['cart']()?.items[0].cantidad).toBe(2); expect(page['busy']()).toBe(false); expect(text()).not.toContain('private trace');
      expect(text()).toContain([403, 404, 409, 422].includes(status) ? 'Mensaje del servidor' : status === 401 ? 'Tu sesión expiró' : 'No fue posible procesar');
    });
  }
  it('handles structured 422 validation errors without exposing JSON', () => {
    load(); page['updateQuantity'](item, 3); http.expectOne(`${url}/items/15`).flush({ detail: [{ loc: ['body'], msg: 'technical' }] }, { status: 422, statusText: 'Error' }); fixture.detectChanges();
    expect(text()).toContain('Revisa la cantidad'); expect(text()).not.toContain('technical');
  });
  it('retries initial failures', () => {
    http.expectOne(url).flush({}, { status: 500, statusText: 'Error' }); fixture.detectChanges();
    expect(text()).toContain('Reintentar'); page['load'](); load(); expect(text()).toContain(item.nombre_producto);
  });
  it('serializes different rows without disabling unrelated controls', () => {
    const other = { ...item, id_variante_producto: 16 }; load({ ...data, items: [item, other] });
    page['updateQuantity'](item, 3); expect(page['blocked'](other)).toBe(false); page['updateQuantity'](other, 4);
    http.expectNone(`${url}/items/16`); const changed = { ...item, cantidad: 3 };
    http.expectOne(`${url}/items/15`).flush({ success: true, data: { ...data, items: [changed, other] }, message: '' });
    http.expectOne(`${url}/items/16`).flush({ success: true, data: { ...data, items: [changed, { ...other, cantidad: 4 }] }, message: '' });
    expect(page['cart']()?.items.map(row => row.cantidad)).toEqual([3, 4]); expect(page['busy']()).toBe(false);
  });
  it('falls back when an image fails', () => {
    load(); fixture.nativeElement.querySelector('img').dispatchEvent(new Event('error')); fixture.detectChanges(); expect(fixture.nativeElement.querySelector('img')).toBeNull(); expect(text()).toContain('FS');
  });
});
