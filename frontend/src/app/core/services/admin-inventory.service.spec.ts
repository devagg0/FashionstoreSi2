import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminInventoryService } from './admin-inventory.service';

const url = `${environment.apiUrl}/api/admin/inventory`;
describe('AdminInventoryService CU14', () => {
  let service: AdminInventoryService;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminInventoryService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    localStorage.clear();
  });
  it('lists with pagination and omits empty filters', () => {
    service.listInventory({ search: '  ' }).subscribe();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys()).toEqual(['page', 'page_size']);
    expect(req.request.params.get('page_size')).toBe('20');
    req.flush({
      success: true,
      data: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
    });
  });
  for (const key of [
    'id_sucursal',
    'id_ciudad',
    'id_categoria',
    'id_producto',
    'id_variante_producto',
    'id_talla',
    'id_color',
  ] as const) {
    it(`sends filter ${key} and Bearer authorization`, () => {
      service.listInventory({ [key]: 8, search: ' CAM-M ', page: 2, pageSize: 10 }).subscribe();
      const req = http.expectOne((r) => r.url === url);
      expect(req.request.params.get(key)).toBe('8');
      expect(req.request.params.get('search')).toBe('CAM-M');
      expect(req.request.params.get('page')).toBe('2');
      expect(req.request.params.get('page_size')).toBe('10');
      expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
      req.flush({});
    });
  }
  it('gets enriched detail', () => {
    service.getInventory(3).subscribe();
    const req = http.expectOne(`${url}/3`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    req.flush({});
  });
  it('creates with only allowed fields even if caller supplies stock fields', () => {
    const fields = {
      id_sucursal: 1,
      id_variante_producto: 2,
      stock_actual: 90,
      stock_reservado: 4,
      estado: true,
    };
    service.createInventory(fields).subscribe();
    const req = http.expectOne(url);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ id_sucursal: 1, id_variante_producto: 2, stock_minimo: 0 });
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    req.flush({});
  });
  it('patches only minimum and sends authorization', () => {
    const fields = { stock_minimo: 5, stock_actual: 90, stock_reservado: 4, id_sucursal: 8 };
    service.updateInventory(3, fields).subscribe();
    const req = http.expectOne(`${url}/3`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ stock_minimo: 5 });
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    req.flush({});
  });
  it('propagates 409', () => {
    const failure = vi.fn();
    service
      .createInventory({ id_sucursal: 1, id_variante_producto: 2 })
      .subscribe({ error: failure });
    http.expectOne(url).flush({ message: 'duplicado' }, { status: 409, statusText: 'Conflict' });
    expect(failure.mock.calls[0][0].status).toBe(409);
  });
});
