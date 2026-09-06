import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminColorsService } from './admin-colors.service';

const url = `${environment.apiUrl}/api/admin/colors`;
describe('AdminColorsService', () => {
  let service: AdminColorsService;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminColorsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    localStorage.clear();
  });
  it('lists with the real filters and Bearer token', () => {
    service.listColors({ search: ' base ', estado: false, page: 2, pageSize: 10 }).subscribe();
    const request = http.expectOne((req) => req.url === url);
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(request.request.params.keys().sort()).toEqual(['estado', 'page', 'page_size', 'search']);
    expect(request.request.params.get('search')).toBe('base');
    expect(request.request.params.get('estado')).toBe('false');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('10');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 10, total: 0, total_pages: 0 },
    });
  });
  it('creates with an optional field omitted', () => {
    service.createColor({ nombre: 'Base' }).subscribe();
    const request = http.expectOne(url);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ nombre: 'Base' });
    request.flush(
      { success: true, message: 'ok', data: {} },
      { status: 201, statusText: 'Created' },
    );
  });
  it('edits only supplied fields and preserves explicit null', () => {
    service.updateColor(7, { codigo_hex: null }).subscribe();
    const request = http.expectOne(`${url}/7`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ codigo_hex: null });
    request.flush({ success: true, message: 'ok', data: {} });
  });
  it('reads detail and changes status without deletion', () => {
    service.getColor(7).subscribe();
    const detail = http.expectOne(`${url}/7`);
    expect(detail.request.method).toBe('GET');
    detail.flush({ success: true, data: {} });
    for (const estado of [false, true]) {
      service.updateStatus(7, estado).subscribe();
      const request = http.expectOne(`${url}/7/status`);
      expect(request.request.method).toBe('PATCH');
      expect(request.request.body).toEqual({ estado });
      expect(request.request.headers.get('Authorization')).toBe('Bearer admin-token');
      request.flush({ success: true, message: 'ok', data: {} });
    }
  });
  it.each([401, 403, 404, 409, 422, 500])('propagates HTTP %s', (status) => {
    const error = vi.fn();
    service.createColor({ nombre: 'Base' }).subscribe({ error });
    http
      .expectOne(url)
      .flush({ success: false, message: 'Conflicto' }, { status, statusText: 'Error' });
    expect(error.mock.calls[0][0].status).toBe(status);
  });
});
