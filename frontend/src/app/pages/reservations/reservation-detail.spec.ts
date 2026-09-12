import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { ReservationDetail } from '../../core/services/client-reservations.service';
import { ReservationDetailPage } from './reservation-detail';

const url = `${environment.apiUrl}/api/client/reservations/4`;
const detail: ReservationDetail = {
  id_reserva: 4,
  codigo: 'RSV-20260911-ABCD123456',
  estado: 'CONFIRMADA',
  created_at: '2026-09-11T12:00:00',
  fecha_atencion_programada: '2026-09-12T20:00:00',
  fecha_expiracion: '2026-09-12T21:00:00',
  sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } },
  cantidad_prendas: 2,
  total: '159.80',
  cancelable: true,
  items: [{
    id_variante_producto: 8,
    sku: 'CAM-M-NEG',
    id_producto: 3,
    producto: 'Camisa Oxford',
    imagen_principal: null,
    talla: { id_talla: 1, nombre: 'M' },
    color: { id_color: 2, nombre: 'Negro', codigo_hex: '#000000' },
    cantidad: 2,
    precio_unitario: '79.90',
    subtotal: '159.80',
  }],
};

describe('ReservationDetailPage CU17', () => {
  let fixture: ComponentFixture<ReservationDetailPage>;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'token');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: { get: (key: string) => key === 'id' ? '4' : null },
              queryParamMap: { get: () => null },
            },
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ReservationDetailPage);
    fixture.detectChanges();
  });
  afterEach(() => { http.verify(); fixture.destroy(); localStorage.clear(); });

  function flushDetail(value = detail) {
    http.expectOne(url).flush({ success: true, data: value, message: '' });
    fixture.detectChanges();
  }

  it('shows branch, product variant, snapshot price and total', () => {
    flushDetail();
    const text = fixture.nativeElement.textContent;
    for (const value of ['Centro', 'Av. 1', 'Camisa Oxford', 'Negro', 'Talla M', 'Bs 79,90', 'Bs 159,80']) {
      expect(text).toContain(value);
    }
    expect(text).toContain('Atención programada');
    expect(text).toContain('Reserva válida hasta');
  });

  it('asks confirmation before cancelling', () => {
    flushDetail();
    fixture.nativeElement.querySelector('.detail-cancel').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alertdialog"]')).toBeTruthy();
    http.expectNone((request) => request.method === 'PATCH');
  });

  it('cancels and removes the action', () => {
    flushDetail();
    fixture.componentInstance['confirmCancel'].set(true);
    fixture.componentInstance['cancel']();
    http.expectOne(`${url}/cancel`).flush({
      success: true,
      data: { ...detail, estado: 'CANCELADA', cancelable: false },
      message: '',
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Cancelada');
    expect(fixture.nativeElement.querySelector('.detail-cancel')).toBeNull();
  });

  it('renders an expired reservation without cancellation', () => {
    flushDetail({ ...detail, estado: 'EXPIRADA', cancelable: false });
    expect(fixture.nativeElement.textContent).toContain('Expirada');
    expect(fixture.nativeElement.querySelector('.detail-cancel')).toBeNull();
  });
});
