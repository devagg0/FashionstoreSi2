import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { CompanyCreateRequest, SaasCompaniesService } from './saas-companies.service';

describe('SaasCompaniesService PK07 CU01-CU02', () => {
  let service: SaasCompaniesService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'superadmin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SaasCompaniesService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('posts the exact CU01 payload with Bearer authentication', () => {
    service.createCompany(fields).subscribe((response) => {
      expect(response.data.id_empresa).toBe(8);
      expect(response.data.estado).toBe('ACTIVA');
    });

    const request = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(fields);
    expect(request.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    request.flush(successResponse, { status: 201, statusText: 'Created' });
  });

  it.each([401, 403, 409, 422])('propagates HTTP %s to the form', (status) => {
    let receivedStatus = 0;
    service.createCompany(fields).subscribe({ error: (error) => (receivedStatus = error.status) });

    httpTesting
      .expectOne(`${environment.apiUrl}/api/saas/empresas`)
      .flush({ success: false, message: 'Error controlado' }, { status, statusText: 'Error' });
    expect(receivedStatus).toBe(status);
  });

  it('lists companies with trimmed filters and backend pagination', () => {
    service
      .listCompanies({
        search: '  moda  ',
        estado: 'SUSPENDIDA',
        page: 2,
        pageSize: 15,
      })
      .subscribe();

    const request = httpTesting.expectOne(
      (candidate) => candidate.url === `${environment.apiUrl}/api/saas/empresas`,
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('search')).toBe('moda');
    expect(request.request.params.get('estado')).toBe('SUSPENDIDA');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('15');
    expect(request.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    request.flush({
      success: true,
      data: [successResponse.data],
      pagination: { page: 2, page_size: 15, total: 16, total_pages: 2 },
    });
  });

  it('connects detail, partial update and state endpoints without DELETE', () => {
    service.getCompany(8).subscribe();
    const detail = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/8`);
    expect(detail.request.method).toBe('GET');
    detail.flush({ success: true, data: successResponse.data });

    const updatePayload = { nombre: 'Moda Oriente', nit: null };
    service.updateCompany(8, updatePayload).subscribe();
    const update = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/8`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual(updatePayload);
    expect(update.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    update.flush({ success: true, message: 'ok', data: successResponse.data });

    service.updateCompanyState(8, 'CANCELADA').subscribe();
    const state = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/8/estado`);
    expect(state.request.method).toBe('PATCH');
    expect(state.request.body).toEqual({ estado: 'CANCELADA' });
    expect(state.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    state.flush({ success: true, message: 'ok', data: successResponse.data });
  });
});

const fields: CompanyCreateRequest = {
  codigo: 'moda-andina',
  nombre: 'Moda Andina SRL',
  nit: '123456789',
  zona_horaria: 'America/La_Paz',
};

const successResponse = {
  success: true as const,
  message: 'Empresa registrada correctamente',
  data: {
    id_empresa: 8,
    ...fields,
    estado: 'ACTIVA' as const,
    created_at: '2026-10-30T12:00:00Z',
    updated_at: '2026-10-30T12:00:00Z',
  },
};
