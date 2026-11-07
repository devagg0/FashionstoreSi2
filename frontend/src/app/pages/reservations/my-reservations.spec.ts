import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { environment } from '../../../environments/environment';
import { ReservationSummary } from '../../core/services/client-reservations.service';
import { OfflineService } from '../../core/services/offline.service';
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

describe('MyReservations CU17 (Online)', () => {
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

  afterEach(() => {
    http.verify();
    fixture.destroy();
    localStorage.clear();
  });

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

describe('MyReservations CU10 (Offline)', () => {
  let fixture: ComponentFixture<MyReservations>;
  let http: HttpTestingController;
  let offlineService: OfflineService;

  const mockReceipt = {
    uuid_reserva_offline: 'uuid-offline-999',
    codigo_local: 'RES-LOC-99999999',
    fecha_registro: '2026-11-01T10:00:00',
    fecha_limite: '2026-11-02T16:00:00',
    sucursal_nombre: 'Sucursal Centro',
    detalles: [
      {
        uuid_reserva_offline: 'uuid-offline-999',
        id_variante_producto: 1,
        id_producto: 1,
        producto_nombre: 'Chaqueta',
        sku: 'CHA-M',
        talla: 'M',
        color: 'Negro',
        cantidad: 1,
        precio_referencial: 80,
        subtotal: 80,
      },
    ],
    total_referencial: 80,
    adelanto_efectivo: 0,
    saldo_pendiente: 80,
    estado: 'REGISTRADA_LOCAL' as const,
  };

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    offlineService = TestBed.inject(OfflineService);
    offlineService.isOnline.set(false);
    vi.spyOn(offlineService, 'getPendingClientReservations').mockResolvedValue([mockReceipt]);
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(MyReservations);
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    fixture.destroy();
    localStorage.clear();
  });

  it('when offline, displays local pending reservations without error and updates counter', async () => {
    await fixture.whenStable();
    fixture.detectChanges();

    http.expectNone(url);
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('1 reserva');
    expect(text).toContain('RES-LOC-99999999');
    expect(text).toContain('Pendiente de sincronización');
    expect(text).not.toContain('No pudimos procesar tus reservas');
    expect(text).not.toContain('No hay reservas para mostrar');
  });

  it('when offline with non-matching state filter, counter is 0 and shows empty state', async () => {
    await fixture.whenStable();
    fixture.detectChanges();

    fixture.componentInstance['state'].setValue('CANCELADA');
    fixture.detectChanges();

    http.expectNone(url);
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('0 reservas');
    expect(text).toContain('No hay reservas para mostrar');
  });
});
