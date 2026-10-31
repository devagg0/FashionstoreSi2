import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  AssignCompanyAdminRequest,
  AssignCompanyAdminResponse,
  AvailableUsersResponse,
  CompanyAdminResponse,
  CreateAndAssignCompanyAdminRequest,
  SaasCompanyAdminService,
} from './saas-company-admin.service';

describe('SaasCompanyAdminService PK07 CU03', () => {
  let service: SaasCompanyAdminService;
  let httpTesting: HttpTestingController;

  const mockAdminResponse: CompanyAdminResponse = {
    success: true,
    message: 'Administrador consultado correctamente',
    data: {
      id_empresa: 2,
      id_usuario: 10,
      nombre: 'Carlos',
      apellido: 'Gomez',
      correo: 'carlos@example.com',
      telefono: '78901234',
      rol: 'ADMINISTRADOR',
      estado: 'ACTIVO',
      es_propietario: true,
      created_at: '2026-10-30T12:00:00Z',
      updated_at: '2026-10-30T12:00:00Z',
    },
  };

  const mockAvailableUsersResponse: AvailableUsersResponse = {
    success: true,
    message: 'Usuarios disponibles obtenidos correctamente',
    data: [
      {
        id_usuario: 10,
        nombre: 'Carlos',
        apellido: 'Gomez',
        correo: 'carlos@example.com',
        telefono: '78901234',
        rol_global: 'ADMINISTRADOR',
        estado: true,
        created_at: '2026-10-30T12:00:00Z',
      },
    ],
    pagination: {
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
    },
  };

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'superadmin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SaasCompanyAdminService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('gets company admin with Bearer authentication', () => {
    service.getCompanyAdmin(2).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.id_usuario).toBe(10);
      expect(res.data.rol).toBe('ADMINISTRADOR');
      expect(res.data.es_propietario).toBe(true);
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/administrador`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    req.flush(mockAdminResponse);
  });

  it('handles 404 when company has no assigned administrator', () => {
    let errorStatus = 0;
    service.getCompanyAdmin(2).subscribe({
      error: (err) => (errorStatus = err.status),
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/administrador`);
    req.flush(
      { success: false, message: 'La empresa no tiene un administrador asignado' },
      { status: 404, statusText: 'Not Found' },
    );
    expect(errorStatus).toBe(404);
  });

  it('lists available users with search query, empresa_id filter and pagination', () => {
    service
      .getAvailableUsers({ search: '  carlos  ', empresaId: 2, page: 2, pageSize: 5 })
      .subscribe((res) => {
        expect(res.success).toBe(true);
        expect(res.data.length).toBe(1);
        expect(res.data[0].rol_global).toBe('ADMINISTRADOR');
        expect(res.pagination.page).toBe(1);
      });

    const req = httpTesting.expectOne(
      (r) => r.url === `${environment.apiUrl}/api/saas/usuarios-disponibles`,
    );
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('search')).toBe('carlos');
    expect(req.request.params.get('empresa_id')).toBe('2');
    expect(req.request.params.get('page')).toBe('2');
    expect(req.request.params.get('page_size')).toBe('5');
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    req.flush(mockAvailableUsersResponse);
  });

  it('assigns company admin with POST and validates payload', () => {
    const payload: AssignCompanyAdminRequest = {
      id_usuario: 10,
      estado: 'ACTIVO',
    };

    const expectedResponse: AssignCompanyAdminResponse = {
      success: true,
      message: 'Administrador asignado correctamente',
      data: mockAdminResponse.data,
    };

    service.assignCompanyAdmin(2, payload).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.id_usuario).toBe(10);
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/administrador`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    req.flush(expectedResponse, { status: 201, statusText: 'Created' });
  });

  it('creates and assigns new company admin with POST /api/saas/empresas/{id}/administrador/nuevo', () => {
    const createPayload: CreateAndAssignCompanyAdminRequest = {
      nombre: 'Nuevo',
      apellido: 'Admin',
      correo: 'nuevo.admin@fs.com',
      password: 'SecurePassword123!',
      telefono: '71234567',
      estado: 'ACTIVO',
    };

    const expectedResponse: AssignCompanyAdminResponse = {
      success: true,
      message: 'Administrador creado y asignado exitosamente',
      data: {
        ...mockAdminResponse.data,
        id_usuario: 88,
        nombre: 'Nuevo',
        apellido: 'Admin',
        correo: 'nuevo.admin@fs.com',
      },
    };

    service.createAndAssignCompanyAdmin(2, createPayload).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.id_usuario).toBe(88);
      expect(res.data.correo).toBe('nuevo.admin@fs.com');
    });

    const req = httpTesting.expectOne(
      `${environment.apiUrl}/api/saas/empresas/2/administrador/nuevo`,
    );
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(createPayload);
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    req.flush(expectedResponse, { status: 201, statusText: 'Created' });
  });

  it.each([401, 403, 404, 409, 422])('propagates error status %s correctly', (status) => {
    let receivedStatus = 0;
    service.assignCompanyAdmin(2, { id_usuario: 10 }).subscribe({
      error: (err) => (receivedStatus = err.status),
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/administrador`);
    req.flush({ success: false, message: 'Controlled error' }, { status, statusText: 'Error' });
    expect(receivedStatus).toBe(status);
  });
});
