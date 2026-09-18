import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';
import { ReturnsService } from './returns.service';
import { routes } from '../../app.routes';
import { cashierGuard } from '../guards/cashier.guard';

const base = `${environment.apiUrl}/api`;
describe('CU24 contrato API', () => {
  let service: ReturnsService;
  let http: HttpTestingController;
  const logout = vi.fn();
  beforeEach(() => {
    sessionStorage.clear();
    logout.mockReset();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: SessionService,
          useValue: { getAccessToken: () => 'token', getUser: () => ({ id_usuario: 12 }), logout },
        },
      ],
    });
    service = TestBed.inject(ReturnsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    sessionStorage.clear();
  });
  it('las rutas staff requieren CAJERO y admin reutiliza el componente', async () => {
    const staff = routes.find((x) => x.path === 'staff')!;
    const admin = routes.find((x) => x.path === 'admin')!;
    for (const path of ['devoluciones', 'devoluciones/:id']) {
      const route = staff.children!.find((x) => x.path === path)!;
      expect(route.canActivate).toEqual([cashierGuard]);
      const adminRoute = admin.children!.find((x) => x.path === path)!;
      expect(await (route.loadComponent as () => Promise<unknown>)()).toBe(
        await (adminRoute.loadComponent as () => Promise<unknown>)(),
      );
    }
  });
  it('consulta propia y detalle staff con Bearer', () => {
    service.own(7).subscribe();
    service.detail(7).subscribe();
    for (const path of [`${base}/client/returns/7`, `${base}/staff/returns/7`]) {
      const req = http.expectOne(path);
      expect(req.request.method).toBe('GET');
      expect(req.request.headers.get('Authorization')).toBe('Bearer token');
      req.flush({ success: true, data: {} });
    }
  });
  it('persistencia de clave permite reintentar y limpiar una solicitud exitosa', () => {
    const key = service.attemptKey('same-body');
    expect(service.attemptKey('same-body')).toBe(key);
    expect(service.attemptKey('other-body')).not.toBe(key);
    service.clearAttempt('same-body');
    expect(service.attemptKey('same-body')).not.toBe(key);
  });
  it('sesión expirada cierra sesión y dirige al login', () => {
    const router = TestBed.inject(Router);
    const navigation = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    expect(service.error(new HttpErrorResponse({ status: 401 }))).toContain('sesión expiró');
    expect(logout).toHaveBeenCalledOnce();
    expect(navigation).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: router.url } });
  });
  it('muestra mensajes para errores de red, permisos, ausencia y resultado incierto', () => {
    for (const [status, text] of [
      [0, 'conexión'],
      [403, 'permisos'],
      [404, 'no está disponible'],
      [503, 'pendiente'],
      [500, 'actualiza'],
    ] as const) {
      expect(service.error(new HttpErrorResponse({ status })).toLowerCase()).toContain(
        text.toLowerCase(),
      );
    }
  });
  it('usa errores de negocio y valida errores 422 sin mensaje', () => {
    expect(
      service.error(
        new HttpErrorResponse({ status: 409, error: { message: 'Compra no cancelable' } }),
      ),
    ).toBe('Compra no cancelable');
    expect(service.error(new HttpErrorResponse({ status: 422, error: { detail: [] } }))).toContain(
      'cantidades',
    );
  });
});
