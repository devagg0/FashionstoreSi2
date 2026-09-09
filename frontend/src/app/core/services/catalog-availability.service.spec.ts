import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { CatalogAvailabilityService } from './catalog-availability.service';

describe('CatalogAvailabilityService CU13', () => {
  let service: CatalogAvailabilityService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/catalog/products/10/availability`;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(CatalogAvailabilityService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });

  it('consults a product anonymously with GET and no body or filters', () => {
    localStorage.clear();
    service.getProductAvailability(10).subscribe();
    const req = http.expectOne(url);
    expect(req.request.method).toBe('GET');
    expect(req.request.body).toBeNull();
    expect(req.request.headers.has('Authorization')).toBe(false);
    expect(req.request.withCredentials).toBe(false);
    req.flush({ success: true, data: { disponibilidad: [] }, message: '' });
  });

  it('does not send a stored JWT and supports every optional filter', () => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    const filters = { id_variante_producto: 25, id_sucursal: 1, id_ciudad: 2, id_talla: 3, id_color: 4 };
    service.getProductAvailability(10, filters).subscribe();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.headers.has('Authorization')).toBe(false);
    for (const [key, value] of Object.entries(filters)) expect(req.request.params.get(key)).toBe(String(value));
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: { disponibilidad: [] }, message: '' });
  });

  it('sends only the selected variant and omits undefined filters', () => {
    service.getProductAvailability(10, { id_variante_producto: 25, id_ciudad: undefined }).subscribe();
    const req = http.expectOne(`${url}?id_variante_producto=25`);
    expect(req.request.params.keys()).toEqual(['id_variante_producto']);
    req.flush({ success: true, data: { disponibilidad: [] }, message: '' });
  });
});
