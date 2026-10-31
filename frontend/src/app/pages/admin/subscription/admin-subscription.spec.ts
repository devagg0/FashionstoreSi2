import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { SessionService } from '../../../core/services/session.service';
import { AdminSubscription } from './admin-subscription';

describe('AdminSubscription Component (CU06)', () => {
  let fixture: ComponentFixture<AdminSubscription>;
  let component: AdminSubscription;
  let httpTesting: HttpTestingController;
  let sessionService: SessionService;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [AdminSubscription],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParamMap: convertToParamMap({}) },
            queryParamMap: of(convertToParamMap({})),
          },
        },
      ],
    }).compileComponents();

    httpTesting = TestBed.inject(HttpTestingController);
    sessionService = TestBed.inject(SessionService);
    sessionService.saveAccessToken('admin-token-123');
    sessionService.saveUser({
      id_usuario: 5,
      nombre: 'Admin',
      apellido: 'Empresa',
      correo: 'admin@fashionstore.com',
      rol: 'ADMINISTRADOR',
      id_empresa: 1,
    });

    fixture = TestBed.createComponent(AdminSubscription);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  function flushInitialData(): void {
    fixture.detectChanges();

    // 1. GET /actual
    const subReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/suscripciones/actual`);
    expect(subReq.request.method).toBe('GET');
    subReq.flush({
      success: true,
      tiene_suscripcion_activa: true,
      data: {
        id_suscripcion: 1,
        id_empresa: 1,
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
      },
    });

    // 2. GET /planes
    const plansReq = httpTesting.expectOne(`${environment.apiUrl}/api/saas/suscripciones/planes`);
    expect(plansReq.request.method).toBe('GET');
    plansReq.flush({
      success: true,
      total: 2,
      data: [
        {
          id_plan_saas: 2,
          codigo: 'BASICO',
          nombre: 'Plan Básico',
          precio: 199,
          moneda: 'BOB',
          periodo_meses: 3,
          limite_sucursales: 2,
          tiene_ia: false,
          funcionalidades: [],
        },
        {
          id_plan_saas: 3,
          codigo: 'PROFESIONAL',
          nombre: 'Plan Profesional',
          precio: 499,
          moneda: 'BOB',
          periodo_meses: 6,
          limite_sucursales: 10,
          tiene_ia: true,
          funcionalidades: [],
        },
      ],
    });
  }

  it('5. Carga y muestra la suscripción activa y los planes comerciales oficiales al iniciar', () => {
    flushInitialData();

    expect(component.hasActiveSub()).toBe(true);
    expect(component.currentSub()?.plan_codigo).toBe('BASICO');
    expect(component.commercialPlans().length).toBe(2);
    expect(component.loading()).toBe(false);
  });

  it('6. Con suscripción activa, bloquea renovación anticipada y cambio de plan mostrando mensaje', () => {
    flushInitialData();

    // A) Bloquea cambio de plan
    component.openPlanChangeModal();
    expect(component.checkoutModalOpen()).toBe(false);
    expect(component.errorMessage()).toContain('Disponible al finalizar tu suscripción actual');

    // B) Bloquea renovación anticipada
    component.openRenewalModal();
    expect(component.checkoutModalOpen()).toBe(false);
    expect(component.errorMessage()).toContain('Disponible al finalizar tu suscripción actual');

    // C) Bloquea apertura directa de modal para cualquier plan
    const planBasico = component.commercialPlans()[0];
    component.openCheckoutModal(planBasico, 'RENOVACION');
    expect(component.checkoutModalOpen()).toBe(false);
    expect(component.errorMessage()).toContain('Disponible al finalizar tu suscripción actual');
  });
});
