import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminBranchesService } from './admin-branches.service';

describe('AdminBranchesService', () => {
  let service: AdminBranchesService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminBranchesService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('lists real branches with filters, pagination and Bearer authentication', () => {
    service.listBranches({ search: 'santa', estado: true, page: 2, pageSize: 10 }).subscribe();

    const request = httpTesting.expectOne(
      (candidate) => candidate.url === `${environment.apiUrl}/api/admin/branches`,
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(request.request.params.get('search')).toBe('santa');
    expect(request.request.params.get('estado')).toBe('true');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('10');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 10, total: 0, total_pages: 0 },
    });
  });

  it('connects detail, create, update and status endpoints', () => {
    service.getBranch(4).subscribe();
    const detail = httpTesting.expectOne(`${environment.apiUrl}/api/admin/branches/4`);
    expect(detail.request.method).toBe('GET');
    expect(detail.request.headers.get('Authorization')).toBe('Bearer admin-token');
    detail.flush({ success: true, data: branch });

    service.createBranch(fields).subscribe();
    const create = httpTesting.expectOne(`${environment.apiUrl}/api/admin/branches`);
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual(fields);
    expect(create.request.headers.get('Authorization')).toBe('Bearer admin-token');
    create.flush({ success: true, message: 'ok', data: branch });

    service.updateBranch(4, { nombre: 'Cercado', telefono: null, hora_apertura: null }).subscribe();
    const update = httpTesting.expectOne(`${environment.apiUrl}/api/admin/branches/4`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ nombre: 'Cercado', telefono: null, hora_apertura: null });
    expect(update.request.headers.get('Authorization')).toBe('Bearer admin-token');
    update.flush({ success: true, message: 'ok', data: { ...branch, nombre: 'Cercado' } });

    service.updateStatus(4, false).subscribe();
    const status = httpTesting.expectOne(`${environment.apiUrl}/api/admin/branches/4/status`);
    expect(status.request.method).toBe('PATCH');
    expect(status.request.body).toEqual({ estado: false });
    expect(status.request.headers.get('Authorization')).toBe('Bearer admin-token');
    status.flush({ success: true, message: 'ok', data: { ...branch, estado: false } });
  });
  it('keeps false status filters and omits empty search with default pagination', () => {
    service.listBranches({ search: '   ', estado: false }).subscribe();
    const request = httpTesting.expectOne((req) => req.url.endsWith('/api/admin/branches'));
    expect(request.request.params.get('estado')).toBe('false');
    expect(request.request.params.has('search')).toBe(false);
    expect(request.request.params.get('page')).toBe('1');
    expect(request.request.params.get('page_size')).toBe('20');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
    });
  });

  it.each([401, 403, 404, 409, 422, 500])(
    'propagates HTTP %s for the shared error handler',
    (status) => {
      let receivedStatus = 0;
      service.getBranch(4).subscribe({ error: (error) => (receivedStatus = error.status) });
      httpTesting
        .expectOne(`${environment.apiUrl}/api/admin/branches/4`)
        .flush({ success: false, message: 'error' }, { status, statusText: 'Error' });
      expect(receivedStatus).toBe(status);
    },
  );
});

const fields = {
  id_ciudad: 2,
  nombre: 'Tarija',
  direccion: 'Calle Central 123',
  telefono: null,
  hora_apertura: '08:00:00',
  hora_cierre: null,
};

const branch = {
  id_sucursal: 4,
  estado: true,
  ...fields,
  created_at: '2026-09-04T10:00:00',
  updated_at: '2026-09-04T10:00:00',
};
