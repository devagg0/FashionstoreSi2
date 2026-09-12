import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { StaffReservationDetail } from '../../../core/services/staff-reservations.service';
import { StaffReservationDetailPage } from './staff-reservation-detail';

const url = `${environment.apiUrl}/api/staff/reservations/4`;
const detail: StaffReservationDetail = {
  id_reserva: 4, codigo: 'RSV-20260912-ABC123', estado: 'PENDIENTE',
  created_at: '2026-09-11T12:00:00', fecha_atencion_programada: '2026-09-12T20:00:00',
  fecha_expiracion: '2026-09-12T21:00:00', fecha_atencion: null,
  cliente: { id_cliente: 7, nombre: 'Ana', apellido: 'Lopez', correo: 'ana@test.com', telefono: '70000000' },
  sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } },
  cantidad_prendas: 2, total: '159.80',
  prendas: [{ id_variante_producto: 8, sku: 'CAM-M-NEG', id_producto: 3, producto: 'Camisa Oxford', talla: { id_talla: 1, nombre: 'M' }, color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000000' }, cantidad: 2, precio_reservado: '79.90', subtotal: '159.80' }],
};

describe('StaffReservationDetailPage CU18', () => {
  let fixture: ComponentFixture<StaffReservationDetailPage>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), {
        provide: ActivatedRoute, useValue: { snapshot: { paramMap: { get: () => '4' } } },
      }],
    });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'l@b.com', rol: 'CAJERO' });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffReservationDetailPage);
    fixture.detectChanges();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  function flushDetail(value = detail): void {
    http.expectOne(url).flush({ success: true, data: value, message: '' });
    http.expectOne(`${environment.apiUrl}/api/catalog/products/3?id_sucursal=2`).flush({ data: { imagen_principal: null } });
    fixture.detectChanges();
  }

  it('shows client, branch, garment, variant and reserved price', () => {
    flushDetail();
    const text = fixture.nativeElement.textContent;
    for (const value of ['Ana Lopez', 'Centro', 'Camisa Oxford', 'CAM-M-NEG', 'Negro', 'Talla M', 'Bs 79,90', 'Bs 159,80']) expect(text).toContain(value);
  });

  it('asks confirmation and confirms a pending reservation', () => {
    flushDetail();
    fixture.nativeElement.querySelector('.staff-detail-action').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    fixture.componentInstance['runAction']();
    http.expectOne(`${url}/confirm`).flush({ success: true, data: { ...detail, estado: 'CONFIRMADA' }, message: '' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Marcar como atendida');
  });

  it('marks a confirmed reservation as attended', () => {
    flushDetail({ ...detail, estado: 'CONFIRMADA' });
    fixture.componentInstance['askAction']('attend');
    fixture.componentInstance['runAction']();
    http.expectOne(`${url}/attend`).flush({ success: true, data: { ...detail, estado: 'ATENDIDA' }, message: '' });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('solo lectura');
    expect(fixture.nativeElement.querySelector('.staff-detail-action')).toBeNull();
  });

  it.each(['ATENDIDA', 'CANCELADA', 'EXPIRADA'] as const)('hides operational actions for %s', (estado) => {
    flushDetail({ ...detail, estado });
    expect(fixture.nativeElement.querySelector('.staff-detail-action')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('solo lectura');
  });
});
