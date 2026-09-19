import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  ClientRecommendationsService,
  recommendationErrorMessage,
} from './client-recommendations.service';

describe('ClientRecommendationsService CU26', () => {
  let service: ClientRecommendationsService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/client/recommendations`;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ClientRecommendationsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('sends GET with the default limit and the session Bearer', () => {
    const received = vi.fn();
    service.list().subscribe(received);
    const req = http.expectOne((request) => request.url === url);

    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('limit')).toBe('12');
    expect(req.request.params.has('id_sucursal')).toBe(false);
    expect(req.request.params.has('id_ciudad')).toBe(false);
    expect(req.request.headers.get('Authorization')).toBe('Bearer client-token');

    const response = { success: true, data: [], origen: 'FALLBACK', message: 'ok' };
    req.flush(response);
    expect(received).toHaveBeenCalledWith(response);
  });

  it('forwards limit, branch and city as query params', () => {
    service.list({ limit: 6, idSucursal: 3, idCiudad: 2 }).subscribe();
    const req = http.expectOne((request) => request.url === url);

    expect(req.request.params.get('limit')).toBe('6');
    expect(req.request.params.get('id_sucursal')).toBe('3');
    expect(req.request.params.get('id_ciudad')).toBe('2');
    req.flush({ success: true, data: [], origen: 'PERSONALIZADO', message: 'ok' });
  });

  it('reads the current token on every call', () => {
    localStorage.setItem('fashionstore_access_token', 'renewed');
    service.list().subscribe();
    const req = http.expectOne((request) => request.url === url);
    expect(req.request.headers.get('Authorization')).toBe('Bearer renewed');
    req.flush({ success: true, data: [], origen: 'FALLBACK', message: 'ok' });
  });

  it('omits the header when there is no session', () => {
    localStorage.clear();
    service.list().subscribe();
    const req = http.expectOne((request) => request.url === url);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({ success: true, data: [], origen: 'FALLBACK', message: 'ok' });
  });

  describe('recommendationErrorMessage', () => {
    const build = (status: number, message?: string) =>
      new HttpErrorResponse({ status, error: message ? { message } : null });

    it('maps 401 to an expired session', () => {
      expect(recommendationErrorMessage(build(401))).toContain('sesión expiró');
    });

    it('prefers the backend message for 403/404/422', () => {
      expect(recommendationErrorMessage(build(403, 'Se requiere el rol CLIENTE'))).toBe(
        'Se requiere el rol CLIENTE',
      );
      expect(recommendationErrorMessage(build(404, 'Sucursal no encontrada'))).toBe(
        'Sucursal no encontrada',
      );
      expect(recommendationErrorMessage(build(422, 'La sucursal no esta activa'))).toBe(
        'La sucursal no esta activa',
      );
    });

    it('falls back to its own copy when the backend sends none', () => {
      expect(recommendationErrorMessage(build(403))).toContain('cuentas de cliente');
      expect(recommendationErrorMessage(build(422))).toContain('no está disponible');
    });

    it('never leaks server internals on 500 or offline', () => {
      const server = recommendationErrorMessage(
        new HttpErrorResponse({ status: 500, error: { message: 'stack trace' } }),
      );
      expect(server).not.toContain('stack trace');
      expect(recommendationErrorMessage(build(0))).toContain('conexión');
    });
  });
});
