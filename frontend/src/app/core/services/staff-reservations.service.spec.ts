import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';
import { StaffReservationsService } from './staff-reservations.service';

describe('StaffReservationsService CU18', () => {
  let service: StaffReservationsService;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/staff/reservations`;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('staff-token');
    session.saveUser({ id_usuario: 8, nombre: 'Luis', apellido: 'Rojas', correo: 'l@b.com', rol: 'CAJERO' });
    service = TestBed.inject(StaffReservationsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); localStorage.clear(); });

  it('lists using only supported filters and never sends a branch id', () => {
    service.listReservations({ estado: 'PENDIENTE', fechaProgramada: '2026-09-12', page: 2 }).subscribe();
    const req = http.expectOne((request) => request.url === url);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('estado')).toBe('PENDIENTE');
    expect(req.request.params.get('fecha_programada')).toBe('2026-09-12');
    expect(req.request.params.get('id_sucursal')).toBeNull();
    expect(req.request.headers.get('Authorization')).toBe('Bearer staff-token');
    req.flush({ success: true, data: [], pagination: {}, message: '' });
  });

  it('searches by encoded code and exposes branch only from backend data', () => {
    service.getReservationByCode('RSV 01').subscribe();
    const req = http.expectOne(`${url}/code/RSV%2001`);
    req.flush({ success: true, data: { sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } } }, message: '' });
    expect(service.branch()?.nombre).toBe('Centro');
  });

  it('confirms and attends with empty PATCH bodies', () => {
    service.confirmReservation(4).subscribe();
    const confirm = http.expectOne(`${url}/4/confirm`);
    expect(confirm.request.method).toBe('PATCH');
    expect(confirm.request.body).toEqual({});
    confirm.flush({ success: true, data: { sucursal: {} }, message: '' });
    service.attendReservation(4).subscribe();
    const attend = http.expectOne(`${url}/4/attend`);
    expect(attend.request.method).toBe('PATCH');
    expect(attend.request.body).toEqual({});
    attend.flush({ success: true, data: { sucursal: {} }, message: '' });
  });
});
