import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { CatalogProductDetail } from '../../core/services/catalog.service';
import { ReservationSelectionService } from '../../core/services/reservation-selection.service';
import { upcomingReservationDays } from '../../core/utils/reservation-schedule';
import { SessionService } from '../../core/services/session.service';
import { ProductDetail } from './product-detail';

const product: CatalogProductDetail = {
  id_producto: 7, nombre: 'Chaqueta', descripcion: null, seccion: 'UNISEX', id_categoria: 2,
  categoria: 'Chaquetas', id_temporada: null, temporada: null, precio_base: '100', precio_final: '80',
  tiene_promocion: true, promociones_vigentes: [], promocion_destacada: null,
  porcentaje_descuento: null, monto_descuento: '20', imagen_principal: null, galeria: [], colecciones: [],
  tallas: [{ id_talla: 1, nombre: 'M' }], colores: [{ id_color: 2, nombre: 'Negro', codigo_hex: '#000' }],
  variantes: [{ id_variante_producto: 9, sku: 'CHA-M-NEG', talla: { id_talla: 1, nombre: 'M' },
    color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000' }, disponibilidad_sucursal: null }],
};

describe('ProductDetail reservation flow CU17', () => {
  it('adds the selected variant to the temporary multi-item selection', () => {
    sessionStorage.clear();
    localStorage.setItem('fashionstore_access_token', 'token');
    localStorage.setItem('fashionstore_user', JSON.stringify({
      id_usuario: 3, nombre: 'Ana', apellido: 'Pérez', correo: 'ana@example.com', rol: 'CLIENTE',
    }));
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ProductDetail);
    const page = fixture.componentInstance;
    page['product'].set(product);
    page['loading'].set(false);
    page['errorMessage'].set('');
    page['selectColor'](2);
    page['selectSize'](1);
    fixture.detectChanges();
    http.expectOne(`${environment.apiUrl}/api/catalog/products/7/availability?id_variante_producto=9`).flush({
      success: true,
      data: { producto: { id_producto: 7, nombre: 'Chaqueta', estado: true }, disponibilidad: [{
        variante: { id_variante_producto: 9, sku: 'CHA-M-NEG', talla: { id_talla: 1, nombre: 'M' }, color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000' }, estado: true },
        id_sucursal: 6, nombre_sucursal: 'Centro', id_ciudad: 1, nombre_ciudad: 'La Paz',
        direccion: 'Av. Principal', hora_apertura: '08:00:00', hora_cierre: '20:00:00',
        stock_actual: 5, stock_reservado: 2, stock_disponible: 3,
      }] },
      message: '',
    });
    fixture.detectChanges();
    page['scheduleChanged']({
      branch: {
        variante: { id_variante_producto: 9, sku: 'CHA-M-NEG', talla: { id_talla: 1, nombre: 'M' }, color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000' }, estado: true },
        id_sucursal: 6, nombre_sucursal: 'Centro', id_ciudad: 1, nombre_ciudad: 'La Paz',
        direccion: 'Av. Principal', hora_apertura: '08:00:00', hora_cierre: '20:00:00',
        stock_actual: 5, stock_reservado: 2, stock_disponible: 3,
      },
      date: upcomingReservationDays()[1].value,
      time: '16:30',
    });
    const quantity = fixture.nativeElement.querySelector('.reservation-selector input[type="number"]') as HTMLInputElement;
    quantity.value = '3'; quantity.dispatchEvent(new Event('input')); fixture.detectChanges();
    fixture.nativeElement.querySelector('.reservation-selector .button--solid').click();
    const selected = TestBed.inject(ReservationSelectionService).items();
    expect(selected).toEqual([expect.objectContaining({
      id_producto: 7,
      id_variante_producto: 9,
      cantidad: 3,
      talla: 'M',
      color: 'Negro',
    })]);
    expect(TestBed.inject(ReservationSelectionService).context()).toEqual(
      expect.objectContaining({ id_sucursal: 6, horario: '16:30' }),
    );
    http.expectNone(`${environment.apiUrl}/api/client/reservations`);
    http.verify();
    fixture.destroy();
    TestBed.inject(SessionService).logout();
    sessionStorage.clear();
  });

  it('keeps the first item context and only asks quantity for a later garment', () => {
    sessionStorage.clear();
    localStorage.setItem('fashionstore_access_token', 'token');
    localStorage.setItem('fashionstore_user', JSON.stringify({
      id_usuario: 3, nombre: 'Ana', apellido: 'Pérez', correo: 'ana@example.com', rol: 'CLIENTE',
    }));
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const selection = TestBed.inject(ReservationSelectionService);
    const date = upcomingReservationDays()[1].value;
    selection.start({
      id_sucursal: 6, nombre_sucursal: 'Centro', nombre_ciudad: 'La Paz', direccion: 'Av. Principal',
      hora_apertura: '08:00:00', hora_cierre: '20:00:00', fecha: date, horario: '16:30',
    }, {
      id_producto: 8, id_variante_producto: 12, producto: 'Camisa', imagen_principal: null,
      sku: 'CAM-L-BLA', talla: 'L', color: 'Blanco', precio_referencia: '50', cantidad: 1,
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ProductDetail);
    const page = fixture.componentInstance;
    page['product'].set(product);
    page['loading'].set(false);
    page['errorMessage'].set('');
    page['selectColor'](2);
    page['selectSize'](1);
    fixture.detectChanges();
    const request = http.expectOne((candidate) =>
      candidate.url === `${environment.apiUrl}/api/catalog/products/7/availability` &&
      candidate.params.get('id_variante_producto') === '9',
    );
    expect(request.request.params.get('id_sucursal')).toBe('6');
    request.flush({
      success: true,
      data: { producto: { id_producto: 7, nombre: 'Chaqueta', estado: true }, disponibilidad: [{
        variante: { id_variante_producto: 9, sku: 'CHA-M-NEG', talla: { id_talla: 1, nombre: 'M' }, color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000' }, estado: true },
        id_sucursal: 6, nombre_sucursal: 'Centro', id_ciudad: 1, nombre_ciudad: 'La Paz',
        direccion: 'Av. Principal', hora_apertura: '08:00:00', hora_cierre: '20:00:00',
        stock_actual: 5, stock_reservado: 0, stock_disponible: 5,
      }] }, message: '',
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-reservation-schedule-picker')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('RESERVA ACTUAL');
    expect(fixture.nativeElement.textContent).toContain('Añadir a esta reserva');
    page['addToReservation']();
    expect(selection.items()).toHaveLength(2);
    expect(selection.context()).toEqual(expect.objectContaining({ id_sucursal: 6, fecha: date, horario: '16:30' }));
    http.verify();
    fixture.destroy();
    TestBed.inject(SessionService).logout();
  });
});
