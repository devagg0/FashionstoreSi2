import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  OfflineReservationDetailLocal,
  OfflineReservationLocal,
  OfflineSyncQueueItem,
} from '../../core/models/offline.model';
import { OfflineStorageService } from '../../core/services/offline-storage.service';
import { OfflineService } from '../../core/services/offline.service';
import {
  ReservationContext,
  ReservationSelectionItem,
  ReservationSelectionService,
} from '../../core/services/reservation-selection.service';
import { SessionService } from '../../core/services/session.service';
import { upcomingReservationDays } from '../../core/utils/reservation-schedule';
import { ReservationCheckout } from './reservation-checkout';

describe('Reserva offline del CLIENTE en flujo CU17 (PK08 - CU10 frontend)', () => {
  let user: { id_usuario: number; nombre: string; apellido: string; correo: string; rol: string; id_empresa: number };
  let saved: {
    reservations: OfflineReservationLocal[];
    details: OfflineReservationDetailLocal[];
    queue: OfflineSyncQueueItem[];
  };
  let stockDisponible: number;
  let storage: Record<string, unknown> & { saveOfflineReservationAtomic: ReturnType<typeof vi.fn> };

  const date = upcomingReservationDays()[1].value;
  const context: ReservationContext = {
    id_sucursal: 6,
    nombre_sucursal: 'Centro',
    nombre_ciudad: 'La Paz',
    direccion: 'Av. Principal',
    hora_apertura: '08:00:00',
    hora_cierre: '20:00:00',
    fecha: date,
    horario: '16:30',
  };
  const item: ReservationSelectionItem = {
    id_producto: 7,
    id_variante_producto: 9,
    producto: 'Chaqueta',
    imagen_principal: null,
    sku: 'CHA-M-NEG',
    talla: 'M',
    color: 'Negro',
    precio_referencia: '80.00',
    cantidad: 2,
  };

  beforeEach(() => {
    sessionStorage.clear();
    user = { id_usuario: 88, nombre: 'Camila', apellido: 'Rojas', correo: 'c@x.com', rol: 'CLIENTE', id_empresa: 2 };
    saved = { reservations: [], details: [], queue: [] };
    stockDisponible = 5;
    storage = {
      getStoredPackageSummary: async () => ({
        metadata: { sucursales_autorizadas_ids: [6] },
        isExpired: false,
        savedAt: '2026-11-01T10:00:00Z',
      }),
      getBranches: async () => [
        { id_sucursal: 6, id_ciudad: 1, ciudad: 'La Paz', nombre: 'Centro', direccion: 'Av. Principal', hora_apertura: '08:00:00', hora_cierre: '20:00:00', estado: true },
      ],
      getCatalogProducts: async () => [{ id_producto: 7, nombre: 'Chaqueta', precio: '80.00', estado: true }],
      getVariants: async () => [
        { id_variante_producto: 9, id_producto: 7, id_talla: 1, talla: 'M', id_color: 1, color: 'Negro', sku: 'CHA-M-NEG', precio: '80.00', estado: true },
      ],
      getInventory: async () => [
        { id_sucursal: 6, id_variante_producto: 9, stock_actual: 10, stock_reservado: 5, stock_disponible: stockDisponible, stock_minimo: 1 },
      ],
      getPendingReservedQuantities: async () => {
        const map = new Map<string, number>();
        for (const r of saved.reservations) {
          for (const d of saved.details.filter((x) => x.uuid_reserva_offline === r.uuid_reserva_offline)) {
            const key = `${r.id_sucursal}_${d.id_variante_producto}`;
            map.set(key, (map.get(key) ?? 0) + d.cantidad);
          }
        }
        return map;
      },
      getOfflineReservations: async () => [...saved.reservations],
      getOfflineReservationDetails: async (_e: number, _u: number, uuid?: string) =>
        saved.details.filter((d) => !uuid || d.uuid_reserva_offline === uuid),
      saveOfflineReservationAtomic: vi.fn(
        async (_e: number, _u: number, r: OfflineReservationLocal, d: OfflineReservationDetailLocal[], q: OfflineSyncQueueItem) => {
          saved.reservations.push(r);
          saved.details.push(...d);
          saved.queue.push(q);
        },
      ),
    };
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: OfflineStorageService, useValue: storage },
        {
          provide: SessionService,
          useValue: {
            getAccessToken: () => 'token',
            getUser: () => user,
            currentUser: () => user,
            logout: () => undefined,
          },
        },
      ],
    });
  });

  afterEach(() => sessionStorage.clear());

  it('1. sin internet guarda la reserva como pendiente local con payload compatible con el backend CU10', async () => {
    const service = TestBed.inject(OfflineService);
    const result = await service.registerClientOfflineReservation({
      uuid: 'a1b2c3d4-e5f6-7890-abcd-112233445566',
      context,
      items: [item],
    });

    expect(result.errors).toEqual([]);
    expect(result.receipt?.estado).toBe('REGISTRADA_LOCAL');
    expect(result.receipt?.codigo_local).toBe('RES-LOC-A1B2C3D4');
    expect(saved.reservations[0].estado).toBe('REGISTRADA_LOCAL');
    const queued = saved.queue[0];
    expect(queued.tipo_operacion).toBe('RESERVA');
    expect(queued.uuid_operacion).toBe('op-a1b2c3d4-e5f6-7890-abcd-112233445566');
    expect(queued.payload.id_sucursal).toBe(6);
    expect(queued.payload.fecha_atencion_programada).toBe(`${date}T16:30:00-04:00`);
    expect(queued.payload.detalles).toEqual([
      { id_variante_producto: 9, id_producto: 7, cantidad: 2, precio_referencial: 80 },
    ]);
    // El cliente/empresa/usuario no se envían: el backend los resuelve desde la sesión.
    expect(queued.payload).not.toHaveProperty('id_cliente');
    expect(queued.payload).not.toHaveProperty('id_empresa');
  });

  it('2. repetir el mismo UUID no duplica la reserva ni la cola', async () => {
    const service = TestBed.inject(OfflineService);
    const uuid = '11111111-2222-3333-4444-555555555555';
    await service.registerClientOfflineReservation({ uuid, context, items: [item] });
    const second = await service.registerClientOfflineReservation({ uuid, context, items: [item] });

    expect(second.alreadyStored).toBe(true);
    expect(second.receipt?.codigo_local).toBe('RES-LOC-11111111');
    expect(storage.saveOfflineReservationAtomic).toHaveBeenCalledTimes(1);
    expect(saved.reservations.length).toBe(1);
    expect(saved.queue.length).toBe(1);
  });

  it('3. rechaza stock local insuficiente considerando reservas pendientes locales', async () => {
    stockDisponible = 3;
    const service = TestBed.inject(OfflineService);
    const first = await service.registerClientOfflineReservation({
      uuid: 'uuid-stock-0000000001', context, items: [{ ...item, cantidad: 2 }],
    });
    expect(first.receipt).not.toBeNull();

    const second = await service.registerClientOfflineReservation({
      uuid: 'uuid-stock-0000000002', context, items: [{ ...item, cantidad: 2 }],
    });
    expect(second.receipt).toBeNull();
    expect(second.errors.join(' ')).toContain('Stock offline insuficiente');
    expect(storage.saveOfflineReservationAtomic).toHaveBeenCalledTimes(1);
  });

  it('4. valida horario de sucursal y rechaza horarios fuera de rango', async () => {
    const service = TestBed.inject(OfflineService);
    const result = await service.registerClientOfflineReservation({
      uuid: 'uuid-horario-0000000001',
      context: { ...context, horario: '22:00' },
      items: [item],
    });
    expect(result.receipt).toBeNull();
    expect(result.errors.join(' ')).toContain('horario');
    expect(storage.saveOfflineReservationAtomic).not.toHaveBeenCalled();
  });

  it('5. CAJERO (rol no cliente) no puede registrar reservas offline', async () => {
    user.rol = 'CAJERO';
    const service = TestBed.inject(OfflineService);
    const result = await service.registerClientOfflineReservation({
      uuid: 'uuid-cajero-00000000001', context, items: [item],
    });
    expect(result.receipt).toBeNull();
    expect(result.errors[0]).toContain('cliente');
    expect(storage.saveOfflineReservationAtomic).not.toHaveBeenCalled();
  });

  it('6. las reservas pendientes persisten y se listan tras recargar', async () => {
    const service = TestBed.inject(OfflineService);
    await service.registerClientOfflineReservation({ uuid: 'uuid-persist-0000000001', context, items: [item] });
    saved.reservations.push({ ...saved.reservations[0], uuid_reserva_offline: 'uuid-otra', estado: 'CONFIRMADA' });

    // Nueva instancia del servicio = recarga de la página; los datos viven en IndexedDB.
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: OfflineStorageService, useValue: storage },
        { provide: SessionService, useValue: { getAccessToken: () => 't', getUser: () => user, currentUser: () => user } },
      ],
    });
    const pending = await TestBed.inject(OfflineService).getPendingClientReservations();
    expect(pending.length).toBe(1);
    expect(pending[0].uuid_reserva_offline).toBe('uuid-persist-0000000001');
    expect(pending[0].estado).toBe('REGISTRADA_LOCAL');
  });

  it('7. checkout sin internet: doble clic guarda una sola vez y muestra comprobante sin afirmar confirmación', async () => {
    const offline = TestBed.inject(OfflineService);
    offline.isOnline.set(false);
    const selection = TestBed.inject(ReservationSelectionService);
    selection.start(context, item);
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ReservationCheckout);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      confirm: () => void;
      canSubmit: () => boolean;
      errorMessage: () => string;
    };
    for (let i = 0; i < 50 && !component.canSubmit(); i++) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    expect(component.canSubmit(), component.errorMessage()).toBe(true);
    component.confirm();
    component.confirm();
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));
    fixture.detectChanges();

    expect(storage.saveOfflineReservationAtomic).toHaveBeenCalledTimes(1);
    http.expectNone((request) => request.method === 'POST');
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('PENDIENTE DE SINCRONIZACIÓN');
    expect(text).toContain('no está confirmada');
    expect(selection.items().length).toBe(0);
    fixture.destroy();
  });
});

