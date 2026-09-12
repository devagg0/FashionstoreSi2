import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { StaffAvailability } from './staff-availability';

describe('StaffAvailability CU18', () => {
  let fixture: ComponentFixture<StaffAvailability>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'l@b.com', rol: 'CAJERO' });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffAvailability);
    fixture.detectChanges();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  it('uses only the branch returned by CU18 and renders read-only variant stock', () => {
    http.expectOne((request) => request.url === `${environment.apiUrl}/api/staff/reservations`).flush({
      success: true,
      data: [{ sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } } }],
      pagination: { page: 1, page_size: 1, total: 1, total_pages: 1 }, message: '',
    });
    const catalog = http.expectOne((request) => request.url === `${environment.apiUrl}/api/catalog/products`);
    expect(catalog.request.params.get('id_sucursal')).toBe('2');
    catalog.flush({ data: [{ id_producto: 3 }], pagination: { page: 1, total_pages: 1 } });
    const detail = http.expectOne((request) => request.url === `${environment.apiUrl}/api/catalog/products/3`);
    expect(detail.request.params.get('id_sucursal')).toBe('2');
    detail.flush({ data: { nombre: 'Camisa Oxford', variantes: [{ id_variante_producto: 8, sku: 'CAM-M-NEG', talla: { nombre: 'M' }, color: { nombre: 'Negro', codigo_hex: '#000000' }, disponibilidad_sucursal: { id_sucursal: 2, cantidad_disponible: 6 } }] } });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    for (const value of ['Camisa Oxford', 'CAM-M-NEG', 'Negro', '6', 'Solo lectura']) expect(text).toContain(value);
    expect(fixture.nativeElement.querySelector('input[type="number"]')).toBeNull();
    http.expectNone((request) => ['PATCH', 'POST', 'PUT', 'DELETE'].includes(request.method));
  });
});
