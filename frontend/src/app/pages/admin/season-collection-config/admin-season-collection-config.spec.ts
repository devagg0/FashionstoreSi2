import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { AdminSeasonCollectionConfig } from './admin-season-collection-config';
import { AdminSeasons } from './admin-seasons';
import { AdminCollections } from './admin-collections';
import { environment } from '../../../../environments/environment';

const url = `${environment.apiUrl}/api/admin`;
const pagination = { page: 1, page_size: 10, total: 11, total_pages: 2 };
const base = {
  nombre: 'Base',
  estado: true,
  created_at: '2026-09-04T10:00:00',
  updated_at: '2026-09-04T10:00:00',
};
const season = {
  ...base,
  id_temporada: 7,
  fecha_inicio: null,
  fecha_fin: null,
  descripcion: 'Original',
};

describe('CU08 independent tabs', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('switches tabs without mixing search, state, pagination or drafts', () => {
    const fixture = TestBed.createComponent(AdminSeasonCollectionConfig);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/seasons`)
      .flush({ success: true, data: [season], pagination });
    const seasons: AdminSeasons = fixture.debugElement.query(
      By.directive(AdminSeasons),
    ).componentInstance;
    seasons['filters'].setValue({ search: 'Base', estado: 'false' });
    seasons['applyFilters']();
    const search = http.expectOne((req) => req.url === `${url}/seasons`);
    expect(search.request.params.get('search')).toBe('Base');
    expect(search.request.params.get('estado')).toBe('false');
    expect(search.request.params.get('page')).toBe('1');
    search.flush({ success: true, data: [season], pagination });
    seasons['nextPage']();
    const next = http.expectOne((req) => req.url === `${url}/seasons`);
    expect(next.request.params.get('page')).toBe('2');
    next.flush({ success: true, data: [season], pagination: { ...pagination, page: 2 } });
    seasons['openSeasonModal']();
    seasons['seasonForm'].controls.nombre.setValue('Borrador');
    fixture.componentInstance['selectTab']('collections');
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/collections`)
      .flush({ success: true, data: [], pagination });
    const collections: AdminCollections = fixture.debugElement.query(
      By.directive(AdminCollections),
    ).componentInstance;
    expect(collections['filters'].getRawValue()).toEqual({ search: '', estado: '' });
    expect(collections['collectionModalOpen']()).toBe(false);
    collections['filters'].setValue({ search: 'Otra', estado: 'true' });
    collections['applyFilters']();
    const collectionSearch = http.expectOne((req) => req.url === `${url}/collections`);
    expect(collectionSearch.request.params.get('search')).toBe('Otra');
    expect(collectionSearch.request.params.get('estado')).toBe('true');
    collectionSearch.flush({ success: true, data: [], pagination });
    collections['nextPage']();
    const collectionPage = http.expectOne((req) => req.url === `${url}/collections`);
    expect(collectionPage.request.params.get('page')).toBe('2');
    collectionPage.flush({ success: true, data: [], pagination: { ...pagination, page: 2 } });
    expect(seasons['filters'].getRawValue()).toEqual({ search: 'Base', estado: 'false' });

    fixture.componentInstance['selectTab']('seasons');
    fixture.detectChanges();
    expect(seasons['pagination']().page).toBe(2);
    expect(seasons['seasonForm'].controls.nombre.value).toBe('Borrador');
    expect(seasons['filters'].controls.estado.value).toBe('false');
    expect(fixture.nativeElement.querySelector('#panel-collections').hidden).toBe(true);
    seasons['closeSeasonModal']();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#season-form-title')).toBeNull();
  });
});

describe('CU08 Seasons interface', () => {
  let http: HttpTestingController;
  const item = {
    ...base,
    id_temporada: 7,
    fecha_inicio: null,
    fecha_fin: null,
    descripcion: 'abc',
  };
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function setup() {
    const fixture = TestBed.createComponent(AdminSeasons);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/seasons`)
      .flush({ success: true, data: [item], pagination });
    return fixture;
  }
  it('allows repeated names, optional null and partial edits', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openSeasonModal']();
    page['seasonForm'].controls.nombre.setValue(' Base ');
    expect(page['seasonForm'].valid).toBe(true);
    page['submitSeason']();
    const create = http.expectOne(`${url}/seasons`);
    expect(create.request.body).toEqual({
      nombre: 'Base',
      descripcion: null,
      fecha_inicio: null,
      fecha_fin: null,
    });
    create.flush({ success: true, data: item, message: 'Creado' });
    http
      .expectOne((req) => req.url === `${url}/seasons`)
      .flush({ success: true, data: [item], pagination });
    expect(page['seasonModalOpen']()).toBe(false);
    page['openSeasonModal'](item);
    page['seasonForm'].controls.descripcion.setValue('');
    page['submitSeason']();
    const edit = http.expectOne(`${url}/seasons/7`);
    expect(edit.request.body).toEqual({ descripcion: null });
    edit.flush({ success: true, data: { ...item, descripcion: null }, message: 'Actualizado' });
    http
      .expectOne((req) => req.url === `${url}/seasons`)
      .flush({ success: true, data: [], pagination });
    expect(page['successMessage']()).toBe('Actualizado');
  });
  it('confirms both status changes and can cancel without a request', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openStatusModal'](item);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    http.expectNone(`${url}/seasons/7/status`);
    page['closeStatusModal']();
    expect(page['statusSeason']()).toBeNull();
    for (const estado of [true, false]) {
      page['openStatusModal']({ ...item, estado });
      page['confirmStatusChange']();
      const request = http.expectOne(`${url}/seasons/7/status`);
      expect(request.request.body).toEqual({ estado: !estado });
      request.flush({
        success: true,
        data: { ...item, estado: !estado },
        message: 'Estado actualizado',
      });
      http
        .expectOne((req) => req.url === `${url}/seasons`)
        .flush({ success: true, data: [item], pagination });
      expect(page['statusSeason']()).toBeNull();
    }
  });
  it('loads actual detail and validates only contract lengths', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/seasons/7`).flush({ success: true, data: item });
    expect(page['detailSeason']()).toEqual(item);
    page['closeDetail']();
    expect(page['detailModalOpen']()).toBe(false);
    page['openSeasonModal']();
    for (const nombre of ['', '   ', 'x'.repeat(100 + 1)]) {
      page['seasonForm'].controls.nombre.setValue(nombre);
      expect(page['seasonForm'].invalid).toBe(true);
    }
    page['seasonForm'].setValue({
      nombre: 'x'.repeat(100),
      descripcion: 'x'.repeat(200),
      fecha_inicio: '',
      fecha_fin: '',
    });
    expect(page['seasonForm'].valid).toBe(true);
    page['seasonForm'].controls.descripcion.setValue('x'.repeat(200 + 1));
    expect(page['seasonForm'].invalid).toBe(true);
  });
  it('cancels stale search and resets filters', () => {
    const page = setup().componentInstance;
    page['filters'].controls.search.setValue('old');
    page['applyFilters']();
    const old = http.expectOne((req) => req.url === `${url}/seasons`);
    page['clearFilters']();
    expect(old.cancelled).toBe(true);
    const current = http.expectOne((req) => req.url === `${url}/seasons`);
    expect(current.request.params.has('search')).toBe(false);
    current.flush({ success: true, data: [], pagination });
    expect(page['loading']()).toBe(false);
  });
  it.each([403, 404, 422, 500])('shows integrated HTTP %s errors', (status) => {
    const page = setup().componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/seasons/7`).flush({ success: false }, { status, statusText: 'Error' });
    expect(page['errorMessage']()).toBeTruthy();
    expect(page['detailModalOpen']()).toBe(false);
  });
  it('accepts reversed dates, displays null clearly and clears a date with partial PATCH', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector('[data-label="Fecha inicio"]').textContent.trim(),
    ).toBe('—');
    page['openSeasonModal']();
    page['seasonForm'].patchValue({
      nombre: 'Base',
      fecha_inicio: '2026-12-31',
      fecha_fin: '2026-01-01',
    });
    expect(page['seasonForm'].valid).toBe(true);
    page['submitSeason']();
    const create = http.expectOne(`${url}/seasons`);
    expect(create.request.body).toEqual({
      nombre: 'Base',
      descripcion: null,
      fecha_inicio: '2026-12-31',
      fecha_fin: '2026-01-01',
    });
    const dated = { ...item, fecha_inicio: '2026-12-31', fecha_fin: '2026-01-01' };
    create.flush({ success: true, data: dated, message: 'Creada' });
    http
      .expectOne((req) => req.url === `${url}/seasons`)
      .flush({ success: true, data: [dated], pagination });
    page['openSeasonModal'](dated);
    page['seasonForm'].controls.fecha_inicio.setValue('');
    page['submitSeason']();
    const edit = http.expectOne(`${url}/seasons/7`);
    expect(edit.request.body).toEqual({ fecha_inicio: null });
    edit.flush({ success: true, data: { ...dated, fecha_inicio: null }, message: 'Actualizada' });
    http
      .expectOne((req) => req.url === `${url}/seasons`)
      .flush({ success: true, data: [], pagination });
  });
});

describe('CU08 Collections interface', () => {
  let http: HttpTestingController;
  const item = { ...base, id_coleccion: 7, descripcion: 'abc' };
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  function setup() {
    const fixture = TestBed.createComponent(AdminCollections);
    fixture.detectChanges();
    http
      .expectOne((req) => req.url === `${url}/collections`)
      .flush({ success: true, data: [item], pagination });
    return fixture;
  }
  it('allows repeated names, optional null and partial edits', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openCollectionModal']();
    page['collectionForm'].controls.nombre.setValue(' Base ');
    expect(page['collectionForm'].valid).toBe(true);
    page['submitCollection']();
    const create = http.expectOne(`${url}/collections`);
    expect(create.request.body).toEqual({ nombre: 'Base', descripcion: null });
    create.flush({ success: true, data: item, message: 'Creado' });
    http
      .expectOne((req) => req.url === `${url}/collections`)
      .flush({ success: true, data: [item], pagination });
    expect(page['collectionModalOpen']()).toBe(false);
    page['openCollectionModal'](item);
    page['collectionForm'].controls.descripcion.setValue('');
    page['submitCollection']();
    const edit = http.expectOne(`${url}/collections/7`);
    expect(edit.request.body).toEqual({ descripcion: null });
    edit.flush({ success: true, data: { ...item, descripcion: null }, message: 'Actualizado' });
    http
      .expectOne((req) => req.url === `${url}/collections`)
      .flush({ success: true, data: [], pagination });
    expect(page['successMessage']()).toBe('Actualizado');
  });
  it('confirms both status changes and can cancel without a request', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['openStatusModal'](item);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    http.expectNone(`${url}/collections/7/status`);
    page['closeStatusModal']();
    expect(page['statusCollection']()).toBeNull();
    for (const estado of [true, false]) {
      page['openStatusModal']({ ...item, estado });
      page['confirmStatusChange']();
      const request = http.expectOne(`${url}/collections/7/status`);
      expect(request.request.body).toEqual({ estado: !estado });
      request.flush({
        success: true,
        data: { ...item, estado: !estado },
        message: 'Estado actualizado',
      });
      http
        .expectOne((req) => req.url === `${url}/collections`)
        .flush({ success: true, data: [item], pagination });
      expect(page['statusCollection']()).toBeNull();
    }
  });
  it('loads actual detail and validates only contract lengths', () => {
    const fixture = setup();
    const page = fixture.componentInstance;
    page['viewDetail'](7);
    http.expectOne(`${url}/collections/7`).flush({ success: true, data: item });
    expect(page['detailCollection']()).toEqual(item);
    page['closeDetail']();
    expect(page['detailModalOpen']()).toBe(false);
    page['openCollectionModal']();
    for (const nombre of ['', '   ', 'x'.repeat(100 + 1)]) {
      page['collectionForm'].controls.nombre.setValue(nombre);
      expect(page['collectionForm'].invalid).toBe(true);
    }
    page['collectionForm'].setValue({ nombre: 'x'.repeat(100), descripcion: 'x'.repeat(200) });
    expect(page['collectionForm'].valid).toBe(true);
    page['collectionForm'].controls.descripcion.setValue('x'.repeat(200 + 1));
    expect(page['collectionForm'].invalid).toBe(true);
  });
  it('cancels stale search and resets filters', () => {
    const page = setup().componentInstance;
    page['filters'].controls.search.setValue('old');
    page['applyFilters']();
    const old = http.expectOne((req) => req.url === `${url}/collections`);
    page['clearFilters']();
    expect(old.cancelled).toBe(true);
    const current = http.expectOne((req) => req.url === `${url}/collections`);
    expect(current.request.params.has('search')).toBe(false);
    current.flush({ success: true, data: [], pagination });
    expect(page['loading']()).toBe(false);
  });
  it.each([403, 404, 422, 500])('shows integrated HTTP %s errors', (status) => {
    const page = setup().componentInstance;
    page['viewDetail'](7);
    http
      .expectOne(`${url}/collections/7`)
      .flush({ success: false }, { status, statusText: 'Error' });
    expect(page['errorMessage']()).toBeTruthy();
    expect(page['detailModalOpen']()).toBe(false);
  });
});
