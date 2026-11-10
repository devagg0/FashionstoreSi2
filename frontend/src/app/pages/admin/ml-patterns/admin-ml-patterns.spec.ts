import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminMlPatternsComponent } from './admin-ml-patterns';
import { AdminPatternsService } from '../../../core/services/admin-patterns.service';

const mockModelInfo = {
  algoritmo: 'K-Means Clustering (scikit-learn compatible)',
  tipo_aprendizaje: 'No supervisado',
  descripcion: 'Segmentación de productos según velocidad de rotación y volumen',
  variables: [
    'unidades_vendidas',
    'ingresos_totales',
    'frecuencia_ventas',
    'precio_unitario',
    'stock_actual',
    'ratio_rotacion',
  ],
  n_clusters: 4,
  metricas: {
    silhouette_score: 0.5562,
    inercia: 818.5,
  },
  es_experimental: true,
  nota_metodologica: 'Modelo referencial entrenado sobre datos sintéticos de FashionStore.',
};

const mockFilters = {
  sucursales: [
    { id: 1, nombre: 'Sucursal Central', extra: 'Av. Principal 123' },
  ],
  categorias: [
    { id: 1, nombre: 'Moda Femenina' },
    { id: 2, nombre: 'Línea Formal' },
  ],
  periodos_sugeridos_dias: [30, 60, 90, 180],
};

const mockAnalysisResponse = {
  success: true,
  datos_suficientes: true,
  mensaje: 'Análisis de patrones completado exitosamente sobre 6 prendas comerciales.',
  filtros_aplicados: {
    periodo: '2026-10-10 a 2026-11-09',
    dias_periodo: 30,
    sucursal: 'Todas',
    categoria: 'Todas',
  },
  total_productos_analizados: 6,
  total_unidades_vendidas: 187,
  total_ingresos_facturados: 19450.0,
  n_clusters: 4,
  calidad_agrupamiento: 'ALTA',
  metricas: {
    silhouette_score: 0.5214,
    inercia: 142.3,
  },
  segmentos: [
    {
      id_cluster: 0,
      nombre: 'Alto Rendimiento (Estrella)',
      descripcion: 'Prendas con alto volumen de ventas y rotación continua.',
      estrategia: 'Garantizar disponibilidad permanente en inventario.',
      color: '#2563eb',
      badge_class: 'badge-star',
      total_productos: 2,
      porcentaje_catalogo: 33.3,
      promedios: {
        unidades_vendidas: 37.5,
        ingresos_totales: 6050.0,
        frecuencia_ventas: 18.0,
        precio_unitario: 160.0,
        stock_actual: 22.5,
        ratio_rotacion: 0.625,
      },
    },
    {
      id_cluster: 1,
      nombre: 'Baja Rotación (Lento Movimiento)',
      descripcion: 'Prendas con rotación reducida en el período analizado.',
      estrategia: 'Estrategias de liquidación y promociones cruzadas.',
      color: '#dc2626',
      badge_class: 'badge-slow',
      total_productos: 1,
      porcentaje_catalogo: 16.7,
      promedios: {
        unidades_vendidas: 0.0,
        ingresos_totales: 0.0,
        frecuencia_ventas: 0.0,
        precio_unitario: 90.0,
        stock_actual: 30.0,
        ratio_rotacion: 0.0,
      },
    },
  ],
  productos: [
    {
      id_producto: 1,
      nombre: 'Vestido Fiesta',
      categoria_nombre: 'Línea Formal',
      seccion: 'MUJER',
      precio_unitario: 180.0,
      unidades_vendidas: 40,
      ingresos_totales: 7200.0,
      frecuencia_ventas: 18,
      stock_actual: 25,
      ratio_rotacion: 0.615,
      id_cluster: 0,
      cluster_nombre: 'Alto Rendimiento (Estrella)',
      cluster_color: '#2563eb',
      cluster_badge: 'badge-star',
    },
    {
      id_producto: 6,
      nombre: 'Bufanda Invierno',
      categoria_nombre: 'Moda Femenina',
      seccion: 'UNISEX',
      precio_unitario: 90.0,
      unidades_vendidas: 0,
      ingresos_totales: 0.0,
      frecuencia_ventas: 0,
      stock_actual: 30,
      ratio_rotacion: 0.0,
      id_cluster: 1,
      cluster_nombre: 'Baja Rotación (Lento Movimiento)',
      cluster_color: '#dc2626',
      cluster_badge: 'badge-slow',
    },
  ],
  modelo_referencial: mockModelInfo,
  disclaimer: 'Patrones descubiertos mediante K-Means no supervisado.',
};

describe('CU23 - Análisis de Patrones mediante Machine Learning', () => {
  let fixture: ComponentFixture<AdminMlPatternsComponent>;
  let component: AdminMlPatternsComponent;
  let mockPatternsService: any;

  beforeEach(async () => {
    mockPatternsService = {
      getModelInfo: vi.fn().mockReturnValue(of(mockModelInfo)),
      getFilters: vi.fn().mockReturnValue(of(mockFilters)),
      analyze: vi.fn().mockReturnValue(of(mockAnalysisResponse)),
    };

    await TestBed.configureTestingModule({
      imports: [AdminMlPatternsComponent],
      providers: [
        provideRouter([]),
        { provide: AdminPatternsService, useValue: mockPatternsService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminMlPatternsComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    fixture.destroy();
  });

  it('debe inicializarse y cargar los filtros y metadatos del modelo K-Means', () => {
    fixture.detectChanges();

    expect(mockPatternsService.getModelInfo).toHaveBeenCalled();
    expect(mockPatternsService.getFilters).toHaveBeenCalled();
    expect(component.modelInfo()?.tipo_aprendizaje).toBe('No supervisado');
    expect(component.branches().length).toBe(1);
    expect(component.categories().length).toBe(2);
    expect(component.selectedPeriod()).toBe(30);
  });

  it('debe ejecutar el análisis no supervisado y renderizar segmentos, KPIs y gráfico de dispersión', () => {
    fixture.detectChanges();

    component.setPeriod(60);
    component.executeAnalysis();

    expect(mockPatternsService.analyze).toHaveBeenCalledWith({
      dias_periodo: 60,
      id_sucursal: null,
      id_categoria: null,
    });

    expect(component.analysisResult()?.success).toBe(true);
    expect(component.analysisResult()?.datos_suficientes).toBe(true);
    expect(component.analysisResult()?.segmentos.length).toBe(2);
    expect(component.scatterPoints().length).toBe(2);
    expect(component.filteredProducts().length).toBe(2);
  });

  it('debe filtrar productos en la tabla al hacer clic en un segmento de cluster', () => {
    fixture.detectChanges();
    component.executeAnalysis();

    // Filtrar solo cluster 0
    component.toggleClusterFilter(0);
    expect(component.selectedClusterFilter()).toBe(0);
    expect(component.filteredProducts().length).toBe(1);
    expect(component.filteredProducts()[0].nombre).toBe('Vestido Fiesta');

    // Desactivar filtro
    component.toggleClusterFilter(0);
    expect(component.selectedClusterFilter()).toBeNull();
    expect(component.filteredProducts().length).toBe(2);
  });

  it('debe manejar errores de análisis y mostrar mensaje amigable', () => {
    mockPatternsService.analyze.mockReturnValue(
      throwError(() => ({ error: { detail: 'Error en consulta K-Means' } })),
    );

    fixture.detectChanges();
    component.executeAnalysis();

    expect(component.isLoading()).toBe(false);
    expect(component.errorMessage()).toBe('Error en consulta K-Means');
  });
});

