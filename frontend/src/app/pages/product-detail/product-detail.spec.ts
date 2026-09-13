import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { Subject } from 'rxjs';
import { CartResponse, ClientCartService } from '../../core/services/client-cart.service';
import { SessionService } from '../../core/services/session.service';
import { ReservationSelectionService } from '../../core/services/reservation-selection.service';
import { CatalogProductDetail } from '../../core/services/catalog.service';
import { ProductDetail } from './product-detail';

const detail: CatalogProductDetail = {
  id_producto: 7,
  nombre: 'Chaqueta urbana',
  descripcion: 'Ligera y versátil',
  seccion: 'UNISEX',
  id_categoria: 2,
  categoria: 'Chaquetas',
  id_temporada: null,
  temporada: null,
  precio_base: '100.00',
  precio_final: '100.00',
  tiene_promocion: false,
  promociones_vigentes: [],
  promocion_destacada: null,
  porcentaje_descuento: null,
  monto_descuento: null,
  imagen_principal: null,
  galeria: [],
  tallas: [{ id_talla: 1, nombre: 'M' }],
  colores: [{ id_color: 2, nombre: 'Negro', codigo_hex: '#000000' }],
  colecciones: [],
  variantes: [
    {
      id_variante_producto: 9,
      sku: 'CHA-M-NEG',
      talla: { id_talla: 1, nombre: 'M' },
      color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000000' },
      disponibilidad_sucursal: {
        id_sucursal: 6,
        estado: 'DISPONIBLE',
        cantidad_disponible: 2,
      },
    },
  ],
};

describe('ProductDetail CU12', () => {
  let fixture: ComponentFixture<ProductDetail>;
  let page: ProductDetail;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    fixture = TestBed.createComponent(ProductDetail);
    page = fixture.componentInstance;
    page['product'].set(detail);
    page['branchId'].set(6);
    page['errorMessage'].set('');
    page['loading'].set(false);
    fixture.detectChanges();
  });

  afterEach(() => { localStorage.clear(); sessionStorage.clear(); });

  function client() {
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 1, nombre: 'Ana', apellido: 'Pérez', correo: 'a@b.com', rol: 'CLIENTE' });
  }

  it('CU19 requires both size and color', () => {
    client(); const add = vi.spyOn(TestBed.inject(ClientCartService), 'addItem');
    page['addToCart'](); expect(page['cartError']()).toBe('Selecciona una talla y un color.');
    page['selectColor'](2); page['addToCart'](); expect(add).not.toHaveBeenCalled();
  });

  it('CU19 sends the selected variant with quantity one, waits for success and prevents duplicate sends', () => {
    client(); page['selectColor'](2); page['selectSize'](1);
    const response = new Subject<CartResponse>();
    const add = vi.spyOn(TestBed.inject(ClientCartService), 'addItem').mockReturnValue(response);
    const reservations = TestBed.inject(ReservationSelectionService).items();
    page['addToCart'](); page['addToCart'](); fixture.detectChanges();
    expect(add).toHaveBeenCalledExactlyOnceWith(9, 1); expect(page['cartSuccess']()).toBe('');
    expect(fixture.nativeElement.querySelector('.cart-add button').disabled).toBe(true);
    expect(fixture.nativeElement.querySelector('.cart-add').textContent).toContain('Agregando...');
    response.next({ success: true, data: { id_carrito: 1, estado: 'ACTIVO', items: [], cantidad_items: 1, cantidad_unidades: 1, subtotal: '100', descuento_total: '0', total: '100' }, message: 'OK' }); response.complete(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.cart-add').textContent).toContain('Producto agregado al carrito');
    expect(page['addingToCart']()).toBe(false);
    expect(TestBed.inject(ReservationSelectionService).items()).toEqual(reservations);
  });

  it('CU19 displays the real stock conflict without reporting success', () => {
    client(); page['selectColor'](2); page['selectSize'](1);
    const response = new Subject<CartResponse>(); vi.spyOn(TestBed.inject(ClientCartService), 'addItem').mockReturnValue(response);
    page['addToCart'](); response.error(new HttpErrorResponse({ status: 409, error: { message: 'Stock insuficiente para esta variante.' } })); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.cart-add [role="alert"]').textContent).toBe('Stock insuficiente para esta variante.');
    expect(page['cartSuccess']()).toBe(''); expect(page['addingToCart']()).toBe(false);
  });

  it('CU19 redirects guests to login without creating an anonymous cart', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const add = vi.spyOn(TestBed.inject(ClientCartService), 'addItem');
    page['addToCart'](); expect(navigate).toHaveBeenCalledWith(['/login']); expect(add).not.toHaveBeenCalled();
  });

  it('CU19 rejects authenticated non-client accounts', () => {
    client(); const session = TestBed.inject(SessionService); session.saveUser({ ...session.getUser()!, rol: 'ADMIN' });
    const add = vi.spyOn(TestBed.inject(ClientCartService), 'addItem'); page['addToCart']();
    expect(page['cartError']()).toContain('cuentas de cliente'); expect(add).not.toHaveBeenCalled();
  });

  it('identifies a variant from the selected color and size', () => {
    page['selectColor'](2);
    page['selectSize'](1);
    fixture.detectChanges();
    expect(page['selectedVariant']()?.sku).toBe('CHA-M-NEG');
    expect(page['availabilityLabel'](detail.variantes[0])).toBe('Pocas unidades');
  });

  it('keeps the reservation selector separate from the future purchase flow', () => {
    expect(fixture.nativeElement.querySelector('.future-purchase')).toBeNull();
    expect(fixture.nativeElement.querySelector('.reservation-selector')).toBeNull();
  });
});
