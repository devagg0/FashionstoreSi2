import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { CatalogService } from './catalog.service';

describe('CatalogService CU12', () => {
  let service: CatalogService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/catalog/products`;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(CatalogService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('sends every catalog filter without an authorization header', () => {
    service
      .listProducts({
        search: ' chaqueta ',
        seccion: 'UNISEX',
        idCategoria: 2,
        idTalla: 3,
        idColor: 4,
        precioMin: 20,
        precioMax: 200,
        enPromocion: true,
        idCiudad: 5,
        idSucursal: 6,
        sort: 'precio_asc',
        page: 2,
        pageSize: 12,
      })
      .subscribe();

    const request = http.expectOne((candidate) => candidate.url === url);
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.has('Authorization')).toBe(false);
    expect(request.request.params.get('search')).toBe('chaqueta');
    expect(request.request.params.get('seccion')).toBe('UNISEX');
    expect(request.request.params.get('id_categoria')).toBe('2');
    expect(request.request.params.get('id_talla')).toBe('3');
    expect(request.request.params.get('id_color')).toBe('4');
    expect(request.request.params.get('precio_min')).toBe('20');
    expect(request.request.params.get('precio_max')).toBe('200');
    expect(request.request.params.get('en_promocion')).toBe('true');
    expect(request.request.params.get('id_ciudad')).toBe('5');
    expect(request.request.params.get('id_sucursal')).toBe('6');
    expect(request.request.params.get('sort')).toBe('precio_asc');
    expect(request.request.params.get('page')).toBe('2');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 12, total: 0, total_pages: 0 },
    });
  });

  it('gets a public product detail contextualized by branch', () => {
    service.getProduct(7, 6).subscribe();
    const request = http.expectOne((candidate) => candidate.url === `${url}/7`);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('id_sucursal')).toBe('6');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({ success: true, data: {} });
  });
});
