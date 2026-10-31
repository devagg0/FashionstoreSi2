import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  CommercialPlansResponse,
  CurrentSubscriptionResponse,
  SaasSubscriptionsService,
  VerifyPaymentResponse,
} from './saas-subscriptions.service';
import { SessionService } from './session.service';

describe('SaasSubscriptionsService', () => {
  let service: SaasSubscriptionsService;
  let httpMock: HttpTestingController;

  const mockSessionService = {
    getAccessToken: () => 'fake-jwt-token',
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SessionService, useValue: mockSessionService },
      ],
    });

    service = TestBed.inject(SaasSubscriptionsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('1. listCommercialPlans consulta GET /api/saas/suscripciones/planes con cabecera Authorization', () => {
    const mockPlansResp: CommercialPlansResponse = {
      success: true,
      total: 1,
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
      ],
    };

    service.listCommercialPlans().subscribe((resp) => {
      expect(resp.success).toBe(true);
      expect(resp.data.length).toBe(1);
      expect(resp.data[0].codigo).toBe('BASICO');
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/saas/suscripciones/planes`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer fake-jwt-token');
    req.flush(mockPlansResp);
  });

  it('2. getCurrentSubscription consulta GET /api/saas/suscripciones/actual e incluye empresa_id si se especifica', () => {
    const mockSubResp: CurrentSubscriptionResponse = {
      success: true,
      tiene_suscripcion_activa: true,
      data: {
        id_suscripcion: 10,
        id_empresa: 1,
        id_plan_saas: 2,
        plan_codigo: 'BASICO',
        plan_nombre: 'Plan Básico',
        plan_precio: 199,
        plan_moneda: 'BOB',
        plan_periodo_meses: 3,
        tiene_ia: false,
        estado: 'ACTIVA',
        fecha_inicio: '2026-10-31T00:00:00',
        fecha_fin_periodo: '2027-01-31T00:00:00',
        dias_restantes: 92,
        renovacion_automatica: false,
      },
    };

    service.getCurrentSubscription(1).subscribe((resp) => {
      expect(resp.tiene_suscripcion_activa).toBe(true);
      expect(resp.data?.plan_codigo).toBe('BASICO');
    });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/saas/suscripciones/actual?empresa_id=1`);
    expect(req.request.method).toBe('GET');
    req.flush(mockSubResp);
  });

  it('3. createCardCheckout envía POST con id_plan_saas y tipo_operacion', () => {
    service
      .createCardCheckout({ id_plan_saas: 3, tipo_operacion: 'CAMBIO_PLAN' })
      .subscribe((resp) => {
        expect(resp.id_sesion).toBe('cs_test_abc');
        expect(resp.tipo_operacion).toBe('CAMBIO_PLAN');
      });

    const req = httpMock.expectOne(`${environment.apiUrl}/api/saas/suscripciones/checkout/tarjeta`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body.id_plan_saas).toBe(3);
    expect(req.request.body.tipo_operacion).toBe('CAMBIO_PLAN');
    req.flush({
      success: true,
      message: 'Sesión creada',
      id_sesion: 'cs_test_abc',
      url_checkout: 'https://checkout.stripe.com/pay',
      tipo_operacion: 'CAMBIO_PLAN',
      metodo_pago: 'TARJETA',
      monto: 499,
      moneda: 'BOB',
      id_plan_saas: 3,
      plan_codigo: 'PROFESIONAL',
      plan_nombre: 'Plan Profesional',
    });
  });

  it('4. verifyPayment llama a POST /api/saas/suscripciones/verificar-pago/{session_id}', () => {
    const mockVerifyResp: VerifyPaymentResponse = {
      success: true,
      message: 'Plan contratado exitosamente.',
      id_suscripcion: 10,
      estado: 'ACTIVA',
      plan_codigo: 'BASICO',
      tipo_operacion: 'CONTRATACION',
      fecha_inicio: '2026-10-31T00:00:00',
      fecha_fin_periodo: '2027-01-31T00:00:00',
      dias_restantes: 92,
    };

    service.verifyPayment('cs_test_xyz123').subscribe((resp) => {
      expect(resp.success).toBe(true);
      expect(resp.id_suscripcion).toBe(10);
    });

    const req = httpMock.expectOne(
      `${environment.apiUrl}/api/saas/suscripciones/verificar-pago/cs_test_xyz123`,
    );
    expect(req.request.method).toBe('POST');
    req.flush(mockVerifyResp);
  });
});
