import { CommonModule, DecimalPipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  AdminDashboardService,
  DashboardAnalyticsRequest,
  DashboardAnalyticsResponse,
  DashboardFilterItem,
  DashboardFiltersResponse,
} from '../../../core/services/admin-dashboard.service';
import { Icon } from '../../../shared/components/icon/icon';

interface TrendSvgPoint {
  x: number;
  y: number;
  date: string;
  label: string;
  units: number;
  revenue: number;
}

@Component({
  selector: 'app-admin-analytics-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, Icon, DecimalPipe],
  templateUrl: './admin-analytics-dashboard.html',
  styleUrl: './admin-analytics-dashboard.scss',
})
export class AdminAnalyticsDashboardComponent implements OnInit {
  private readonly dashboardService = inject(AdminDashboardService);
  private readonly destroyRef = inject(DestroyRef);

  readonly isLoading = signal(false);
  readonly isLoadingFilters = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly branches = signal<DashboardFilterItem[]>([]);
  readonly categories = signal<DashboardFilterItem[]>([]);
  readonly availablePeriods = signal<number[]>([7, 15, 30, 60, 90]);

  readonly selectedPeriod = signal<number>(30);
  readonly selectedBranchId = signal<number | null>(null);
  readonly selectedCategoryId = signal<number | null>(null);

  readonly analytics = signal<DashboardAnalyticsResponse | null>(null);

  // SVG Trend Chart Computations
  readonly chartPoints = computed<TrendSvgPoint[]>(() => {
    const data = this.analytics()?.tendencia_diaria;
    if (!data || data.length === 0) return [];

    const width = 640;
    const height = 180;
    const paddingX = 40;
    const paddingY = 25;

    const maxRev = Math.max(...data.map((d) => d.ingresos), 10);
    const n = data.length;
    const stepX = n > 1 ? (width - paddingX * 2) / (n - 1) : 0;

    return data.map((d, i) => {
      const x = paddingX + i * stepX;
      const y = height - paddingY - (d.ingresos / maxRev) * (height - paddingY * 2);
      return {
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        date: d.fecha,
        label: d.dia_etiqueta,
        units: d.unidades,
        revenue: d.ingresos,
      };
    });
  });

  readonly svgLinePath = computed<string>(() => {
    const pts = this.chartPoints();
    if (pts.length === 0) return '';
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y}`;

    return pts.reduce((acc, p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`), '');
  });

  readonly svgAreaPath = computed<string>(() => {
    const pts = this.chartPoints();
    if (pts.length < 2) return '';
    const line = this.svgLinePath();
    const lastX = pts[pts.length - 1].x;
    const firstX = pts[0].x;
    const bottomY = 160;
    return `${line} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  });

  ngOnInit(): void {
    this.loadFilters();
    this.loadAnalytics();
  }

  loadFilters(): void {
    this.isLoadingFilters.set(true);
    this.dashboardService
      .getFilters()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: DashboardFiltersResponse) => {
          this.branches.set(res.sucursales || []);
          this.categories.set(res.categorias || []);
          if (res.periodos_disponibles && res.periodos_disponibles.length > 0) {
            this.availablePeriods.set(res.periodos_disponibles);
          }
          this.isLoadingFilters.set(false);
        },
        error: (err) => {
          this.isLoadingFilters.set(false);
          // Si falla por suscripción o red, mantenemos valores por defecto
        },
      });
  }

  loadAnalytics(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    const payload: DashboardAnalyticsRequest = {
      dias_periodo: this.selectedPeriod(),
      id_sucursal: this.selectedBranchId() !== null ? Number(this.selectedBranchId()) : null,
      id_categoria: this.selectedCategoryId() !== null ? Number(this.selectedCategoryId()) : null,
    };

    this.dashboardService
      .getAnalytics(payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.analytics.set(res);
          this.isLoading.set(false);
        },
        error: (err) => {
          this.isLoading.set(false);
          const detail =
            err?.error?.detail ||
            err?.error?.message ||
            'No fue posible cargar la información analítica del dashboard.';
          this.errorMessage.set(detail);
        },
      });
  }

  onPeriodChange(days: number): void {
    this.selectedPeriod.set(days);
    this.loadAnalytics();
  }

  onBranchChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.selectedBranchId.set(val ? Number(val) : null);
    this.loadAnalytics();
  }

  onCategoryChange(event: Event): void {
    const val = (event.target as HTMLSelectElement).value;
    this.selectedCategoryId.set(val ? Number(val) : null);
    this.loadAnalytics();
  }

  getRiskBadgeClass(level: string): string {
    switch (level) {
      case 'CRITICO':
        return 'badge-critical';
      case 'ALTO':
        return 'badge-high';
      case 'MEDIO':
        return 'badge-medium';
      default:
        return 'badge-low';
    }
  }
}

