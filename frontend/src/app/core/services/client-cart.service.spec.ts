import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { ClientCartService } from './client-cart.service';

describe('ClientCartService CU19', () => {
  let service: ClientCartService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/client/cart`;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ClientCartService); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });
  const cases = [
    { name: 'GET cart', method: 'GET', path: '', body: null, call: (s: ClientCartService) => s.getCart() },
    { name: 'POST variant', method: 'POST', path: '/items', body: { id_variante_producto: 15, cantidad: 2 }, call: (s: ClientCartService) => s.addItem(15, 2) },
    { name: 'PATCH final quantity', method: 'PATCH', path: '/items/15', body: { cantidad: 5 }, call: (s: ClientCartService) => s.updateQuantity(15, 5) },
    { name: 'DELETE variant', method: 'DELETE', path: '/items/15', body: null, call: (s: ClientCartService) => s.removeItem(15) },
    { name: 'DELETE all', method: 'DELETE', path: '/items', body: null, call: (s: ClientCartService) => s.clearCart() },
  ];
  for (const test of cases) {
    it(`${test.name}: exact URL, method, body, Bearer and response`, () => {
      const response = { success: true, data: { items: [], total: '0.00' }, message: 'OK' };
      const received = vi.fn(); test.call(service).subscribe(received);
      const req = http.expectOne(`${url}${test.path}`);
      expect(req.request.method).toBe(test.method);
      expect(req.request.body).toEqual(test.body);
      expect(req.request.headers.get('Authorization')).toBe('Bearer client-token');
      req.flush(response); expect(received).toHaveBeenCalledWith(response);
    });
  }
  it('reads the current JWT for every request', () => {
    localStorage.setItem('fashionstore_access_token', 'renewed');
    service.getCart().subscribe();
    const req = http.expectOne(url);
    expect(req.request.headers.get('Authorization')).toBe('Bearer renewed'); req.flush({});
  });
});
