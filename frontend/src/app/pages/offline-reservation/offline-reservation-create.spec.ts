import '@angular/compiler';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import {
  OfflineBranchData,
  OfflineCategoryData,
  OfflineClientData,
  OfflineProductData,
  OfflineSizeData,
  OfflineStockData,
  OfflineStoredSummary,
  OfflineVariantData,
} from '../../core/models/offline.model';
import { OfflineStorageService } from '../../core/services/offline-storage.service';
import { SessionService } from '../../core/services/session.service';
import { OfflineReservationCreate } from './offline-reservation-create';

describe('OfflineReservationCreate (PK08 - CU10)', () => {
  let component: OfflineReservationCreate;
  let storageMock: any;

  const mockUser = {
    id_usuario: 15,
    nombre: 'Ana',
    apellido: 'Cajera',
    correo: 'ana@fashionstore.com',
    rol: 'CAJERO',
    id_empresa: 2,
  };

  const mockSessionService = {
    getAccessToken: () => 'mock-jwt-token-cu10',
    getUser: () => mockUser,
    currentUser: () => mockUser,
  };

  const mockSummary: OfflineStoredSummary = {
    metadata: {
      version: 'FS-OFFLINE-E2-cu10test',
      fecha_generacion: '2026-10-31T18:00:00Z',
      valido_hasta: '2026-11-02T18:00:00Z',
      vigencia_segundos: 172800,
      id_empresa: 2,
      empresa_codigo: 'moda-oriente',
      empresa_nombre: 'Moda Oriente',
      id_usuario: 15,
      usuario_rol: 'CAJERO',
      sucursales_autorizadas_ids: [10],
      suscripcion_activa: true,
      funcionalidad_offline: true,
      total_sucursales: 1,
      total_categorias: 1,
      total_productos: 1,
      total_variantes: 2,
      total_existencias: 2,
      total_clientes: 1,
    },
    savedAt: '2026-10-31T18:05:00Z',
    counts: {
      sucursales: 1,
      categorias: 1,
      tallas: 1,
      colores: 2,
      productos: 1,
      variantes: 2,
      existencias: 2,
      clientes: 1,
    },
    isExpired: false,
    timeRemainingText: '47h 50m restantes',
  };

  const mockBranches: OfflineBranchData[] = [
    {
      id_sucursal: 10,
      id_ciudad: 1,
      ciudad: 'Santa Cruz',
      nombre: 'Sucursal Central',
      direccion: 'Av. San Martín 123',
      estado: true,
    },
  ];

  const mockClients: OfflineClientData[] = [
    {
      id_cliente: 42,
      id_usuario: 88,
      nombre: 'Carlos',
      apellido: 'Mendoza',
      correo: 'carlos@cliente.com',
      telefono: '70012345',
    },
  ];

  const mockProducts: OfflineProductData[] = [
    {
      id_producto: 101,
      id_categoria: 1,
      categoria: 'Camisas',
      nombre: 'Camisa Lino Premium',
      seccion: 'HOMBRE',
      descripcion: 'Camisa 100% lino',
      precio: 250.0,
      estado: true,
    },
  ];

  const mockVariants: OfflineVariantData[] = [
    {
      id_variante_producto: 201,
      id_producto: 101,
      id_talla: 1,
      talla: 'M',
      id_color: 1,
      color: 'Blanco',
      sku: 'CAM-M-BLA',
      precio: 250.0,
      estado: true,
    },
    {
      id_variante_producto: 202,
      id_producto: 101,
      id_talla: 1,
      talla: 'M',
      id_color: 2,
      color: 'Azul',
      sku: 'CAM-M-AZU',
      precio: 260.0,
      estado: true,
    },
  ];

  const mockStock: OfflineStockData[] = [
    {
      id_inventario_sucursal: 501,
      id_sucursal: 10,
      id_variante_producto: 201,
      id_producto: 101,
      stock_actual: 10,
      stock_reservado: 2,
      stock_disponible: 8, // 8 disponibles descargados
      stock_minimo: 1,
      updated_at: '2026-10-31T18:00:00Z',
    },
    {
      id_inventario_sucursal: 502,
      id_sucursal: 10,
      id_variante_producto: 202,
      id_producto: 101,
      stock_actual: 3,
      stock_reservado: 2,
      stock_disponible: 1,
      stock_minimo: 1,
      updated_at: '2026-10-31T18:00:00Z',
    },
  ];

  const mockCategories: OfflineCategoryData[] = [
    { id_categoria: 1, nombre: 'Camisas', estado: true },
  ];

  beforeEach(() => {
    // Mapa con 2 unidades ya reservadas en local para la variante 201 en la sucursal 10
    const pendingMap = new Map<string, number>();
    pendingMap.set('10_201', 2);

    storageMock = {
      getStoredPackageSummary: vi.fn().mockResolvedValue(mockSummary),
      getBranches: vi.fn().mockResolvedValue(mockBranches),
      getClients: vi.fn().mockResolvedValue(mockClients),
      getCatalogProducts: vi.fn().mockResolvedValue(mockProducts),
      getVariants: vi.fn().mockResolvedValue(mockVariants),
      getInventory: vi.fn().mockResolvedValue(mockStock),
      getCategories: vi.fn().mockResolvedValue(mockCategories),
      getPendingReservedQuantities: vi.fn().mockResolvedValue(pendingMap),
      saveOfflineReservationAtomic: vi.fn().mockResolvedValue(undefined),
    };

    TestBed.configureTestingModule({
      imports: [OfflineReservationCreate],
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
        { provide: OfflineStorageService, useValue: storageMock },
      ],
    });

    const fixture = TestBed.createComponent(OfflineReservationCreate);
    component = fixture.componentInstance;
  });

  it('1. Debe cargar datos iniciales (sucursales, clientes, productos, existencias) exclusivamente desde IndexedDB', async () => {
    await component.ngOnInit();

    expect(storageMock.getStoredPackageSummary).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getBranches).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getClients).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getCatalogProducts).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getVariants).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getInventory).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getPendingReservedQuantities).toHaveBeenCalledWith(2, 15);

    expect(component.branches().length).toBe(1);
    expect(component.clients().length).toBe(1);
    expect(component.products().length).toBe(1);
    expect(component.isLoading()).toBe(false);
  });

  it('2. Debe preseleccionar la sucursal autorizada y descontar reservas locales pendientes para calcular stock estimado', async () => {
    await component.ngOnInit();

    // Sucursal única se preselecciona
    expect(component.selectedBranchId()).toBe(10);

    // Seleccionar producto 101 y variante 201
    component.selectedProductId.set(101);
    component.selectedVariantId.set(201);

    // Stock descargado: 8, Reservado en local pendiente: 2 => Disponible estimado: 6
    const stockEstimado = component.estimatedStockForSelectedVariant();
    expect(stockEstimado).toBe(6);
  });

  it('3. Debe impedir agregar cantidades superiores al stock estimado disponible', async () => {
    await component.ngOnInit();

    component.selectedProductId.set(101);
    component.selectedVariantId.set(201); // 6 disponibles estimados
    component.lineQuantity.set(7); // Cantidad superior a 6

    component.addLineItem();

    expect(component.lineItems().length).toBe(0);
    expect(component.validationErrors().length).toBeGreaterThan(0);
    expect(component.validationErrors()[0]).toContain('supera el stock disponible estimado (6)');
  });

  it('4. Debe agregar prendas válidas al pedido y calcular subtotales y totales referenciales correctamente', async () => {
    await component.ngOnInit();

    component.selectedProductId.set(101);
    component.selectedVariantId.set(201);
    component.lineQuantity.set(2);

    component.addLineItem();

    expect(component.lineItems().length).toBe(1);
    const item = component.lineItems()[0];
    expect(item.id_variante_producto).toBe(201);
    expect(item.producto_nombre).toBe('Camisa Lino Premium');
    expect(item.sku).toBe('CAM-M-BLA');
    expect(item.cantidad).toBe(2);
    expect(item.precio_referencial).toBe(250);
    expect(item.subtotal).toBe(500);

    expect(component.totalReferencial()).toBe(500);
    expect(component.saldoPendiente()).toBe(500);

    // Ingresar adelanto de 100
    component.adelantoEfectivo.set(100);
    expect(component.saldoPendiente()).toBe(400);
  });

  it('5. Debe guardar atómicamente la reserva en IndexedDB con estado REGISTRADA_LOCAL, UUID idempotente y comprobante local', async () => {
    await component.ngOnInit();

    // Configurar cliente
    component.onSelectClient(42);

    // Agregar prenda
    component.selectedProductId.set(101);
    component.selectedVariantId.set(201);
    component.lineQuantity.set(2);
    component.addLineItem();

    // Adelanto opcional
    component.adelantoEfectivo.set(150);
    component.observaciones.set('Cliente retira el fin de semana');

    // Registrar
    await component.submitReservation();

    expect(storageMock.saveOfflineReservationAtomic).toHaveBeenCalledTimes(1);

    const [empresaId, userId, reservation, details, queueItem] =
      storageMock.saveOfflineReservationAtomic.mock.calls[0];

    expect(empresaId).toBe(2);
    expect(userId).toBe(15);

    // Verificación de la entidad reserva
    expect(reservation.estado).toBe('REGISTRADA_LOCAL');
    expect(reservation.id_sucursal).toBe(10);
    expect(reservation.id_cliente).toBe(42);
    expect(reservation.total_referencial).toBe(500);
    expect(reservation.adelanto_efectivo).toBe(150);
    expect(reservation.saldo_pendiente).toBe(350);
    expect(reservation.codigo_local).toMatch(/^RES-LOC-[A-Z0-9]{8}$/);
    expect(reservation.uuid_reserva_offline.length).toBeGreaterThan(20);

    // Verificación de detalles
    expect(details.length).toBe(1);
    expect(details[0].id_variante_producto).toBe(201);
    expect(details[0].cantidad).toBe(2);
    expect(details[0].subtotal).toBe(500);

    // Verificación de la cola Outbox compatible con FastAPI CU10
    expect(queueItem.tipo_operacion).toBe('RESERVA');
    expect(queueItem.estado).toBe('REGISTRADA_LOCAL');
    expect(queueItem.payload.uuid_reserva_offline).toBe(reservation.uuid_reserva_offline);
    expect(queueItem.payload.id_sucursal).toBe(10);
    expect(queueItem.payload.id_cliente).toBe(42);
    expect(queueItem.payload.detalles.length).toBe(1);

    // Modal de confirmación y comprobante
    expect(component.showSuccessModal()).toBe(true);
    expect(component.successReservation()).not.toBeNull();
    expect(component.successReservation()?.codigo_local).toBe(reservation.codigo_local);
  });

  it('6. Debe manejar fallos de IndexedDB (ej. cuota excedida) conservando los datos del formulario', async () => {
    storageMock.saveOfflineReservationAtomic.mockRejectedValue(
      new Error('QuotaExceededError: El almacenamiento del dispositivo está lleno.'),
    );

    await component.ngOnInit();
    component.onSelectClient(42);
    component.selectedProductId.set(101);
    component.selectedVariantId.set(201);
    component.lineQuantity.set(1);
    component.addLineItem();

    await component.submitReservation();

    expect(component.errorMessage()).toContain('QuotaExceededError');
    expect(component.errorMessage()).toContain('Sus datos se conservan en pantalla');
    expect(component.isSubmitting()).toBe(false);
    expect(component.lineItems().length).toBe(1); // Datos intactos
    expect(component.showSuccessModal()).toBe(false);
  });

  it('7. Debe advertir si el paquete está vencido pero permitir el registro local de la reserva', async () => {
    const expiredSummary: OfflineStoredSummary = {
      ...mockSummary,
      isExpired: true,
      timeRemainingText: 'Expirado',
    };
    storageMock.getStoredPackageSummary.mockResolvedValue(expiredSummary);

    await component.ngOnInit();

    expect(component.summary()?.isExpired).toBe(true);

    component.onSelectClient(42);
    component.selectedProductId.set(101);
    component.selectedVariantId.set(201);
    component.lineQuantity.set(1);
    component.addLineItem();

    await component.submitReservation();

    expect(storageMock.saveOfflineReservationAtomic).toHaveBeenCalledTimes(1);
    const [, , reservation] = storageMock.saveOfflineReservationAtomic.mock.calls[0];
    expect(reservation.estado).toBe('REGISTRADA_LOCAL');
  });
});

