import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminPromotionsService } from './admin-promotions.service';

const url = `${environment.apiUrl}/api/admin/promotions`;

describe('AdminPromotionsService CU11', () => {
  let service: AdminPromotionsService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminPromotionsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('lists with every filter, pagination and Bearer token', () => {
    service
      .listPromotions({
        search: ' denim ',
        estado: false,
        vigencia: 'PROGRAMADA',
        page: 2,
        pageSize: 10,
      })
      .subscribe();
    const request = http.expectOne((item) => item.url === url);
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(request.request.params.get('search')).toBe('denim');
    expect(request.request.params.get('estado')).toBe('false');
    expect(request.request.params.get('vigencia')).toBe('PROGRAMADA');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('10');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 10, total: 0, total_pages: 0 },
    });
  });

  it('creates, reads, edits and changes status without DELETE', () => {
    const fields = {
      nombre: 'Semana Denim',
      codigo: 'DENIM20',
      descripcion: null,
      tipo_descuento: 'PORCENTAJE' as const,
      valor: 20,
      fecha_inicio: '2026-09-08T14:00:00.000Z',
      fecha_fin: '2026-09-10T14:00:00.000Z',
      acumulable: false,
    };
    service.createPromotion(fields).subscribe();
    let request = http.expectOne(url);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(fields);
    request.flush({ success: true, message: 'ok', data: {} });

    service.getPromotion(7).subscribe();
    request = http.expectOne(`${url}/7`);
    expect(request.request.method).toBe('GET');
    request.flush({ success: true, data: {} });

    service.updatePromotion(7, { valor: 25 }).subscribe();
    request = http.expectOne(`${url}/7`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ valor: 25 });
    request.flush({ success: true, message: 'ok', data: {} });

    service.updateStatus(7, false).subscribe();
    request = http.expectOne(`${url}/7/status`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ estado: false });
    request.flush({ success: true, message: 'ok', data: {} });

    http.expectNone((item) => item.method === 'DELETE');
  });

  it('uses both product association endpoints', () => {
    service.listProducts(7).subscribe();
    let request = http.expectOne(`${url}/7/products`);
    expect(request.request.method).toBe('GET');
    request.flush({ success: true, data: [] });

    service.addProducts(7, [11, 12]).subscribe();
    request = http.expectOne(`${url}/7/products`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ id_productos: [11, 12] });
    request.flush({ success: true, message: 'ok', data: [] });
  });
});
