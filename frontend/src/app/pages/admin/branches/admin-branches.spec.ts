import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AdminBranches } from './admin-branches';
import { environment } from '../../../../environments/environment';

const url = `${environment.apiUrl}/api/admin`;
const branch = {
  id_sucursal: 3,
  id_ciudad: 1,
  nombre: 'Centro',
  direccion: 'Calle 1',
  telefono: null,
  hora_apertura: null,
  hora_cierre: null,
  estado: true,
  created_at: '2026-09-04T10:00:00',
  updated_at: '2026-09-04T10:00:00',
};

describe('AdminBranches city selection', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('reads every city page and retains the inactive association only when editing', () => {
    const fixture = TestBed.createComponent(AdminBranches);
    const page = fixture.componentInstance;
    fixture.detectChanges();
    for (const request of http.match(req => req.url === `${url}/branches` || req.url === `${url}/cities`)) {
      request.flush({ success: true, data: [], pagination: { page: 1, page_size: 100, total: 0, total_pages: 0 } });
    }
    page['openBranchModal'](branch);
    const first = http.expectOne((req) => req.url === `${url}/cities`);
    expect(first.request.params.get('page')).toBe('1');
    first.flush({
      success: true,
      data: [{ id_ciudad: 1, nombre: 'Antigua', estado: false }],
      pagination: { page: 1, page_size: 1, total: 2, total_pages: 2 },
    });
    const second = http.expectOne((req) => req.url === `${url}/cities`);
    expect(second.request.params.get('page')).toBe('2');
    expect(second.request.params.get('page_size')).toBe('1');
    second.flush({
      success: true,
      data: [{ id_ciudad: 2, nombre: 'Activa', estado: true }],
      pagination: { page: 2, page_size: 1, total: 2, total_pages: 2 },
    });
    expect(page['cityOptions']().length).toBe(2);
    expect(page['cityName'](1)).toBe('Antigua');
    expect(page['branchForm'].valid).toBe(true);
    page['submitBranch']();
    const update = http.expectOne(`${url}/branches/3`);
    expect(update.request.body).toEqual({
      id_ciudad: 1,
      nombre: 'Centro',
      direccion: 'Calle 1',
      telefono: null,
      hora_apertura: null,
      hora_cierre: null,
    });
    update.flush({ success: false }, { status: 422, statusText: 'Unprocessable Content' });
    expect(page['modalErrorMessage']()).toBeTruthy();
    fixture.detectChanges();
    const citySelect = () =>
      fixture.nativeElement.querySelector('#branch-city') as HTMLSelectElement;
    expect(citySelect().textContent).toContain('Antigua');
    expect(citySelect().textContent).toContain('Activa');
    page['closeBranchModal']();
    page['openBranchModal']();
    http
      .expectOne((req) => req.url === `${url}/cities`)
      .flush({
        success: true,
        data: [
          { id_ciudad: 1, nombre: 'Antigua', estado: false },
          { id_ciudad: 2, nombre: 'Activa', estado: true },
        ],
        pagination: { page: 1, page_size: 100, total: 2, total_pages: 1 },
      });
    fixture.detectChanges();
    expect(citySelect().textContent).not.toContain('Antigua');
    expect(citySelect().textContent).toContain('Activa');
    fixture.destroy();
  });

  it('requires city and nonblank name/address but permits empty optional fields', () => {
    const fixture = TestBed.createComponent(AdminBranches);
    const form = fixture.componentInstance['branchForm'];
    expect(form.invalid).toBe(true);
    form.patchValue({ id_ciudad: 2, nombre: 'Centro', direccion: 'Calle 1' });
    expect(form.valid).toBe(true);
    form.patchValue({ nombre: '   ' });
    expect(form.invalid).toBe(true);
    form.patchValue({ nombre: 'x'.repeat(151) });
    expect(form.invalid).toBe(true);
    form.patchValue({ nombre: 'Centro', direccion: 'x'.repeat(201) });
    expect(form.invalid).toBe(true);
    form.patchValue({ direccion: 'Calle 1', telefono: 'x'.repeat(31) });
    expect(form.invalid).toBe(true);
    fixture.destroy();
  });
});
