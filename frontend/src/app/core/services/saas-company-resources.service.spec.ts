import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  AssociateExistingBranchRequest,
  AssociateUserRequest,
  CompanyBranchesListResponse,
  CompanyBranchResponse,
  CompanyResourcesResponse,
  CompanyUserResponse,
  CompanyUsersListResponse,
  CreateCompanyBranchRequest,
  SaasCompanyResourcesService,
} from './saas-company-resources.service';

describe('SaasCompanyResourcesService PK07 CU04', () => {
  let service: SaasCompanyResourcesService;
  let httpTesting: HttpTestingController;

  const mockUsersResponse: CompanyUsersListResponse = {
    success: true,
    total: 1,
    data: [
      {
        id_empresa: 2,
        id_usuario: 10,
        nombre: 'Carlos',
        apellido: 'Gomez',
        correo: 'carlos@example.com',
        telefono: '78901234',
        id_rol: 3,
        rol: 'CAJERO',
        estado: 'ACTIVO',
        es_propietario: false,
        created_at: '2026-10-30T12:00:00Z',
        updated_at: '2026-10-30T12:00:00Z',
      },
    ],
  };

  const mockBranchesResponse: CompanyBranchesListResponse = {
    success: true,
    total: 1,
    data: [
      {
        id_sucursal: 5,
        empresa_id: 2,
        id_ciudad: 1,
        ciudad_nombre: 'Santa Cruz',
        nombre: 'Sucursal Central',
        direccion: 'Av. San Martín #123',
        telefono: '78901234',
        hora_apertura: '08:30:00',
        hora_cierre: '20:00:00',
        estado: true,
        created_at: '2026-10-30T12:00:00Z',
        updated_at: '2026-10-30T12:00:00Z',
      },
    ],
  };

  const mockResourcesResponse: CompanyResourcesResponse = {
    success: true,
    data: {
      id_empresa: 2,
      empresa_nombre: 'Moda Oriente SRL',
      empresa_codigo: 'moda-oriente',
      usuarios: mockUsersResponse.data,
      sucursales: mockBranchesResponse.data,
    },
  };

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'superadmin-test-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SaasCompanyResourcesService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('1. gets company users with Bearer authentication and query filters', () => {
    service
      .getCompanyUsers(2, { role: 'CAJERO', estado: 'ACTIVO', search: 'Carlos' })
      .subscribe((res) => {
        expect(res.success).toBe(true);
        expect(res.data.length).toBe(1);
        expect(res.data[0].rol).toBe('CAJERO');
        expect(res.data[0].id_empresa).toBe(2);
      });

    const req = httpTesting.expectOne(
      (r) =>
        r.url === `${environment.apiUrl}/api/saas/empresas/2/usuarios` &&
        r.params.get('role') === 'CAJERO' &&
        r.params.get('estado') === 'ACTIVO' &&
        r.params.get('search') === 'Carlos',
    );
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-test-token');
    req.flush(mockUsersResponse);
  });

  it('2. gets company branches with state filter and Bearer header', () => {
    service.getCompanyBranches(2, { estado: true, search: 'Central' }).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.length).toBe(1);
      expect(res.data[0].nombre).toBe('Sucursal Central');
      expect(res.data[0].empresa_id).toBe(2);
    });

    const req = httpTesting.expectOne(
      (r) =>
        r.url === `${environment.apiUrl}/api/saas/empresas/2/sucursales` &&
        r.params.get('estado') === 'true' &&
        r.params.get('search') === 'Central',
    );
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer superadmin-test-token');
    req.flush(mockBranchesResponse);
  });

  it('3. gets consolidated company resources (users and branches)', () => {
    service.getCompanyResources(2).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.id_empresa).toBe(2);
      expect(res.data.empresa_nombre).toBe('Moda Oriente SRL');
      expect(res.data.usuarios.length).toBe(1);
      expect(res.data.sucursales.length).toBe(1);
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/asociaciones`);
    expect(req.request.method).toBe('GET');
    req.flush(mockResourcesResponse);
  });

  it('4. associates existing user with valid role and sends POST request', () => {
    const payload: AssociateUserRequest = {
      id_usuario: 10,
      rol: 'CAJERO',
      estado: 'ACTIVO',
      es_propietario: false,
    };

    const mockResponse: CompanyUserResponse = {
      success: true,
      message: 'Usuario asociado correctamente a la empresa',
      data: mockUsersResponse.data[0],
    };

    service.associateUser(2, payload).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.id_usuario).toBe(10);
      expect(res.data.rol).toBe('CAJERO');
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/usuarios`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    req.flush(mockResponse);
  });

  it('5. creates branch within company with exclusive ownership', () => {
    const payload: CreateCompanyBranchRequest = {
      id_ciudad: 1,
      nombre: 'Sucursal Norte',
      direccion: 'Av. Banzer Km 5',
      telefono: '78901234',
      hora_apertura: '08:30:00',
      hora_cierre: '20:00:00',
    };

    const mockResponse: CompanyBranchResponse = {
      success: true,
      message: 'Sucursal creada y asociada correctamente a la empresa',
      data: {
        ...mockBranchesResponse.data[0],
        id_sucursal: 8,
        nombre: 'Sucursal Norte',
      },
    };

    service.createBranch(2, payload).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.nombre).toBe('Sucursal Norte');
      expect(res.data.empresa_id).toBe(2);
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/sucursales`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    req.flush(mockResponse);
  });

  it('6. associates or reactivates existing branch for company', () => {
    const payload: AssociateExistingBranchRequest = { id_sucursal: 5 };
    const mockResponse: CompanyBranchResponse = {
      success: true,
      message: 'Sucursal asociada correctamente a la empresa',
      data: mockBranchesResponse.data[0],
    };

    service.associateExistingBranch(2, payload).subscribe((res) => {
      expect(res.success).toBe(true);
      expect(res.data.id_sucursal).toBe(5);
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/sucursales/asociar`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    req.flush(mockResponse);
  });

  it('7. handles 409 conflict when associating already associated user', () => {
    let errorStatus = 0;
    service
      .associateUser(2, { id_usuario: 10, rol: 'CAJERO' })
      .subscribe({
        error: (err) => (errorStatus = err.status),
      });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/usuarios`);
    req.flush(
      { success: false, message: 'El usuario ya se encuentra activamente asociado a esta empresa' },
      { status: 409, statusText: 'Conflict' },
    );
    expect(errorStatus).toBe(409);
  });

  it('8. handles 409 conflict when attempting to associate branch of another company', () => {
    let errorMessage = '';
    service.associateExistingBranch(2, { id_sucursal: 99 }).subscribe({
      error: (err) => (errorMessage = err.error?.message),
    });

    const req = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/2/sucursales/asociar`);
    req.flush(
      {
        success: false,
        message: 'La sucursal pertenece a otra empresa y no puede transferirse entre empresas',
      },
      { status: 409, statusText: 'Conflict' },
    );
    expect(errorMessage).toContain('pertenece a otra empresa');
  });
});

