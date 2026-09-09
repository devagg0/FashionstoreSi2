import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminGlobalInventoryService } from './admin-global-inventory.service';

const url = `${environment.apiUrl}/api/admin/global-inventory`;
describe('AdminGlobalInventoryService CU16', () => {
  let service: AdminGlobalInventoryService;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminGlobalInventoryService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('lists with default pagination and Bearer authorization', () => {
    const received = vi.fn();
    service.listGlobalInventory().subscribe(received);
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(req.request.params.get('page')).toBe('1');
    expect(req.request.params.get('page_size')).toBe('20');
    const response = {
      success: true,
      data: [],
      message: 'OK',
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
    };
    req.flush(response);
    expect(received).toHaveBeenCalledWith(response);
  });

  for (const field of [
    'id_categoria',
    'id_producto',
    'id_talla',
    'id_color',
    'id_ciudad',
    'id_sucursal',
  ] as const) {
    it(`sends ${field} with search and pagination`, () => {
      service
        .listGlobalInventory({ [field]: 7, search: ' CAM-M ', page: 2, pageSize: 10 })
        .subscribe();
      const req = http.expectOne((r) => r.url === url);
      expect(req.request.params.get(field)).toBe('7');
      expect(req.request.params.get('search')).toBe('CAM-M');
      expect(req.request.params.get('page')).toBe('2');
      expect(req.request.params.get('page_size')).toBe('10');
      req.flush({});
    });
  }

  it('preserves search special characters for backend escaping', () => {
    service.listGlobalInventory({ search: '%_\\' }).subscribe();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.params.get('search')).toBe('%_\\');
    req.flush({});
  });

  it('omits blank search and absent filters', () => {
    service.listGlobalInventory({ search: '  ' }).subscribe();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.params.keys()).toEqual(['page', 'page_size']);
    req.flush({});
  });

  it('gets detail by variant ID using GET and Bearer', () => {
    service.getGlobalInventoryDetail(21).subscribe();
    const req = http.expectOne(`${url}/21`);
    expect(req.request.method).toBe('GET');
    expect(req.request.body).toBeNull();
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(req.request.params.keys()).toEqual([]);
    req.flush({});
  });

  it('does not invent an authorization token without a session', () => {
    localStorage.clear();
    service.getGlobalInventoryDetail(21).subscribe();
    const req = http.expectOne(`${url}/21`);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  for (const status of [401, 403, 404, 422, 500]) {
    it(`propagates ${status} for UI handling`, () => {
      const failure = vi.fn();
      service.getGlobalInventoryDetail(21).subscribe({ error: failure });
      http
        .expectOne(`${url}/21`)
        .flush({ message: 'Error de consulta' }, { status, statusText: 'Error' });
      expect(failure.mock.calls[0][0].status).toBe(status);
    });
  }

  it('exposes only query operations', () => {
    expect(
      Object.getOwnPropertyNames(AdminGlobalInventoryService.prototype).filter(
        (key) => !['constructor', 'headers'].includes(key),
      ),
    ).toEqual(['listGlobalInventory', 'getGlobalInventoryDetail']);
  });
});
