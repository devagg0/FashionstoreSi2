import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { ManageCompanies } from './manage-companies';

describe('ManageCompanies PK07 CU02', () => {
  let httpTesting: HttpTestingController;
  let session: SessionService;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [ManageCompanies],
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

  function createPage(): { fixture: ComponentFixture<ManageCompanies>; page: any } {
    const fixture = TestBed.createComponent(ManageCompanies);
    fixture.detectChanges();
    return { fixture, page: fixture.componentInstance as any };
  }

  function expectList(page = 1, data = [company], totalPages = 2): void {
    const request = httpTesting.expectOne(
      (candidate) =>
        candidate.url === `${environment.apiUrl}/api/saas/empresas` &&
        candidate.params.get('page') === String(page),
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('page_size')).toBe('10');
    expect(request.request.headers.get('Authorization')).toBe('Bearer superadmin-token');
    request.flush({
      success: true,
      data,
      pagination: { page, page_size: 10, total: data.length ? 11 : 0, total_pages: totalPages },
    });
  }

  it('loads and renders a responsive company table with empty-state support', () => {
    const { fixture } = createPage();
    expectList();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('tbody').textContent).toContain('Moda Andina');
    expect(fixture.nativeElement.querySelector('.status').textContent).toContain('ACTIVA');

    (fixture.componentInstance as any).loadCompanies(1);
    expectList(1, [], 0);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.empty-state').textContent).toContain(
      'No encontramos empresas',
    );
  });

  it('applies search/state filters and preserves them when paginating', () => {
    const { page } = createPage();
    expectList();
    page.filtersForm.setValue({ search: '  moda  ', estado: 'SUSPENDIDA' });
    page.applyFilters();

    const filtered = httpTesting.expectOne(
      (request) =>
        request.url.endsWith('/api/saas/empresas') &&
        request.params.get('search') === 'moda' &&
        request.params.get('estado') === 'SUSPENDIDA' &&
        request.params.get('page') === '1',
    );
    filtered.flush({
      success: true,
      data: [{ ...company, estado: 'SUSPENDIDA' }],
      pagination: { page: 1, page_size: 10, total: 11, total_pages: 2 },
    });
    page.nextPage();
    const secondPage = httpTesting.expectOne(
      (request) => request.params.get('page') === '2' && request.params.get('search') === 'moda',
    );
    secondPage.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 10, total: 11, total_pages: 2 },
    });
  });

  it('loads company detail from the real detail endpoint', () => {
    const { fixture, page } = createPage();
    expectList();
    page.openDetails(company);
    const detail = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/8`);
    expect(detail.request.method).toBe('GET');
    detail.flush({ success: true, data: company });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="dialog"]').textContent).toContain(
      'America/La_Paz',
    );
  });

  it('validates, normalizes and saves edits before refreshing the list', () => {
    const { page } = createPage();
    expectList();
    page.openEdit(company);
    page.editForm.setValue({
      codigo: '  MODA-ORIENTE  ',
      nombre: '  Moda Oriente  ',
      nit: ' 99887766 ',
      zona_horaria: 'America/La_Paz',
    });
    page.saveEdit();

    const update = httpTesting.expectOne(`${environment.apiUrl}/api/saas/empresas/8`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({
      codigo: 'moda-oriente',
      nombre: 'Moda Oriente',
      nit: '99887766',
      zona_horaria: 'America/La_Paz',
    });
    update.flush({ success: true, message: 'ok', data: { ...company, nombre: 'Moda Oriente' } });
    expectList();
    expect(page.successMessage()).toContain('actualizada');
  });

  it('confirms state changes, prevents duplicate submits and refreshes automatically', () => {
    const { page } = createPage();
    expectList();
    page.openStateDialog(company, 'SUSPENDIDA');
    page.confirmStateChange();
    page.confirmStateChange();

    const requests = httpTesting.match(`${environment.apiUrl}/api/saas/empresas/8/estado`);
    expect(requests).toHaveLength(1);
    expect(requests[0].request.method).toBe('PATCH');
    expect(requests[0].request.body).toEqual({ estado: 'SUSPENDIDA' });
    requests[0].flush({
      success: true,
      message: 'ok',
      data: { ...company, estado: 'SUSPENDIDA' },
    });
    expectList();
    expect(page.modal()).toBeNull();
  });

  it('shows backend conflicts and keeps the edit dialog available', () => {
    const { fixture, page } = createPage();
    expectList();
    page.openEdit(company);
    page.saveEdit();
    httpTesting
      .expectOne(`${environment.apiUrl}/api/saas/empresas/8`)
      .flush(
        { success: false, message: 'El código de empresa ya existe' },
        { status: 409, statusText: 'Conflict' },
      );
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'El código de empresa ya existe',
    );
    expect(page.modal()).toBe('edit');
  });

  it('clears the session and navigates to login on HTTP 401', () => {
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    createPage();
    httpTesting
      .expectOne((request) => request.url.endsWith('/api/saas/empresas'))
      .flush({ success: false, message: 'Token expirado' }, { status: 401, statusText: 'Unauthorized' });
    expect(session.getAccessToken()).toBeNull();
    expect(session.getUser()).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login', expect.any(Object));
  });
});

const company = {
  id_empresa: 8,
  codigo: 'moda-andina',
  nombre: 'Moda Andina SRL',
  nit: '123456789',
  zona_horaria: 'America/La_Paz',
  estado: 'ACTIVA' as const,
  created_at: '2026-10-30T12:00:00Z',
  updated_at: '2026-10-30T12:00:00Z',
};
