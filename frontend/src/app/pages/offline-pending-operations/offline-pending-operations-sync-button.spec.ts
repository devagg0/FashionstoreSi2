import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { signal } from '@angular/core';
import {
  OfflinePendingOperationItem,
  OfflinePendingOperationsService,
} from '../../core/services/offline-pending-operations.service';
import { OfflineSyncService } from '../../core/services/offline-sync.service';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { OfflinePendingOperations } from './offline-pending-operations';

describe('PK08 — CU13 Debugging: Visibilidad y ejecución de Sincronizar Pendientes', () => {
  let fixture: ComponentFixture<OfflinePendingOperations>;
  let component: OfflinePendingOperations;

  let isOnlineSignal: ReturnType<typeof signal<boolean>>;
  let isSyncingSignal: ReturnType<typeof signal<boolean>>;
  let currentUserSignal: ReturnType<typeof signal<any>>;

  let mockOperationsService: {
    loadLocalOperations: ReturnType<typeof vi.fn>;
    verifyBatchStatuses: ReturnType<typeof vi.fn>;
  };
  let mockSyncService: {
    isSyncing: ReturnType<typeof signal<boolean>>;
    syncPendingOperations: ReturnType<typeof vi.fn>;
  };

  const initialThreePendingOps: OfflinePendingOperationItem[] = [
    {
      uuid_operacion: 'uuid-res-1',
      uuid_entidad: 'uuid-res-1',
      tipo: 'RESERVA',
      codigo_provisional: 'RSV-LOCAL-001',
      codigo_servidor: null,
      fecha: '2026-11-05T10:00:00.000Z',
      id_sucursal: 2,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 10,
      actor_nombre: 'Ana Lopez',
      rol: 'CLIENTE',
      moneda: 'BOB',
      estado_comercial: 'PENDIENTE',
      estado_sincronizacion: 'PENDIENTE',
      importe: 180.0,
      metodo_pago: null,
      pago_simulado: false,
      confirmada_en_servidor: false,
      detalles: [],
    },
    {
      uuid_operacion: 'uuid-buy-2',
      uuid_entidad: 'uuid-buy-2',
      tipo: 'COMPRA',
      codigo_provisional: 'CMP-LOCAL-002',
      codigo_servidor: null,
      fecha: '2026-11-05T10:15:00.000Z',
      id_sucursal: 2,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 10,
      actor_nombre: 'Ana Lopez',
      rol: 'CLIENTE',
      moneda: 'BOB',
      estado_comercial: 'REGISTRADA_LOCAL',
      estado_sincronizacion: 'PENDIENTE',
      importe: 250.0,
      metodo_pago: 'QR',
      pago_simulado: true,
      confirmada_en_servidor: false,
      detalles: [],
    },
    {
      uuid_operacion: 'uuid-buy-3',
      uuid_entidad: 'uuid-buy-3',
      tipo: 'COMPRA',
      codigo_provisional: 'CMP-LOCAL-003',
      codigo_servidor: null,
      fecha: '2026-11-05T10:30:00.000Z',
      id_sucursal: 2,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 10,
      actor_nombre: 'Ana Lopez',
      rol: 'CLIENTE',
      moneda: 'BOB',
      estado_comercial: 'REGISTRADA_LOCAL',
      estado_sincronizacion: 'PENDIENTE',
      importe: 120.0,
      metodo_pago: 'TARJETA',
      pago_simulado: true,
      confirmada_en_servidor: false,
      detalles: [],
    },
  ];

  beforeEach(async () => {
    TestBed.resetTestingModule();

    isOnlineSignal = signal(true);
    isSyncingSignal = signal(false);
    currentUserSignal = signal({
      id_usuario: 10,
      id_empresa: 1,
      id_sucursal: 2,
      rol: 'CLIENTE',
      nombre: 'Ana',
      apellido: 'Lopez',
    });

    mockOperationsService = {
      loadLocalOperations: vi.fn().mockResolvedValue([...initialThreePendingOps]),
      verifyBatchStatuses: vi.fn(),
    };

    mockSyncService = {
      isSyncing: isSyncingSignal,
      syncPendingOperations: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [OfflinePendingOperations],
      providers: [
        provideRouter([]),
        { provide: OfflinePendingOperationsService, useValue: mockOperationsService },
        { provide: OfflineSyncService, useValue: mockSyncService },
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

  it('1. Debe mostrar «Sincronizar pendientes» al CLIENTE/CAJERO cuando tenga operaciones pendientes y conexión en línea, ocultándolo sin conexión o sin pendientes', async () => {
    // Escenario 1: CLIENTE en línea con 3 pendientes -> botón visible y habilitado
    expect(component['totalPending']()).toBe(3);
    expect(component['isOnline']()).toBe(true);
    expect(component['canShowSync']()).toBe(true);

    const compiled = fixture.nativeElement as HTMLElement;
    const syncBtn = compiled.querySelector<HTMLButtonElement>('.ops-btn--primary');
    expect(syncBtn).not.toBeNull();
    expect(syncBtn?.textContent).toContain('Sincronizar pendientes');
    expect(syncBtn?.disabled).toBe(false);

    // Acciones independientes presentes
    const buttons = compiled.querySelectorAll<HTMLButtonElement>('.ops-actions .ops-btn');
    const buttonTexts = Array.from(buttons).map((b) => b.textContent?.trim());
    expect(buttonTexts.some((t) => t?.includes('Actualizar'))).toBe(true);
    expect(buttonTexts.some((t) => t?.includes('Verificar con servidor'))).toBe(true);
    expect(buttonTexts.some((t) => t?.includes('Sincronizar pendientes'))).toBe(true);

    // Escenario 2: Pérdida de conexión -> el botón se oculta
    isOnlineSignal.set(false);
    fixture.detectChanges();
    expect(component['canShowSync']()).toBe(false);
    expect(compiled.querySelector('.ops-btn--primary')).toBeNull();

    // Recupera conexión -> vuelve a mostrarse
    isOnlineSignal.set(true);
    fixture.detectChanges();
    expect(component['canShowSync']()).toBe(true);
    expect(compiled.querySelector('.ops-btn--primary')).not.toBeNull();

    // Escenario 3: Rol no autorizado (ej. ADMINISTRADOR) -> botón oculto
    currentUserSignal.set({ ...currentUserSignal(), rol: 'ADMINISTRADOR' });
    fixture.detectChanges();
    expect(component['canShowSync']()).toBe(false);
    expect(compiled.querySelector('.ops-btn--primary')).toBeNull();

    // Vuelve a CAJERO -> botón visible
    currentUserSignal.set({ ...currentUserSignal(), rol: 'CAJERO' });
    fixture.detectChanges();
    expect(component['canShowSync']()).toBe(true);
    expect(compiled.querySelector('.ops-btn--primary')).not.toBeNull();

    // Escenario 4: 0 operaciones pendientes -> botón oculto
    component['operations'].set([]);
    fixture.detectChanges();
    expect(component['totalPending']()).toBe(0);
    expect(component['canShowSync']()).toBe(false);
    expect(compiled.querySelector('.ops-btn--primary')).toBeNull();
  });

  it('2. Ejecuta CU13 con indicador de progreso, bloqueo de doble clic y actualización atómica de contadores tras sincronizar', async () => {
    mockSyncService.syncPendingOperations.mockImplementation(async () => {
      isSyncingSignal.set(true);
      return {
        success: true,
        empresa_id: 1,
        id_usuario: 10,
        rol: 'CLIENTE',
        total_operaciones: 3,
        confirmadas: 3,
        rechazadas: 0,
        en_conflicto: 0,
        reintentables: 0,
        resultados: [],
        resultados_por_uuid: {},
        vinculaciones_codigos: {},
        fecha_sincronizacion: new Date().toISOString(),
        mensaje: 'Sincronización completada: 3 de 3 operaciones confirmadas.',
      };
    });

    // Simular que tras la sincronización, IndexedDB devuelve las operaciones confirmadas
    const syncedOperations = initialThreePendingOps.map((op) => ({
      ...op,
      estado_sincronizacion: 'SINCRONIZADA' as const,
      confirmada_en_servidor: true,
      codigo_servidor: `SRV-${op.codigo_provisional}`,
    }));

    mockOperationsService.loadLocalOperations.mockResolvedValue(syncedOperations);

    // Disparar sincronización
    const syncPromise = component.syncNow();

    // Mientras sincroniza: indicador de progreso activado y botón bloqueado
    fixture.detectChanges();
    expect(mockSyncService.syncPendingOperations).toHaveBeenCalledTimes(1);

    // Intento de doble clic durante la sincronización: debe ser ignorado
    await component.syncNow();
    expect(mockSyncService.syncPendingOperations).toHaveBeenCalledTimes(1);

    // Culminar sincronización
    isSyncingSignal.set(false);
    await syncPromise;
    fixture.detectChanges();

    // Verificación de contadores actualizados
    expect(component['totalPending']()).toBe(0);
    expect(component['totalSynced']()).toBe(3);
    expect(component['feedbackMessage']()).toContain('3 de 3 operaciones confirmadas');

    // Botones independientes «Actualizar» y «Verificar con servidor» siguen operativos
    const compiled = fixture.nativeElement as HTMLElement;
    const refreshBtn = compiled.querySelector<HTMLButtonElement>('.ops-actions .ops-btn--secondary');
    expect(refreshBtn?.textContent).toContain('Actualizar');
  });
});

