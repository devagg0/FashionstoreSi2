import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../../environments/environment';
import {
  GlobalInventory,
  GlobalInventoryDetail,
} from '../../../core/services/admin-global-inventory.service';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { routes } from '../../../app.routes';
import { adminGuard, adminChildGuard } from '../../../core/guards/admin.guard';
import { AdminGlobalInventory } from './admin-global-inventory';

const base = `${environment.apiUrl}/api/admin`;
const url = `${base}/global-inventory`;
const item: GlobalInventory = {
  producto: { id_producto: 5, nombre: 'Camisa Oxford', estado: false },
  categoria: { id_categoria: 8, nombre: 'Camisas' },
  variante: { id_variante_producto: 21, sku: 'OX-M-BLANCO', estado: false },
  talla: { id_talla: 6, nombre: 'M' },
  color: { id_color: 7, nombre: 'Blanco' },
  total_stock_actual: 35,
  total_stock_reservado: 4,
  total_stock_disponible: 31,
  cantidad_sucursales: 3,
  cantidad_sucursales_con_stock: 2,
};
const detail: GlobalInventoryDetail = {
  ...item,
  sucursales: [
    {
      id_sucursal: 1,
      nombre_sucursal: 'Equipetrol',
      estado_sucursal: false,
      id_ciudad: 4,
      nombre_ciudad: 'Santa Cruz',
      id_inventario_sucursal: 71,
      stock_actual: 20,
      stock_reservado: 1,
      stock_disponible: 19,
      stock_minimo: 5,
    },
    {
      id_sucursal: 2,
      nombre_sucursal: 'Centro',
      estado_sucursal: true,
      id_ciudad: 4,
      nombre_ciudad: 'Santa Cruz',
      id_inventario_sucursal: 72,
      stock_actual: 10,
      stock_reservado: 3,
      stock_disponible: 7,
      stock_minimo: 3,
    },
  ],
};
const listing = (data: unknown[] = [item], page = 1, total = data.length) => ({
  success: true,
  data,
  message: 'Consulta realizada',
  pagination: { page, page_size: 10, total, total_pages: Math.ceil(total / 10) },
});

describe('AdminGlobalInventory CU16', () => {
  let fixture: ComponentFixture<AdminGlobalInventory>;
  let page: AdminGlobalInventory;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminGlobalInventory);
    page = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne((r) => r.url === url).flush(listing());
    flushOptions();
    fixture.detectChanges();
  });
  afterEach(() => {
    http.verify();
    fixture.destroy();
    localStorage.clear();
  });

  function flushOptions() {
    for (const [resource, data] of [
      ['branches', { id_sucursal: 1, id_ciudad: 4, nombre: 'Equipetrol', estado: false }],
      ['products', { id_producto: 5, nombre: 'Camisa Oxford', estado: false }],
      ['cities', { id_ciudad: 4, nombre: 'Santa Cruz', estado: true }],
      ['categories', { id_categoria: 8, nombre: 'Camisas', estado: true }],
      ['sizes', { id_talla: 6, nombre: 'M', estado: true }],
      ['colors', { id_color: 7, nombre: 'Blanco', estado: true }],
    ] as const)
      http.expectOne((r) => r.url === `${base}/${resource}`).flush(listing([data]));
  }

  function openDetail(data: GlobalInventoryDetail = detail) {
    fixture.nativeElement.querySelector('.global-table tbody button').click();
    http.expectOne(`${url}/21`).flush({ success: true, data, message: 'OK' });
    fixture.detectChanges();
  }

  for (const [column, value] of [
    [0, 'Camisa Oxford'],
    [1, 'OX-M-BLANCO'],
    [2, 'M'],
    [3, 'Blanco'],
    [4, 'Camisas'],
    [5, '35'],
    [6, '4'],
    [7, '31'],
    [8, '3'],
    [9, '2'],
  ] as const) {
    it(`renders backend column ${column}: ${value}`, () => {
      const cells = fixture.nativeElement.querySelectorAll('.global-table tbody tr:first-child td');
      expect(cells[column].textContent).toContain(value);
    });
  }

  it('shows a consolidated heading and natural labels', () => {
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Consulta las existencias consolidadas');
    expect(text).toContain('Con stock');
    expect(text).not.toContain('total_stock_actual');
    expect(text).not.toContain('cantidad_sucursales');
  });

  for (const field of [
    'id_categoria',
    'id_producto',
    'id_talla',
    'id_color',
    'id_ciudad',
    'id_sucursal',
  ] as const) {
    it(`applies ${field} by selector, preserves it when paginating`, () => {
      expect(
        fixture.nativeElement.querySelector(`select[formControlName="${field}"]`),
      ).not.toBeNull();
      page['filters'].patchValue({ [field]: 8, search: ' Oxford ' });
      page['applyFilters']();
      let req = http.expectOne((r) => r.url === url);
      expect(req.request.params.get(field)).toBe('8');
      expect(req.request.params.get('search')).toBe('Oxford');
      expect(req.request.params.get('page')).toBe('1');
      req.flush(listing([item], 1, 21));
      // Unapplied form edits must not change filters on the next page.
      page['filters'].controls.search.setValue('Pendiente');
      page['loadInventory'](2);
      req = http.expectOne((r) => r.url === url);
      expect(req.request.params.get(field)).toBe('8');
      expect(req.request.params.get('search')).toBe('Oxford');
      expect(req.request.params.get('page')).toBe('2');
      expect(req.request.params.get('page_size')).toBe('10');
      req.flush(listing([item], 2, 21));
      expect(page['pagination']().page).toBe(2);
    });
  }

  it('clears filters and resets pagination', () => {
    page['filters'].patchValue({ id_ciudad: 4, search: 'Camisa' });
    page['applyFilters']();
    http.expectOne((r) => r.url === url).flush(listing());
    page['clearFilters']();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.params.keys()).toEqual(['page', 'page_size']);
    expect(page['filters'].controls.id_ciudad.value).toBeNull();
    req.flush(listing());
  });

  it('rejects a search longer than 200 characters without a request', () => {
    page['filters'].controls.search.setValue('x'.repeat(201));
    page['applyFilters']();
    expect(page['errorMessage']()).toContain('200');
    http.expectNone((r) => r.url === url);
  });

  it('uses backend pagination metadata rather than page row count', () => {
    page['loadInventory']();
    http
      .expectOne((r) => r.url === url)
      .flush({ ...listing(), pagination: { page: 2, page_size: 10, total: 43, total_pages: 5 } });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.table-card__meta').textContent).toContain(
      '43 variantes',
    );
    expect(fixture.nativeElement.querySelector('.pagination').textContent).toContain(
      'Página 2 de 5',
    );
  });

  it('opens detail with product, variant and state information', () => {
    openDetail();
    const text = fixture.nativeElement.querySelector('#global-detail').textContent;
    for (const value of [
      'Camisa Oxford',
      'Camisas',
      'OX-M-BLANCO',
      'Blanco',
      'Estado producto',
      'Estado variante',
    ])
      expect(text).toContain(value);
    expect(text).toContain('independientemente de los filtros');
  });

  it('shows multiple branches, city, stock minimum and inactive history', () => {
    openDetail();
    const rows = fixture.nativeElement.querySelectorAll('.branch-table tbody tr');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('Equipetrol');
    expect(rows[0].textContent).toContain('Santa Cruz');
    expect(rows[0].textContent).toContain('Inactivo');
    expect(rows[0].querySelectorAll('td')[5].textContent.trim()).toBe('5');
    expect(rows[1].textContent).toContain('Centro');
    expect(rows[1].querySelectorAll('td')[5].textContent.trim()).toBe('3');
  });

  it('never derives global totals or branch availability from other fields', () => {
    const unusual = {
      ...item,
      total_stock_actual: 901,
      total_stock_reservado: 88,
      total_stock_disponible: 777,
      cantidad_sucursales: 12,
      cantidad_sucursales_con_stock: 9,
    };
    page['loadInventory']();
    http.expectOne((r) => r.url === url).flush(listing([unusual]));
    fixture.detectChanges();
    const cells = fixture.nativeElement.querySelectorAll('.global-table tbody td');
    expect(
      Array.from(cells)
        .slice(5, 10)
        .map((c) => (c as HTMLElement).textContent?.trim()),
    ).toEqual(['901', '88', '777', '12', '9']);
    openDetail({ ...unusual, sucursales: [{ ...detail.sucursales[0], stock_disponible: 321 }] });
    const totals = fixture.nativeElement.querySelectorAll('.stock-summary dd');
    expect(Array.from(totals).map((c) => (c as HTMLElement).textContent?.trim())).toEqual([
      '901',
      '88',
      '777',
      '12',
      '9',
    ]);
    expect(
      fixture.nativeElement.querySelectorAll('.branch-table tbody td')[4].textContent.trim(),
    ).toBe('321');
  });

  it('shows inactive products and variants in listing and catalog selectors', () => {
    expect(fixture.nativeElement.querySelectorAll('.global-table tbody .badge').length).toBe(2);
    for (const badge of fixture.nativeElement.querySelectorAll('.global-table tbody .badge'))
      expect(badge.textContent).toBe('Inactivo');
    expect(
      fixture.nativeElement.querySelector('select[formControlName="id_producto"]').textContent,
    ).toContain('Camisa Oxford (Inactivo)');
    expect(
      fixture.nativeElement.querySelector('select[formControlName="id_sucursal"]').textContent,
    ).toContain('Equipetrol');
  });

  it('shows zero stock and an empty branch list without an error', () => {
    const zero = {
      ...item,
      total_stock_actual: 0,
      total_stock_reservado: 0,
      total_stock_disponible: 0,
      cantidad_sucursales: 0,
      cantidad_sucursales_con_stock: 0,
    };
    page['loadInventory']();
    http.expectOne((r) => r.url === url).flush(listing([zero]));
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelectorAll('.global-table tbody td')[7].textContent.trim(),
    ).toBe('0');
    openDetail({ ...zero, sucursales: [] });
    expect(fixture.nativeElement.querySelector('#global-detail').textContent).toContain(
      'No hay inventario registrado para esta variante.',
    );
    expect(page['detailError']()).toBeNull();
    expect(fixture.nativeElement.querySelector('.stock-summary dd').textContent).toBe('0');
  });

  it('has no write controls and only sends GET requests during consultation', () => {
    openDetail();
    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button')).map(
      (b) => (b as HTMLElement).textContent,
    );
    expect(buttons.join(' ')).not.toMatch(
      /Registrar|Crear|Editar|Eliminar|Aumentar|Disminuir|Guardar|Reservar/,
    );
    expect(fixture.nativeElement.querySelector('input[type="number"]')).toBeNull();
    http.expectNone((r) => r.method !== 'GET');
    expect(detail.sucursales[0].stock_actual).toBe(20);
  });

  for (const path of ['/admin/inventario', '/admin/movimientos-inventario']) {
    it(`links to ${path} without embedding write operations`, () => {
      expect(fixture.nativeElement.querySelector(`a[href="${path}"]`)).not.toBeNull();
      expect(
        routes.find((r) => r.path === 'admin')?.children?.some((r) => '/admin/' + r.path === path),
      ).toBe(true);
    });
  }

  it('is registered under existing administrator guards', async () => {
    const admin = routes.find((r) => r.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    const route = admin.children!.find((r) => r.path === 'inventario-global')!;
    expect(route.title).toBe('Inventario global | FashionStore');
    expect(await (route.loadComponent! as () => Promise<unknown>)()).toBe(AdminGlobalInventory);
  });

  it('shows loading and disables pagination while waiting', () => {
    page['loadInventory']();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Cargando inventario global…');
    for (const button of fixture.nativeElement.querySelectorAll('.pagination button'))
      expect(button.disabled).toBe(true);
    http.expectOne((r) => r.url === url).flush(listing());
    expect(page['loading']()).toBe(false);
  });

  it('shows the exact empty listing message', () => {
    page['loadInventory']();
    http.expectOne((r) => r.url === url).flush(listing([]));
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(
      'No se encontraron registros de inventario.',
    );
  });

  it('shows detail loading, closes with Escape and cancels pending detail', () => {
    page['openDetail'](21);
    const req = http.expectOne(`${url}/21`);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Cargando detalle…');
    fixture.nativeElement
      .querySelector('#global-detail')
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(req.cancelled).toBe(true);
    expect(page['detailLoading']()).toBe(false);
    expect(page['detailId']()).toBeNull();
  });

  it('focuses the detail panel and restores the trigger when closing', () => {
    const trigger = fixture.nativeElement.querySelector('.global-table tbody button');
    openDetail();
    expect(document.activeElement).toBe(fixture.nativeElement.querySelector('#global-detail'));
    page['closeDetail']();
    expect(document.activeElement).toBe(trigger);
  });

  for (const [status, message, expected] of [
    [403, 'Prohibido', 'Acceso no autorizado.'],
    [404, 'Variante no encontrada', 'Variante no encontrada'],
    [422, 'Filtros inválidos', 'Filtros inválidos'],
    [
      500,
      'No fue posible consultar el inventario global',
      'No fue posible consultar el inventario global',
    ],
  ] as const) {
    it(`handles ${status} through AdminApiErrorService`, () => {
      const resolve = vi.spyOn(TestBed.inject(AdminApiErrorService), 'resolve');
      page['openDetail'](21);
      http.expectOne(`${url}/21`).flush({ message }, { status, statusText: 'Error' });
      fixture.detectChanges();
      expect(resolve).toHaveBeenCalled();
      expect(page['detailError']()).toBe(expected);
      expect(page['detailLoading']()).toBe(false);
      expect(
        fixture.nativeElement.querySelector('#global-detail [role="alert"]').textContent,
      ).toContain(expected);
    });
  }

  it('ends an expired session on 401', () => {
    localStorage.setItem('fashionstore_access_token', 'expired');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    page['loadInventory']();
    http.expectOne((r) => r.url === url).flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(localStorage.getItem('fashionstore_access_token')).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login');
    expect(page['errorMessage']()).toContain('sesión expiró');
  });

  it('shows list errors separately from empty and can retry', () => {
    page['loadInventory']();
    http.expectOne((r) => r.url === url).flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('No se encontraron registros');
    expect(fixture.nativeElement.textContent).toContain('No pudimos consultar');
    fixture.nativeElement.querySelector('.global-table tbody button').click();
    http.expectOne((r) => r.url === url).flush(listing());
    expect(page['errorMessage']()).toBeNull();
  });

  it('cancels superseded list and detail requests', () => {
    page['loadInventory']();
    const oldList = http.expectOne((r) => r.url === url);
    page['loadInventory'](2);
    expect(oldList.cancelled).toBe(true);
    http.expectOne((r) => r.url === url).flush(listing([item], 2, 21));
    page['openDetail'](21);
    const oldDetail = http.expectOne(`${url}/21`);
    page['openDetail'](22);
    expect(oldDetail.cancelled).toBe(true);
    http
      .expectOne(`${url}/22`)
      .flush({
        success: true,
        data: { ...detail, variante: { ...item.variante, id_variante_producto: 22 } },
      });
    expect(page['detail']()?.variante.id_variante_producto).toBe(22);
  });

  it('loads every catalog page including inactive options', () => {
    page['loadOptions']();
    const requests = http.match((r) => r.url !== url);
    for (const req of requests) {
      expect(req.request.method).toBe('GET');
      expect(req.request.params.has('estado')).toBe(false);
      req.flush({
        ...listing([]),
        pagination: { page: 1, page_size: 100, total: 101, total_pages: 2 },
      });
      const next = http.expectOne((r) => r.url === req.request.url && r.params.get('page') === '2');
      next.flush({
        ...listing([]),
        pagination: { page: 2, page_size: 100, total: 101, total_pages: 2 },
      });
    }
    expect(requests.length).toBe(6);
    expect(page['optionsLoading']()).toBe(false);
  });

  it('can retry catalog failures without hiding inventory', () => {
    page['loadOptions']();
    http
      .expectOne((r) => r.url === `${base}/branches`)
      .flush({}, { status: 500, statusText: 'Error' });
    for (const req of http.match(() => true)) expect(req.cancelled).toBe(true);
    expect(page['optionsError']()).not.toBeNull();
    expect(page['inventory']()).toHaveLength(1);
    page['loadOptions']();
    flushOptions();
    expect(page['optionsError']()).toBeNull();
  });

  it('cancels requests when the page is destroyed', () => {
    page['loadInventory']();
    page['openDetail'](21);
    const requests = http.match(() => true);
    fixture.destroy();
    for (const req of requests) expect(req.cancelled).toBe(true);
  });
});
