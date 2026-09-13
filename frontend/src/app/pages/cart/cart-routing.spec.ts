import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from '../../app.routes';
import { clientGuard } from '../../core/guards/client.guard';
import { SessionService } from '../../core/services/session.service';
import { Cart } from './cart';

describe('CU19 routing', () => {
  beforeEach(() => { localStorage.clear(); TestBed.configureTestingModule({ providers: [provideRouter(routes)] }); });
  afterEach(() => localStorage.clear());
  it('registers /carrito with lazy Cart and clientGuard', async () => {
    const route = routes.find(route => route.path === 'carrito')!;
    expect(route.canActivate).toEqual([clientGuard]); expect(await (route.loadComponent as () => Promise<unknown>)()).toBe(Cart);
  });
  for (const role of [null, 'ADMIN', 'CLIENTE']) {
    it(`enforces access for ${role ?? 'guest'}`, () => {
      if (role) {
        const session = TestBed.inject(SessionService); session.saveAccessToken('token');
        session.saveUser({ id_usuario: 1, nombre: 'Ana', apellido: 'Pérez', correo: 'ana@example.com', rol: role });
      }
      const result = TestBed.runInInjectionContext(() => clientGuard({} as never, {} as never));
      if (role === 'CLIENTE') expect(result).toBe(true);
      else expect(TestBed.inject(Router).serializeUrl(result as never)).toBe(role ? '/' : '/login');
    });
  }
});
