import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminCitiesService } from './admin-cities.service';

describe('AdminCitiesService', () => {
  let service: AdminCitiesService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminCitiesService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('lists real cities with filters, pagination and Bearer authentication', () => {
    service.listCities({ search: 'santa', estado: true, page: 2, pageSize: 10 }).subscribe();

    const request = httpTesting.expectOne(
      (candidate) => candidate.url === `${environment.apiUrl}/api/admin/cities`,
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
    service.getCity(4).subscribe();
    const detail = httpTesting.expectOne(`${environment.apiUrl}/api/admin/cities/4`);
    expect(detail.request.method).toBe('GET');
    expect(detail.request.headers.get('Authorization')).toBe('Bearer admin-token');
    detail.flush({ success: true, data: city });

    service.createCity('  Tarija  ').subscribe();
    const create = httpTesting.expectOne(`${environment.apiUrl}/api/admin/cities`);
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual({ nombre: 'Tarija' });
    create.flush({ success: true, message: 'ok', data: city });

    service.updateCity(4, '  Cercado  ').subscribe();
    const update = httpTesting.expectOne(`${environment.apiUrl}/api/admin/cities/4`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ nombre: 'Cercado' });
    update.flush({ success: true, message: 'ok', data: { ...city, nombre: 'Cercado' } });

    service.updateStatus(4, false).subscribe();
    const status = httpTesting.expectOne(`${environment.apiUrl}/api/admin/cities/4/status`);
    expect(status.request.method).toBe('PATCH');
    expect(status.request.body).toEqual({ estado: false });
    status.flush({ success: true, message: 'ok', data: { ...city, estado: false } });
  });
});

const city = {
  id_ciudad: 4,
  nombre: 'Tarija',
  estado: true,
};
