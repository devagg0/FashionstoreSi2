import { CommonModule } from '@angular/common';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import {
  AdminPredictionsService,
  DailyTrendPoint,
  ModelInfoResponse,
  PredictionFilterItem,
  PredictionResponse,
} from '../../../core/services/admin-predictions.service';
import { Icon } from '../../../shared/components/icon/icon';

interface ChartCoordinatePoint {
  x: number;
  y: number;
  label: string;
  value: number;
  date: string;
  type: 'REAL' | 'PROYECTADO';
  showLabel: boolean;
}

@Component({
  selector: 'app-admin-ml-predictions',
  standalone: true,
  imports: [CommonModule, FormsModule, Icon],
  templateUrl: './admin-ml-predictions.html',
  styleUrl: './admin-ml-predictions.scss',
})
export class AdminMlPredictionsComponent implements OnInit {
  private readonly predictionsService = inject(AdminPredictionsService);
  private readonly destroyRef = inject(DestroyRef);

  readonly isLoading = signal(false);
  readonly isLoadingFilters = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly modelInfo = signal<ModelInfoResponse | null>(null);
  readonly branches = signal<PredictionFilterItem[]>([]);
  readonly products = signal<PredictionFilterItem[]>([]);
  readonly availableHorizons = signal<number[]>([7, 15, 30]);

  readonly selectedBranchId = signal<number | null>(null);
  readonly selectedProductId = signal<number | null>(null);
  readonly selectedHorizon = signal<number>(15);

  readonly predictionResult = signal<PredictionResponse | null>(null);

  // SVG Chart computed dimensions & coordinates
  readonly chartPoints = computed<ChartCoordinatePoint[]>(() => {
    const res = this.predictionResult();
    if (!res || !res.serie_temporal || res.serie_temporal.length === 0) {
      return [];
    }

    const serie = res.serie_temporal;
    const maxVal = Math.max(...serie.map((p) => p.unidades), 5);
    const width = 800;
    const height = 240;
    const padX = 45;
    const padY = 25;
    const chartW = width - padX * 2;
    const chartH = height - padY * 2 - 25;

    const stepX = chartW / Math.max(serie.length - 1, 1);

    // Calcular etiquetas visibles espaciadas para evitar amontonamiento en el eje X
    const interval = Math.max(2, Math.round(serie.length / 7));
    const transitionIdx = serie.findIndex(
      (p, i) => i > 0 && p.tipo === 'PROYECTADO' && serie[i - 1].tipo === 'REAL',
    );

    const candidateIndices = new Set<number>();
    candidateIndices.add(0);
    candidateIndices.add(serie.length - 1);
    if (transitionIdx > 0) {
      candidateIndices.add(transitionIdx - 1);
    }
    for (let i = 0; i < serie.length; i += interval) {
      candidateIndices.add(i);
    }

    const sorted = Array.from(candidateIndices).sort((a, b) => a - b);
    const visibleSet = new Set<number>();
    let lastAccepted = -999;
    for (const idx of sorted) {
      if (idx === 0 || idx === serie.length - 1 || idx === transitionIdx - 1) {
        visibleSet.add(idx);
        lastAccepted = idx;
      } else if (idx - lastAccepted >= Math.max(2, Math.floor(interval * 0.75))) {
        visibleSet.add(idx);
        lastAccepted = idx;
      }
    }

    return serie.map((pt, idx) => {
      const x = padX + idx * stepX;
      const y = padY + chartH - (pt.unidades / maxVal) * chartH;
      return {
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        label: pt.dia_etiqueta,
        value: pt.unidades,
        date: pt.fecha,
        type: pt.tipo,
        showLabel: visibleSet.has(idx),
      };
    });
  });

  readonly transitionX = computed<number | null>(() => {
    const pts = this.chartPoints();
    const lastReal = pts.filter((p) => p.type === 'REAL').slice(-1)[0];
    return lastReal ? lastReal.x : null;
  });

  readonly realLinePath = computed<string>(() => {
    const pts = this.chartPoints().filter((p) => p.type === 'REAL');
    if (pts.length === 0) return '';
    return pts.reduce((acc, p, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`, '');
  });

  readonly projectedLinePath = computed<string>(() => {
    const all = this.chartPoints();
    const lastReal = all.filter((p) => p.type === 'REAL').slice(-1)[0];
    const projected = all.filter((p) => p.type === 'PROYECTADO');
    if (projected.length === 0) return '';

    const startFrom = lastReal ? [lastReal, ...projected] : projected;
    return startFrom.reduce((acc, p, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`, '');
  });

  readonly maxChartValue = computed<number>(() => {
    const res = this.predictionResult();
    if (!res || !res.serie_temporal) return 10;
    return Math.max(...res.serie_temporal.map((p) => p.unidades), 5);
  });

  ngOnInit(): void {
    this.loadModelInfo();
    this.loadFilters();
  }

  loadModelInfo(): void {
    this.predictionsService
      .getModelInfo()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (info) => this.modelInfo.set(info),
        error: (err) => console.error('Error cargando metadatos del modelo ML:', err),
      });
  }

  loadFilters(): void {
    this.isLoadingFilters.set(true);
    this.errorMessage.set(null);

    this.predictionsService
      .getFilters()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (filters) => {
          this.isLoadingFilters.set(false);
          this.branches.set(filters.sucursales);
          this.products.set(filters.productos);
          this.availableHorizons.set(filters.horizontes_disponibles);

          // Preseleccionar primero si no hay selección previa
          if (!this.selectedBranchId() && filters.sucursales.length > 0) {
            this.selectedBranchId.set(filters.sucursales[0].id);
          }
          if (!this.selectedProductId() && filters.productos.length > 0) {
            this.selectedProductId.set(filters.productos[0].id);
          }
        },
        error: (err) => {
          this.isLoadingFilters.set(false);
          this.errorMessage.set(
            err.error?.detail || err.error?.message || 'Error al cargar opciones de filtrado.',
          );
        },
      });
  }

  setHorizon(days: number): void {
    this.selectedHorizon.set(days);
  }

  generatePrediction(): void {
    const branchId = this.selectedBranchId();
    const productId = this.selectedProductId();
    const horizon = this.selectedHorizon();

    if (!branchId || !productId) {
      this.errorMessage.set('Debe seleccionar una sucursal y un producto para generar la predicción.');
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.predictionsService
      .predict({
        id_producto: Number(productId),
        id_sucursal: Number(branchId),
        horizonte_dias: Number(horizon),
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.isLoading.set(false);
          this.predictionResult.set(res);
        },
        error: (err) => {
          this.isLoading.set(false);
          this.errorMessage.set(
            err.error?.detail || err.error?.message || 'Error al generar la predicción supervisada.',
          );
        },
      });
  }

  resetPrediction(): void {
    this.predictionResult.set(null);
    this.errorMessage.set(null);
  }

  getRiskBadgeClass(level: string): string {
    switch (level) {
      case 'CRITICO':
        return 'badge-critical';
      case 'ALTO':
        return 'badge-high';
      case 'MEDIO':
        return 'badge-medium';
      case 'BAJO':
      default:
        return 'badge-low';
    }
  }

  getConfidenceBadgeClass(conf: string): string {
    switch (conf) {
      case 'ALTA':
        return 'badge-confidence-high';
      case 'MEDIA':
        return 'badge-confidence-med';
      case 'EXPERIMENTAL':
      default:
        return 'badge-confidence-exp';
    }
  }
}

