import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { ReturnDetail } from '../../../core/services/returns.service';
import { SessionService } from '../../../core/services/session.service';
import { StaffReturnsPage } from './staff-returns';

const base = `${environment.apiUrl}/api/staff/returns`;
const sampleReturn: ReturnDetail = {
  id_devolucion: 25,
  id_venta: 10,
  tipo: 'DEVOLUCION',
  estado: 'SOLICITADA',
  motivo: 'Talla no adecuada',
  id_usuario_solicitante: 12,
  created_at: '2026-11-07T12:00:00',
  lineas: [
    {
      id_variante_producto: 101,
      cantidad: 1,
      cantidad_reintegrar: 0,
      importe_restitucion: '150.00',
    },
  ],
  reembolsos: [],
};

describe('CU16 Personal - Evaluar e Inspeccionar Solicitud', () => {
  let fixture: ComponentFixture<StaffReturnsPage>;
  let page: StaffReturnsPage;
  let http: HttpTestingController;

  function setup(id: string = '25', data: ReturnDetail = sampleReturn) {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { paramMap: of(convertToParamMap({ id })) },
        },
        {
          provide: SessionService,
          useValue: {
            getAccessToken: () => 'valid-staff-token',
            getUser: () => ({ id_usuario: 11 }),
            logout: () => {},
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(StaffReturnsPage);
    page = fixture.componentInstance;

    http.expectOne(`${base}/${id}`).flush({ success: true, data });
    fixture.detectChanges();
  }

  afterEach(() => {
    fixture?.destroy();
    http?.verify();
  });

  it('permite al cajero aceptar inicialmente una solicitud en estado SOLICITADA', () => {
    setup('25', sampleReturn);
    expect(page.detail()?.estado).toBe('SOLICITADA');

    page.open('ACEPTAR_INICIAL');
    expect(page.action()).toBe('ACEPTAR_INICIAL');

    page.confirm();
    const req = http.expectOne(`${base}/25/initial-review`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ resultado: 'ACEPTADA' });

    const acceptedReturn: ReturnDetail = {
      ...sampleReturn,
      estado: 'ACEPTADA_INICIALMENTE',
      id_usuario_evaluador: 11,
      fecha_evaluacion_inicial: '2026-11-07T12:30:00',
    };
    req.flush({ success: true, data: acceptedReturn });
    fixture.detectChanges();

    expect(page.detail()?.estado).toBe('ACEPTADA_INICIALMENTE');
    expect(page.success()).toContain('aceptada inicialmente');
  });

  it('permite confirmar la recepción de prenda y luego registrar la inspección física', () => {
    const pendingDeliveryReturn: ReturnDetail = {
      ...sampleReturn,
      estado: 'PENDIENTE_ENTREGA',
      modalidad_entrega: 'DELIVERY_SIMULADO',
      fecha_seleccion_modalidad: '2026-11-07T13:00:00',
    };
    setup('25', pendingDeliveryReturn);

    // 1. Confirmar recepción
    page.open('CONFIRMAR_RECEPCION');
    page.observacionesRecepcion.set('Paquete recibido en tienda');
    page.confirm();

    const recvReq = http.expectOne(`${base}/25/receive`);
    expect(recvReq.request.body).toEqual({ observaciones: 'Paquete recibido en tienda' });

    const receivedReturn: ReturnDetail = {
      ...pendingDeliveryReturn,
      estado: 'RECIBIDA',
      id_usuario_receptor: 11,
      fecha_recepcion: '2026-11-07T14:00:00',
      observaciones_inspeccion: 'Paquete recibido en tienda',
    };
    recvReq.flush({ success: true, data: receivedReturn });
    fixture.detectChanges();
    expect(page.detail()?.estado).toBe('RECIBIDA');

    // 2. Registrar inspección física y aprobar definitivamente
    page.open('INSPECCIONAR');
    page.estadoFisico.set('OPTIMO');
    page.etiquetasIntactas.set(true);
    page.correspondenciaCompra.set(true);
    page.observacionesInspeccion.set('Prenda limpia y con etiqueta original');
    page.resultadoInspeccion.set('APROBADA');
    page.confirm();

    const inspectReq = http.expectOne(`${base}/25/inspect`);
    expect(inspectReq.request.body).toEqual({
      resultado: 'APROBADA',
      estado_fisico: 'OPTIMO',
      etiquetas_intactas: true,
      correspondencia_compra: true,
      observaciones: 'Prenda limpia y con etiqueta original',
      motivo_rechazo: undefined,
    });

    const approvedReturn: ReturnDetail = {
      ...receivedReturn,
      estado: 'APROBADA',
      estado_fisico: 'OPTIMO',
      etiquetas_intactas: true,
      correspondencia_compra: true,
      id_usuario_inspector: 11,
      fecha_inspeccion: '2026-11-07T14:15:00',
      id_usuario_resolutor: 11,
      fecha_resolucion: '2026-11-07T14:15:00',
    };
    inspectReq.flush({ success: true, data: approvedReturn });
    fixture.detectChanges();

    expect(page.detail()?.estado).toBe('APROBADA');
    expect(page.success()).toContain('Inspección completada');
  });
});
