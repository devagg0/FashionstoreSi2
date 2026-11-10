import { CommonModule } from '@angular/common';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import {
  AdminPatternsService,
  PatternAnalysisResponse,
  PatternFilterOption,
  PatternModelInfoResponse,
  ProductPatternItem,
} from '../../../core/services/admin-patterns.service';
import { Icon } from '../../../shared/components/icon/icon';

interface ScatterPlotPoint {
  x: number;
  y: number;
  r: number;
  color: string;
  clusterName: string;
  productName: string;
  units: number;
  revenue: number;
  stock: number;
  rotation: number;
  price: number;
}

@Component({
  selector: 'app-admin-ml-patterns',
  standalone: true,
  imports: [CommonModule, FormsModule, Icon],
  templateUrl: './admin-ml-patterns.html',
  styleUrl: './admin-ml-patterns.scss',
})
export class AdminMlPatternsComponent implements OnInit {
  private readonly patternsService = inject(AdminPatternsService);
  private readonly destroyRef = inject(DestroyRef);

  readonly isLoading = signal(false);
  readonly isLoadingFilters = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly modelInfo = signal<PatternModelInfoResponse | null>(null);
  readonly branches = signal<PatternFilterOption[]>([]);
  readonly categories = signal<PatternFilterOption[]>([]);
  readonly availablePeriods = signal<number[]>([30, 60, 90, 180]);

  readonly selectedPeriod = signal<number>(30);
  readonly selectedBranchId = signal<number | null>(null);
  readonly selectedCategoryId = signal<number | null>(null);

  readonly analysisResult = signal<PatternAnalysisResponse | null>(null);
  readonly searchQuery = signal<string>('');
  readonly selectedClusterFilter = signal<number | null>(null);

  // SVG Scatter plot computed points
  readonly scatterPoints = computed<ScatterPlotPoint[]>(() => {
    const res = this.analysisResult();
    if (!res || !res.productos || res.productos.length === 0) {
      return [];
    }

    const prods = res.productos;
    const maxUnits = Math.max(...prods.map((p) => p.unidades_vendidas), 10);
    const maxRevenue = Math.max(...prods.map((p) => p.ingresos_totales), 100);
    const maxStock = Math.max(...prods.map((p) => p.stock_actual), 20);

    const width = 760;
    const height = 260;
    const padLeft = 60;
    const padRight = 30;
    const padTop = 30;
    const padBottom = 45;
    const chartW = width - padLeft - padRight;
    const chartH = height - padTop - padBottom;

    return prods.map((p) => {
      const x = padLeft + (p.unidades_vendidas / maxUnits) * chartW;
      const y = padTop + chartH - (p.ingresos_totales / maxRevenue) * chartH;
      // Radius between 5px and 11px according to stock
      const r = 5 + (p.stock_actual / maxStock) * 6;

      return {
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        r: Math.round(r * 10) / 10,
        color: p.cluster_color,
        clusterName: p.cluster_nombre,
        productName: p.nombre,
        units: p.unidades_vendidas,
        revenue: p.ingresos_totales,
        stock: p.stock_actual,
        rotation: p.ratio_rotacion,
        price: p.precio_unitario,
      };
    });
  });

  readonly maxXValue = computed<number>(() => {
    const res = this.analysisResult();
    if (!res || !res.productos || res.productos.length === 0) return 50;
    return Math.max(...res.productos.map((p) => p.unidades_vendidas), 10);
  });

  readonly maxYValue = computed<number>(() => {
    const res = this.analysisResult();
    if (!res || !res.productos || res.productos.length === 0) return 500;
    return Math.max(...res.productos.map((p) => p.ingresos_totales), 100);
  });

  readonly filteredProducts = computed<ProductPatternItem[]>(() => {
    const res = this.analysisResult();
    if (!res || !res.productos) return [];

    let list = res.productos;
    const query = this.searchQuery().trim().toLowerCase();
    const clusterId = this.selectedClusterFilter();

    if (clusterId !== null) {
      list = list.filter((p) => p.id_cluster === clusterId);
    }

    if (query) {
      list = list.filter(
        (p) =>
          p.nombre.toLowerCase().includes(query) ||
          p.categoria_nombre.toLowerCase().includes(query) ||
          p.cluster_nombre.toLowerCase().includes(query),
      );
    }

    return list;
  });

  ngOnInit(): void {
    this.loadModelInfo();
    this.loadFilters();
  }

  loadModelInfo(): void {
    this.patternsService
      .getModelInfo()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (info) => this.modelInfo.set(info),
        error: (err) => console.error('Error cargando metadatos del modelo no supervisado:', err),
      });
  }

  loadFilters(): void {
    this.isLoadingFilters.set(true);
    this.errorMessage.set(null);

    this.patternsService
      .getFilters()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (filters) => {
          this.isLoadingFilters.set(false);
          this.branches.set(filters.sucursales);
          this.categories.set(filters.categorias);
          this.availablePeriods.set(filters.periodos_sugeridos_dias);
        },
        error: (err) => {
          this.isLoadingFilters.set(false);
          this.errorMessage.set(
            err.error?.detail || err.error?.message || 'Error al cargar filtros de análisis.',
          );
        },
      });
  }

  setPeriod(days: number): void {
    this.selectedPeriod.set(days);
  }

  toggleClusterFilter(clusterId: number | null): void {
    if (this.selectedClusterFilter() === clusterId) {
      this.selectedClusterFilter.set(null);
    } else {
      this.selectedClusterFilter.set(clusterId);
    }
  }

  executeAnalysis(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.selectedClusterFilter.set(null);

    this.patternsService
      .analyze({
        dias_periodo: this.selectedPeriod(),
        id_sucursal: this.selectedBranchId() ? Number(this.selectedBranchId()) : null,
        id_categoria: this.selectedCategoryId() ? Number(this.selectedCategoryId()) : null,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.isLoading.set(false);
          this.analysisResult.set(res);
        },
        error: (err) => {
          this.isLoading.set(false);
          this.errorMessage.set(
            err.error?.detail || err.error?.message || 'Error al ejecutar el análisis de patrones.',
          );
        },
      });
  }

  resetAnalysis(): void {
    this.analysisResult.set(null);
    this.errorMessage.set(null);
    this.searchQuery.set('');
    this.selectedClusterFilter.set(null);
  }
}

