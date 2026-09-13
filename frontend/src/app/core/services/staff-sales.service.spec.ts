import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';
import { SaleRequest, StaffSalesService } from './staff-sales.service';

describe('StaffSalesService CU20', () => {
  let service: StaffSalesService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/staff/sales`;
  const payload: SaleRequest = {
    id_sucursal: 2,
    id_reserva: 4,
    items: [{ id_variante_producto: 8, cantidad: 1 }],
  };
  const key = 'ad057527-095e-4c01-bd9a-99af9de3e91c';
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    TestBed.inject(SessionService).saveAccessToken('cashier-token');
    service = TestBed.inject(StaffSalesService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    localStorage.clear();
  });
  it.each(['branches', 'quote', 'create', 'get'] as const)(
    '%s uses exact URL, verb, bearer, payload and headers',
    (operation) => {
      const calls: Record<string, () => Observable<unknown>> = {
        branches: () => service.getBranches(),
        quote: () => service.quoteSale(payload),
        create: () => service.createSale(payload, key),
        get: () => service.getSale(5),
      };
      calls[operation]().subscribe();
      const suffix = { branches: '/branches', quote: '/quote', create: '', get: '/5' }[operation];
      const request = http.expectOne(url + suffix);
      expect(request.request.method).toBe(['quote', 'create'].includes(operation) ? 'POST' : 'GET');
      expect(request.request.headers.get('Authorization')).toBe('Bearer cashier-token');
      expect(request.request.headers.get('Idempotency-Key')).toBe(
        operation === 'create' ? key : null,
      );
      expect(request.request.body).toEqual(
        ['quote', 'create'].includes(operation) ? payload : null,
      );
      request.flush({ success: true, data: {} });
    },
  );
  it('does not fabricate a bearer when logged out', () => {
    TestBed.inject(SessionService).logout();
    service.getBranches().subscribe();
    const request = http.expectOne(url + '/branches');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({ data: [] });
  });
});
