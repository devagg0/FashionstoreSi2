import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AdminEmployeeBranches } from './admin-employee-branches';
import { environment } from '../../../../environments/environment';

const base = `${environment.apiUrl}/api/admin`;
const url = `${base}/employee-branches`;
const employee = { id_empleado: 3, id_usuario: 50, nombre: 'Ana', apellido: 'Pérez', correo: 'ana@example.com', rol: 'CAJERO', estado: true };
const branch = { id_sucursal: 7, nombre: 'Centro', estado: true };
const assignment = { id_empleado_sucursal: 9, id_empleado: 3, nombre_empleado: 'Ana Pérez', correo: 'ana@example.com', rol: 'CAJERO', id_sucursal: 7, nombre_sucursal: 'Centro', fecha_asignacion: '2026-01-01', estado: true };
const paged = (data: unknown[], page = 1, total_pages = 1, page_size = 100) => ({ success: true, data, pagination: { page, total_pages, page_size, total: data.length * total_pages } });

describe('AdminEmployeeBranches', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<AdminEmployeeBranches>;
  let page: AdminEmployeeBranches;
  const list = () => http.expectOne(r => r.url === url && r.method === 'GET');
  function options() {
    http.expectOne(r => r.url === `${url}/options/employees`).flush(paged([employee]));
    http.expectOne(r => r.url === `${base}/branches`).flush(paged([branch, { ...branch, id_sucursal: 8, nombre: 'Antigua', estado: false }]));
  }
  function start() { fixture.detectChanges(); options(); list().flush(paged([assignment], 1, 2, 10)); }
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminEmployeeBranches); page = fixture.componentInstance;
  });
  afterEach(() => { fixture.destroy(); http.verify(); });

  it('loads all employee and branch pages and shows only active branches for creation', () => {
    fixture.detectChanges();
    http.expectOne(r => r.url === `${url}/options/employees`).flush(paged([employee], 1, 2, 1));
    const second = http.expectOne(r => r.url === `${url}/options/employees`);
    expect(second.request.params.get('page')).toBe('2');
    second.flush(paged([{ ...employee, id_empleado: 4, id_usuario: 60, rol: 'ENCARGADO_SUCURSAL' }], 2, 2, 1));
    http.expectOne(r => r.url === `${base}/branches`).flush(paged([branch], 1, 2, 1));
    const branchPage = http.expectOne(r => r.url === `${base}/branches`);
    expect(branchPage.request.params.get('page')).toBe('2');
    branchPage.flush(paged([{ ...branch, id_sucursal: 8, estado: false }], 2, 2, 1));
    list().flush(paged([assignment]));
    expect(page['employees']().map(e => e.id_empleado)).toEqual([3, 4]);
    expect(page['branches']().length).toBe(2); expect(page['activeBranches']().length).toBe(1);
    expect(page['assignments']()).toEqual([assignment]);
    fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('Ana Pérez');
  });
  it('applies filters and pagination and resets filters', () => {
    start(); page['filters'].setValue({ id_empleado: 3, id_sucursal: 7, estado: 'false' }); page['loadAssignments']();
    let req = list(); expect(req.request.params.get('id_empleado')).toBe('3');
    expect(req.request.params.get('id_sucursal')).toBe('7'); expect(req.request.params.get('estado')).toBe('false');
    req.flush(paged([assignment], 1, 2, 10)); page['changePage'](1);
    req = list(); expect(req.request.params.get('page')).toBe('2'); req.flush(paged([assignment], 2, 2, 10));
    page['clearFilters'](); req = list(); expect(req.request.params.has('id_empleado')).toBe(false); req.flush(paged([]));
  });
  it.each([201, 200])('handles POST %s with the real employee ID and refreshes', status => {
    start(); page['openForm'](); options(); fixture.detectChanges();
    const select: HTMLSelectElement = fixture.nativeElement.querySelector('#assignment-employee');
    select.selectedIndex = 1; select.dispatchEvent(new Event('change'));
    page['form'].controls.id_sucursal.setValue(7); page['submit']();
    const req = http.expectOne(r => r.url === url && r.method === 'POST');
    expect(req.request.body).toEqual({ id_empleado: 3, id_sucursal: 7 });
    req.flush({ success: true, data: assignment, message: 'ok' }, { status, statusText: 'OK' });
    expect(page['successMessage']()).toContain(status === 201 ? 'creada' : 'reactivada');
    expect(page['formOpen']()).toBe(false); list().flush(paged([assignment]));
  });
  it('shows a controlled 409 and keeps the form', () => {
    start(); page['openForm'](); options(); page['form'].setValue({ id_empleado: 3, id_sucursal: 7 }); page['submit']();
    http.expectOne(r => r.url === url && r.method === 'POST').flush({ message: 'private' }, { status: 409, statusText: 'Conflict' });
    expect(page['modalError']()).toContain('ya se encuentra activa'); expect(page['modalError']()).not.toContain('private');
    expect(page['formOpen']()).toBe(true); expect(page['saving']()).toBe(false);
  });
  it.each([true, false])('requires confirmation before changing active=%s', estado => {
    start(); page['requestStatus']({ ...assignment, estado }); http.expectNone(`${url}/9/status`);
    page['confirmStatus'](); const req = http.expectOne(`${url}/9/status`);
    expect(req.request.method).toBe('PATCH'); expect(req.request.body).toEqual({ estado: !estado });
    req.flush({ success: true, data: { ...assignment, estado: !estado }, message: 'ok' });
    expect(page['statusAssignment']()).toBeNull(); list().flush(paged([assignment]));
  });
  it('shows historical detail using the assignment response', () => {
    start(); page['viewDetail'](9); http.expectOne(`${url}/9`).flush({ success: true, data: { ...assignment, nombre_sucursal: 'Antigua', estado: false } });
    fixture.detectChanges(); expect(page['detail']()?.nombre_sucursal).toBe('Antigua'); expect(fixture.nativeElement.textContent).toContain('ana@example.com');
  });
  it('handles API failure and allows option retry without submitting incomplete options', () => {
    fixture.detectChanges();
    http.expectOne(r => r.url === `${base}/branches`).flush(paged([]));
    http.expectOne(r => r.url === `${url}/options/employees`).flush({}, { status: 500, statusText: 'Error' });
    list().flush({}, { status: 500, statusText: 'Error' });
    expect(page['optionsError']()).toBeTruthy(); expect(page['errorMessage']()).toBeTruthy();
    page['loadOptions'](); options(); expect(page['optionsError']()).toBeNull();
  });
});
