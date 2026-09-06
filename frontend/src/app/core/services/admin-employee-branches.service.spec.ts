import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminEmployeeBranchesService } from './admin-employee-branches.service';

describe('AdminEmployeeBranchesService', () => {
  let api: AdminEmployeeBranchesService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/admin/employee-branches`;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(AdminEmployeeBranchesService); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });
  it('sends filters, pagination and the existing Bearer token', () => {
    api.listAssignments({ id_empleado: 3, id_sucursal: 7, estado: false, page: 2, pageSize: 10 }).subscribe();
    const req = http.expectOne(r => r.url === url);
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(req.request.params.get('id_empleado')).toBe('3');
    expect(req.request.params.get('id_sucursal')).toBe('7');
    expect(req.request.params.get('estado')).toBe('false');
    expect(req.request.params.get('page')).toBe('2');
    expect(req.request.params.get('page_size')).toBe('10'); req.flush({});
  });
  it('uses employee options and detail endpoints', () => {
    api.listEmployees(2, 100).subscribe();
    const options = http.expectOne(r => r.url === `${url}/options/employees`);
    expect(options.request.params.get('page')).toBe('2');
    expect(options.request.params.get('page_size')).toBe('100'); options.flush({});
    api.getAssignment(9).subscribe();
    const detail = http.expectOne(`${url}/9`); expect(detail.request.method).toBe('GET'); detail.flush({});
  });
  it.each([201, 200])('accepts POST %s and preserves real IDs', status => {
    let result = 0;
    api.createAssignment({ id_empleado: 3, id_sucursal: 7 }).subscribe(r => result = r.status);
    const req = http.expectOne(url);
    expect(req.request.body).toEqual({ id_empleado: 3, id_sucursal: 7 });
    expect(req.request.method).toBe('POST'); req.flush({}, { status, statusText: 'OK' }); expect(result).toBe(status);
  });
  it.each([false, true])('changes only assignment status to %s', estado => {
    api.updateStatus(9, estado).subscribe();
    const req = http.expectOne(`${url}/9/status`);
    expect(req.request.method).toBe('PATCH'); expect(req.request.body).toEqual({ estado }); req.flush({});
  });
  it.each([401, 403, 404, 409, 422, 500])('propagates HTTP %s', status => {
    let received = 0;
    api.getAssignment(9).subscribe({ error: e => received = e.status });
    http.expectOne(`${url}/9`).flush({}, { status, statusText: 'Error' }); expect(received).toBe(status);
  });
});
