import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { SessionService } from '../../core/services/session.service';
import { StaffLayout } from './staff-layout';

describe('StaffLayout CU18', () => {
  let fixture: ComponentFixture<StaffLayout>;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'l@b.com', rol: 'CAJERO' });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffLayout);
    fixture.detectChanges();
    http.expectOne((request) => request.url === `${environment.apiUrl}/api/staff/reservations`).flush({
      success: true, data: [], pagination: { page: 1, page_size: 1, total: 0, total_pages: 0 }, message: '',
    });
    fixture.detectChanges();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  it('shows only the operational sidebar for cashier', () => {
    const text = fixture.nativeElement.querySelector('.staff-sidebar').textContent;
    for (const item of ['Inicio', 'Reservas', 'Disponibilidad', 'Mi perfil', 'Cerrar sesión']) expect(text).toContain(item);
    for (const forbidden of ['Usuarios', 'Ciudades', 'Promociones', 'Inventario global']) expect(text).not.toContain(forbidden);
  });

  it('keeps the branch manager on the same backend-authorized modules', () => {
    TestBed.inject(SessionService).saveUser({ id_usuario: 3, nombre: 'Leo', apellido: 'Paz', correo: 'l@b.com', rol: 'ENCARGADO_SUCURSAL' });
    fixture.detectChanges();
    const text = fixture.nativeElement.querySelector('.staff-sidebar').textContent;
    expect(text).toContain('Reservas');
    expect(text).toContain('Disponibilidad');
    expect(text).not.toContain('Inventario');
    expect(text).not.toContain('Usuarios');
  });

  it('opens and closes the responsive sidebar', () => {
    fixture.nativeElement.querySelector('.staff-topbar__menu').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.staff-shell').classList).toContain('sidebar-is-open');
    fixture.nativeElement.querySelector('.staff-backdrop').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.staff-shell').classList).not.toContain('sidebar-is-open');
  });
});
