import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminAnalyticsDashboardComponent } from './admin-analytics-dashboard';
import {
  AdminDashboardService,
  DashboardAnalyticsResponse,
  DashboardFiltersResponse,
} from '../../../core/services/admin-dashboard.service';

const mockFilters: DashboardFiltersResponse = {
  sucursales: [
    { id: 1, nombre: 'Sucursal Central', extra: 'Av. Principal 123' },
    { id: 2, nombre: 'Sucursal Norte', extra: 'Calle Norte 456' },
  ],
  categorias: [
    { id: 1, nombre: 'Moda Femenina' },
    { id: 2, nombre: 'Calzado y Accesorios' },
  ],
  periodos_disponibles: [7, 15, 30, 60, 90],
};

const mockAnalyticsResponse: DashboardAnalyticsResponse = {
  success: true,
  filtros_aplicados: {
    periodo: '2026-10-10 a 2026-11-09',
    dias_periodo: 30,
    sucursal: 'Todas',
    categoria: 'Todas',
  },
  kpis: {
    total_ventas: 24,
    ingresos_totales: 8540.0,
    ticket_promedio: 355.83,
    unidades_vendidas: 52,
    stock_disponible: 320,
    total_reservas: 15,
    reservas_atendidas: 12,
    total_devoluciones: 1,
    tasa_devolucion_pct: 4.2,
  },
  tendencia_diaria: [
    { fecha: '2026-11-01', dia_etiqueta: '01', unidades: 4, ingresos: 650.0 },
    { fecha: '2026-11-02', dia_etiqueta: '02', unidades: 6, ingresos: 920.0 },
    { fecha: '2026-11-03', dia_etiqueta: '03', unidades: 8, ingresos: 1200.0 },
  ],
  distribucion_categorias: [
    { categoria: 'Moda Femenina', unidades: 30, ingresos: 5200.0, porcentaje: 60.9 },
    { categoria: 'Calzado', unidades: 22, ingresos: 3340.0, porcentaje: 39.1 },
  ],
  distribucion_canales: [
    { canal: 'PRESENCIAL', unidades: 32, ingresos: 5124.0, porcentaje: 60.0 },
    { canal: 'DIGITAL', unidades: 20, ingresos: 3416.0, porcentaje: 40.0 },
  ],
  distribucion_secciones: [
    { seccion: 'MUJER', unidades: 28, ingresos: 4800.0, porcentaje: 56.2 },
    { seccion: 'HOMBRE', unidades: 16, ingresos: 2600.0, porcentaje: 30.4 },
    { seccion: 'UNISEX', unidades: 8, ingresos: 1140.0, porcentaje: 13.4 },
  ],
  ml_predicciones: {
    algoritmo: 'GradientBoostingRegressor (scikit-learn)',
    mae: 1.6,
    rmse: 2.14,
    r2: 0.9619,
    productos_con_riesgo_stock: 2,
    items_riesgo: [
      {
        id_producto: 1,
        producto_nombre: 'Vestido Fiesta',
        stock_actual: 5,
        demanda_estimada_15d: 14,
        cobertura_dias: 5.4,
        nivel_riesgo: 'CRITICO',
      },
    ],
    disclaimer: 'Estimaciones de demanda supervisada a 15 días.',
  },
  ml_patrones: {
    algoritmo: 'K-Means Clustering',
    silhouette_score: 0.556,
    calidad_agrupamiento: 'ALTA',
    n_clusters: 4,
    segmentos: [
      {
        id_cluster: 0,
        nombre: 'Alta Rotación (Estrella)',
        color: '#2563eb',
        total_productos: 3,
        porcentaje_catalogo: 50.0,
        unidades_promedio: 35.0,
      },
    ],
    disclaimer: 'Segmentación no supervisada por velocidad de rotación.',
  },
  reportes_ia: {
    total_reportes_guardados: 5,
    ultimos_reportes: [
      {
        id_reporte: 10,
        tipo: 'VENTAS',
        titulo: 'Reporte Ventas Mensuales',
        creado_en: '09/11/2026 14:30',
        consulta: '¿Cuáles fueron las ventas del mes?',
      },
    ],
  },
};

describe('CU24 - Dashboard Analítico Inteligente', () => {
  let fixture: ComponentFixture<AdminAnalyticsDashboardComponent>;
  let component: AdminAnalyticsDashboardComponent;
  let mockDashboardService: any;

  beforeEach(async () => {
    mockDashboardService = {
      getFilters: vi.fn().mockReturnValue(of(mockFilters)),
      getAnalytics: vi.fn().mockReturnValue(of(mockAnalyticsResponse)),
    };

    await TestBed.configureTestingModule({
      imports: [AdminAnalyticsDashboardComponent],
      providers: [
        provideRouter([]),
        { provide: AdminDashboardService, useValue: mockDashboardService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminAnalyticsDashboardComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    fixture.destroy();
  });

  it('debe inicializarse y cargar los filtros y consolidado analítico del dashboard', () => {
    fixture.detectChanges();

    expect(mockDashboardService.getFilters).toHaveBeenCalled();
    expect(mockDashboardService.getAnalytics).toHaveBeenCalledWith({
      dias_periodo: 30,
      id_sucursal: null,
      id_categoria: null,
    });

    expect(component.branches().length).toBe(2);
    expect(component.categories().length).toBe(2);
    expect(component.analytics()?.success).toBe(true);
    expect(component.analytics()?.kpis.total_ventas).toBe(24);
    expect(component.analytics()?.kpis.ingresos_totales).toBe(8540.0);
    expect(component.analytics()?.ml_predicciones.productos_con_riesgo_stock).toBe(2);
    expect(component.analytics()?.reportes_ia.total_reportes_guardados).toBe(5);
  });

  it('debe actualizar el consolidado analítico al cambiar el período', () => {
    fixture.detectChanges();

    component.onPeriodChange(15);

    expect(component.selectedPeriod()).toBe(15);
    expect(mockDashboardService.getAnalytics).toHaveBeenCalledWith({
      dias_periodo: 15,
      id_sucursal: null,
      id_categoria: null,
    });
  });

  it('debe calcular la ruta SVG de tendencia y puntos de datos correctamente', () => {
    fixture.detectChanges();

    const points = component.chartPoints();
    expect(points.length).toBe(3);
    expect(points[0].revenue).toBe(650.0);
    expect(points[2].revenue).toBe(1200.0);

    const linePath = component.svgLinePath();
    expect(linePath).toContain('M');
    expect(linePath).toContain('L');

    const areaPath = component.svgAreaPath();
    expect(areaPath).toContain('Z');
  });

  it('debe manejar errores de carga y desplegar el mensaje de alerta', () => {
    mockDashboardService.getAnalytics.mockReturnValue(
      throwError(() => ({ error: { detail: 'Error al consolidar dashboard analítico' } })),
    );

    fixture.detectChanges();
    component.loadAnalytics();

    expect(component.isLoading()).toBe(false);
    expect(component.errorMessage()).toBe('Error al consolidar dashboard analítico');
  });
});

