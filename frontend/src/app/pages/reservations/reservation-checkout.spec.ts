import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { vi } from 'vitest';
import { environment } from '../../../environments/environment';
import { ReservationSelectionService } from '../../core/services/reservation-selection.service';
import { upcomingReservationDays } from '../../core/utils/reservation-schedule';
import { ReservationCheckout } from './reservation-checkout';

const selectedItems = [
  {
    id_producto: 7, id_variante_producto: 9, producto: 'Chaqueta', imagen_principal: null,
    sku: 'CHA-M-NEG', talla: 'M', color: 'Negro', precio_referencia: '80.00', cantidad: 2,
  },
  {
    id_producto: 8, id_variante_producto: 12, producto: 'Camisa', imagen_principal: null,
    sku: 'CAM-L-BLA', talla: 'L', color: 'Blanco', precio_referencia: '50.00', cantidad: 1,
  },
];

describe('ReservationCheckout CU17', () => {
  let fixture: ComponentFixture<ReservationCheckout>;
  let http: HttpTestingController;
  let selection: ReservationSelectionService;
  const reservationDate = upcomingReservationDays()[1].value;
  const context = {
    id_sucursal: 6,
    nombre_sucursal: 'Centro',
    nombre_ciudad: 'La Paz',
    direccion: 'Av. Principal',
    hora_apertura: '08:00:00',
    hora_cierre: '20:00:00',
    fecha: reservationDate,
    horario: '16:30',
  };

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'token');
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    selection = TestBed.inject(ReservationSelectionService);
    selection.start(context, selectedItems[0]);
    selection.add(selectedItems[1]);
    fixture = TestBed.createComponent(ReservationCheckout);
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    fixture.destroy();
    localStorage.clear();
    sessionStorage.clear();
  });

  function flushAvailability(
    stock: number | number[] = 5,
    hours: [string | null, string | null] = ['08:00:00', '20:00:00'],
  ) {
    const requests = http.match(
      (request) => request.url.includes('/api/catalog/products/') && request.url.endsWith('/availability'),
    );
    expect(requests.length).toBe(selection.items().length);
    requests.forEach((request, index) => {
      const item = selection.items()[index];
      const itemStock = Array.isArray(stock) ? stock[index] : stock;
      request.flush({
        success: true,
        data: {
          producto: { id_producto: item.id_producto, nombre: item.producto, estado: true },
          disponibilidad: [{
            variante: {
              id_variante_producto: item.id_variante_producto,
              sku: item.sku,
              talla: { id_talla: 1, nombre: item.talla },
              color: { id_color: 1, nombre: item.color, codigo_hex: null },
              estado: true,
            },
            id_sucursal: 6,
            nombre_sucursal: 'Centro',
            direccion: 'Av. Principal',
            hora_apertura: hours[0],
            hora_cierre: hours[1],
            id_ciudad: 1,
            nombre_ciudad: 'La Paz',
            stock_actual: itemStock,
            stock_reservado: 0,
            stock_disponible: itemStock,
          }],
        },
        message: '',
      });
    });
    fixture.detectChanges();
  }

  it('shows several garments and allows quantity changes and removal', () => {
    flushAvailability();
    expect(fixture.nativeElement.textContent).toContain('Chaqueta');
    expect(fixture.nativeElement.textContent).toContain('Camisa');
    expect(fixture.nativeElement.textContent).toContain('16:30');

    const quantity = fixture.nativeElement.querySelector('input[type="number"]') as HTMLInputElement;
    quantity.value = '3';
    quantity.dispatchEvent(new Event('change'));
    expect(selection.items()[0].cantidad).toBe(3);
    flushAvailability();

    fixture.nativeElement.querySelector('.checkout-item__remove').click();
    expect(selection.items()).toHaveLength(1);
    flushAvailability();
  });

  it('does not offer a branch if one selected garment lacks stock there', () => {
    flushAvailability([5, 0]);
    expect(fixture.componentInstance['branches']()).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain('disponibilidad completa');
  });

  it('reports a branch whose opening hours are missing', () => {
    flushAvailability(5, [null, null]);
    expect(fixture.componentInstance['branches']()).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain('horario válido configurado');
  });

  it('does not accept a context change to a branch that was not valid for every item', () => {
    flushAvailability();
    fixture.componentInstance['beginContextChange']();
    const unavailableBranch = {
      ...fixture.componentInstance['branches']()[0],
      id_sucursal: 99,
      nombre_sucursal: 'Sin stock común',
    };
    fixture.componentInstance['scheduleChanged']({
      branch: unavailableBranch,
      date: reservationDate,
      time: '17:00',
    });
    fixture.componentInstance['applyContextChange']();
    expect(selection.context()?.id_sucursal).toBe(6);
    expect(fixture.componentInstance['errorMessage']()).toContain('válidos');
  });

  it('confirms every item with one POST and preserves the selected local time', () => {
    flushAvailability();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture.componentInstance['confirm']();
    const request = http.expectOne(`${environment.apiUrl}/api/client/reservations`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      id_sucursal: 6,
      fecha_atencion_programada: `${reservationDate}T16:30:00-04:00`,
      items: [
        { id_variante_producto: 9, cantidad: 2 },
        { id_variante_producto: 12, cantidad: 1 },
      ],
    });
    expect(request.request.body.id_cliente).toBeUndefined();
    request.flush({ success: true, data: { id_reserva: 44 }, message: '' });
    expect(selection.items()).toEqual([]);
    expect(selection.context()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/mis-reservas', 44], {
      queryParams: { creada: 1 },
    });
  });
});
