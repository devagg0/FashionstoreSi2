import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { StaffDashboard } from './staff-dashboard';

describe('StaffDashboard CU18', () => {
  let fixture: ComponentFixture<StaffDashboard>;
  let http: HttpTestingController;
  const url = `${environment.apiUrl}/api/staff/reservations`;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'l@b.com', rol: 'CAJERO' });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffDashboard);
    fixture.detectChanges();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  it('loads the four real summary counts', () => {
    const requests = http.match((request) => request.url === url);
    expect(requests.length).toBe(4);
    const totals: Record<string, number> = { PENDIENTE: 3, CONFIRMADA: 2, ATENDIDA: 8 };
    for (const request of requests) {
      const state = request.request.params.get('estado');
      const total = state ? totals[state] : 4;
      request.flush({ success: true, data: [], pagination: { page: 1, page_size: 1, total, total_pages: 1 }, message: '' });
    }
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    for (const value of ['Reservas pendientes', 'Reservas confirmadas', 'Reservas para hoy', 'Reservas atendidas']) expect(text).toContain(value);
    expect(fixture.nativeElement.querySelectorAll('.staff-summary-card').length).toBe(4);
  });
});
