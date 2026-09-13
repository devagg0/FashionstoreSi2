import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from '../../app.routes';
import { SessionService } from '../services/session.service';
import { cashierGuard } from './cashier.guard';

describe('cashierGuard CU20', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
  });
  afterEach(() => localStorage.clear());
  it.each(['CAJERO', 'ENCARGADO_SUCURSAL', 'CLIENTE', 'ADMINISTRADOR', 'PROVEEDOR', null])(
    'authorizes only CAJERO: %s',
    (rol) => {
      const session = TestBed.inject(SessionService);
      if (rol) {
        session.saveAccessToken('token');
        session.saveUser({ id_usuario: 3, nombre: 'Ana', apellido: 'Paz', correo: 'a@b.com', rol });
      }
      const result = TestBed.runInInjectionContext(() => cashierGuard({} as never, {} as never));
      if (rol === 'CAJERO') expect(result).toBe(true);
      else expect(TestBed.inject(Router).serializeUrl(result as never)).toBe(rol ? '/' : '/login');
    },
  );
  it('requires a token even with a saved cashier user', () => {
    TestBed.inject(SessionService).saveUser({
      id_usuario: 3,
      nombre: 'Ana',
      apellido: 'Paz',
      correo: 'a@b.com',
      rol: 'CAJERO',
    });
    const result = TestBed.runInInjectionContext(() => cashierGuard({} as never, {} as never));
    expect(TestBed.inject(Router).serializeUrl(result as never)).toBe('/login');
  });
  it('lazy loads CU20 under staff and applies cashierGuard', async () => {
    const route = routes
      .find((r) => r.path === 'staff')
      ?.children?.find((r) => r.path === 'ventas/nueva');
    expect(route?.canActivate).toEqual([cashierGuard]);
    expect(route?.loadComponent).toBeTypeOf('function');
    expect(await (route!.loadComponent as () => Promise<unknown>)()).toBeTruthy();
  });
});
