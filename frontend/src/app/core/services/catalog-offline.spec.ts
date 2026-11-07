import '@angular/compiler';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { environment } from '../../../environments/environment';
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
} from '../models/offline.model';
import { CatalogAvailabilityService } from './catalog-availability.service';
import { CatalogService } from './catalog.service';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

describe('PK08 - CU09: Consultar catálogo y disponibilidad offline (Web Angular PWA)', () => {
  let catalogService: CatalogService;
  let availabilityService: CatalogAvailabilityService;
  let offlineService: OfflineService;
  let storageService: OfflineStorageService;
  let httpMock: HttpTestingController;

  const mockClientUser = {
    id_usuario: 88,
    nombre: 'Camila',
    apellido: 'Rojas',
    correo: 'camila.cliente@gmail.com',
    rol: 'CLIENTE',
    id_empresa: 2,
  };

  const mockSessionService = {
    getAccessToken: () => 'mock-jwt-client-cu09',
    getUser: () => mockClientUser,
    currentUser: () => mockClientUser,
  };

  const mockBranches: OfflineBranchData[] = [
    {
      id_sucursal: 10,
      id_ciudad: 1,
      ciudad: 'Santa Cruz',
      nombre: 'Sucursal Central',
      direccion: 'Calle Comercio 100',
      hora_apertura: '09:00',
      hora_cierre: '20:00',
      estado: true,
    },
    {
      id_sucursal: 20,
      id_ciudad: 2,
      ciudad: 'La Paz',
      nombre: 'Sucursal El Prado',
      direccion: 'Av. 16 de Julio 500',
      hora_apertura: '09:00',
      hora_cierre: '20:00',
      estado: true,
    },
  ];

  const mockCategories: OfflineCategoryData[] = [
    { id_categoria: 1, nombre: 'Blusas', estado: true },
    { id_categoria: 2, nombre: 'Vestidos', estado: true },
  ];

  const mockSizes: OfflineSizeData[] = [
    { id_talla: 1, nombre: 'S', estado: true },
    { id_talla: 2, nombre: 'M', estado: true },
  ];

  const mockColors: OfflineColorData[] = [
    { id_color: 10, nombre: 'Blanco', codigo_hex: '#FFFFFF', estado: true },
    { id_color: 20, nombre: 'Verde', codigo_hex: '#2E7D32', estado: true },
  ];

  const mockProducts: OfflineProductData[] = [
    {
      id_producto: 101,
      id_categoria: 1,
      categoria: 'Blusas',
      id_temporada: 3,
      temporada: 'Primavera 2026',
      nombre: 'Blusa Seda Imperial',
      seccion: 'MUJER',
      descripcion: 'Blusa elegante de seda natural',
      descripcion_corta: 'Blusa elegante de seda',
      precio: '200.00',
      precio_base: '200.00',
      precio_final: '160.00',
      tiene_promocion: true,
      imagen_principal: 'https://cdn.fashionstore.bo/img/blusa-101.jpg',
      imagenes: [
        'https://cdn.fashionstore.bo/img/blusa-101.jpg',
        'https://cdn.fashionstore.bo/img/blusa-101-back.jpg',
      ],
      galeria: [
        {
          id_imagen_producto: 1,
          url_imagen: 'https://cdn.fashionstore.bo/img/blusa-101.jpg',
          es_principal: true,
        },
        {
          id_imagen_producto: 2,
          url_imagen: 'https://cdn.fashionstore.bo/img/blusa-101-back.jpg',
          es_principal: false,
        },
      ],
      tallas_disponibles: [{ id_talla: 2, nombre: 'M' }],
      colores_disponibles: [{ id_color: 10, nombre: 'Blanco', codigo_hex: '#FFFFFF' }],
      colecciones: [{ id_coleccion: 1, nombre: 'Gala 2026' }],
      stock_total_disponible: 18,
      disponible_red: true,
      estado: true,
    },
    {
      id_producto: 102,
      id_categoria: 2,
      categoria: 'Vestidos',
      id_temporada: 3,
      temporada: 'Primavera 2026',
      nombre: 'Vestido Lino Floreado',
      seccion: 'MUJER',
      descripcion: 'Vestido fresco de lino para temporada',
      descripcion_corta: 'Vestido fresco de lino',
      precio: '350.00',
      precio_base: '350.00',
      precio_final: '350.00',
      tiene_promocion: false,
      imagen_principal: 'https://cdn.fashionstore.bo/img/vestido-102.jpg',
      imagenes: ['https://cdn.fashionstore.bo/img/vestido-102.jpg'],
      galeria: [
        {
          id_imagen_producto: 3,
          url_imagen: 'https://cdn.fashionstore.bo/img/vestido-102.jpg',
          es_principal: true,
        },
      ],
      tallas_disponibles: [{ id_talla: 1, nombre: 'S' }],
      colores_disponibles: [{ id_color: 20, nombre: 'Verde', codigo_hex: '#2E7D32' }],
      colecciones: [],
      stock_total_disponible: 10,
      disponible_red: true,
      estado: true,
    },
  ];

  const mockVariants: OfflineVariantData[] = [
    {
      id_variante_producto: 201,
      id_producto: 101,
      id_talla: 2,
      talla: 'M',
      id_color: 10,
      color: 'Blanco',
      color_hex: '#FFFFFF',
      sku: 'BLU-SED-BLA-M',
      precio: '160.00',
      stock_total_disponible: 18,
      disponible_red: true,
      estado: true,
    },
    {
      id_variante_producto: 202,
      id_producto: 102,
      id_talla: 1,
      talla: 'S',
      id_color: 20,
      color: 'Verde',
      color_hex: '#2E7D32',
      sku: 'VES-LIN-VER-S',
      precio: '350.00',
      stock_total_disponible: 10,
      disponible_red: true,
      estado: true,
    },
  ];

  const mockStock: OfflineStockData[] = [
    {
      id_inventario_sucursal: 501,
      id_sucursal: 10,
      id_variante_producto: 201,
      id_producto: 101,
      sku: 'BLU-SED-BLA-M',
      id_talla: 2,
      talla: 'M',
      id_color: 10,
      color: 'Blanco',
      color_hex: '#FFFFFF',
      nombre_sucursal: 'Sucursal Central',
      id_ciudad: 1,
      nombre_ciudad: 'Santa Cruz',
      stock_actual: 20,
      stock_reservado: 2,
      stock_disponible: 18,
      stock_minimo: 3,
      estado_disponibilidad: 'DISPONIBLE',
      updated_at: '2026-11-01T10:00:00Z',
    },
    {
      id_inventario_sucursal: 502,
      id_sucursal: 20,
      id_variante_producto: 202,
      id_producto: 102,
      sku: 'VES-LIN-VER-S',
      id_talla: 1,
      talla: 'S',
      id_color: 20,
      color: 'Verde',
      color_hex: '#2E7D32',
      nombre_sucursal: 'Sucursal El Prado',
      id_ciudad: 2,
      nombre_ciudad: 'La Paz',
      stock_actual: 12,
      stock_reservado: 2,
      stock_disponible: 10,
      stock_minimo: 2,
      estado_disponibilidad: 'DISPONIBLE',
      updated_at: '2026-11-01T10:00:00Z',
    },
  ];

  beforeEach(() => {
    TestBed.resetTestingModule();
    localStorage.clear();

    TestBed.configureTestingModule({
      providers: [
        OfflineStorageService,
        OfflineService,
        CatalogService,
        CatalogAvailabilityService,
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: SessionService, useValue: mockSessionService },
      ],
    });

    storageService = TestBed.inject(OfflineStorageService);
    offlineService = TestBed.inject(OfflineService);
    catalogService = TestBed.inject(CatalogService);
    availabilityService = TestBed.inject(CatalogAvailabilityService);
    httpMock = TestBed.inject(HttpTestingController);

    // Configurar espías por defecto sobre almacenes de IndexedDB
    vi.spyOn(storageService, 'getCatalogProducts').mockResolvedValue([...mockProducts]);
    vi.spyOn(storageService, 'getCategories').mockResolvedValue([...mockCategories]);
    vi.spyOn(storageService, 'getSizes').mockResolvedValue([...mockSizes]);
    vi.spyOn(storageService, 'getColors').mockResolvedValue([...mockColors]);
    vi.spyOn(storageService, 'getVariants').mockResolvedValue([...mockVariants]);
    vi.spyOn(storageService, 'getInventory').mockResolvedValue([...mockStock]);
    vi.spyOn(storageService, 'getBranches').mockResolvedValue([...mockBranches]);
    vi.spyOn(storageService, 'getPendingReservedQuantities').mockResolvedValue(new Map());
  });

  afterEach(() => {
    httpMock.verify();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('1. detecta desconexión y consulta catálogo directamente en IndexedDB sin emitir peticiones HTTP', async () => {
    offlineService.isOnline.set(false);

    const response = await firstValueFrom(catalogService.listProducts({ page: 1, pageSize: 12 }));

    httpMock.expectNone(`${environment.apiUrl}/api/catalog/products`);
    expect(response.success).toBe(true);
    expect(response.fromOffline).toBe(true);
    expect(response.pagination.total).toBe(2);
    expect(response.data.length).toBe(2);
    expect(response.data[0].nombre).toBe('Vestido Lino Floreado'); // 'recientes' (id_producto desc)
    expect(response.data[1].nombre).toBe('Blusa Seda Imperial');
    expect(response.data[1].colores_disponibles[0].nombre).toBe('Blanco');
  });

  it('2. realiza búsqueda por texto, nombre, descripción y SKU sobre variantes en IndexedDB sin internet', async () => {
    offlineService.isOnline.set(false);

    // Búsqueda por SKU
    const skuResponse = await firstValueFrom(catalogService.listProducts({ search: 'VES-LIN-VER' }));
    httpMock.expectNone(`${environment.apiUrl}/api/catalog/products`);
    expect(skuResponse.data.length).toBe(1);
    expect(skuResponse.data[0].id_producto).toBe(102);

    // Búsqueda por palabra clave en descripción
    const keywordResponse = await firstValueFrom(catalogService.listProducts({ search: 'seda' }));
    expect(keywordResponse.data.length).toBe(1);
    expect(keywordResponse.data[0].id_producto).toBe(101);
  });

  it('3. aplica filtros por categoría, talla, color, rango de precios y ofertas en IndexedDB', async () => {
    offlineService.isOnline.set(false);

    // Filtro por solo promociones
    const promoResponse = await firstValueFrom(catalogService.listProducts({ enPromocion: true }));
    expect(promoResponse.data.length).toBe(1);
    expect(promoResponse.data[0].id_producto).toBe(101);
    expect(promoResponse.data[0].tiene_promocion).toBe(true);
    expect(promoResponse.data[0].precio_final).toBe('160.00');

    // Filtro por categoría y rango de precio
    const filteredResponse = await firstValueFrom(
      catalogService.listProducts({ idCategoria: 2, precioMin: 300, precioMax: 400 }),
    );
    expect(filteredResponse.data.length).toBe(1);
    expect(filteredResponse.data[0].id_producto).toBe(102);
  });

  it('4. ordena deterministamente por precio ascendente, descendente, nombre y más recientes', async () => {
    offlineService.isOnline.set(false);

    // Orden por precio ascendente
    const ascResponse = await firstValueFrom(catalogService.listProducts({ sort: 'precio_asc' }));
    expect(Number(ascResponse.data[0].precio_final)).toBeLessThan(
      Number(ascResponse.data[1].precio_final),
    );
    expect(ascResponse.data[0].id_producto).toBe(101); // 160.00 < 350.00

    // Orden por precio descendente
    const descResponse = await firstValueFrom(catalogService.listProducts({ sort: 'precio_desc' }));
    expect(Number(descResponse.data[0].precio_final)).toBeGreaterThan(
      Number(descResponse.data[1].precio_final),
    );
    expect(descResponse.data[0].id_producto).toBe(102); // 350.00 > 160.00

    // Orden por nombre
    const nameResponse = await firstValueFrom(catalogService.listProducts({ sort: 'nombre' }));
    expect(nameResponse.data[0].nombre).toBe('Blusa Seda Imperial');
    expect(nameResponse.data[1].nombre).toBe('Vestido Lino Floreado');
  });

  it('5. carga detalle integral del producto offline con temporada, galería, colecciones y variantes con IDs reales', async () => {
    offlineService.isOnline.set(false);

    const mockDetail: OfflineProductDetail = {
      producto: mockProducts[0],
      categoriaNombre: 'Blusas',
      variantes: [
        {
          id_variante_producto: 201,
          id_producto: 101,
          id_talla: 2,
          id_color: 10,
          sku: 'BLU-SED-BLA-M',
          talla: 'M',
          color: 'Blanco',
          color_hex: '#FFFFFF',
          precio: 160,
          estado: true,
          stockTotalDisponible: 18,
          disponibilidadPorSucursal: [
            {
              id_sucursal: 10,
              nombre_sucursal: 'Sucursal Central',
              ciudad: 'Santa Cruz',
              stock_actual: 20,
              stock_reservado: 2,
              stock_disponible: 18,
            },
          ],
        },
      ],
      totalStockDisponible: 18,
      sucursalesConStock: 1,
      disponibilidadPorSucursal: [
        {
          id_sucursal: 10,
          nombre_sucursal: 'Sucursal Central',
          ciudad: 'Santa Cruz',
          stock_actual: 20,
          stock_reservado: 2,
          stock_disponible: 18,
        },
      ],
    };

    vi.spyOn(storageService, 'getProductDetail').mockResolvedValue(mockDetail);

    const result = await firstValueFrom(catalogService.getProduct(101, 10));

    httpMock.expectNone(`${environment.apiUrl}/api/catalog/products/101`);
    expect(result.success).toBe(true);
    expect(result.fromOffline).toBe(true);
    expect(result.data.temporada).toBe('Primavera 2026');
    expect(result.data.precio_base).toBe('200.00');
    expect(result.data.precio_final).toBe('160.00');
    expect(result.data.tiene_promocion).toBe(true);
    expect(result.data.galeria.length).toBe(2);
    expect(result.data.colecciones[0].nombre).toBe('Gala 2026');
    expect(result.data.variantes[0].talla.id_talla).toBe(2);
    expect(result.data.variantes[0].color.id_color).toBe(10);
    expect(result.data.variantes[0].disponibilidad_sucursal?.cantidad_disponible).toBe(18);
  });

  it('6. consulta disponibilidad por sucursal con CatalogAvailabilityService descontando reservas locales pendientes', async () => {
    offlineService.isOnline.set(false);

    // Simular que existen 3 unidades reservadas localmente (pendientes) para sucursal 10 y variante 201
    const pendingReservationsMap = new Map<string, number>();
    pendingReservationsMap.set('10_201', 3);
    vi.spyOn(storageService, 'getPendingReservedQuantities').mockResolvedValue(
      pendingReservationsMap,
    );

    const result = await firstValueFrom(
      availabilityService.getProductAvailability(101, {
        id_variante_producto: 201,
        id_sucursal: 10,
      }),
    );

    httpMock.expectNone(`${environment.apiUrl}/api/catalog/products/101/availability`);
    expect(result.success).toBe(true);
    expect(result.data.disponibilidad.length).toBe(1);

    const branchRow = result.data.disponibilidad[0];
    expect(branchRow.id_sucursal).toBe(10);
    expect(branchRow.stock_actual).toBe(20);
    // 2 reservadas en servidor + 3 pendientes locales = 5
    expect(branchRow.stock_reservado).toBe(5);
    // 18 disponibles en servidor - 3 pendientes locales = 15
    expect(branchRow.stock_disponible).toBe(15);
  });

  it('7. con conexión a internet mantiene el comportamiento HTTP original y soporta fallback en caso de falla de red', async () => {
    offlineService.isOnline.set(true);

    const listPromise = firstValueFrom(catalogService.listProducts({ page: 1 }));

    const req = httpMock.expectOne((r) => r.url === `${environment.apiUrl}/api/catalog/products`);
    expect(req.request.method).toBe('GET');

    // Simular caída repentina de red (status 0)
    req.error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });

    // Debe activar fallback transparente hacia IndexedDB sin lanzar excepción al usuario
    const result = await listPromise;
    expect(result.success).toBe(true);
    expect(result.fromOffline).toBe(true);
    expect(result.data.length).toBe(2);
  });

  it('8. detecta modo offline, calcula fecha real de preparación del paquete y advierte cuando está vencido', () => {
    offlineService.isOnline.set(false);

    // 1. Paquete vencido
    const expiredSummary: OfflineStoredSummary = {
      metadata: {
        version: 'FS-OFFLINE-TEST-EXPIRED',
        fecha_generacion: '2026-11-02T10:30:00Z',
        valido_hasta: '2026-11-01T10:30:00Z', // Vencido ayer
        vigencia_segundos: 86400,
        id_empresa: 2,
        empresa_codigo: 'moda-oriente',
        empresa_nombre: 'Moda Oriente',
        id_usuario: 88,
        usuario_rol: 'CLIENTE',
        sucursales_autorizadas_ids: [10],
        suscripcion_activa: true,
        funcionalidad_offline: true,
        total_sucursales: 1,
        total_categorias: 2,
        total_productos: 2,
        total_variantes: 2,
        total_existencias: 2,
        total_clientes: 1,
      },
      savedAt: '2026-11-02T10:35:00Z',
      counts: {
        sucursales: 1,
        categorias: 2,
        tallas: 2,
        colores: 2,
        productos: 2,
        variantes: 2,
        existencias: 2,
        clientes: 1,
      },
      isExpired: true,
      timeRemainingText: 'Expirado',
    };

    offlineService.localSummary.set(expiredSummary);

    expect(offlineService.isOnline()).toBe(false);
    expect(offlineService.offlinePreparationDate()).toBeTruthy();
    expect(offlineService.offlineExpiryDate()).toBeTruthy();
    expect(offlineService.isPackageExpired()).toBe(true);

    // 2. Paquete vigente
    const activeSummary: OfflineStoredSummary = {
      ...expiredSummary,
      metadata: {
        ...expiredSummary.metadata,
        valido_hasta: '2027-11-01T10:30:00Z', // Vigente
      },
      isExpired: false,
      timeRemainingText: '365d restantes',
    };

    offlineService.localSummary.set(activeSummary);
    expect(offlineService.isPackageExpired()).toBe(false);
    expect(offlineService.offlinePreparationDate()).toBeTruthy();
  });
});

