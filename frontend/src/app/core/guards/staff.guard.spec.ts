import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from '../../app.routes';
import { SessionService } from '../services/session.service';
import { staffChildGuard, staffGuard } from './staff.guard';

describe('staffGuard CU18', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
  });
  afterEach(() => localStorage.clear());

  it('protects the staff layout and every child route', () => {
    const route = routes.find((item) => item.path === 'staff');
    expect(route?.canActivate).toEqual([staffGuard]);
    expect(route?.canActivateChild).toEqual([staffChildGuard]);
    expect(route?.children?.map((child) => child.path)).toEqual([
      '', 'inicio', 'reservas', 'reservas/:id', 'disponibilidad', 'perfil',
    ]);
  });

  it('allows cashier and branch manager roles', () => {
    const session = TestBed.inject(SessionService);
    for (const rol of ['CAJERO', 'ENCARGADO_SUCURSAL']) {
      session.saveAccessToken('token');
      session.saveUser({ id_usuario: 1, nombre: 'Ana', apellido: 'Paz', correo: 'a@b.com', rol });
      expect(TestBed.runInInjectionContext(() => staffGuard({} as never, {} as never))).toBe(true);
    }
  });

  it('redirects anonymous users to login and other roles home', () => {
    const router = TestBed.inject(Router);
    const anonymous = TestBed.runInInjectionContext(() => staffGuard({} as never, {} as never));
    expect(router.serializeUrl(anonymous as never)).toBe('/login');
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 1, nombre: 'Ana', apellido: 'Paz', correo: 'a@b.com', rol: 'ADMINISTRADOR' });
    const denied = TestBed.runInInjectionContext(() => staffGuard({} as never, {} as never));
    expect(router.serializeUrl(denied as never)).toBe('/');
  });
});
