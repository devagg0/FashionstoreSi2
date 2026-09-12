import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { StaffReservationSummary } from '../../../core/services/staff-reservations.service';
import { StaffReservations } from './staff-reservations';

const url = `${environment.apiUrl}/api/staff/reservations`;
const reservation: StaffReservationSummary = {
  id_reserva: 4, codigo: 'RSV-20260912-ABC123', estado: 'PENDIENTE',
  created_at: '2026-09-11T12:00:00', fecha_atencion_programada: '2026-09-12T20:00:00',
  fecha_expiracion: '2026-09-12T21:00:00', fecha_atencion: null,
  cliente: { id_cliente: 7, nombre: 'Ana', apellido: 'Lopez', correo: 'ana@test.com', telefono: null },
  sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } },
  cantidad_prendas: 2, total: '159.80',
};

describe('StaffReservations CU18', () => {
  let fixture: ComponentFixture<StaffReservations>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'l@b.com', rol: 'CAJERO' });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffReservations);
    fixture.detectChanges();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  function flushList(data = [reservation]): void {
    http.expectOne((request) => request.url === url).flush({
      success: true, data, pagination: { page: 1, page_size: 12, total: data.length, total_pages: data.length ? 1 : 0 }, message: '',
    });
    fixture.detectChanges();
  }

  it('renders the operational reservation data and detail action', () => {
    flushList();
    const text = fixture.nativeElement.textContent;
    for (const value of [reservation.codigo, 'Ana Lopez', 'Pendiente', 'Bs 159,80', 'Centro']) expect(text).toContain(value);
    expect(fixture.nativeElement.querySelector('a[href="/staff/reservas/4"]')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('[data-label="Código"]')).toBeTruthy();
  });

  it('sends state and date filters without a branch id', () => {
    flushList();
    fixture.componentInstance['filterForm'].patchValue({ estado: 'CONFIRMADA', fechaProgramada: '2026-09-12' });
    fixture.componentInstance['applyFilters']();
    const req = http.expectOne((request) => request.url === url);
    expect(req.request.params.get('estado')).toBe('CONFIRMADA');
    expect(req.request.params.get('fecha_programada')).toBe('2026-09-12');
    expect(req.request.params.has('id_sucursal')).toBe(false);
    req.flush({ success: true, data: [], pagination: { page: 1, page_size: 12, total: 0, total_pages: 0 }, message: '' });
  });

  it('uses the dedicated code lookup', () => {
    flushList();
    fixture.componentInstance['filterForm'].patchValue({ codigo: reservation.codigo });
    fixture.componentInstance['applyFilters']();
    http.expectOne(`${url}/code/${reservation.codigo}`).flush({ success: true, data: { ...reservation, prendas: [] }, message: '' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(reservation.codigo);
  });

  it('shows the no-results state', () => {
    flushList([]);
    expect(fixture.nativeElement.textContent).toContain('Sin resultados');
  });
});
