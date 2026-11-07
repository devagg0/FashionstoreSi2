import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { environment } from '../../../../environments/environment';
import {
  OfflineReservationDetailLocal,
  OfflineReservationLocal,
  OfflineSyncQueueItem,
} from '../../../core/models/offline.model';
import { OfflineStorageService } from '../../../core/services/offline-storage.service';
import { OfflineService } from '../../../core/services/offline.service';
import { SessionService } from '../../../core/services/session.service';
import {
  StaffReservationDetail,
  StaffReservationsService,
} from '../../../core/services/staff-reservations.service';

describe('PK08 - CU11: Cajero - Caché y Operación de Reservas Offline (FashionStore)', () => {
  let cashierUser: {
    id_usuario: number;
    nombre: string;
    apellido: string;
    correo: string;
    rol: string;
    id_empresa: number;
  };

  let localReservations: OfflineReservationLocal[];
  let localReservationDetails: OfflineReservationDetailLocal[];
  let localSyncQueue: OfflineSyncQueueItem[];

  let storageMock: Record<string, unknown>;
  let reservationsService: StaffReservationsService;
  let offlineService: OfflineService;
  let sessionService: SessionService;
  let httpTesting: HttpTestingController;

  const url = `${environment.apiUrl}/api/staff/reservations`;

  const sampleServerReservation: StaffReservationDetail = {
    id_reserva: 88,
    codigo: 'RSV-20261104-7B44CEA067',
    estado: 'PENDIENTE',
    created_at: '2026-11-04T10:00:00Z',
    fecha_atencion_programada: '2026-11-04T17:00:00Z',
    fecha_expiracion: '2026-11-04T20:00:00Z',
    fecha_atencion: null,
    cliente: {
      id_cliente: 42,
      nombre: 'Lucia',
      apellido: 'Mendez',
      correo: 'lucia@test.com',
      telefono: '78912345',
    },
    sucursal: {
      id_sucursal: 1,
      nombre: 'Sucursal Central',
      direccion: 'Av. Las Palmas 500',
      ciudad: { id_ciudad: 1, nombre: 'Santa Cruz' },
    },
    cantidad_prendas: 2,
    total: '350.00',
    prendas: [
      {
        id_variante_producto: 501,
        sku: 'VES-ELEG-M',
        id_producto: 120,
        producto: 'Vestido Elegante',
        imagen_principal: 'https://cdn.fashionstore.com/v1.jpg',
        talla: { id_talla: 2, nombre: 'M' },
        color: { id_color: 4, nombre: 'Azul Marino', codigo_hex: '#000080' },
        cantidad: 2,
        precio_reservado: '175.00',
        subtotal: '350.00',
      },
    ],
  };

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();

    cashierUser = {
      id_usuario: 5,
      nombre: 'Pedro',
      apellido: 'Cajero',
      correo: 'pedro@fashionstore.com',
      rol: 'CAJERO',
      id_empresa: 1,
    };

    localReservations = [];
    localReservationDetails = [];
    localSyncQueue = [];

    storageMock = {
      getBranches: async () => [
        {
          id_sucursal: 1,
          id_ciudad: 1,
          ciudad: 'Santa Cruz',
          nombre: 'Sucursal Central',
          direccion: 'Av. Las Palmas 500',
          estado: true,
        },
      ],
      getCatalogProducts: async () => [
        {
          id_producto: 120,
          id_categoria: 1,
          nombre: 'Vestido Elegante',
          seccion: 'MUJER',
          precio: 175,
          estado: true,
        },
      ],
      getVariants: async () => [
        {
          id_variante_producto: 501,
          id_producto: 120,
          id_talla: 2,
          talla: 'M',
          id_color: 4,
          color: 'Azul Marino',
          sku: 'VES-ELEG-M',
          precio: 175,
          estado: true,
        },
      ],
      getOfflineReservations: async () => [...localReservations],
      getOfflineReservationDetails: async (
        _empresaId: number,
        _userId: number,
        uuid?: string,
      ) => {
        if (uuid) {
          return localReservationDetails.filter((d) => d.uuid_reserva_offline === uuid);
        }
        return [...localReservationDetails];
      },
      saveStaffReservations: async (
        _empresaId: number,
        _userId: number,
        reservations: OfflineReservationLocal[],
        details: OfflineReservationDetailLocal[] = [],
      ) => {
        const pendingEntities = new Set(
          localSyncQueue
            .filter((item) => item.tipo_operacion === 'RESERVA')
            .map((item) => item.uuid_entidad),
        );

        for (const res of reservations) {
          if (!pendingEntities.has(res.uuid_reserva_offline)) {
            const idx = localReservations.findIndex(
              (r) => r.uuid_reserva_offline === res.uuid_reserva_offline,
            );
            if (idx >= 0) {
              localReservations[idx] = res;
            } else {
              localReservations.push(res);
            }
          }
        }

        if (details.length > 0) {
          const uuids = new Set(reservations.map((r) => r.uuid_reserva_offline));
          localReservationDetails = localReservationDetails.filter(
            (d) => !uuids.has(d.uuid_reserva_offline),
          );
          localReservationDetails.push(...details);
        }
      },
      updateOfflineReservationState: async (
        _empresaId: number,
        _userId: number,
        reservation: OfflineReservationLocal,
        queueItem?: OfflineSyncQueueItem,
      ) => {
        const idx = localReservations.findIndex(
          (r) => r.uuid_reserva_offline === reservation.uuid_reserva_offline,
        );
        if (idx >= 0) {
          localReservations[idx] = reservation;
        } else {
          localReservations.push(reservation);
        }
        if (queueItem) {
          localSyncQueue.push(queueItem);
        }
      },
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: OfflineStorageService, useValue: storageMock },
      ],
    });

    sessionService = TestBed.inject(SessionService);
    offlineService = TestBed.inject(OfflineService);
    httpTesting = TestBed.inject(HttpTestingController);

    sessionService.saveAccessToken('caj-token-jwt');
    sessionService.saveUser(cashierUser);

    reservationsService = TestBed.inject(StaffReservationsService);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  it('1. almacena en IndexedDB al consultar online y lista la reserva RSV-20261104-7B44CEA067 sin internet tras recargar sin mostrar "Sin resultados"', async () => {
    // 1. Simulación online: cajero consulta la lista de reservas
    offlineService.isOnline.set(true);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);

    const list$ = reservationsService.listReservations({ page: 1, pageSize: 12 });
    const listPromise = firstValueFrom(list$);

    const req = httpTesting.expectOne((r) => r.url === url);
    req.flush({
      success: true,
      data: [sampleServerReservation],
      pagination: { page: 1, page_size: 12, total: 1, total_pages: 1 },
      message: 'OK',
    });

    const onlineRes = await listPromise;
    expect(onlineRes.data.length).toBe(1);
    expect(onlineRes.data[0].codigo).toBe('RSV-20261104-7B44CEA067');

    // Esperar micro-tareas de persistencia asíncrona
    await new Promise((resolve) => setTimeout(resolve, 50));

    // Verificar que se guardó en el almacenamiento persistente
    expect(localReservations.length).toBe(1);
    expect(localReservations[0].codigo_local).toBe('RSV-20261104-7B44CEA067');
    expect(localReservations[0].id_sucursal).toBe(1);

    // Verificar que la sucursal quedó respaldada en localStorage para sobrevivir recargas offline
    const storedBranch = localStorage.getItem(`fashionstore_staff_branch_${cashierUser.id_usuario}`);
    expect(storedBranch).toBeTruthy();
    expect(JSON.parse(storedBranch!).branch.id_sucursal).toBe(1);

    // 2. Simular activar Offline y recargar la página (nueva instancia de servicio con estado offline)
    offlineService.isOnline.set(false);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    const reloadedService = TestBed.inject(StaffReservationsService);

    // Consultar reservas offline
    const offlineList = await firstValueFrom(reloadedService.listReservations());

    // Asegurar que NO retorne vacío ("Sin resultados") y presente datos válidos
    expect(offlineList.data.length).toBe(1);
    const offlineRow = offlineList.data[0];
    expect(offlineRow.codigo).toBe('RSV-20261104-7B44CEA067');
    expect(offlineRow.estado).toBe('PENDIENTE');
    expect(offlineRow.cantidad_prendas).toBe(2);
    expect(offlineRow.sucursal.id_sucursal).toBe(1);
    expect(offlineRow.cliente.nombre).toBe('Lucia');
  });

  it('2. permite consultar detalle y realizar transiciones PENDIENTE -> CONFIRMADA -> ATENDIDA offline registrando la cola para CU13 y protegiendo el estado local', async () => {
    // Preparar estado offline inicial con la reserva RSV-20261104-7B44CEA067 ya en IndexedDB
    offlineService.isOnline.set(false);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);

    localReservations = [
      {
        uuid_reserva_offline: sampleServerReservation.codigo,
        codigo_local: sampleServerReservation.codigo,
        id_reserva: sampleServerReservation.id_reserva,
        id_empresa: 1,
        id_usuario: cashierUser.id_usuario,
        id_sucursal: 1,
        id_cliente: 42,
        cliente_nombre: 'Lucia',
        cliente_apellido: 'Mendez',
        cliente_correo: 'lucia@test.com',
        fecha_reserva_offline: sampleServerReservation.created_at,
        fecha_atencion_programada: sampleServerReservation.fecha_atencion_programada,
        fecha_expiracion: sampleServerReservation.fecha_expiracion,
        total_referencial: 350,
        saldo_pendiente: 350,
        estado: 'PENDIENTE',
        cantidad_prendas: 2,
        created_at: sampleServerReservation.created_at,
      },
    ];

    localReservationDetails = [
      {
        id_detalle_local: 1,
        uuid_reserva_offline: sampleServerReservation.codigo,
        id_variante_producto: 501,
        id_producto: 120,
        producto_nombre: 'Vestido Elegante',
        sku: 'VES-ELEG-M',
        talla: 'M',
        color: 'Azul Marino',
        cantidad: 2,
        precio_referencial: 175,
        subtotal: 350,
      },
    ];

    // Consultar detalle offline por código
    const detailResp = await firstValueFrom(
      reservationsService.getReservationByCode('RSV-20261104-7B44CEA067'),
    );
    expect(detailResp.data.codigo).toBe('RSV-20261104-7B44CEA067');
    expect(detailResp.data.prendas.length).toBe(1);
    expect(detailResp.data.prendas[0].cantidad).toBe(2);

    // Transición 1: PENDIENTE -> CONFIRMADA
    const confirmResp = await firstValueFrom(
      reservationsService.confirmReservation(sampleServerReservation.id_reserva),
    );
    expect(confirmResp.data.estado).toBe('CONFIRMADA');
    expect(localReservations[0].estado).toBe('CONFIRMADA');
    expect(localSyncQueue.length).toBe(1);
    expect(localSyncQueue[0].payload.accion).toBe('confirm');

    // Transición 2: CONFIRMADA -> ATENDIDA
    const attendResp = await firstValueFrom(
      reservationsService.attendReservation(sampleServerReservation.id_reserva),
    );
    expect(attendResp.data.estado).toBe('ATENDIDA');
    expect(localReservations[0].estado).toBe('ATENDIDA');
    expect(localReservations[0].fecha_atencion).toBeTruthy();
    expect(localSyncQueue.length).toBe(2);
    expect(localSyncQueue[1].payload.accion).toBe('attend');

    // Verificar protección: saveStaffReservations no debe revertir una reserva con transición pendiente en cola
    const saveFn = storageMock['saveStaffReservations'] as (
      e: number,
      u: number,
      r: OfflineReservationLocal[],
    ) => Promise<void>;
    await saveFn(1, cashierUser.id_usuario, [
      {
        ...localReservations[0],
        estado: 'PENDIENTE', // El servidor aún la tiene en PENDIENTE
      },
    ]);
    expect(localReservations[0].estado).toBe('ATENDIDA');
  });

  it('3. aísla reservas de otras sucursales y borradores pendientes de clientes REGISTRADA_LOCAL para no confundirlas en la vista del cajero', async () => {
    offlineService.isOnline.set(false);
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);

    // Pre-establecer contexto de sucursal 1 para el cajero
    localStorage.setItem(
      `fashionstore_staff_branch_${cashierUser.id_usuario}`,
      JSON.stringify({
        userId: cashierUser.id_usuario,
        branch: {
          id_sucursal: 1,
          nombre: 'Sucursal Central',
          direccion: 'Av. Las Palmas 500',
          ciudad: { id_ciudad: 1, nombre: 'Santa Cruz' },
        },
      }),
    );

    localReservations = [
      // 1. Reserva oficial autorizada de la sucursal 1 del cajero
      {
        uuid_reserva_offline: 'RSV-20261104-7B44CEA067',
        codigo_local: 'RSV-20261104-7B44CEA067',
        id_reserva: 88,
        id_empresa: 1,
        id_usuario: cashierUser.id_usuario,
        id_sucursal: 1,
        total_referencial: 350,
        saldo_pendiente: 350,
        estado: 'PENDIENTE',
        cantidad_prendas: 2,
        fecha_reserva_offline: '2026-11-04T10:00:00Z',
        created_at: '2026-11-04T10:00:00Z',
        fecha_atencion_programada: '2026-11-04T17:00:00Z',
      },
      // 2. Borrador local no sincronizado del CLIENTE (CU10 - REGISTRADA_LOCAL sin id_reserva)
      {
        uuid_reserva_offline: 'draft-client-uuid-999',
        codigo_local: 'RES-LOC-0001',
        id_reserva: undefined, // Sin ID de servidor
        id_empresa: 1,
        id_usuario: 99, // Usuario cliente
        id_sucursal: 1,
        total_referencial: 120,
        saldo_pendiente: 120,
        estado: 'REGISTRADA_LOCAL',
        cantidad_prendas: 1,
        fecha_reserva_offline: '2026-11-04T11:00:00Z',
        created_at: '2026-11-04T11:00:00Z',
        fecha_atencion_programada: '2026-11-04T18:00:00Z',
      },
      // 3. Reserva oficial de OTRA sucursal (sucursal 99)
      {
        uuid_reserva_offline: 'RSV-OTRA-SUCURSAL-123',
        codigo_local: 'RSV-OTRA-SUCURSAL-123',
        id_reserva: 999,
        id_empresa: 1,
        id_usuario: 50,
        id_sucursal: 99, // Sucursal distinta
        total_referencial: 200,
        saldo_pendiente: 200,
        estado: 'PENDIENTE',
        cantidad_prendas: 1,
        fecha_reserva_offline: '2026-11-04T09:00:00Z',
        created_at: '2026-11-04T09:00:00Z',
        fecha_atencion_programada: '2026-11-04T16:00:00Z',
      },
    ];

    const result = await firstValueFrom(reservationsService.listReservations());

    // Solo debe listarse la reserva autorizada de su sucursal asignada
    expect(result.data.length).toBe(1);
    expect(result.data[0].codigo).toBe('RSV-20261104-7B44CEA067');
    expect(result.data[0].id_reserva).toBe(88);

    // Intentar acceder a la reserva de otra sucursal por código debe ser rechazado
    await expect(
      firstValueFrom(reservationsService.getReservationByCode('RSV-OTRA-SUCURSAL-123')),
    ).rejects.toThrow();
  });
});
