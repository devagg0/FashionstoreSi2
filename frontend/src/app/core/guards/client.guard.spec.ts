import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from '../../app.routes';
import { SessionService } from '../services/session.service';
import { clientGuard } from './client.guard';

describe('clientGuard CU17', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
  });
  afterEach(() => localStorage.clear());

  it('protects list and detail routes', () => {
    for (const path of ['reservar', 'mis-reservas', 'mis-reservas/:id']) {
      expect(routes.find((route) => route.path === path)?.canActivate).toEqual([clientGuard]);
    }
  });

  it('redirects an anonymous user to login', () => {
    const result = TestBed.runInInjectionContext(() => clientGuard({} as never, {} as never));
    expect(TestBed.inject(Router).serializeUrl(result as never)).toBe('/login');
  });

  it('allows only a client session', () => {
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('token');
    session.saveUser({ id_usuario: 1, nombre: 'Ana', apellido: 'Pérez', correo: 'a@b.com', rol: 'CLIENTE' });
    expect(TestBed.runInInjectionContext(() => clientGuard({} as never, {} as never))).toBe(true);
  });
});
