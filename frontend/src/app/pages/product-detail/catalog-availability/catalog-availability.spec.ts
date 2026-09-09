import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { BranchAvailability } from '../../../core/services/catalog-availability.service';
import { CatalogProductDetail } from '../../../core/services/catalog.service';
import { routes } from '../../../app.routes';
import { ProductDetail } from '../product-detail';
import { CatalogAvailability } from './catalog-availability';

const url = `${environment.apiUrl}/api/catalog/products/10/availability`;
const variant = { id_variante_producto: 25, sku: 'CAM-M-BLA', estado: true,
  talla: { id_talla: 3, nombre: 'M' }, color: { id_color: 4, nombre: 'Blanco', codigo_hex: '#FFFFFF' } };
const row: BranchAvailability = { variante: variant, id_sucursal: 901, nombre_sucursal: 'Centro',
  id_ciudad: 902, nombre_ciudad: 'Santa Cruz', stock_actual: 20, stock_reservado: 8, stock_disponible: 12 };
const response = (rows: BranchAvailability[] = [row]) => ({ success: true,
  data: { producto: { id_producto: 10, nombre: 'Camisa', estado: true }, disponibilidad: rows }, message: '' });

describe('CatalogAvailability CU13', () => {
  let fixture: ComponentFixture<CatalogAvailability>;
  let http: HttpTestingController;
  const text = () => fixture.nativeElement.textContent as string;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(CatalogAvailability);
    fixture.componentRef.setInput('productId', 10);
    fixture.detectChanges();
  });
  afterEach(() => http.verify());
  function select(id = 25) {
    fixture.componentRef.setInput('variantId', id);
    fixture.detectChanges();
    return http.expectOne((r) => r.url === url && r.params.get('id_variante_producto') === String(id));
  }

  it('prompts for selection without making requests', () => {
    expect(text()).toContain('Selecciona talla y color');
    http.expectNone(() => true);
  });
  it('shows loading while requesting a variant', () => {
    const req = select();
    expect(text()).toContain('Cargando disponibilidad...');
    expect(fixture.nativeElement.querySelector('section').getAttribute('aria-busy')).toBe('true');
    req.flush(response());
    fixture.detectChanges();
    expect(text()).not.toContain('Cargando disponibilidad...');
  });
  it('renders multiple branches, city, size, color, SKU and available units', () => {
    select().flush(response([row, { ...row, id_sucursal: 903, nombre_sucursal: 'Norte', stock_disponible: 4 }]));
    fixture.detectChanges();
    for (const value of ['Centro', 'Norte', 'Santa Cruz', 'Talla M', 'Blanco', 'CAM-M-BLA', 'Disponible: 12 unidades', 'Disponible: 4 unidades']) expect(text()).toContain(value);
    expect(fixture.nativeElement.querySelectorAll('article').length).toBe(2);
  });
  it('keeps zero stock branches visible', () => {
    select().flush(response([{ ...row, stock_disponible: 0 }]));
    fixture.detectChanges();
    expect(text()).toContain('Centro');
    expect(text()).toContain('Sin stock');
  });
  it('renders empty availability as a normal state', () => {
    select().flush(response([]));
    fixture.detectChanges();
    expect(text()).toContain('No hay disponibilidad registrada para esta variante.');
    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
  });
  it.each([404, 500, 0])('handles backend/network error %s without exposing details', (status) => {
    select().flush({ message: 'private details' }, { status, statusText: 'Error' });
    fixture.detectChanges();
    expect(text()).toContain(status === 404 ? 'ya no está disponible' : 'No se pudo consultar la disponibilidad. Inténtalo nuevamente.');
    expect(text()).not.toContain('private details');
  });
  it('retries after an error', () => {
    select().flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    fixture.nativeElement.querySelector('button').click();
    fixture.detectChanges();
    http.expectOne((r) => r.url === url).flush(response());
    fixture.detectChanges();
    expect(text()).toContain('Centro');
  });
  it('cancels the previous request on variant change and uses the new result', () => {
    const old = select();
    const next = select(26);
    expect(old.cancelled).toBe(true);
    next.flush(response([{ ...row, variante: { ...variant, id_variante_producto: 26, sku: 'NEW-SKU' } }]));
    fixture.detectChanges();
    expect(text()).toContain('NEW-SKU');
    expect(text()).not.toContain('CAM-M-BLA');
  });
  it('does not repeat a request for the same selection', () => {
    select().flush(response());
    fixture.componentRef.setInput('variantId', 25);
    fixture.detectChanges();
    http.expectNone(() => true);
  });
  it('clears results and cancels requests when selection becomes invalid', () => {
    const req = select();
    fixture.componentRef.setInput('variantId', null);
    fixture.detectChanges();
    expect(req.cancelled).toBe(true);
    expect(text()).toContain('Selecciona talla y color');
    expect(text()).not.toContain('Centro');
  });
  it('passes branch and city context and reloads when it changes', () => {
    fixture.componentRef.setInput('branchId', 1);
    fixture.componentRef.setInput('cityId', 2);
    const req = select();
    expect(req.request.params.get('id_sucursal')).toBe('1');
    expect(req.request.params.get('id_ciudad')).toBe('2');
    req.flush(response());
    fixture.componentRef.setInput('branchId', 5);
    fixture.detectChanges();
    http.expectOne((r) => r.params.get('id_sucursal') === '5').flush(response([]));
  });
  it('does not expose technical IDs, internal stock or write actions', () => {
    const req = select();
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush(response());
    fixture.detectChanges();
    for (const value of ['901', '902', 'id_variante_producto', 'id_sucursal', 'stock_actual', 'stock_reservado']) expect(text()).not.toContain(value);
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
    http.expectNone((r) => r.method !== 'GET');
  });
  it('cancels requests on destruction', () => {
    const req = select();
    fixture.destroy();
    expect(req.cancelled).toBe(true);
  });
});

describe('ProductDetail integration CU13', () => {
  it('uses public CU12 size/color buttons to request the variant without login or reservations', () => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ProductDetail);
    const detail: CatalogProductDetail = {
      id_producto: 10, nombre: 'Camisa', descripcion: null, seccion: 'UNISEX', id_categoria: 1,
      categoria: 'Camisas', id_temporada: null, temporada: null, precio_base: '100', precio_final: '100',
      tiene_promocion: false, promociones_vigentes: [], promocion_destacada: null,
      porcentaje_descuento: null, monto_descuento: null, imagen_principal: null, galeria: [], colecciones: [],
      tallas: [variant.talla, { id_talla: 5, nombre: 'L' }], colores: [variant.color],
      variantes: [{ ...variant, disponibilidad_sucursal: null },
        { ...variant, id_variante_producto: 26, talla: { id_talla: 5, nombre: 'L' }, disponibilidad_sucursal: null }],
    };
    fixture.componentInstance['product'].set(detail);
    fixture.componentInstance['loading'].set(false);
    fixture.componentInstance['errorMessage'].set('');
    fixture.detectChanges();
    http.expectNone(() => true);
    fixture.nativeElement.querySelector('.color-options button').click();
    fixture.detectChanges();
    http.expectNone(() => true);
    fixture.nativeElement.querySelector('.size-options button').click();
    fixture.detectChanges();
    const req = http.expectOne(`${url}?id_variante_producto=25`);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush(response());
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Disponible: 12 unidades');
    fixture.nativeElement.querySelectorAll('.size-options button')[1].click();
    fixture.detectChanges();
    http.expectOne(`${url}?id_variante_producto=26`).flush(response([]));
    const route = routes.find((r) => r.path === 'catalogo/producto/:id')!;
    expect(route.canActivate).toBeUndefined();
    expect(fixture.nativeElement.querySelector('.future-purchase').disabled).toBe(true);
    http.verify();
  });
});
