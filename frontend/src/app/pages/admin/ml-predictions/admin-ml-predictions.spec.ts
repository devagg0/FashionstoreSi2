import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminMlPredictionsComponent } from './admin-ml-predictions';
import { AdminPredictionsService } from '../../../core/services/admin-predictions.service';

const mockModelInfo = {
  algoritmo: 'GradientBoostingRegressor (scikit-learn)',
  descripcion: 'Modelo supervisado de regresión para estimar demanda de prendas',
  variables: [
    'precio_unitario',
    'ventas_ultimos_7d',
    'ventas_ultimos_14d',
    'ventas_ultimos_30d',
    'stock_actual',
    'dias_horizonte',
    'mes',
    'es_temporada_alta',
    'seccion_HOMBRE',
    'seccion_MUJER',
    'seccion_UNISEX',
  ],
  total_variables: 11,
  dataset_size: 3000,
  train_size: 2400,
  test_size: 600,
  metricas: {
    mae: 1.6,
    rmse: 2.14,
    r2: 0.9619,
  },
  es_experimental: true,
  nota_metodologica: 'Entrenado sobre datos sintéticos generados para FashionStore.',
  entrenado_en: '2026-11-09T10:00:00Z',
};

const mockFilters = {
  productos: [
    { id: 1, nombre: 'Vestido Floral', codigo: 'SECC-MUJER', extra: 'Bs. 120.00' },
    { id: 2, nombre: 'Camisa Lino', codigo: 'SECC-HOMBRE', extra: 'Bs. 90.00' },
  ],
  sucursales: [
    { id: 1, nombre: 'Sucursal Central', codigo: 'Av. Principal 123' },
  ],
  horizontes_disponibles: [7, 15, 30],
};

const mockPredictionResponse = {
  success: true,
  id_producto: 1,
  producto_nombre: 'Vestido Floral',
  id_sucursal: 1,
  sucursal_nombre: 'Sucursal Central',
  horizonte_dias: 15,
  prediccion: {
    demanda_estimada: 15,
    demanda_estimada_raw: 15.04,
    rango_minimo: 13,
    rango_maximo: 17,
    unidades_diarias_promedio: 1.0,
    cobertura_stock_dias: 25.0,
    riesgo_desabastecimiento: false,
    nivel_riesgo: 'BAJO' as const,
    confianza_estimacion: 'ALTA' as const,
    explicacion: 'Demanda proyectada de 15 unidades cubierta por el stock actual (25 un.).',
  },
  historico: {
    ventas_ultimos_7d: 7,
    ventas_ultimos_14d: 12,
    ventas_ultimos_30d: 20,
    stock_actual: 25,
    stock_minimo: 5,
    precio_unitario: 120.0,
    seccion: 'MUJER',
    datos_suficientes: true,
    mensaje_suficiencia: 'Se identificaron 20 unidades vendidas en los últimos 30 días.',
  },
  serie_temporal: [
    { fecha: '2026-10-26', dia_etiqueta: '26/10', tipo: 'REAL' as const, unidades: 1.0 },
    { fecha: '2026-10-27', dia_etiqueta: '27/10', tipo: 'REAL' as const, unidades: 2.0 },
    { fecha: '2026-11-10', dia_etiqueta: '10/11', tipo: 'PROYECTADO' as const, unidades: 1.0 },
  ],
  modelo: mockModelInfo,
  disclaimer: 'Estimación experimental generada mediante GradientBoostingRegressor.',
};

describe('CU22 - Predicciones de demanda con Machine Learning', () => {
  let fixture: ComponentFixture<AdminMlPredictionsComponent>;
  let component: AdminMlPredictionsComponent;
  let mockPredictionsService: any;

  beforeEach(async () => {
    mockPredictionsService = {
      getModelInfo: vi.fn().mockReturnValue(of(mockModelInfo)),
      getFilters: vi.fn().mockReturnValue(of(mockFilters)),
      predict: vi.fn().mockReturnValue(of(mockPredictionResponse)),
    };

    await TestBed.configureTestingModule({
      imports: [AdminMlPredictionsComponent],
      providers: [
        provideRouter([]),
        { provide: AdminPredictionsService, useValue: mockPredictionsService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(AdminMlPredictionsComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    fixture.destroy();
  });

  it('debe inicializarse y cargar los filtros y metadatos del modelo ML', () => {
    fixture.detectChanges();

    expect(mockPredictionsService.getModelInfo).toHaveBeenCalled();
    expect(mockPredictionsService.getFilters).toHaveBeenCalled();
    expect(component.modelInfo()?.algoritmo).toContain('GradientBoostingRegressor');
    expect(component.branches().length).toBe(1);
    expect(component.products().length).toBe(2);
    expect(component.selectedBranchId()).toBe(1);
    expect(component.selectedProductId()).toBe(1);
  });

  it('debe enviar la solicitud de predicción y renderizar los KPIs y gráficos', () => {
    fixture.detectChanges();

    component.setHorizon(15);
    component.generatePrediction();

    expect(mockPredictionsService.predict).toHaveBeenCalledWith({
      id_producto: 1,
      id_sucursal: 1,
      horizonte_dias: 15,
    });
    expect(component.predictionResult()?.success).toBe(true);
    expect(component.predictionResult()?.prediccion.demanda_estimada).toBe(15);
    expect(component.predictionResult()?.prediccion.cobertura_stock_dias).toBe(25.0);
    expect(component.chartPoints().length).toBe(3);
    expect(component.chartPoints().some((p) => p.showLabel)).toBe(true);
    expect(component.transitionX()).toBeTruthy();
    expect(component.realLinePath()).toBeTruthy();
    expect(component.projectedLinePath()).toBeTruthy();
  });

  it('debe manejar errores de predicción y mostrar mensaje amigable', () => {
    mockPredictionsService.predict.mockReturnValue(
      throwError(() => ({ error: { detail: 'Error en la base de datos' } })),
    );

    fixture.detectChanges();
    component.generatePrediction();

    expect(component.isLoading()).toBe(false);
    expect(component.errorMessage()).toBe('Error en la base de datos');
  });
});
