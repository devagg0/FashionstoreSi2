import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { ClientCheckoutService } from './client-checkout.service';
import { SessionService } from './session.service';

describe('ClientCheckoutService CU21', () => {
  let service: ClientCheckoutService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ClientCheckoutService); http = TestBed.inject(HttpTestingController);
    TestBed.inject(SessionService).saveAccessToken('client-token');
  });
  afterEach(() => { http.verify(); localStorage.clear(); sessionStorage.clear(); });
  it('posts only cart/branch IDs with the current Bearer token', () => {
    service.confirm(9, 2).subscribe();
    const req = http.expectOne(`${environment.apiUrl}/api/client/cart/checkout`);
    expect(req.request.method).toBe('POST'); expect(req.request.body).toEqual({ id_carrito: 9, id_sucursal: 2 });
    expect(req.request.headers.get('Authorization')).toBe('Bearer client-token'); req.flush({});
  });
  it('gets the pending sale with renewed authentication', () => {
    TestBed.inject(SessionService).saveAccessToken('renewed'); service.getPendingSale(31).subscribe();
    const req = http.expectOne(`${environment.apiUrl}/api/client/sales/31`);
    expect(req.request.method).toBe('GET'); expect(req.request.headers.get('Authorization')).toBe('Bearer renewed'); req.flush({});
  });
  it('isolates presentation metadata by authenticated user and tolerates corrupt storage', () => {
    const session = TestBed.inject(SessionService);
    session.saveUser({ id_usuario: 1, nombre: 'Ana', apellido: 'Pérez', correo: 'ana@example.com', rol: 'CLIENTE' });
    const metadata = { id_sucursal: 2, sucursal: 'Centro', items: [] };
    service.savePresentation(31, metadata); expect(service.presentation(31)).toEqual(metadata);
    session.saveUser({ id_usuario: 2, nombre: 'Luis', apellido: 'Pérez', correo: 'luis@example.com', rol: 'CLIENTE' });
    expect(service.presentation(31)).toBeNull();
    sessionStorage.setItem('fashionstore_checkout_2_31', '{invalid'); expect(service.presentation(31)).toBeNull();
  });
});
