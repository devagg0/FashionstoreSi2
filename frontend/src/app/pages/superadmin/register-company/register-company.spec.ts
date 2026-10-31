import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { RegisterCompany } from './register-company';

describe('RegisterCompany PK07 CU01', () => {
  let httpTesting: HttpTestingController;
  let session: SessionService;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [RegisterCompany],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    httpTesting = TestBed.inject(HttpTestingController);
    session = TestBed.inject(SessionService);
    session.saveAccessToken('superadmin-token');
    session.saveUser({
      id_usuario: 1,
      nombre: 'Sara',
      apellido: 'Admin',
      correo: 'sara@example.com',
      rol: 'SUPERADMIN',
      id_empresa: null,
    });
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('shows validation messages and does not submit invalid fields', () => {
    const fixture = TestBed.createComponent(RegisterCompany);
    fixture.detectChanges();
    (fixture.componentInstance as any).submit();
    fixture.detectChanges();

    httpTesting.expectNone(`${environment.apiUrl}/api/saas/empresas`);
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'Revisa los campos',
    );
    expect((fixture.componentInstance as any).companyForm.controls.codigo.touched).toBe(true);
  });

  it('normalizes fields, prevents duplicate submits and renders the created company', () => {
    const fixture = TestBed.createComponent(RegisterCompany);
    const component = fixture.componentInstance as any;
    fixture.detectChanges();
    component.companyForm.setValue({
      codigo: '  MODA-ANDINA  ',
      nombre: '  Moda Andina SRL  ',
      nit: ' 123456789 ',
      zona_horaria: 'America/La_Paz',
    });

    component.submit();
    component.submit();

    const requests = httpTesting.match(`${environment.apiUrl}/api/saas/empresas`);
    expect(requests).toHaveLength(1);
    expect(requests[0].request.body).toEqual({
      codigo: 'moda-andina',
      nombre: 'Moda Andina SRL',
      nit: '123456789',
      zona_horaria: 'America/La_Paz',
    });
    requests[0].flush(successResponse, { status: 201, statusText: 'Created' });
    fixture.detectChanges();

    expect(component.companyForm.disabled).toBe(true);
    expect(fixture.nativeElement.querySelector('.success-panel').textContent).toContain(
      'Moda Andina SRL',
    );
    expect(fixture.nativeElement.querySelector('.success-panel').textContent).toContain('ACTIVA');
  });

  it('shows the backend duplicate conflict and keeps the form available', () => {
    const fixture = TestBed.createComponent(RegisterCompany);
    const component = fixture.componentInstance as any;
    fixture.detectChanges();
    component.companyForm.setValue(validForm);
    component.submit();

    httpTesting
      .expectOne(`${environment.apiUrl}/api/saas/empresas`)
      .flush(
        { success: false, message: 'El NIT ya pertenece a otra empresa' },
        { status: 409, statusText: 'Conflict' },
      );
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'El NIT ya pertenece a otra empresa',
    );
    expect(component.companyForm.enabled).toBe(true);
  });

  it('clears the local session and returns to login after HTTP 401', async () => {
    const fixture = TestBed.createComponent(RegisterCompany);
    const component = fixture.componentInstance as any;
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    component.companyForm.setValue(validForm);
    component.submit();

    httpTesting
      .expectOne(`${environment.apiUrl}/api/saas/empresas`)
      .flush({ success: false, message: 'Token expirado' }, { status: 401, statusText: 'Unauthorized' });

    expect(session.getAccessToken()).toBeNull();
    expect(session.getUser()).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login', expect.any(Object));
  });
});

const validForm = {
  codigo: 'moda-andina',
  nombre: 'Moda Andina SRL',
  nit: '',
  zona_horaria: 'America/La_Paz',
};

const successResponse = {
  success: true,
  message: 'Empresa registrada correctamente',
  data: {
    id_empresa: 8,
    codigo: 'moda-andina',
    nombre: 'Moda Andina SRL',
    nit: '123456789',
    zona_horaria: 'America/La_Paz',
    estado: 'ACTIVA',
    created_at: '2026-10-30T12:00:00Z',
    updated_at: '2026-10-30T12:00:00Z',
  },
};
