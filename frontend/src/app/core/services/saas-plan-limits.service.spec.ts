import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  CompanyBranchConsumptionResponse,
  CompanyPlanLimitsResponse,
  SaasPlanLimitsService,
} from './saas-plan-limits.service';
import { SessionService } from './session.service';

describe('SaasPlanLimitsService (CU07)', () => {
  let service: SaasPlanLimitsService;
  let httpMock: HttpTestingController;

  const mockSessionService = {
    getAccessToken: () => 'mock-jwt-token-cu07',
  };

  const mockPlanLimitsResponse: CompanyPlanLimitsResponse = {
    success: true,
    id_empresa: 2,
    empresa_codigo: 'moda-oriente',
    empresa_nombre: 'Moda Oriente',
    tiene_suscripcion_activa: true,
    suscripcion: {
      id_suscripcion: 10,
      estado: 'ACTIVA',
      fecha_inicio: '2026-10-01T00:00:00',
      fecha_fin_periodo: '2027-01-01T00:00:00',
      dias_restantes: 62,
      renovacion_automatica: false,
      proveedor: 'STRIPE',
    },
    plan: {
      id_plan_saas: 2,
      codigo: 'BASICO',
      nombre: 'Plan Básico',
      descripcion: 'Plan Básico 2 sucursales',
      precio: '199.00',
      moneda: 'BOB',
      periodo_meses: 3,
    },
    consumo_sucursales: {
      limite_sucursales: 2,
      sucursales_activas: 1,
      sucursales_inactivas: 0,
      sucursales_totales: 1,
      disponibles_para_crear: 1,
      limite_alcanzado: false,
      puede_crear_sucursal: true,
    },
    funcionalidades: [
      { codigo: 'SUCURSALES', nombre: 'Sucursales', habilitada: true, limite: 2 },
      { codigo: 'PRODUCTOS', nombre: 'Productos', habilitada: true, limite: null },
      { codigo: 'VENTAS', nombre: 'Ventas', habilitada: true, limite: null },
      { codigo: 'REPORTES_IA', nombre: 'Reportes IA', habilitada: false, limite: null },
    ],
    permisos: {
      SUCURSALES: true,
      PRODUCTOS: true,
      VENTAS: true,
      REPORTES_IA: false,
    },
    tiene_ia: false,
    puede_crear_sucursal: true,
  };

  const mockBranchConsumptionResponse: CompanyBranchConsumptionResponse = {
    success: true,
    id_empresa: 2,
    empresa_codigo: 'moda-oriente',
    empresa_nombre: 'Moda Oriente',
    consumo: {
      limite_sucursales: 2,
      sucursales_activas: 2,
      sucursales_inactivas: 1,
      sucursales_totales: 3,
      disponibles_para_crear: 0,
      limite_alcanzado: true,
      puede_crear_sucursal: false,
    },
    sucursales: [
      {
        id_sucursal: 1,
        nombre: 'Sucursal Central',
        direccion: 'Av. Las Américas 123',
        estado: true,
        id_ciudad: 1,
      },
      {
        id_sucursal: 2,
        nombre: 'Sucursal Norte',
        direccion: 'Calle 5 #45',
        estado: true,
        id_ciudad: 1,
      },
      {
        id_sucursal: 3,
        nombre: 'Sucursal Sur',
        direccion: 'Av. Santos Dumont',
        estado: false,
        id_ciudad: 1,
      },
    ],
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SessionService, useValue: mockSessionService },
      ],
    });

    service = TestBed.inject(SaasPlanLimitsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('1. getCurrentPlanLimits consulta GET /api/saas/plan-vigente y actualiza las señales reactivas', () => {
    service.getCurrentPlanLimits().subscribe((resp) => {
      expect(resp.success).toBe(true);
      expect(resp.plan?.codigo).toBe('BASICO');
      expect(resp.tiene_suscripcion_activa).toBe(true);
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/saas/plan-vigente`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer mock-jwt-token-cu07');
    req.flush(mockPlanLimitsResponse);

    // Verificación de señales reactivas
    expect(service.currentPlanLimits()).toEqual(mockPlanLimitsResponse);
    expect(service.hasActiveSubscription()).toBe(true);
    expect(service.hasAiReports()).toBe(false);
    expect(service.branchLimit()).toBe(2);
    expect(service.activeBranchesCount()).toBe(1);
    expect(service.canCreateBranch()).toBe(true);
  });

  it('2. getCurrentBranchConsumption consulta GET /api/saas/plan-vigente/consumo-sucursales', () => {
    service.getCurrentBranchConsumption().subscribe((resp) => {
      expect(resp.success).toBe(true);
      expect(resp.consumo.sucursales_activas).toBe(2);
      expect(resp.consumo.limite_alcanzado).toBe(true);
    });

    const req = httpMock.expectOne(
      `${environment.apiUrl}/api/saas/plan-vigente/consumo-sucursales`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockBranchConsumptionResponse);

    expect(service.isBranchLimitReached()).toBe(true);
    expect(service.canCreateBranch()).toBe(false);
    expect(service.availableBranchesQuota()).toBe(0);
  });

  it('3. hasFeature retorna true para funciones habilitadas y false para no contratadas', () => {
    service.currentPlanLimits.set(mockPlanLimitsResponse);

    expect(service.hasFeature('VENTAS')).toBe(true);
    expect(service.hasFeature('PRODUCTOS')).toBe(true);
    expect(service.hasFeature('REPORTES_IA')).toBe(false);
    expect(service.hasFeature('MODULO_INEXISTENTE')).toBe(false);
  });

  it('4. getCompanyPlanLimitsById consulta GET /api/saas/empresas/{id}/plan-vigente para SUPERADMIN', () => {
    service.getCompanyPlanLimitsById(5).subscribe((resp) => {
      expect(resp.success).toBe(true);
      expect(resp.id_empresa).toBe(2);
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/saas/empresas/5/plan-vigente`);
    expect(req.request.method).toBe('GET');
    req.flush(mockPlanLimitsResponse);
  });

  it('5. getCompanyBranchConsumptionById consulta GET /api/saas/empresas/{id}/consumo-sucursales para SUPERADMIN', () => {
    service.getCompanyBranchConsumptionById(5).subscribe((resp) => {
      expect(resp.success).toBe(true);
      expect(resp.sucursales.length).toBe(3);
    });

    const req = httpMock.expectOne(
      `${environment.apiUrl}/api/saas/empresas/5/consumo-sucursales`,
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockBranchConsumptionResponse);
  });

  it('6. hasActiveSubscription es false cuando la empresa no cuenta con suscripción', () => {
    const unSubscribedResponse: CompanyPlanLimitsResponse = {
      ...mockPlanLimitsResponse,
      tiene_suscripcion_activa: false,
      suscripcion: null,
      plan: null,
      permisos: {},
      tiene_ia: false,
      puede_crear_sucursal: false,
    };

    service.currentPlanLimits.set(unSubscribedResponse);

    expect(service.hasActiveSubscription()).toBe(false);
    expect(service.hasAiReports()).toBe(false);
    expect(service.canCreateBranch()).toBe(false);
    expect(service.hasFeature('VENTAS')).toBe(false);
  });
});
