import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { SubscriptionDetail } from '../../../core/services/saas-subscriptions.service';
import { SessionService } from '../../../core/services/session.service';
import { ManageSubscriptions } from './manage-subscriptions';

describe('ManageSubscriptions Component (CU06 SUPERADMIN)', () => {
  let fixture: ComponentFixture<ManageSubscriptions>;
  let component: ManageSubscriptions;
  let httpTesting: HttpTestingController;
  let sessionService: SessionService;

  const mockSub: SubscriptionDetail = {
    id_suscripcion: 1,
    id_empresa: 1,
    empresa_codigo: 'fashionstore-inicial',
    empresa_nombre: 'FashionStore Inicial',
    id_plan_saas: 2,
    plan_codigo: 'BASICO',
    plan_nombre: 'Plan Básico',
    plan_precio: 199,
    plan_moneda: 'BOB',
    plan_periodo_meses: 3,
    limite_sucursales: 2,
    tiene_ia: false,
    estado: 'ACTIVA',
    fecha_inicio: '2026-10-31T00:00:00',
    fecha_fin_periodo: '2027-01-31T00:00:00',
    dias_restantes: 92,
    renovacion_automatica: false,
  };

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [ManageSubscriptions],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    }).compileComponents();

    httpTesting = TestBed.inject(HttpTestingController);
    sessionService = TestBed.inject(SessionService);
    sessionService.saveAccessToken('superadmin-token-123');
    sessionService.saveUser({
      id_usuario: 1,
      nombre: 'Super',
      apellido: 'Admin',
      correo: 'superadmin@fashionstore.com',
      rol: 'SUPERADMIN',
      id_empresa: null,
    });

    fixture = TestBed.createComponent(ManageSubscriptions);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  function flushInitialData(): void {
    fixture.detectChanges();

    // 1. GET /empresas
    const compReq = httpTesting.expectOne((r) => r.url.includes('/api/saas/empresas'));
    compReq.flush({
      success: true,
      data: [{ id_empresa: 1, codigo: 'fashionstore-inicial', nombre: 'FashionStore Inicial' }],
      pagination: { total: 1, page: 1, page_size: 100, total_pages: 1 },
    });

    // 2. GET /suscripciones
    const subsReq = httpTesting.expectOne((r) => r.url === `${environment.apiUrl}/api/saas/suscripciones`);
    subsReq.flush({
      success: true,
      total: 1,
      data: [mockSub],
    });
  }

  it('7. Carga el listado multiempresa de suscripciones para SUPERADMIN al inicializarse', () => {
    flushInitialData();

    expect(component.subscriptions().length).toBe(1);
    expect(component.subscriptions()[0].empresa_codigo).toBe('fashionstore-inicial');
    expect(component.loading()).toBe(false);
  });

  it('8. Permite abrir modal de cambio de estado y ejecutar la transición administrativa', () => {
    flushInitialData();

    component.openStatusModal(mockSub, 'SUSPENDIDA');

    expect(component.statusModalOpen()).toBe(true);
    expect(component.targetSubscription()?.id_suscripcion).toBe(1);
    expect(component.targetNewStatus()).toBe('SUSPENDIDA');

    component.confirmStatusChange();

    const patchReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/suscripciones/1/estado`);
    expect(patchReq.request.method).toBe('PATCH');
    expect(patchReq.request.body.nuevo_estado).toBe('SUSPENDIDA');
    patchReq.flush({
      success: true,
      data: { ...mockSub, estado: 'SUSPENDIDA' },
    });

    // Re-consulta de la lista
    const reloadReq = httpTesting.expectOne((r) => r.url === `${environment.apiUrl}/api/saas/suscripciones`);
    reloadReq.flush({
      success: true,
      total: 1,
      data: [{ ...mockSub, estado: 'SUSPENDIDA' }],
    });

    expect(component.statusModalOpen()).toBe(false);
  });
});
