import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { StaffProfile } from './staff-profile';

describe('StaffProfile CU18', () => {
  let fixture: ComponentFixture<StaffProfile>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'leo@test.com', rol: 'ENCARGADO_SUCURSAL' });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffProfile);
    fixture.detectChanges();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  it('shows identity, role and backend-derived branch without edit controls', () => {
    http.expectOne((request) => request.url === `${environment.apiUrl}/api/staff/reservations`).flush({
      success: true,
      data: [{ sucursal: { id_sucursal: 2, nombre: 'Centro', direccion: 'Av. 1', ciudad: { id_ciudad: 1, nombre: 'La Paz' } } }],
      pagination: { page: 1, page_size: 1, total: 1, total_pages: 1 }, message: '',
    });
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    for (const value of ['Leo', 'Paz', 'leo@test.com', 'ENCARGADO_SUCURSAL', 'Centro']) expect(text).toContain(value);
    expect(fixture.nativeElement.querySelector('select')).toBeNull();
    expect(text).toContain('no pueden modificarse');
  });
});
