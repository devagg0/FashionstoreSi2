import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { SaasCompaniesService, SaasCompany } from '../../../core/services/saas-companies.service';
import {
  AvailableUserData,
  CompanyAdminData,
  SaasCompanyAdminService,
} from '../../../core/services/saas-company-admin.service';
import { SessionService } from '../../../core/services/session.service';
import { AssignCompanyAdmin } from './assign-company-admin';

describe('AssignCompanyAdmin PK07 CU03 Component', () => {
  let fixture: ComponentFixture<AssignCompanyAdmin>;
  let component: AssignCompanyAdmin;
  let companiesService: any;
  let adminService: any;
  let sessionService: any;

  const mockCompany: SaasCompany = {
    id_empresa: 2,
    codigo: 'moda-andina',
    nombre: 'Moda Andina SRL',
    nit: '1020304050',
    zona_horaria: 'America/La_Paz',
    estado: 'ACTIVA',
    created_at: '2026-10-30T12:00:00Z',
    updated_at: '2026-10-30T12:00:00Z',
  };

  const mockAdmin: CompanyAdminData = {
    id_empresa: 2,
    id_usuario: 5,
    nombre: 'Admin',
    apellido: 'Actual',
    correo: 'actual@empresa.com',
    telefono: '70000000',
    rol: 'ADMINISTRADOR',
    estado: 'ACTIVO',
    es_propietario: true,
    created_at: '2026-10-30T12:00:00Z',
    updated_at: '2026-10-30T12:00:00Z',
  };

  const mockUser: AvailableUserData = {
    id_usuario: 10,
    nombre: 'Carlos',
    apellido: 'Gomez',
    correo: 'carlos@empresa.com',
    telefono: '78901234',
    rol_global: 'ADMINISTRADOR',
    estado: true,
    created_at: '2026-10-30T12:00:00Z',
  };

  beforeEach(async () => {
    companiesService = {
      listCompanies: vi.fn().mockReturnValue(
        of({
          success: true,
          data: [mockCompany],
          pagination: { page: 1, page_size: 100, total: 1, total_pages: 1 },
        }),
      ),
    };

    adminService = {
      getCompanyAdmin: vi.fn().mockReturnValue(
        of({
          success: true,
          message: 'OK',
          data: mockAdmin,
        }),
      ),
      getAvailableUsers: vi.fn().mockReturnValue(
        of({
          success: true,
          message: 'OK',
          data: [mockUser],
          pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 },
        }),
      ),
      assignCompanyAdmin: vi.fn().mockReturnValue(
        of({
          success: true,
          message: 'Asignado',
          data: { ...mockAdmin, id_usuario: mockUser.id_usuario, nombre: mockUser.nombre },
        }),
      ),
      createAndAssignCompanyAdmin: vi.fn().mockReturnValue(
        of({
          success: true,
          message: 'Creado y asignado',
          data: {
            ...mockAdmin,
            id_usuario: 99,
            nombre: 'Roberto',
            apellido: 'Morales',
            correo: 'roberto@empresa.com',
          },
        }),
      ),
    };

    sessionService = {
      logout: vi.fn(),
      getAccessToken: vi.fn().mockReturnValue('fake-token'),
    };

    await TestBed.configureTestingModule({
      imports: [AssignCompanyAdmin],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: SaasCompaniesService, useValue: companiesService },
        { provide: SaasCompanyAdminService, useValue: adminService },
        { provide: SessionService, useValue: sessionService },
        {
          provide: ActivatedRoute,
          useValue: {
            queryParamMap: of(new Map([['empresa', '2']])),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AssignCompanyAdmin);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('initializes and selects company from query params and loads current admin', () => {
    expect(companiesService.listCompanies).toHaveBeenCalledWith({ estado: 'ACTIVA', pageSize: 100 });
    expect(adminService.getAvailableUsers).toHaveBeenCalledWith({
      search: undefined,
      empresaId: 2,
      page: 1,
      pageSize: 10,
    });
    expect(adminService.getCompanyAdmin).toHaveBeenCalledWith(2);

    expect(component['selectedCompanyId']()).toBe(2);
    expect(component['currentAdmin']()).toEqual(mockAdmin);
    expect(component['currentAdminNotFound']()).toBe(false);
  });

  it('handles 404 when company has no administrator assigned', () => {
    adminService.getCompanyAdmin.mockReturnValue(
      throwError(() => ({ status: 404, error: { message: 'Sin admin' } })),
    );

    component['loadCurrentAdmin'](2);

    expect(component['currentAdmin']()).toBeNull();
    expect(component['currentAdminNotFound']()).toBe(true);
  });

  it('searches available users with query and resets search', () => {
    component['searchForm'].controls.search.setValue('carlos');
    component['submitSearch']();

    expect(adminService.getAvailableUsers).toHaveBeenCalledWith({
      search: 'carlos',
      empresaId: 2,
      page: 1,
      pageSize: 10,
    });

    component['resetSearch']();
    expect(component['searchForm'].controls.search.value).toBe('');
    expect(component['activeSearch']()).toBe('');
  });

  it('opens confirmation modal with user and allows closing', () => {
    component['openAssignModal'](mockUser);

    expect(component['modalOpen']()).toBe(true);
    expect(component['userToAssign']()).toEqual(mockUser);
    expect(component['membershipStateControl'].value).toBe('ACTIVO');

    component['closeModal']();
    expect(component['modalOpen']()).toBe(false);
    expect(component['userToAssign']()).toBeNull();
  });

  it('prevents opening modal if user is already the current admin', () => {
    const existingAdminUser: AvailableUserData = {
      ...mockUser,
      id_usuario: mockAdmin.id_usuario,
    };

    component['openAssignModal'](existingAdminUser);
    expect(component['modalOpen']()).toBe(false);
    expect(component['feedbackError']()).toContain('ya es el administrador asignado');
  });

  it('confirms assignment successfully, closes modal, and refreshes admin', () => {
    component['openAssignModal'](mockUser);
    component['confirmAssignment']();

    expect(adminService.assignCompanyAdmin).toHaveBeenCalledWith(2, {
      id_usuario: mockUser.id_usuario,
      estado: 'ACTIVO',
    });

    expect(component['modalOpen']()).toBe(false);
    expect(component['currentAdmin']()?.id_usuario).toBe(mockUser.id_usuario);
    expect(component['feedbackSuccess']()).toContain('Administrador asignado correctamente');
  });

  it('handles assignment error inside modal when user is already administrator of another company', () => {
    adminService.assignCompanyAdmin.mockReturnValue(
      throwError(() => ({
        status: 409,
        error: {
          message:
            'El usuario ya es administrador principal de otra empresa. Cada administrador solo puede estar a cargo de una única empresa',
        },
      })),
    );

    component['openAssignModal'](mockUser);
    component['confirmAssignment']();

    expect(component['modalOpen']()).toBe(true);
    expect(component['modalError']()).toContain('ya es administrador principal de otra empresa');
    expect(component['isSubmitting']()).toBe(false);
  });

  // --- Pruebas de Creación de nuevo administrador ---
  it('opens create admin modal and resets form defaults', () => {
    component['openCreateModal']();

    expect(component['createModalOpen']()).toBe(true);
    expect(component['showPassword']()).toBe(false);
    expect(component['createModalError']()).toBeNull();
    expect(component['createAdminForm'].controls.estado.value).toBe('ACTIVO');

    component['closeCreateModal']();
    expect(component['createModalOpen']()).toBe(false);
  });

  it('blocks opening create modal when no company is selected', () => {
    component['selectedCompanyId'].set(null);
    component['openCreateModal']();

    expect(component['createModalOpen']()).toBe(false);
    expect(component['feedbackError']()).toContain('selecciona una empresa activa');
  });

  it('toggles password visibility', () => {
    expect(component['showPassword']()).toBe(false);
    component['toggleShowPassword']();
    expect(component['showPassword']()).toBe(true);
    component['toggleShowPassword']();
    expect(component['showPassword']()).toBe(false);
  });

  it('validates create admin form fields and strong password', () => {
    const form = component['createAdminForm'];
    expect(form.valid).toBe(false);

    form.setValue({
      nombre: 'A', // too short
      apellido: 'Morales',
      correo: 'invalid-email',
      password: 'weak',
      telefono: '123',
      estado: 'ACTIVO',
    });
    expect(form.valid).toBe(false);
    expect(form.controls.nombre.invalid).toBe(true);
    expect(form.controls.correo.invalid).toBe(true);
    expect(form.controls.password.invalid).toBe(true);

    // Contraseña válida
    form.setValue({
      nombre: 'Roberto',
      apellido: 'Morales',
      correo: 'roberto@fashionstore.com',
      password: 'StrongPassword2026!',
      telefono: '+591 70012345',
      estado: 'ACTIVO',
    });
    expect(form.valid).toBe(true);
  });

  it('creates and assigns new admin successfully and updates admin card', () => {
    component['openCreateModal']();
    component['createAdminForm'].setValue({
      nombre: 'Roberto',
      apellido: 'Morales',
      correo: 'roberto@empresa.com',
      password: 'StrongPassword2026!',
      telefono: '70012345',
      estado: 'ACTIVO',
    });

    component['submitCreateAdmin']();

    expect(adminService.createAndAssignCompanyAdmin).toHaveBeenCalledWith(2, {
      nombre: 'Roberto',
      apellido: 'Morales',
      correo: 'roberto@empresa.com',
      password: 'StrongPassword2026!',
      telefono: '70012345',
      estado: 'ACTIVO',
    });

    expect(component['createModalOpen']()).toBe(false);
    expect(component['currentAdmin']()?.id_usuario).toBe(99);
    expect(component['currentAdmin']()?.nombre).toBe('Roberto');
    expect(component['feedbackSuccess']()).toContain('creado y asignado exitosamente');
  });

  it('handles duplicate email or conflict in create admin modal', () => {
    adminService.createAndAssignCompanyAdmin.mockReturnValue(
      throwError(() => ({
        status: 409,
        error: { message: 'El correo electrónico ya se encuentra registrado' },
      })),
    );

    component['openCreateModal']();
    component['createAdminForm'].setValue({
      nombre: 'Roberto',
      apellido: 'Morales',
      correo: 'repetido@empresa.com',
      password: 'StrongPassword2026!',
      telefono: '',
      estado: 'ACTIVO',
    });

    component['submitCreateAdmin']();

    expect(component['createModalOpen']()).toBe(true);
    expect(component['createModalError']()).toBe('El correo electrónico ya se encuentra registrado');
    expect(component['isSubmitting']()).toBe(false);
  });
});
