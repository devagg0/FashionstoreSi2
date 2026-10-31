import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from '../../app.routes';
import { SessionService } from '../services/session.service';
import { superadminChildGuard, superadminGuard } from './superadmin.guard';

describe('superadminGuard PK07 CU01', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
  });

  afterEach(() => localStorage.clear());

  it.each(['SUPERADMIN', 'ADMINISTRADOR', 'CLIENTE', null])(
    'authorizes only authenticated SUPERADMIN: %s',
    (rol) => {
      const session = TestBed.inject(SessionService);
      if (rol) {
        session.saveAccessToken('signed-token');
        session.saveUser({
          id_usuario: 1,
          nombre: 'Sara',
          apellido: 'Admin',
          correo: 'sara@example.com',
          rol,
          id_empresa: rol === 'SUPERADMIN' ? null : 1,
        });
      }

      const result = TestBed.runInInjectionContext(() =>
        superadminGuard({} as never, {} as never),
      );

      if (rol === 'SUPERADMIN') expect(result).toBe(true);
      else expect(TestBed.inject(Router).serializeUrl(result as never)).toBe(rol ? '/' : '/login');
    },
  );

  it('requires a JWT even when a SUPERADMIN user is stored', () => {
    TestBed.inject(SessionService).saveUser({
      id_usuario: 1,
      nombre: 'Sara',
      apellido: 'Admin',
      correo: 'sara@example.com',
      rol: 'SUPERADMIN',
      id_empresa: null,
    });

    const result = TestBed.runInInjectionContext(() =>
      superadminChildGuard({} as never, {} as never),
    );
    expect(TestBed.inject(Router).serializeUrl(result as never)).toBe('/login');
  });

  it('protects the SUPERADMIN layout and both company routes', async () => {
    const route = routes.find((candidate) => candidate.path === 'superadmin');
    const registrationRoute = route?.children?.find(
      (candidate) => candidate.path === 'empresas/nueva',
    );
    const managementRoute = route?.children?.find((candidate) => candidate.path === 'empresas');

    expect(route?.canActivate).toEqual([superadminGuard]);
    expect(route?.canActivateChild).toEqual([superadminChildGuard]);
    expect(route?.children?.find((candidate) => candidate.path === '')?.redirectTo).toBe('empresas');
    expect(registrationRoute?.loadComponent).toBeTypeOf('function');
    expect(managementRoute?.loadComponent).toBeTypeOf('function');
    expect(await (registrationRoute!.loadComponent as () => Promise<unknown>)()).toBeTruthy();
    expect(await (managementRoute!.loadComponent as () => Promise<unknown>)()).toBeTruthy();
  });
});
