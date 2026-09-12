import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { ClientReservationsService } from './client-reservations.service';

describe('ClientReservationsService CU17', () => {
  let service: ClientReservationsService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/client/reservations`;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'client-token');
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ClientReservationsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });

  it('creates a reservation without accepting a client id', () => {
    const body = {
      id_sucursal: 2,
      fecha_atencion_programada: '2026-09-12T16:00:00-04:00',
      items: [{ id_variante_producto: 8, cantidad: 2 }],
    };
    service.createReservation(body).subscribe();
    const req = http.expectOne(url);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(body);
    expect(req.request.body.id_cliente).toBeUndefined();
    expect(req.request.headers.get('Authorization')).toBe('Bearer client-token');
    req.flush({ success: true, data: {}, message: '' });
  });

  it('lists with state and pagination', () => {
    service.listReservations({ estado: 'PENDIENTE', page: 2, pageSize: 10 }).subscribe();
    const req = http.expectOne((request) => request.url === url);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('estado')).toBe('PENDIENTE');
    expect(req.request.params.get('page')).toBe('2');
    req.flush({ success: true, data: [], pagination: {}, message: '' });
  });

  it('gets detail', () => {
    service.getReservation(12).subscribe();
    const req = http.expectOne(`${url}/12`);
    expect(req.request.method).toBe('GET');
    req.flush({ success: true, data: {}, message: '' });
  });

  it('cancels with an empty PATCH body', () => {
    service.cancelReservation(12).subscribe();
    const req = http.expectOne(`${url}/12/cancel`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({});
    req.flush({ success: true, data: {}, message: '' });
  });
});
