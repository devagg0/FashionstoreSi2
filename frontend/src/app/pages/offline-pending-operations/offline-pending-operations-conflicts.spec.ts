import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import {
  OfflineOperationConflictDiagnosis,
  OfflineConflictDiagnoseResponse,
  OfflineConflictResolveResponse,
  OfflineOperationResolutionResult,
} from '../../core/models/offline.model';
import { OfflineConflictsService } from '../../core/services/offline-conflicts.service';
import {
  OfflinePendingOperationItem,
  OfflinePendingOperationsService,
} from '../../core/services/offline-pending-operations.service';
import { OfflineSyncService } from '../../core/services/offline-sync.service';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { OfflinePendingOperations } from './offline-pending-operations';

describe('PK08 — CU14 Frontend: Gestionar conflictos y resultados de sincronización', () => {
  let fixture: ComponentFixture<OfflinePendingOperations>;
  let component: OfflinePendingOperations;

  let isOnlineSignal: ReturnType<typeof signal<boolean>>;
  let isSyncingSignal: ReturnType<typeof signal<boolean>>;
  let isDiagnosingSignal: ReturnType<typeof signal<boolean>>;
  let isResolvingSignal: ReturnType<typeof signal<boolean>>;
  let currentUserSignal: ReturnType<typeof signal<any>>;

  let mockOperationsService: {
    loadLocalOperations: ReturnType<typeof vi.fn>;
    verifyBatchStatuses: ReturnType<typeof vi.fn>;
  };
  let mockSyncService: {
    isSyncing: ReturnType<typeof signal<boolean>>;
    syncPendingOperations: ReturnType<typeof vi.fn>;
  };
  let mockConflictsService: {
    isDiagnosing: ReturnType<typeof signal<boolean>>;
    isResolving: ReturnType<typeof signal<boolean>>;
    diagnose: ReturnType<typeof vi.fn>;
    resolve: ReturnType<typeof vi.fn>;
    actionLabel: ReturnType<typeof vi.fn>;
    conflictTypeLabel: ReturnType<typeof vi.fn>;
  };

  const sampleOperations: OfflinePendingOperationItem[] = [
    {
      uuid_operacion: 'uuid-res-sched-1',
      uuid_entidad: 'uuid-res-sched-1',
      tipo: 'RESERVA',
      codigo_provisional: 'RES-LOC-SCHED1',
      codigo_servidor: null,
      fecha: '2026-11-06T09:00:00.000Z',
      id_sucursal: 1,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 10,
      actor_nombre: 'Ana Lopez',
      rol: 'CLIENTE',
      moneda: 'BOB',
      estado_comercial: 'REGISTRADA_LOCAL',
      estado_sincronizacion: 'CONFLICTO',
      importe: 220.0,
      metodo_pago: 'EFECTIVO',
      pago_simulado: false,
      confirmada_en_servidor: false,
      motivo_servidor: 'El horario programado de recogida expiró en el servidor',
      conflictos: [
        {
          tipo_conflicto: 'HORARIO_VENCIDO',
          codigo_conflicto: 'HORARIO_VENCIDO',
          detalle: 'Horario programado anterior a la fecha actual',
        },
      ],
      detalles: [],
    },
    {
      uuid_operacion: 'uuid-buy-price-2',
      uuid_entidad: 'uuid-buy-price-2',
      tipo: 'COMPRA',
      codigo_provisional: 'CMP-LOC-PRICE2',
      codigo_servidor: null,
      fecha: '2026-11-06T10:00:00.000Z',
      id_sucursal: 1,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 10,
      actor_nombre: 'Ana Lopez',
      rol: 'CLIENTE',
      moneda: 'BOB',
      estado_comercial: 'REGISTRADA_LOCAL',
      estado_sincronizacion: 'CONFLICTO',
      importe: 150.0,
      metodo_pago: 'QR',
      pago_simulado: true,
      confirmada_en_servidor: false,
      motivo_servidor: 'Precios modificados en el servidor central',
      conflictos: [
        {
          tipo_conflicto: 'PRECIO_MODIFICADO',
          codigo_conflicto: 'PRECIO_MODIFICADO',
          detalle: 'Precio neto actual es Bs 175.00 vs Bs 150.00 capturado',
        },
      ],
      detalles: [],
    },
    {
      uuid_operacion: 'uuid-sale-dep-3',
      uuid_entidad: 'uuid-sale-dep-3',
      tipo: 'VENTA',
      codigo_provisional: 'VTA-LOC-DEP3',
      codigo_servidor: null,
      fecha: '2026-11-06T11:00:00.000Z',
      id_sucursal: 1,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 20,
      actor_nombre: 'Carlos Cajero',
      rol: 'CAJERO',
      moneda: 'BOB',
      estado_comercial: 'REGISTRADA_LOCAL',
      estado_sincronizacion: 'CONFLICTO',
      importe: 220.0,
      metodo_pago: 'EFECTIVO',
      pago_simulado: false,
      confirmada_en_servidor: false,
      depende_de_uuid: 'uuid-res-sched-1',
      motivo_servidor: 'Operación dependiente bloqueada por reserva antecedente en conflicto',
      conflictos: [
        {
          tipo_conflicto: 'DEPENDENCIA_BLOQUEADA',
          codigo_conflicto: 'DEPENDENCIA_BLOQUEADA',
          detalle: 'Reserva previa no sincronizada',
        },
      ],
      detalles: [],
    },
  ];

  beforeEach(async () => {
    TestBed.resetTestingModule();

    isOnlineSignal = signal(true);
    isSyncingSignal = signal(false);
    isDiagnosingSignal = signal(false);
    isResolvingSignal = signal(false);
    currentUserSignal = signal({
      id_usuario: 10,
      id_empresa: 1,
      id_sucursal: 1,
      rol: 'CLIENTE',
      nombre: 'Ana',
      apellido: 'Lopez',
    });

    mockOperationsService = {
      loadLocalOperations: vi.fn().mockResolvedValue([...sampleOperations]),
      verifyBatchStatuses: vi.fn(),
    };

    mockSyncService = {
      isSyncing: isSyncingSignal,
      syncPendingOperations: vi.fn(),
    };

    mockConflictsService = {
      isDiagnosing: isDiagnosingSignal,
      isResolving: isResolvingSignal,
      diagnose: vi.fn(),
      resolve: vi.fn(),
      actionLabel: vi.fn((act: string) => {
        if (act === 'REPROGRAMAR_HORARIO') return 'Reprogramar horario de recogida';
        if (act === 'ACEPTAR_PRECIO_SERVIDOR') return 'Aceptar precios actuales del servidor';
        if (act === 'DESCARTAR_OPERACION') return 'Descartar operación';
        if (act === 'REINTENTAR_SIN_CAMBIOS') return 'Reintentar sincronización';
        return act;
      }),
      conflictTypeLabel: vi.fn((code: string) => {
        if (code === 'HORARIO_VENCIDO') return 'Horario de recogida expirado';
        if (code === 'PRECIO_MODIFICADO') return 'Precios o descuentos modificados';
        if (code === 'DEPENDENCIA_BLOQUEADA') return 'Bloqueada por fallo en operación previa';
        return code;
      }),
    };

    await TestBed.configureTestingModule({
      imports: [OfflinePendingOperations],
      providers: [
        provideRouter([]),
        { provide: OfflinePendingOperationsService, useValue: mockOperationsService },
        { provide: OfflineSyncService, useValue: mockSyncService },
        { provide: OfflineConflictsService, useValue: mockConflictsService },
        {
          provide: OfflineService,
          useValue: {
            isOnline: isOnlineSignal,
          },
        },
        {
          provide: SessionService,
          useValue: {
            currentUser: currentUserSignal,
            getUser: () => currentUserSignal(),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(OfflinePendingOperations);
    component = fixture.componentInstance;
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  afterEach(() => {
    TestBed.resetTestingModule();
  });

  it('1. Debe diagnosticar operaciones en conflicto y renderizar la comparativa local vs servidor con acciones permitidas por rol', async () => {
    const resOp = sampleOperations[0]; // uuid-res-sched-1

    const mockDiagnosisResponse: OfflineConflictDiagnoseResponse = {
      success: true,
      empresa_id: 1,
      id_usuario: 10,
      rol: 'CLIENTE',
      total_diagnosticadas: 1,
      ya_sincronizadas: 0,
      en_conflicto: 1,
      rechazadas: 0,
      listas_para_sincronizar: 0,
      diagnosticos: [
        {
          uuid_operacion: 'uuid-res-sched-1',
          uuid_entidad: 'uuid-res-sched-1',
          tipo_operacion: 'RESERVA',
          secuencia: 1,
          codigo_local: 'RES-LOC-SCHED1',
          confirmada_en_servidor: false,
          estado_resultado: 'EN_CONFLICTO',
          estado_sincronizacion: 'CONFLICTO',
          codigo_conflicto_principal: 'HORARIO_VENCIDO',
          motivo: 'El horario programado ya expiró; elija un horario sugerido dentro del horario de apertura',
          corregible: true,
          requiere_consentimiento: true,
          bloqueada_por_dependencia: false,
          conflictos: [
            {
              tipo_conflicto: 'HORARIO_VENCIDO',
              codigo_conflicto: 'HORARIO_VENCIDO',
              detalle: 'Horario expirado',
            },
          ],
          datos_actuales_servidor: {
            id_sucursal: 1,
            sucursal_nombre: 'Sucursal Central',
            sucursal_activa: true,
            hora_apertura_sucursal: '08:00',
            hora_cierre_sucursal: '19:00',
            horarios_sugeridos: [
              '2026-11-08T10:00:00.000Z',
              '2026-11-08T15:00:00.000Z',
            ],
            variantes: [],
          },
          acciones_permitidas: ['REPROGRAMAR_HORARIO', 'DESCARTAR_OPERACION'],
          mensaje: 'Conflicto de horario corregible con reprogramación',
        },
      ],
      diagnosticos_por_uuid: {},
      fecha_diagnostico: new Date().toISOString(),
      mensaje: 'Diagnóstico completado',
    };
    mockDiagnosisResponse.diagnosticos_por_uuid['uuid-res-sched-1'] = mockDiagnosisResponse.diagnosticos[0];
    mockConflictsService.diagnose.mockResolvedValue(mockDiagnosisResponse);

    // Ejecutar diagnóstico al hacer clic en "Gestionar conflicto"
    await component.manageConflict(resOp);
    fixture.detectChanges();

    // Verificaciones
    expect(mockConflictsService.diagnose).toHaveBeenCalledTimes(1);
    expect(component['activeConflictUuid']()).toBe('uuid-res-sched-1');

    const diag = component.getDiagnosis('uuid-res-sched-1');
    expect(diag).toBeDefined();
    expect(diag?.codigo_conflicto_principal).toBe('HORARIO_VENCIDO');
    expect(diag?.acciones_permitidas).toContain('REPROGRAMAR_HORARIO');
    expect(diag?.acciones_permitidas).toContain('DESCARTAR_OPERACION');

    // Comprobar que en el DOM se renderizó el panel interactivo
    const compiled = fixture.nativeElement as HTMLElement;
    const panel = compiled.querySelector('.ops-conflict-panel');
    expect(panel).toBeTruthy();
    expect(panel?.textContent).toContain('El horario programado ya expiró');
    expect(panel?.textContent).toContain('08:00 - 19:00');

    // Horarios sugeridos renderizados como chips
    const chips = compiled.querySelectorAll('.ops-chip');
    expect(chips.length).toBe(2);
  });

  it('2. Debe exigir consentimiento explícito para aplicar una resolución de precio y actualizar estados en confirmación', async () => {
    const buyOp = sampleOperations[1]; // uuid-buy-price-2

    const mockPriceDiagnosis: OfflineConflictDiagnoseResponse = {
      success: true,
      empresa_id: 1,
      id_usuario: 10,
      rol: 'CLIENTE',
      total_diagnosticadas: 1,
      ya_sincronizadas: 0,
      en_conflicto: 1,
      rechazadas: 0,
      listas_para_sincronizar: 0,
      diagnosticos: [
        {
          uuid_operacion: 'uuid-buy-price-2',
          uuid_entidad: 'uuid-buy-price-2',
          tipo_operacion: 'COMPRA',
          secuencia: 1,
          codigo_local: 'CMP-LOC-PRICE2',
          confirmada_en_servidor: false,
          estado_resultado: 'EN_CONFLICTO',
          estado_sincronizacion: 'CONFLICTO',
          codigo_conflicto_principal: 'PRECIO_MODIFICADO',
          motivo: 'El precio del producto subió a Bs 175.00 en PostgreSQL',
          corregible: true,
          requiere_consentimiento: true,
          bloqueada_por_dependencia: false,
          conflictos: [],
          datos_actuales_servidor: {
            id_sucursal: 1,
            sucursal_activa: true,
            horarios_sugeridos: [],
            variantes: [
              {
                id_variante_producto: 101,
                nombre_producto: 'Chaqueta Denim',
                sku: 'CHAQ-DNM-M',
                activa: true,
                stock_actual: 10,
                stock_reservado: 0,
                stock_disponible: 10,
                precio_base_servidor: 175.0,
                descuento_unitario_servidor: 0,
                precio_neto_servidor: 175.0,
                cantidad_solicitada: 1,
                precio_capturado_offline: 150.0,
              },
            ],
            total_servidor: 175.0,
          },
          acciones_permitidas: ['ACEPTAR_PRECIO_SERVIDOR', 'DESCARTAR_OPERACION'],
          mensaje: 'Precio modificado en servidor',
        },
      ],
      diagnosticos_por_uuid: {},
      fecha_diagnostico: new Date().toISOString(),
      mensaje: 'Diagnóstico completado',
    };
    mockPriceDiagnosis.diagnosticos_por_uuid['uuid-buy-price-2'] = mockPriceDiagnosis.diagnosticos[0];
    mockConflictsService.diagnose.mockResolvedValue(mockPriceDiagnosis);

    await component.manageConflict(buyOp);
    fixture.detectChanges();

    // Seleccionar acción ACEPTAR_PRECIO_SERVIDOR
    component.selectAction('ACEPTAR_PRECIO_SERVIDOR');
    expect(component['selectedAction']()).toBe('ACEPTAR_PRECIO_SERVIDOR');

    // 1. Intento sin consentimiento explícito: debe ser rechazado
    component['consentAccepted'].set(false);
    await component.applyResolution(buyOp);
    expect(mockConflictsService.resolve).not.toHaveBeenCalled();
    expect(component['feedbackMessage']()).toContain('Consentimiento requerido');

    // 2. Con consentimiento explícito
    component['consentAccepted'].set(true);

    const mockResolveResponse: OfflineConflictResolveResponse = {
      success: true,
      empresa_id: 1,
      id_usuario: 10,
      rol: 'CLIENTE',
      total_procesadas: 1,
      confirmadas: 1,
      descartadas: 0,
      en_conflicto: 0,
      rechazadas: 0,
      reintentables: 0,
      resultados: [
        {
          uuid_operacion: 'uuid-buy-price-2',
          uuid_entidad: 'uuid-buy-price-2',
          tipo_operacion: 'COMPRA',
          secuencia: 1,
          accion_aplicada: 'ACEPTAR_PRECIO_SERVIDOR',
          consentimiento_verificado: true,
          resuelta: true,
          descartada_por_usuario: false,
          confirmada: true,
          estado_resultado: 'CONFIRMADA',
          estado_sincronizacion: 'SINCRONIZADA',
          id_servidor: 405,
          codigo_servidor: 'CMP-SRV-405',
          codigo_local: 'CMP-LOC-PRICE2',
          estado_pago: 'PENDIENTE_VALIDACION',
          pago_simulado: true,
          total: 175.0,
          id_usuario: 10,
          id_empresa: 1,
          reintentable: false,
          conservar_en_cola: false,
          mensaje: 'Compra digital confirmada con precio actualizado del servidor',
          fecha_resolucion: new Date().toISOString(),
        },
      ],
      resultados_por_uuid: {},
      vinculaciones_codigos: {},
      fecha_resolucion: new Date().toISOString(),
      mensaje: 'Resolución aplicada exitosamente',
    };
    mockResolveResponse.resultados_por_uuid['uuid-buy-price-2'] = mockResolveResponse.resultados[0];
    mockConflictsService.resolve.mockResolvedValue(mockResolveResponse);

    await component.applyResolution(buyOp);

    // Verificar llamada al servicio con consentimiento explícito
    expect(mockConflictsService.resolve).toHaveBeenCalledWith([
      expect.objectContaining({
        uuid_operacion: 'uuid-buy-price-2',
        accion_resolucion: 'ACEPTAR_PRECIO_SERVIDOR',
        consentimiento_usuario: true,
      }),
    ]);

    // Verificar actualización de feedback y cierre del panel
    expect(component['activeConflictUuid']()).toBeNull();
    expect(component['feedbackMessage']()).toContain('CMP-SRV-405');
  });

  it('3. Debe bloquear operaciones dependientes hasta resolver su antecedente y desbloquearlas al confirmarse', async () => {
    const parentOp = sampleOperations[0]; // uuid-res-sched-1 (en conflicto)
    const depOp = sampleOperations[2]; // uuid-sale-dep-3 (depende_de_uuid = 'uuid-res-sched-1')

    // El antecedente aún no está sincronizado -> la dependiente debe estar bloqueada
    expect(component.isOperationBlocked(depOp)).toBe(true);
    expect(component.getBlockedReason(depOp)).toContain('Operación bloqueada');

    // Comprobar que en el template la tarjeta dependiente recibe indicador visual de bloqueo
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const cards = compiled.querySelectorAll('.ops-card');
    const depCard = cards[2];
    expect(depCard.classList.contains('ops-card--blocked')).toBe(true);
    expect(depCard.textContent).toContain('Bloqueada por dependencia');

    // Intentar aplicar resolución directamente sobre la dependiente bloqueada debe impedirse
    component['consentAccepted'].set(true);
    component['selectedAction'].set('REINTENTAR_SIN_CAMBIOS');
    await component.applyResolution(depOp);
    expect(mockConflictsService.resolve).not.toHaveBeenCalled();
    expect(component['feedbackMessage']()).toContain('Operación bloqueada');

    // Simular que el antecedente parentOp se resuelve y sincroniza con éxito
    parentOp.estado_sincronizacion = 'SINCRONIZADA';
    parentOp.confirmada_en_servidor = true;
    parentOp.codigo_servidor = 'RSV-SRV-100';

    // Ahora la operación dependiente debe desbloquearse
    expect(component.isOperationBlocked(depOp)).toBe(false);
    expect(component.getBlockedReason(depOp)).toBeNull();
  });
});

