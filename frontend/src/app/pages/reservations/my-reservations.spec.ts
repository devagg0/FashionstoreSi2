import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { ReservationSummary } from '../../core/services/client-reservations.service';
import { MyReservations } from './my-reservations';

const url = `${environment.apiUrl}/api/client/reservations`;
const reservation: ReservationSummary = {
  id_reserva: 4,
  codigo: 'RSV-20260911-ABCD123456',
  estado: 'PENDIENTE',
  created_at: '2026-09-11T12:00:00',
  fecha_atencion_programada: '2026-09-12T20:00:00',
  fecha_expiracion: '2026-09-12T21:00:00',
  sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } },
  cantidad_prendas: 2,
  total: '159.80',
  cancelable: true,
};
const listing = (data = [reservation]) => ({
  success: true,
  data,
  message: '',
  pagination: { page: 1, page_size: 10, total: data.length, total_pages: data.length ? 1 : 0 },
});

describe('MyReservations CU17', () => {
  let fixture: ComponentFixture<MyReservations>;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(MyReservations);
    fixture.detectChanges();
  });
  afterEach(() => { http.verify(); fixture.destroy(); localStorage.clear(); });

  function flushList(data = [reservation]) {
    http.expectOne((request) => request.url === url && request.params.get('page_size') === '10').flush(listing(data));
    fixture.detectChanges();
  }

  it('shows history, status and totals', () => {
    flushList();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain(reservation.codigo);
    expect(text).toContain('Pendiente');
    expect(text).toContain('Atención programada');
    expect(text).toContain('Bs 159,80');
    expect(fixture.nativeElement.querySelector(`a[href="/mis-reservas/4"]`)).toBeTruthy();
  });

  it('filters by state', () => {
    flushList();
    fixture.componentInstance['state'].setValue('CANCELADA');
    const req = http.expectOne((request) => request.url === url);
    expect(req.request.params.get('estado')).toBe('CANCELADA');
    req.flush(listing([]));
  });

  it('confirms cancellation and updates the row', () => {
    flushList();
    fixture.nativeElement.querySelector('.reservation-card__bottom button').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    fixture.componentInstance['cancel']();
    http.expectOne(`${url}/4/cancel`).flush({
      success: true,
      data: { ...reservation, estado: 'CANCELADA', cancelable: false, items: [] },
      message: '',
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Cancelada');
    expect(fixture.nativeElement.querySelector('.reservation-card__bottom button')).toBeNull();
  });

  it('shows the empty state', () => {
    flushList([]);
    expect(fixture.nativeElement.textContent).toContain('No hay reservas para mostrar');
  });
});
