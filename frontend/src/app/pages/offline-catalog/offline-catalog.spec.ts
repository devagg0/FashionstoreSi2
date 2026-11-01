import '@angular/compiler';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import {
  OfflineBranchData,
  OfflineCategoryData,
  OfflineColorData,
  OfflineProductData,
  OfflineProductDetail,
  OfflineSizeData,
  OfflineStockData,
  OfflineStoredSummary,
  OfflineVariantData,
} from '../../core/models/offline.model';
import { OfflineStorageService } from '../../core/services/offline-storage.service';
import { SessionService } from '../../core/services/session.service';
import { OfflineCatalog } from './offline-catalog';

describe('OfflineCatalog (PK08 - CU09)', () => {
  let component: OfflineCatalog;
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
    getAccessToken: () => 'mock-jwt-token-cu09',
    getUser: () => mockUser,
    currentUser: () => mockUser,
  };

  const mockStoredSummary: OfflineStoredSummary = {
    metadata: {
      version: 'FS-OFFLINE-E2-cu09test',
      fecha_generacion: '2026-10-31T18:00:00Z',
      valido_hasta: '2026-11-01T18:00:00Z',
      vigencia_segundos: 86400,
      id_empresa: 2,
      empresa_codigo: 'moda-oriente',
      empresa_nombre: 'Moda Oriente',
      id_usuario: 15,
      usuario_rol: 'CAJERO',
      sucursales_autorizadas_ids: [10],
      suscripcion_activa: true,
      funcionalidad_offline: true,
      total_sucursales: 1,
      total_categorias: 2,
      total_productos: 2,
      total_variantes: 3,
      total_existencias: 3,
      total_clientes: 0,
    },
    savedAt: '2026-10-31T18:05:00Z',
    counts: {
      sucursales: 1,
      categorias: 2,
      tallas: 2,
      colores: 2,
      productos: 2,
      variantes: 3,
      existencias: 3,
      clientes: 0,
    },
    isExpired: false,
    timeRemainingText: '23h 50m restantes',
  };

  const mockProducts: OfflineProductData[] = [
    {
      id_producto: 101,
      id_categoria: 1,
      categoria: 'Camisas',
      nombre: 'Camisa Lino Premium',
      seccion: 'HOMBRE',
      descripcion: 'Camisa 100% lino natural',
      precio: 249.5,
      imagen_principal: 'https://cdn.fashionstore.com/camisa1.jpg',
      imagenes: ['https://cdn.fashionstore.com/camisa1.jpg'],
      estado: true,
    },
    {
      id_producto: 102,
      id_categoria: 2,
      categoria: 'Vestidos',
      nombre: 'Vestido Seda Floral',
      seccion: 'MUJER',
      descripcion: 'Vestido fresco de seda estampada',
      precio: 380.0,
      imagen_principal: null,
      imagenes: [],
      estado: true,
    },
  ];

  const mockCategories: OfflineCategoryData[] = [
    { id_categoria: 1, nombre: 'Camisas', estado: true },
    { id_categoria: 2, nombre: 'Vestidos', estado: true },
  ];

  const mockSizes: OfflineSizeData[] = [
    { id_talla: 1, nombre: 'M', estado: true },
    { id_talla: 2, nombre: 'L', estado: true },
  ];

  const mockColors: OfflineColorData[] = [
    { id_color: 1, nombre: 'Blanco', codigo_hex: '#ffffff', estado: true },
    { id_color: 2, nombre: 'Azul', codigo_hex: '#0000ff', estado: true },
  ];

  const mockVariants: OfflineVariantData[] = [
    {
      id_variante_producto: 201,
      id_producto: 101,
      id_talla: 1,
      talla: 'M',
      id_color: 1,
      color: 'Blanco',
      color_hex: '#ffffff',
      sku: 'CAM-M-BLA',
      precio: 249.5,
      estado: true,
    },
    {
      id_variante_producto: 202,
      id_producto: 101,
      id_talla: 2,
      talla: 'L',
      id_color: 2,
      color: 'Azul',
      color_hex: '#0000ff',
      sku: 'CAM-L-AZU',
      precio: 249.5,
      estado: true,
    },
    {
      id_variante_producto: 203,
      id_producto: 102,
      id_talla: 1,
      talla: 'M',
      id_color: 2,
      color: 'Azul',
      color_hex: '#0000ff',
      sku: 'VES-M-AZU',
      precio: 380.0,
      estado: true,
    },
  ];

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

  const mockStock: OfflineStockData[] = [
    {
      id_inventario_sucursal: 501,
      id_sucursal: 10,
      id_variante_producto: 201,
      id_producto: 101,
      stock_actual: 10,
      stock_reservado: 2,
      stock_disponible: 8,
      stock_minimo: 1,
      updated_at: '2026-10-31T18:00:00Z',
    },
    {
      id_inventario_sucursal: 502,
      id_sucursal: 10,
      id_variante_producto: 202,
      id_producto: 101,
      stock_actual: 5,
      stock_reservado: 5,
      stock_disponible: 0, // Agotado
      stock_minimo: 1,
      updated_at: '2026-10-31T18:00:00Z',
    },
    {
      id_inventario_sucursal: 503,
      id_sucursal: 10,
      id_variante_producto: 203,
      id_producto: 102,
      stock_actual: 7,
      stock_reservado: 1,
      stock_disponible: 6,
      stock_minimo: 1,
      updated_at: '2026-10-31T18:00:00Z',
    },
  ];

  beforeEach(() => {
    storageMock = {
      getStoredPackageSummary: vi.fn().mockResolvedValue(mockStoredSummary),
      getCatalogProducts: vi.fn().mockResolvedValue(mockProducts),
      getCategories: vi.fn().mockResolvedValue(mockCategories),
      getSizes: vi.fn().mockResolvedValue(mockSizes),
      getColors: vi.fn().mockResolvedValue(mockColors),
      getVariants: vi.fn().mockResolvedValue(mockVariants),
      getInventory: vi.fn().mockResolvedValue(mockStock),
      getBranches: vi.fn().mockResolvedValue(mockBranches),
      getProductDetail: vi.fn().mockImplementation((empId: number, uId: number, prodId: number) => {
        if (prodId === 101) {
          const detail: OfflineProductDetail = {
            producto: mockProducts[0],
            categoriaNombre: 'Camisas',
            variantes: [
              {
                id_variante_producto: 201,
                id_producto: 101,
                sku: 'CAM-M-BLA',
                talla: 'M',
                color: 'Blanco',
                color_hex: '#ffffff',
                precio: 249.5,
                estado: true,
                stockTotalDisponible: 8,
                disponibilidadPorSucursal: [
                  {
                    id_sucursal: 10,
                    nombre_sucursal: 'Sucursal Central',
                    ciudad: 'Santa Cruz',
                    stock_actual: 10,
                    stock_reservado: 2,
                    stock_disponible: 8,
                  },
                ],
              },
            ],
            totalStockDisponible: 8,
            sucursalesConStock: 1,
            disponibilidadPorSucursal: [
              {
                id_sucursal: 10,
                nombre_sucursal: 'Sucursal Central',
                ciudad: 'Santa Cruz',
                stock_actual: 15,
                stock_reservado: 7,
                stock_disponible: 8,
              },
            ],
          };
          return Promise.resolve(detail);
        }
        return Promise.resolve(null);
      }),
    };

    TestBed.configureTestingModule({
      imports: [OfflineCatalog],
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
        { provide: OfflineStorageService, useValue: storageMock },
      ],
    });

    const fixture = TestBed.createComponent(OfflineCatalog);
    component = fixture.componentInstance;
  });

  it('1. Debe cargar el catálogo y las existencias exclusivamente desde IndexedDB', async () => {
    await component.ngOnInit();

    expect(storageMock.getCatalogProducts).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getCategories).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getVariants).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getInventory).toHaveBeenCalledWith(2, 15);
    expect(storageMock.getBranches).toHaveBeenCalledWith(2, 15);

    expect(component.rawProducts().length).toBe(2);
    expect(component.enrichedItems().length).toBe(2);
    expect(component.isLoading()).toBe(false);
  });

  it('2. Debe calcular el stock disponible y enriquecer los productos del catálogo local', async () => {
    await component.ngOnInit();

    const items = component.enrichedItems();
    const camisa = items.find((i) => i.producto.id_producto === 101);
    expect(camisa).toBeDefined();
    // 8 disponibles de la variante 201 + 0 disponibles de la 202 = 8
    expect(camisa?.totalStockDisponible).toBe(8);
    expect(camisa?.categoriaNombre).toBe('Camisas');
    expect(camisa?.totalVariantes).toBe(2);
    expect(camisa?.skus).toContain('CAM-M-BLA');
    expect(camisa?.skus).toContain('CAM-L-AZU');
  });

  it('3. Debe filtrar productos localmente por término de búsqueda (nombre y SKU)', async () => {
    await component.ngOnInit();

    // Búsqueda por nombre
    component.searchTerm.set('Floral');
    expect(component.filteredItems().length).toBe(1);
    expect(component.filteredItems()[0].producto.nombre).toBe('Vestido Seda Floral');

    // Búsqueda por SKU de variante
    component.searchTerm.set('CAM-L-AZU');
    expect(component.filteredItems().length).toBe(1);
    expect(component.filteredItems()[0].producto.id_producto).toBe(101);

    // Búsqueda sin coincidencias
    component.searchTerm.set('Zapatos');
    expect(component.filteredItems().length).toBe(0);
  });

  it('4. Debe filtrar productos por categoría, talla y color de forma reactiva', async () => {
    await component.ngOnInit();

    // Filtro categoría
    component.selectedCategory.set('Vestidos');
    expect(component.filteredItems().length).toBe(1);
    expect(component.filteredItems()[0].producto.nombre).toBe('Vestido Seda Floral');

    component.selectedCategory.set('TODAS');

    // Filtro talla
    component.selectedSize.set('L');
    expect(component.filteredItems().length).toBe(1);
    expect(component.filteredItems()[0].producto.nombre).toBe('Camisa Lino Premium');

    // Filtro color
    component.selectedSize.set('TODAS');
    component.selectedColor.set('Blanco');
    expect(component.filteredItems().length).toBe(1);
    expect(component.filteredItems()[0].producto.nombre).toBe('Camisa Lino Premium');
  });

  it('5. Debe filtrar productos por disponibilidad (sólo con stock)', async () => {
    await component.ngOnInit();

    // Ambos productos tienen stock disponible (8 y 6)
    component.onlyInStock.set(true);
    expect(component.filteredItems().length).toBe(2);

    // Modificar stock temporal para probar producto agotado vs producto con existencias
    component.rawStock.set([
      {
        id_inventario_sucursal: 999,
        id_sucursal: 10,
        id_variante_producto: 201,
        id_producto: 101,
        stock_actual: 5,
        stock_reservado: 5,
        stock_disponible: 0, // Producto 101 sin stock disponible
        stock_minimo: 1,
        updated_at: '2026-10-31T18:00:00Z',
      },
      {
        id_inventario_sucursal: 503,
        id_sucursal: 10,
        id_variante_producto: 203,
        id_producto: 102,
        stock_actual: 7,
        stock_reservado: 1,
        stock_disponible: 6, // Producto 102 con stock disponible
        stock_minimo: 1,
        updated_at: '2026-10-31T18:00:00Z',
      },
    ]);

    expect(component.filteredItems().length).toBe(1);
    expect(component.filteredItems()[0].producto.id_producto).toBe(102);
  });

  it('6. Debe abrir el detalle del producto con variantes y disponibilidad por sucursal autorizada', async () => {
    await component.ngOnInit();

    await component.openProductDetail(101);

    expect(storageMock.getProductDetail).toHaveBeenCalledWith(2, 15, 101);
    expect(component.isDetailOpen()).toBe(true);

    const detail = component.selectedProductDetail();
    expect(detail).toBeDefined();
    expect(detail?.producto.id_producto).toBe(101);
    expect(detail?.variantes.length).toBe(1);
    expect(detail?.variantes[0].sku).toBe('CAM-M-BLA');
    expect(detail?.variantes[0].precio).toBe(249.5);
    expect(detail?.disponibilidadPorSucursal[0].nombre_sucursal).toBe('Sucursal Central');
    expect(detail?.disponibilidadPorSucursal[0].stock_disponible).toBe(8);

    component.closeProductDetail();
    expect(component.isDetailOpen()).toBe(false);
    expect(component.selectedProductDetail()).toBeNull();
  });

  it('7. Debe detectar advertencia de paquete expirado y ofrecer enlace de actualización', async () => {
    storageMock.getStoredPackageSummary.mockResolvedValueOnce({
      ...mockStoredSummary,
      isExpired: true,
      timeRemainingText: 'Expirado',
    });

    await component.ngOnInit();

    expect(component.summary()?.isExpired).toBe(true);
    expect(component.offlineOperationUrl()).toBe('/staff/offline');
  });
});

