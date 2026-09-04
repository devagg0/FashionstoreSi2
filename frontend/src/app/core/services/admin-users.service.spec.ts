import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminUsersService } from './admin-users.service';

describe('AdminUsersService', () => {
  let service: AdminUsersService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminUsersService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('lists users with filters, pagination and Bearer authentication', () => {
    service
      .listUsers({ search: 'ana', rol: 'CLIENTE', estado: true, page: 2, pageSize: 10 })
      .subscribe();

    const request = httpTesting.expectOne(
      (candidate) => candidate.url === `${environment.apiUrl}/api/admin/users`,
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(request.request.params.get('search')).toBe('ana');
    expect(request.request.params.get('rol')).toBe('CLIENTE');
    expect(request.request.params.get('estado')).toBe('true');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('10');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 10, total: 0, total_pages: 0 },
    });
  });

  it('connects detail, status, role and role-list endpoints', () => {
    service
      .createUser({
        nombre: 'Luis',
        apellido: 'Rojas',
        correo: 'luis@fashionstore.com',
        telefono: null,
        rol: 'CAJERO',
        password: 'Fashion@2026',
        confirm_password: 'Fashion@2026',
      })
      .subscribe();
    const create = httpTesting.expectOne(`${environment.apiUrl}/api/admin/users`);
    expect(create.request.method).toBe('POST');
    expect(create.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(create.request.body.rol).toBe('CAJERO');
    create.flush({ success: true, message: 'Usuario creado correctamente', data: adminUser });

    service.getUser(9).subscribe();
    const detail = httpTesting.expectOne(`${environment.apiUrl}/api/admin/users/9`);
    expect(detail.request.method).toBe('GET');
    detail.flush({ success: true, data: adminUser });

    service.updateStatus(9, false).subscribe();
    const status = httpTesting.expectOne(`${environment.apiUrl}/api/admin/users/9/status`);
    expect(status.request.method).toBe('PATCH');
    expect(status.request.body).toEqual({ estado: false });
    status.flush({ success: true, message: 'ok', data: { ...adminUser, estado: false } });

    service.updateRole(9, 'CLIENTE').subscribe();
    const role = httpTesting.expectOne(`${environment.apiUrl}/api/admin/users/9/role`);
    expect(role.request.method).toBe('PATCH');
    expect(role.request.body).toEqual({ rol: 'CLIENTE' });
    role.flush({ success: true, message: 'ok', data: adminUser });

    service.listRoles().subscribe();
    const roles = httpTesting.expectOne(`${environment.apiUrl}/api/admin/roles`);
    expect(roles.request.method).toBe('GET');
    expect(roles.request.headers.get('Authorization')).toBe('Bearer admin-token');
    roles.flush({ success: true, data: [] });
  });
});

const adminUser = {
  id_usuario: 9,
  nombre: 'Ana',
  apellido: 'Pérez',
  correo: 'ana@example.com',
  rol: 'CLIENTE',
  estado: true,
};
