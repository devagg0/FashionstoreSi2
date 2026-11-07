import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import {
  ServerBatchStatusResponse,
  OfflinePendingOperationItem,
  OfflinePendingOperationsService,
} from '../../core/services/offline-pending-operations.service';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { OfflinePendingOperations } from './offline-pending-operations';
import { signal } from '@angular/core';

describe('PK08 — CU12: Consultar operaciones locales pendientes', () => {
  let fixture: ComponentFixture<OfflinePendingOperations>;
  let component: OfflinePendingOperations;

  const mockOperations: OfflinePendingOperationItem[] = [
    {
      uuid_operacion: 'uuid-res-1',
      uuid_entidad: 'uuid-res-1',
      tipo: 'RESERVA',
      codigo_provisional: 'RSV-LOCAL-001',
      codigo_servidor: null,
      fecha: '2026-11-04T10:00:00.000Z',
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
      ruta_comprobante: undefined,
      confirmada_en_servidor: false,
      detalles: [
        {
          id_variante_producto: 101,
          producto_nombre: 'Blusa Seda',
          talla: 'M',
          color: 'Blanco',
          cantidad: 1,
          precio: 180.0,
          subtotal: 180.0,
        },
      ],
    },
    {
      uuid_operacion: 'uuid-buy-2',
      uuid_entidad: 'uuid-buy-2',
      tipo: 'COMPRA',
      codigo_provisional: 'CMP-LOCAL-002',
      codigo_servidor: null,
      fecha: '2026-11-04T10:30:00.000Z',
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
      ruta_comprobante: '/mis-compras/uuid-buy-2/comprobante',
      confirmada_en_servidor: false,
      detalles: [
        {
          id_variante_producto: 102,
          producto_nombre: 'Pantalón Denim',
          talla: '38',
          color: 'Azul',
          cantidad: 1,
          precio: 250.0,
          subtotal: 250.0,
        },
      ],
    },
    {
      uuid_operacion: 'uuid-sale-3',
      uuid_entidad: 'uuid-sale-3',
      tipo: 'VENTA',
      codigo_provisional: 'POS-LOCAL-003',
      codigo_servidor: null,
      fecha: '2026-11-04T11:00:00.000Z',
      id_sucursal: 2,
      sucursal_nombre: 'Sucursal Central',
      id_usuario: 5,
      actor_nombre: 'Carlos Cajero',
      rol: 'CAJERO',
      moneda: 'BOB',
      estado_comercial: 'REGISTRADA_LOCAL',
      estado_sincronizacion: 'PENDIENTE',
      importe: 320.0,
      metodo_pago: 'EFECTIVO',
      pago_simulado: false,
      ruta_comprobante: '/staff/ventas/uuid-sale-3/comprobante',
      confirmada_en_servidor: false,
      detalles: [
        {
          id_variante_producto: 103,
          producto_nombre: 'Chaqueta Cuero',
          talla: 'L',
          color: 'Negro',
          cantidad: 1,
          precio: 320.0,
          subtotal: 320.0,
        },
      ],
    },
  ];

  let mockOperationsService: {
    loadLocalOperations: ReturnType<typeof vi.fn>;
    verifyBatchStatuses: ReturnType<typeof vi.fn>;
  };
  let isOnlineSignal: ReturnType<typeof signal<boolean>>;
  let currentUserSignal: ReturnType<typeof signal<any>>;

  beforeEach(async () => {
    isOnlineSignal = signal(false);
    currentUserSignal = signal({
      id_usuario: 10,
      id_empresa: 1,
      id_sucursal: 2,
      rol: 'CLIENTE',
      nombre: 'Ana',
      apellido: 'Lopez',
    });

    mockOperationsService = {
      loadLocalOperations: vi.fn().mockImplementation((filters?: { tipo?: string; estadoSync?: string }) => {
        let filtered = [...mockOperations];
        if (filters?.tipo && filters.tipo !== 'TODOS') {
          filtered = filtered.filter((op) => op.tipo === filters.tipo);
        }
        if (filters?.estadoSync && filters.estadoSync !== 'TODOS') {
          filtered = filtered.filter((op) => op.estado_sincronizacion === filters.estadoSync);
        }
        return Promise.resolve(filtered);
      }),
      verifyBatchStatuses: vi.fn(),
    };

    await TestBed.configureTestingModule({
      imports: [OfflinePendingOperations],
      providers: [
        provideRouter([]),
        { provide: OfflinePendingOperationsService, useValue: mockOperationsService },
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

  it('1. Debe consultar y listar operaciones locales offline desde IndexedDB respetando aislamiento y métricas', async () => {
    expect(mockOperationsService.loadLocalOperations).toHaveBeenCalled();
    expect(component['operations']().length).toBe(3);
    expect(component['totalPending']()).toBe(3);
    expect(component['totalSynced']()).toBe(0);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('RSV-LOCAL-001');
    expect(compiled.textContent).toContain('CMP-LOCAL-002');
    expect(compiled.textContent).toContain('POS-LOCAL-003');
    expect(compiled.textContent).toContain('Sin conexión');
    expect(compiled.textContent).toContain('3 pendientes');
  });

  it('2. Debe permitir filtrar por tipo de operación y expandir detalles sin alterar ni borrar registros locales', async () => {
    // Filtrar por RESERVA
    component['filterTipo'].set('RESERVA');
    component.onFilterChange();
    await fixture.whenStable();

    expect(mockOperationsService.loadLocalOperations).toHaveBeenCalledWith({
      tipo: 'RESERVA',
      estadoSync: 'TODOS',
    });
    expect(component['operations']().length).toBe(1);
    expect(component['operations']()[0].codigo_provisional).toBe('RSV-LOCAL-001');

    // Desplegar prendas del item
    expect(component.isExpanded('uuid-res-1')).toBe(false);
    component.toggleDetails('uuid-res-1');
    expect(component.isExpanded('uuid-res-1')).toBe(true);

    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Blusa Seda');
    expect(compiled.textContent).toContain('Talla');
    expect(compiled.textContent).toContain('Precio unitario');

    // Colapsar
    component.toggleDetails('uuid-res-1');
    expect(component.isExpanded('uuid-res-1')).toBe(false);
  });

  it('3. Con conexión, debe verificar lotes con el servidor actualizando a SINCRONIZADA las confirmadas y manteniendo PENDIENTES las no encontradas', async () => {
    // Activar conexión
    isOnlineSignal.set(true);
    // Cargar todas
    component['filterTipo'].set('TODOS');
    component['filterEstadoSync'].set('TODOS');
    await component.load();
    fixture.detectChanges();

    const batchResponse: ServerBatchStatusResponse = {
      success: true,
      total_consultados: 3,
      total_sincronizados: 1,
      mensaje: 'Verificación batch completada exitosamente',
      operaciones: {
        'uuid-buy-2': {
          confirmada: true,
          estado_sincronizacion: 'SINCRONIZADA',
          codigo_servidor: 'VTA-SERVER-888',
        },
        // uuid-res-1 y uuid-sale-3 no han sido sincronizadas en el servidor aún
      },
    };

    mockOperationsService.verifyBatchStatuses.mockReturnValue(of(batchResponse));

    component.verifyWithServer();
    fixture.detectChanges();

    const ops = component['operations']();
    const buyOp = ops.find((o) => o.uuid_operacion === 'uuid-buy-2');
    const resOp = ops.find((o) => o.uuid_operacion === 'uuid-res-1');
    const saleOp = ops.find((o) => o.uuid_operacion === 'uuid-sale-3');

    // Item confirmado se actualiza a SINCRONIZADA con código de servidor
    expect(buyOp?.estado_sincronizacion).toBe('SINCRONIZADA');
    expect(buyOp?.confirmada_en_servidor).toBe(true);
    expect(buyOp?.codigo_servidor).toBe('VTA-SERVER-888');

    // Regla de oro CU12: Los no encontrados en servidor se mantienen PENDIENTES
    expect(resOp?.estado_sincronizacion).toBe('PENDIENTE');
    expect(resOp?.confirmada_en_servidor).toBe(false);
    expect(saleOp?.estado_sincronizacion).toBe('PENDIENTE');
    expect(saleOp?.confirmada_en_servidor).toBe(false);

    expect(component['totalSynced']()).toBe(1);
    expect(component['totalPending']()).toBe(2);
    expect(component['feedbackMessage']()).toContain('1 de 3 operaciones confirmadas');
  });
});
