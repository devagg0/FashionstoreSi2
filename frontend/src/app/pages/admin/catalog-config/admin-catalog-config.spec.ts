import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { AdminCatalogConfig } from './admin-catalog-config';
import { AdminCategories } from './admin-categories';
import { AdminSizes } from './admin-sizes';
import { AdminColors } from './admin-colors';
import { environment } from '../../../../environments/environment';

const url = `${environment.apiUrl}/api/admin`;
const pagination = { page: 1, page_size: 10, total: 11, total_pages: 2 };
const base = {
  nombre: 'Base',
  estado: true,
  created_at: '2026-09-04T10:00:00',
  updated_at: '2026-09-04T10:00:00',
};
const category = { ...base, id_categoria: 7, descripcion: 'Original' };

describe('CU07 independent tabs', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('switches tabs without mixing search, state, pagination or drafts', () => {
    const fixture = TestBed.createComponent(AdminCatalogConfig);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/categories`)
      .flush({ success: true, data: [category], pagination });
    const categories: AdminCategories = fixture.debugElement.query(
      By.directive(AdminCategories),
    ).componentInstance;
    categories['filters'].setValue({ search: 'Base', estado: 'false' });
    categories['applyFilters']();
    const search = http.expectOne((req) => req.url === `${url}/categories`);
    expect(search.request.params.get('search')).toBe('Base');
    expect(search.request.params.get('estado')).toBe('false');
    expect(search.request.params.get('page')).toBe('1');
    search.flush({ success: true, data: [category], pagination });
    categories['nextPage']();
    const next = http.expectOne((req) => req.url === `${url}/categories`);
    expect(next.request.params.get('page')).toBe('2');
    next.flush({ success: true, data: [category], pagination: { ...pagination, page: 2 } });
    categories['openCategoryModal']();
    categories['categoryForm'].controls.nombre.setValue('Borrador');
    fixture.componentInstance['selectTab']('sizes');
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/sizes`)
      .flush({ success: true, data: [], pagination });
    const sizes: AdminSizes = fixture.debugElement.query(
      By.directive(AdminSizes),
    ).componentInstance;
    expect(sizes['filters'].getRawValue()).toEqual({ search: '', estado: '' });
    expect(sizes['sizeModalOpen']()).toBe(false);
    fixture.componentInstance['selectTab']('colors');
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/colors`)
      .flush({ success: true, data: [], pagination });
    fixture.componentInstance['selectTab']('categories');
    fixture.detectChanges();
    expect(categories['pagination']().page).toBe(2);
    expect(categories['categoryForm'].controls.nombre.value).toBe('Borrador');
    expect(categories['filters'].controls.estado.value).toBe('false');
    expect(fixture.nativeElement.querySelector('#panel-sizes').hidden).toBe(true);
    categories['closeCategoryModal']();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#category-form-title')).toBeNull();
  });
});

describe('CU07 Categories interface', () => {
  let http: HttpTestingController;
  const item = { ...base, id_categoria: 7, descripcion: 'abc' };
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function setup() {
    const fixture = TestBed.createComponent(AdminCategories);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/categories`)
      .flush({ success: true, data: [item], pagination });
    return fixture;
  }
  it('creates with optional null, clears conflicts and sends partial edits', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openCategoryModal']();
    page['categoryForm'].controls.nombre.setValue(' Nuevo ');
    expect(page['categoryForm'].valid).toBe(true);
    page['submitCategory']();
    const create = http.expectOne(`${url}/categories`);
    expect(create.request.body).toEqual({ nombre: 'Nuevo', descripcion: null });
    create.flush(
      { success: false, message: 'Ya existe ese nombre' },
      { status: 409, statusText: 'Conflict' },
    );
    expect(page['modalErrorMessage']()).toContain('Ya existe');
    expect(page['categoryForm'].controls.nombre.hasError('duplicate')).toBe(true);
    page['categoryForm'].controls.nombre.setValue('Otro');
    page['clearNameConflict']();
    page['submitCategory']();
    http.expectOne(`${url}/categories`).flush({ success: true, data: item, message: 'Creado' });
    http
      .expectOne((req) => req.url === `${url}/categories`)
      .flush({ success: true, data: [item], pagination });
    expect(page['categoryModalOpen']()).toBe(false);
    page['openCategoryModal'](item);
    page['categoryForm'].controls.descripcion.setValue('');
    page['submitCategory']();
    const edit = http.expectOne(`${url}/categories/7`);
    expect(edit.request.body).toEqual({ descripcion: null });
    edit.flush({ success: true, data: { ...item, descripcion: null }, message: 'Actualizado' });
    http
      .expectOne((req) => req.url === `${url}/categories`)
      .flush({ success: true, data: [], pagination });
    expect(page['successMessage']()).toBe('Actualizado');
  });
  it('confirms both status changes and can cancel without a request', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openStatusModal'](item);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    http.expectNone(`${url}/categories/7/status`);
    page['closeStatusModal']();
    expect(page['statusCategory']()).toBeNull();
    for (const estado of [true, false]) {
      page['openStatusModal']({ ...item, estado });
      page['confirmStatusChange']();
      const request = http.expectOne(`${url}/categories/7/status`);
      expect(request.request.body).toEqual({ estado: !estado });
      request.flush({
        success: true,
        data: { ...item, estado: !estado },
        message: 'Estado actualizado',
      });
      http
        .expectOne((req) => req.url === `${url}/categories`)
        .flush({ success: true, data: [item], pagination });
      expect(page['statusCategory']()).toBeNull();
    }
  });
  it('loads actual detail and validates only contract lengths', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/categories/7`).flush({ success: true, data: item });
    expect(page['detailCategory']()).toEqual(item);
    page['closeDetail']();
    expect(page['detailModalOpen']()).toBe(false);
    page['openCategoryModal']();
    for (const nombre of ['', '   ', 'x'.repeat(100 + 1)]) {
      page['categoryForm'].controls.nombre.setValue(nombre);
      expect(page['categoryForm'].invalid).toBe(true);
    }
    page['categoryForm'].setValue({ nombre: 'x'.repeat(100), descripcion: 'x'.repeat(200) });
    expect(page['categoryForm'].valid).toBe(true);
    page['categoryForm'].controls.descripcion.setValue('x'.repeat(200 + 1));
    expect(page['categoryForm'].invalid).toBe(true);
  });
  it('cancels stale search and resets filters', () => {
    const page = setup().componentInstance;
    page['filters'].controls.search.setValue('old');
    page['applyFilters']();
    const old = http.expectOne((req) => req.url === `${url}/categories`);
    page['clearFilters']();
    expect(old.cancelled).toBe(true);
    const current = http.expectOne((req) => req.url === `${url}/categories`);
    expect(current.request.params.has('search')).toBe(false);
    current.flush({ success: true, data: [], pagination });
    expect(page['loading']()).toBe(false);
  });
  it.each([403, 404, 422, 500])('shows integrated HTTP %s errors', (status) => {
    const page = setup().componentInstance;
    page['viewDetail'](7);
    http
      .expectOne(`${url}/categories/7`)
      .flush({ success: false }, { status, statusText: 'Error' });
    expect(page['errorMessage']()).toBeTruthy();
    expect(page['detailModalOpen']()).toBe(false);
  });
});

describe('CU07 Sizes interface', () => {
  let http: HttpTestingController;
  const item = { ...base, id_talla: 7, descripcion: 'abc' };
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function setup() {
    const fixture = TestBed.createComponent(AdminSizes);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/sizes`)
      .flush({ success: true, data: [item], pagination });
    return fixture;
  }
  it('creates with optional null, clears conflicts and sends partial edits', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openSizeModal']();
    page['sizeForm'].controls.nombre.setValue(' Nuevo ');
    expect(page['sizeForm'].valid).toBe(true);
    page['submitSize']();
    const create = http.expectOne(`${url}/sizes`);
    expect(create.request.body).toEqual({ nombre: 'Nuevo', descripcion: null });
    create.flush(
      { success: false, message: 'Ya existe ese nombre' },
      { status: 409, statusText: 'Conflict' },
    );
    expect(page['modalErrorMessage']()).toContain('Ya existe');
    expect(page['sizeForm'].controls.nombre.hasError('duplicate')).toBe(true);
    page['sizeForm'].controls.nombre.setValue('Otro');
    page['clearNameConflict']();
    page['submitSize']();
    http.expectOne(`${url}/sizes`).flush({ success: true, data: item, message: 'Creado' });
    http
      .expectOne((req) => req.url === `${url}/sizes`)
      .flush({ success: true, data: [item], pagination });
    expect(page['sizeModalOpen']()).toBe(false);
    page['openSizeModal'](item);
    page['sizeForm'].controls.descripcion.setValue('');
    page['submitSize']();
    const edit = http.expectOne(`${url}/sizes/7`);
    expect(edit.request.body).toEqual({ descripcion: null });
    edit.flush({ success: true, data: { ...item, descripcion: null }, message: 'Actualizado' });
    http
      .expectOne((req) => req.url === `${url}/sizes`)
      .flush({ success: true, data: [], pagination });
    expect(page['successMessage']()).toBe('Actualizado');
  });
  it('confirms both status changes and can cancel without a request', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openStatusModal'](item);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    http.expectNone(`${url}/sizes/7/status`);
    page['closeStatusModal']();
    expect(page['statusSize']()).toBeNull();
    for (const estado of [true, false]) {
      page['openStatusModal']({ ...item, estado });
      page['confirmStatusChange']();
      const request = http.expectOne(`${url}/sizes/7/status`);
      expect(request.request.body).toEqual({ estado: !estado });
      request.flush({
        success: true,
        data: { ...item, estado: !estado },
        message: 'Estado actualizado',
      });
      http
        .expectOne((req) => req.url === `${url}/sizes`)
        .flush({ success: true, data: [item], pagination });
      expect(page['statusSize']()).toBeNull();
    }
  });
  it('loads actual detail and validates only contract lengths', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/sizes/7`).flush({ success: true, data: item });
    expect(page['detailSize']()).toEqual(item);
    page['closeDetail']();
    expect(page['detailModalOpen']()).toBe(false);
    page['openSizeModal']();
    for (const nombre of ['', '   ', 'x'.repeat(20 + 1)]) {
      page['sizeForm'].controls.nombre.setValue(nombre);
      expect(page['sizeForm'].invalid).toBe(true);
    }
    page['sizeForm'].setValue({ nombre: 'x'.repeat(20), descripcion: 'x'.repeat(100) });
    expect(page['sizeForm'].valid).toBe(true);
    page['sizeForm'].controls.descripcion.setValue('x'.repeat(100 + 1));
    expect(page['sizeForm'].invalid).toBe(true);
  });
  it('cancels stale search and resets filters', () => {
    const page = setup().componentInstance;
    page['filters'].controls.search.setValue('old');
    page['applyFilters']();
    const old = http.expectOne((req) => req.url === `${url}/sizes`);
    page['clearFilters']();
    expect(old.cancelled).toBe(true);
    const current = http.expectOne((req) => req.url === `${url}/sizes`);
    expect(current.request.params.has('search')).toBe(false);
    current.flush({ success: true, data: [], pagination });
    expect(page['loading']()).toBe(false);
  });
  it.each([403, 404, 422, 500])('shows integrated HTTP %s errors', (status) => {
    const page = setup().componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/sizes/7`).flush({ success: false }, { status, statusText: 'Error' });
    expect(page['errorMessage']()).toBeTruthy();
    expect(page['detailModalOpen']()).toBe(false);
  });
});

describe('CU07 Colors interface', () => {
  let http: HttpTestingController;
  const item = { ...base, id_color: 7, codigo_hex: 'abc' };
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function setup() {
    const fixture = TestBed.createComponent(AdminColors);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/colors`)
      .flush({ success: true, data: [item], pagination });
    return fixture;
  }
  it('creates with optional null, clears conflicts and sends partial edits', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openColorModal']();
    page['colorForm'].controls.nombre.setValue(' Nuevo ');
    expect(page['colorForm'].valid).toBe(true);
    page['submitColor']();
    const create = http.expectOne(`${url}/colors`);
    expect(create.request.body).toEqual({ nombre: 'Nuevo', codigo_hex: null });
    create.flush(
      { success: false, message: 'Ya existe ese nombre' },
      { status: 409, statusText: 'Conflict' },
    );
    expect(page['modalErrorMessage']()).toContain('Ya existe');
    expect(page['colorForm'].controls.nombre.hasError('duplicate')).toBe(true);
    page['colorForm'].controls.nombre.setValue('Otro');
    page['clearNameConflict']();
    page['submitColor']();
    http.expectOne(`${url}/colors`).flush({ success: true, data: item, message: 'Creado' });
    http
      .expectOne((req) => req.url === `${url}/colors`)
      .flush({ success: true, data: [item], pagination });
    expect(page['colorModalOpen']()).toBe(false);
    page['openColorModal'](item);
    page['colorForm'].controls.codigo_hex.setValue('');
    page['submitColor']();
    const edit = http.expectOne(`${url}/colors/7`);
    expect(edit.request.body).toEqual({ codigo_hex: null });
    edit.flush({ success: true, data: { ...item, codigo_hex: null }, message: 'Actualizado' });
    http
      .expectOne((req) => req.url === `${url}/colors`)
      .flush({ success: true, data: [], pagination });
    expect(page['successMessage']()).toBe('Actualizado');
  });
  it('confirms both status changes and can cancel without a request', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openStatusModal'](item);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    http.expectNone(`${url}/colors/7/status`);
    page['closeStatusModal']();
    expect(page['statusColor']()).toBeNull();
    for (const estado of [true, false]) {
      page['openStatusModal']({ ...item, estado });
      page['confirmStatusChange']();
      const request = http.expectOne(`${url}/colors/7/status`);
      expect(request.request.body).toEqual({ estado: !estado });
      request.flush({
        success: true,
        data: { ...item, estado: !estado },
        message: 'Estado actualizado',
      });
      http
        .expectOne((req) => req.url === `${url}/colors`)
        .flush({ success: true, data: [item], pagination });
      expect(page['statusColor']()).toBeNull();
    }
  });
  it('loads actual detail and validates only contract lengths', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/colors/7`).flush({ success: true, data: item });
    expect(page['detailColor']()).toEqual(item);
    page['closeDetail']();
    expect(page['detailModalOpen']()).toBe(false);
    page['openColorModal']();
    for (const nombre of ['', '   ', 'x'.repeat(50 + 1)]) {
      page['colorForm'].controls.nombre.setValue(nombre);
      expect(page['colorForm'].invalid).toBe(true);
    }
    page['colorForm'].setValue({ nombre: 'x'.repeat(50), codigo_hex: 'x'.repeat(7) });
    expect(page['colorForm'].valid).toBe(true);
    page['colorForm'].controls.codigo_hex.setValue('x'.repeat(7 + 1));
    expect(page['colorForm'].invalid).toBe(true);
  });
  it('cancels stale search and resets filters', () => {
    const page = setup().componentInstance;
    page['filters'].controls.search.setValue('old');
    page['applyFilters']();
    const old = http.expectOne((req) => req.url === `${url}/colors`);
    page['clearFilters']();
    expect(old.cancelled).toBe(true);
    const current = http.expectOne((req) => req.url === `${url}/colors`);
    expect(current.request.params.has('search')).toBe(false);
    current.flush({ success: true, data: [], pagination });
    expect(page['loading']()).toBe(false);
  });
  it.each([403, 404, 422, 500])('shows integrated HTTP %s errors', (status) => {
    const page = setup().componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/colors/7`).flush({ success: false }, { status, statusText: 'Error' });
    expect(page['errorMessage']()).toBeTruthy();
    expect(page['detailModalOpen']()).toBe(false);
  });
});
