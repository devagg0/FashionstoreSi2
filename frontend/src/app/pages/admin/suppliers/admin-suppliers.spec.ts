import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { AdminSuppliers } from './admin-suppliers';
import { AdminSupplier } from '../../../core/services/admin-suppliers.service';
import { environment } from '../../../../environments/environment';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';

const url = `${environment.apiUrl}/api/admin/suppliers`;
const supplier: AdminSupplier = {
  id_proveedor: 3,
  nombre: 'Proveedor Base',
  nit: '123',
  telefono: null,
  correo: 'base@example.com',
  direccion: null,
  id_usuario: null,
  estado: true,
  created_at: '2026-09-05T10:00:00',
  updated_at: '2026-09-05T10:00:00',
};
const listing = (data = [supplier], page = 1, total = data.length) => ({
  success: true,
  data,
  pagination: { page, page_size: 10, total, total_pages: Math.ceil(total / 10) },
});

describe('AdminSuppliers CU09', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<AdminSuppliers>;
  let page: AdminSuppliers;
  function flushLists() {
    for (const request of http.match((req) => req.url === url && req.method === 'GET')) {
      request.flush(listing());
    }
  }
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminSuppliers);
    page = fixture.componentInstance;
    fixture.detectChanges();
    flushLists();
    fixture.detectChanges();
  });
  afterEach(() => {
    http.verify();
    fixture.destroy();
  });

  it('renders the list, empty state and loading state', () => {
    expect(fixture.nativeElement.textContent).toContain('Proveedor Base');
    expect(fixture.nativeElement.textContent).toContain('123');
    page['loadSuppliers']();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.loading-row')).toBeTruthy();
    http.expectOne((req) => req.url === url).flush(listing([]));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.empty-state')).toBeTruthy();
  });

  it('searches on the server and filters state, resetting pagination', () => {
    page['filters'].setValue({ search: ' base@example.com ', estado: 'false' });
    page['applyFilters']();
    const request = http.expectOne((req) => req.url === url);
    expect(request.request.params.get('search')).toBe('base@example.com');
    expect(request.request.params.get('estado')).toBe('false');
    expect(request.request.params.get('page')).toBe('1');
    request.flush(listing());
    page['clearFilters']();
    const clear = http.expectOne((req) => req.url === url);
    expect(clear.request.params.has('search')).toBe(false);
    expect(clear.request.params.has('estado')).toBe(false);
    clear.flush(listing());
  });

  it('paginates using server metadata', () => {
    page['pagination'].set({ page: 1, page_size: 10, total: 11, total_pages: 2 });
    page['nextPage']();
    const next = http.expectOne((req) => req.url === url);
    expect(next.request.params.get('page')).toBe('2');
    expect(next.request.params.get('page_size')).toBe('10');
    next.flush(listing([supplier], 2, 11));
    page['previousPage']();
    const previous = http.expectOne((req) => req.url === url);
    expect(previous.request.params.get('page')).toBe('1');
    previous.flush(listing([supplier], 1, 11));
  });

  it('creates a duplicate name and sends optional blanks as null', () => {
    page['openSupplierModal']();
    page['supplierForm'].patchValue({ nombre: ' Proveedor Base ' });
    page['submitSupplier']();
    const request = http.expectOne(url);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      nombre: 'Proveedor Base',
      nit: null,
      telefono: null,
      correo: null,
      direccion: null,
    });
    request.flush(
      { success: true, message: 'ok', data: supplier },
      { status: 201, statusText: 'Created' },
    );
    flushLists();
    expect(page['supplierModalOpen']()).toBe(false);
    expect(page['successMessage']()).toBeTruthy();
  });

  it('validates required name, lengths and optional email', () => {
    page['openSupplierModal']();
    const form = page['supplierForm'];
    form.patchValue({ nombre: '   ' });
    expect(form.invalid).toBe(true);
    form.patchValue({ nombre: 'Base' });
    expect(form.valid).toBe(true);
    for (const field of page['textFields']) {
      form.controls[field.name].setValue('x'.repeat(field.max + 1));
      expect(form.controls[field.name].invalid).toBe(true);
      form.controls[field.name].setValue(field.name === 'nombre' ? 'Base' : '');
    }
    form.controls.correo.setValue('invalid');
    page['submitSupplier']();
    http.expectNone(url);
    expect(form.controls.correo.invalid).toBe(true);
    form.controls.correo.setValue('valid@example.com');
    expect(form.valid).toBe(true);
  });

  it('patches only changed commercial fields and preserves explicit null', () => {
    page['openSupplierModal']({ ...supplier, id_usuario: 8 });
    page['supplierForm'].patchValue({ nit: '', telefono: '70000000' });
    page['submitSupplier']();
    const request = http.expectOne(`${url}/3`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ nit: null, telefono: '70000000' });
    request.flush({
      success: true,
      message: 'ok',
      data: { ...supplier, nit: null, telefono: '70000000', id_usuario: 8 },
    });
    flushLists();
  });

  it('does not submit an empty patch', () => {
    page['openSupplierModal'](supplier);
    page['submitSupplier']();
    http.expectNone(`${url}/3`);
    expect(page['modalErrorMessage']()).toBeTruthy();
  });

  it('preserves untouched optional empty strings when editing another field', () => {
    page['openSupplierModal']({ ...supplier, telefono: '' });
    page['supplierForm'].patchValue({ nombre: 'Otro nombre' });
    page['submitSupplier']();
    const request = http.expectOne(`${url}/3`);
    expect(request.request.body).toEqual({ nombre: 'Otro nombre' });
    request.flush({ success: true, message: 'ok', data: { ...supplier, nombre: 'Otro nombre' } });
    flushLists();
  });

  it.each([null, 8])('shows detail with user association %s as read-only', (id_usuario) => {
    page['viewDetail'](3);
    const request = http.expectOne(`${url}/3`);
    expect(request.request.method).toBe('GET');
    request.flush({ success: true, data: { ...supplier, id_usuario } });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(
      id_usuario === null ? 'Sin cuenta vinculada' : 'Cuenta vinculada #8',
    );
    expect(fixture.nativeElement.querySelector('[formControlName="id_usuario"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[formControlName="id_sucursal"]')).toBeNull();
  });

  it.each([true, false])('confirms status change from %s without deleting', (estado) => {
    page['openStatusModal']({ ...supplier, estado });
    http.expectNone(`${url}/3/status`);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    page['confirmStatusChange']();
    const request = http.expectOne(`${url}/3/status`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ estado: !estado });
    request.flush({ success: true, message: 'ok', data: { ...supplier, estado: !estado } });
    flushLists();
    expect(page['statusSupplier']()).toBeNull();
  });

  it.each([401, 403, 404, 409, 422, 500])(
    'handles HTTP %s through AdminApiErrorService',
    (status) => {
      const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
      page['openSupplierModal']();
      page['supplierForm'].patchValue({ nombre: 'Base' });
      page['submitSupplier']();
      http
        .expectOne(url)
        .flush(
          { success: false, message: status === 409 ? 'Conflicto real' : 'internal SQL details' },
          { status, statusText: 'Error' },
        );
      expect(page['modalErrorMessage']()).toBeTruthy();
      expect(page['modalErrorMessage']()).not.toContain('internal SQL details');
      if (status === 409) expect(page['modalErrorMessage']()).toBe('Conflicto real');
      if (status === 401) expect(navigate).toHaveBeenCalledWith('/login');
      expect(page['saving']()).toBe(false);
    },
  );

  it('handles missing detail and failed status updates', () => {
    page['viewDetail'](3);
    http.expectOne(`${url}/3`).flush({}, { status: 404, statusText: 'Not Found' });
    expect(page['detailModalOpen']()).toBe(false);
    expect(page['errorMessage']()).toBeTruthy();
    page['openStatusModal'](supplier);
    page['confirmStatusChange']();
    http.expectOne(`${url}/3/status`).flush({}, { status: 500, statusText: 'Error' });
    expect(page['errorMessage']()).toBeTruthy();
    expect(page['saving']()).toBe(false);
  });

  it('registers a lazy route under the existing admin guards', async () => {
    const admin = routes.find((route) => route.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    const route = admin.children!.find((route) => route.path === 'proveedores')!;
    expect(await (route.loadComponent! as () => Promise<unknown>)()).toBe(AdminSuppliers);
  });
});
