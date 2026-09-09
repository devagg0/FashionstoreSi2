import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { Inventory } from '../../../core/services/admin-inventory.service';
import { routes } from '../../../app.routes';
import { adminGuard, adminChildGuard } from '../../../core/guards/admin.guard';
import { AdminInventory } from './admin-inventory';

const base = `${environment.apiUrl}/api/admin`;
const url = `${base}/inventory`;
const item: Inventory = {
  id_inventario_sucursal: 3,
  id_sucursal: 1,
  sucursal: 'Centro',
  sucursal_estado: true,
  id_ciudad: 4,
  ciudad: 'La Paz',
  id_producto: 5,
  producto: 'Camisa',
  producto_estado: true,
  id_variante_producto: 2,
  sku: 'CAM-M',
  variante_estado: true,
  id_talla: 6,
  talla: 'M',
  id_color: 7,
  color: 'Azul',
  stock_actual: 10,
  stock_reservado: 3,
  stock_disponible: 7,
  stock_minimo: 0,
  created_at: '2026-09-09T12:00:00',
  updated_at: '2026-09-09T12:00:00',
};
const listing = (data: unknown[] = [item], page = 1, total = data.length) => ({
  success: true,
  data,
  pagination: { page, page_size: 10, total, total_pages: Math.ceil(total / 10) },
});
describe('AdminInventory CU14', () => {
  let fixture: ComponentFixture<AdminInventory>;
  let page: AdminInventory;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([{ path: 'admin/movimientos-inventario', component: AdminInventory }]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminInventory);
    page = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne((r) => r.url === url).flush(listing());
    http
      .expectOne((r) => r.url === `${base}/branches`)
      .flush(
        listing([
          { id_sucursal: 1, id_ciudad: 4, nombre: 'Centro', estado: true },
          { id_sucursal: 9, id_ciudad: 4, nombre: 'Historica', estado: false },
        ]),
      );
    http
      .expectOne((r) => r.url === `${base}/products`)
      .flush(
        listing([
          { id_producto: 5, id_categoria: 8, nombre: 'Camisa', estado: true },
          { id_producto: 9, id_categoria: 8, nombre: 'Antiguo', estado: false },
          { id_producto: 10, id_categoria: 10, nombre: 'Pantalón', estado: true },
        ]),
      );
    http
      .expectOne((r) => r.url === `${base}/categories`)
      .flush(
        listing([
          { id_categoria: 8, nombre: 'Ropa', estado: true },
          { id_categoria: 10, nombre: 'Pantalones', estado: true },
          { id_categoria: 11, nombre: 'Histórica', estado: false },
          { id_categoria: 12, nombre: 'Sin productos', estado: true },
        ]),
      );
    for (const [resource, data] of [
      ['cities', { id_ciudad: 4, nombre: 'La Paz' }],
      ['sizes', { id_talla: 6, nombre: 'M' }],
      ['colors', { id_color: 7, nombre: 'Azul' }],
    ] as const) {
      http.expectOne((r) => r.url === `${base}/${resource}`).flush(listing([data]));
    }
    fixture.detectChanges();
  });
  afterEach(() => {
    http.verify();
    fixture.destroy();
    localStorage.clear();
  });
  function selectProduct() {
    page['form'].controls.id_categoria.setValue(8);
    page['form'].controls.id_producto.setValue(5);
    http.expectOne(`${base}/products/5`).flush({
      success: true,
      data: {
        variantes: [
          { id_variante_producto: 2, sku: 'CAM-M', talla: 'M', color: 'Azul', estado: true },
          { id_variante_producto: 9, sku: 'OLD', talla: 'S', color: 'Azul', estado: false },
        ],
      },
    });
  }
  function validCreate() {
    page['openCreate']();
    selectProduct();
    page['form'].patchValue({ id_sucursal: 1, id_variante_producto: 2 });
  }
  it('renders inventory and all stock columns', () => {
    const text = fixture.nativeElement.textContent;
    for (const label of [
      'Camisa',
      'CAM-M',
      'Centro',
      'La Paz',
      'Stock actual',
      'Stock reservado',
      'Stock disponible',
    ])
      expect(text).toContain(label);
  });
  it('loads categories and offers only active ones for registration', () => {
    expect(page['categories']()).toHaveLength(4);
    page['openCreate']();
    fixture.detectChanges();
    const selector = fixture.nativeElement.querySelector(
      '[role="dialog"] select[formControlName="id_categoria"]',
    );
    expect(selector.textContent).toContain('Ropa');
    expect(selector.textContent).toContain('Pantalones');
    expect(selector.textContent).not.toContain('Histórica');
    // Las categorías históricas siguen disponibles en los filtros de consulta.
    expect(
      fixture.nativeElement.querySelector('.filters select[formControlName="id_categoria"]')
        .textContent,
    ).toContain('Histórica');
  });
  it('guides category then product selection before offering variants', () => {
    page['openCreate']();
    fixture.detectChanges();
    const modal = fixture.nativeElement.querySelector('[role="dialog"]');
    expect(modal.querySelector('select[formControlName="id_producto"]').textContent).toContain(
      'Selecciona primero una categoría',
    );
    expect(modal.querySelector('select[formControlName="id_producto"]').options.length).toBe(1);
    expect(
      modal.querySelector('select[formControlName="id_variante_producto"]').textContent,
    ).toContain('Selecciona primero un producto');
    const category: HTMLSelectElement = modal.querySelector(
      'select[formControlName="id_categoria"]',
    );
    category.value = category.options[1].value;
    category.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(page['form'].controls.id_categoria.value).toBe(8);
    const productText = modal.querySelector('select[formControlName="id_producto"]').textContent;
    expect(productText).toContain('Camisa');
    expect(productText).not.toContain('Pantalón');
    expect(productText).not.toContain('Antiguo');
    http.expectNone((r) => r.url === `${base}/products`);
  });
  it('clears product and variant on category change while preserving branch and minimum', () => {
    validCreate();
    page['form'].controls.stock_minimo.setValue(5);
    page['form'].controls.id_categoria.setValue(10);
    expect(page['form'].controls.id_producto.value).toBeNull();
    expect(page['form'].controls.id_variante_producto.value).toBeNull();
    expect(page['form'].controls.id_sucursal.value).toBe(1);
    expect(page['form'].controls.stock_minimo.value).toBe(5);
    expect(page['createProductOptions']().map((p) => p.nombre)).toEqual(['Pantalón']);
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector(
        '[role="dialog"] select[formControlName="id_variante_producto"]',
      ).textContent,
    ).not.toContain('CAM-M');
    page['form'].controls.id_categoria.setValue(null);
    expect(page['createProductOptions']()).toEqual([]);
  });
  it('changing branch preserves category, product and variant', () => {
    validCreate();
    page['form'].controls.id_sucursal.setValue(9);
    expect(page['form'].controls.id_categoria.value).toBe(8);
    expect(page['form'].controls.id_producto.value).toBe(5);
    expect(page['form'].controls.id_variante_producto.value).toBe(2);
  });
  it('loads only the selected product variants after changing category', () => {
    validCreate();
    page['form'].controls.id_categoria.setValue(10);
    page['form'].controls.id_producto.setValue(10);
    http
      .expectOne(`${base}/products/10`)
      .flush({
        success: true,
        data: {
          variantes: [
            { id_variante_producto: 20, sku: 'PAN-L', talla: 'L', color: 'Negro', estado: true },
          ],
        },
      });
    fixture.detectChanges();
    const selector = fixture.nativeElement.querySelector(
      '[role="dialog"] select[formControlName="id_variante_producto"]',
    );
    expect(selector.textContent).toContain('PAN-L');
    expect(selector.textContent).not.toContain('CAM-M');
    expect(page['form'].controls.id_variante_producto.value).toBeNull();
  });
  it('shows an empty category message without offering other products', () => {
    page['openCreate']();
    page['form'].controls.id_categoria.setValue(12);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="dialog"]').textContent).toContain(
      'No hay productos activos en esta categoría.',
    );
    expect(page['createProductOptions']()).toEqual([]);
  });
  it('rejects a product outside the selected category and inactive categories', () => {
    validCreate();
    for (const category of [10, 11]) {
      page['form'].controls.id_categoria.setValue(category);
      page['form'].patchValue({ id_producto: 5, id_variante_producto: 2 });
      page['submitCreate']();
      http.expectNone((r) => r.method === 'POST');
      expect(page['modalError']()).toContain('categoría');
    }
  });
  it('sends only the existing CU14 payload, without category or stock fields', () => {
    validCreate();
    page['form'].controls.stock_minimo.setValue(5);
    page['submitCreate']();
    const req = http.expectOne(url);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ id_sucursal: 1, id_variante_producto: 2, stock_minimo: 5 });
    for (const field of ['id_categoria', 'id_producto', 'stock_actual', 'stock_reservado']) {
      expect(req.request.body).not.toHaveProperty(field);
    }
    req.flush({ success: true, data: item });
    http.expectOne((r) => r.url === url).flush(listing());
    expect(page['mode']()).toBeNull();
  });
  for (const field of [
    'id_sucursal',
    'id_categoria',
    'id_producto',
    'id_variante_producto',
  ] as const) {
    it(`requires ${field}`, () => {
      validCreate();
      page['form'].controls[field].setValue(null);
      page['submitCreate']();
      expect(page['form'].invalid).toBe(true);
      http.expectNone((r) => r.url === url);
    });
  }
  for (const minimum of [-1, 1.5, null]) {
    it(`rejects minimum ${minimum} in both forms`, () => {
      page['form'].controls.stock_minimo.setValue(minimum);
      page['minimumForm'].controls.stock_minimo.setValue(minimum);
      expect(page['form'].controls.stock_minimo.invalid).toBe(true);
      expect(page['minimumForm'].invalid).toBe(true);
    });
  }
  it('selects product then active variants and resets previous selection', () => {
    validCreate();
    expect(page['variantOptions'](5, true).map((v) => v.sku)).toEqual(['CAM-M']);
    page['form'].controls.id_producto.setValue(null);
    expect(page['form'].controls.id_variante_producto.value).toBeNull();
  });
  it('offers only active branches/products for creation with city labels', () => {
    page['openCreate']();
    fixture.detectChanges();
    const modal = fixture.nativeElement.querySelector('[role="dialog"]');
    expect(modal.textContent).toContain('La Paz');
    expect(modal.textContent).not.toContain('Historica');
    expect(modal.textContent).not.toContain('Antiguo');
  });
  it('creates without stock fields and reloads listing', () => {
    validCreate();
    page['submitCreate']();
    const req = http.expectOne(url);
    expect(req.request.body).toEqual({ id_sucursal: 1, id_variante_producto: 2, stock_minimo: 0 });
    req.flush({ success: true, data: item });
    http.expectOne((r) => r.url === url).flush(listing());
    expect(page['mode']()).toBeNull();
    expect(page['successMessage']()).toBe('Producto registrado en el inventario de la sucursal.');
  });
  it('shows duplicate 409 without closing form', () => {
    validCreate();
    page['submitCreate']();
    http
      .expectOne(url)
      .flush(
        { message: 'Ya existe inventario para esa sucursal y variante' },
        { status: 409, statusText: 'Conflict' },
      );
    expect(page['modalError']()).toBe(
      'Esta variante ya est\u00e1 registrada en la sucursal seleccionada.',
    );
    expect(page['mode']()).toBe('create');
    expect(page['saving']()).toBe(false);
  });
  it('shows concurrent conflict backend message', () => {
    validCreate();
    page['submitCreate']();
    http
      .expectOne(url)
      .flush(
        { message: 'Conflicto concurrente; reintente' },
        { status: 409, statusText: 'Conflict' },
      );
    expect(page['modalError']()).toBe('Conflicto concurrente; reintente');
  });
  it('updates only minimum and reloads same page', () => {
    page['openDetail'](3, true);
    http.expectOne(`${url}/3`).flush({ success: true, data: item });
    page['minimumForm'].controls.stock_minimo.setValue(4);
    page['submitMinimum']();
    const req = http.expectOne(`${url}/3`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ stock_minimo: 4 });
    req.flush({ success: true, data: { ...item, stock_minimo: 4 } });
    const reload = http.expectOne((r) => r.url === url);
    expect(reload.request.params.get('page')).toBe('1');
    reload.flush(listing());
    expect(page['successMessage']()).toBe('Stock m\u00ednimo actualizado correctamente.');
  });
  it('keeps applied filters on page changes', () => {
    page['filters'].patchValue({
      search: 'CAM',
      id_sucursal: 1,
      id_ciudad: 4,
      id_categoria: 8,
      id_talla: 6,
      id_color: 7,
    });
    page['applyFilters']();
    http.expectOne((r) => r.url === url).flush(listing([item], 1, 21));
    page['filters'].controls.search.setValue('not applied');
    page['loadInventory'](2);
    const req = http.expectOne((r) => r.url === url);
    for (const [key, value] of Object.entries({
      search: 'CAM',
      id_sucursal: '1',
      id_ciudad: '4',
      id_categoria: '8',
      id_talla: '6',
      id_color: '7',
      page: '2',
    }))
      expect(req.request.params.get(key)).toBe(value);
    req.flush(listing([item], 2, 21));
  });
  it('displays inactive historical detail and never offers stock inputs', () => {
    page['openDetail'](3, true);
    http.expectOne(`${url}/3`).flush({
      success: true,
      data: { ...item, sucursal_estado: false, producto_estado: false, variante_estado: false },
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.badge--inactive').length).toBe(3);
    expect(
      fixture.nativeElement.querySelectorAll(
        'input[formControlName="stock_actual"], input[formControlName="stock_reservado"], input[formControlName="stock_disponible"]',
      ).length,
    ).toBe(0);
    expect(Object.keys(page['minimumForm'].controls)).toEqual(['stock_minimo']);
    page['openCreate']();
    fixture.detectChanges();
    expect(Object.keys(page['form'].controls)).toEqual([
      'id_sucursal',
      'id_categoria',
      'id_producto',
      'id_variante_producto',
      'stock_minimo',
    ]);
  });
  it('keeps CU15 route and navigates to movements', async () => {
    const admin = routes.find((r) => r.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    expect(admin.children?.some((r) => r.path === 'inventario')).toBe(true);
    expect(admin.children?.some((r) => r.path === 'movimientos-inventario')).toBe(true);
    const link: HTMLAnchorElement = fixture.nativeElement.querySelector(
      'a[href="/admin/movimientos-inventario"]',
    );
    expect(link).toBeTruthy();
    link.click();
    await fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/admin/movimientos-inventario');
  });
  it('handles 404 detail and resets loading', () => {
    page['openDetail'](99);
    http
      .expectOne(`${url}/99`)
      .flush({ message: 'Inventario no encontrado' }, { status: 404, statusText: 'Not Found' });
    expect(page['modalError']()).toBe('Inventario no encontrado');
    expect(page['detailLoading']()).toBe(false);
  });
  it('cancels stale list responses', () => {
    page['loadInventory']();
    const previous = http.expectOne((r) => r.url === url);
    page['loadInventory'](2);
    expect(previous.cancelled).toBe(true);
    http.expectOne((r) => r.url === url).flush(listing([item], 2, 21));
  });
});
