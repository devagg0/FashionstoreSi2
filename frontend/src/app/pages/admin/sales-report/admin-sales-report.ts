import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { EMPTY, Observable, Subscription, expand, forkJoin, reduce } from 'rxjs';
import { AdminSalesReportService, SalesReportData, SalesReportFilters } from '../../../core/services/admin-sales-report.service';
import { AdminBranchesService, AdminBranch } from '../../../core/services/admin-branches.service';
import { AdminCategoriesService, AdminCategory } from '../../../core/services/admin-categories.service';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { formatBs } from '../../../core/utils/money';

interface ChartRow { label: string; value: number; display: string }
interface OptionPage<T> { data: T[]; pagination: { page: number; total_pages: number } }

export function currentSalesMonth(now = new Date()): SalesReportFilters {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/La_Paz', year: 'numeric', month: '2-digit' }).formatToParts(now);
  const year = parts.find(p => p.type === 'year')!.value;
  const month = parts.find(p => p.type === 'month')!.value;
  const last = new Date(Number(year), Number(month), 0).getDate();
  return { fecha_desde: `${year}-${month}-01`, fecha_hasta: `${year}-${month}-${last}` };
}

@Component({
  selector: 'app-admin-sales-report', imports: [FormsModule],
  templateUrl: './admin-sales-report.html', styleUrl: './admin-sales-report.scss',
})
export class AdminSalesReport {
  private readonly api = inject(AdminSalesReportService);
  private readonly branchApi = inject(AdminBranchesService);
  private readonly categoryApi = inject(AdminCategoriesService);
  private readonly errors = inject(AdminApiErrorService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  filters = currentSalesMonth();
  readonly report = signal<SalesReportData | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly validation = signal('');
  readonly optionsError = signal('');
  readonly optionsLoading = signal(false);
  readonly branches = signal<AdminBranch[]>([]);
  readonly categories = signal<AdminCategory[]>([]);
  readonly money = formatBs;
  readonly kpis = computed(() => {
    const k = this.report()?.kpis;
    return k ? [
      { label: 'Cantidad de ventas', value: k.cantidad_ventas },
      { label: 'Importe vendido', value: formatBs(k.importe_vendido) },
      { label: 'Ticket promedio', value: formatBs(k.ticket_promedio ?? 0) },
      { label: 'Unidades vendidas', value: k.unidades_vendidas },
      { label: 'Descuentos', value: formatBs(k.descuentos) },
      { label: 'Clientes identificados', value: k.clientes_identificados },
    ] : [];
  });
  readonly charts = computed(() => {
    const r = this.report();
    return r ? [
      { title: 'Ventas por canal', unit: 'Importe vendido · BOB', rows: r.por_canal.map(x => ({ label: x.canal === 'DIGITAL' ? 'Digital' : 'Presencial', value: Number(x.importe_vendido), display: formatBs(x.importe_vendido) })) },
      { title: 'Ventas por sucursal', unit: 'Importe vendido · BOB', rows: r.por_sucursal.map(x => ({ label: x.nombre_sucursal, value: Number(x.importe_vendido), display: formatBs(x.importe_vendido) })) },
      { title: 'Productos más vendidos', unit: 'Unidades vendidas', rows: r.productos_mas_vendidos.map(x => ({ label: x.nombre_producto, value: x.unidades_vendidas, display: `${x.unidades_vendidas} unidades` })) },
    ] : [];
  });
  readonly daily = computed(() => {
    const rows = [...(this.report()?.serie_diaria ?? [])].sort((a, b) => a.fecha.localeCompare(b.fecha));
    const max = Math.max(1, ...rows.map(x => Number(x.importe_vendido)));
    const start = Date.parse(rows[0]?.fecha ?? '1970-01-01');
    const span = Date.parse(rows.at(-1)?.fecha ?? '1970-01-01') - start;
    return rows.map(x => ({ ...x, x: span ? 20 + (Date.parse(x.fecha) - start) / span * 560 : 300, y: 180 - Number(x.importe_vendido) / max * 160 }));
  });
  readonly dailyPoints = computed(() => this.daily().map(p => `${p.x},${p.y}`).join(' '));

  constructor() { this.loadOptions(); this.apply(); }

  apply(): void {
    this.validation.set('');
    if (this.filters.fecha_desde && this.filters.fecha_hasta && this.filters.fecha_desde > this.filters.fecha_hasta) {
      this.validation.set('La fecha desde debe ser anterior o igual a la fecha hasta.');
      return;
    }
    this.request?.unsubscribe();
    this.loading.set(true);
    this.error.set('');
    this.report.set(null);
    this.request = this.api.report({ ...this.filters }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.report.set(result.data); this.loading.set(false); },
      error: error => { this.error.set(this.errors.resolve(error, { fallback: 'No pudimos cargar el reporte de ventas. Inténtalo nuevamente.' })); this.loading.set(false); },
    });
  }
  clear(): void { this.filters = currentSalesMonth(); this.apply(); }
  width(row: ChartRow, rows: ChartRow[]): number {
    return Math.max(0, row.value) / Math.max(1, ...rows.map(x => x.value)) * 100;
  }
  loadOptions(): void {
    this.optionsLoading.set(true);
    this.optionsError.set('');
    forkJoin({
      branches: this.allPages(page => this.branchApi.listBranches({ page, pageSize: 100 })),
      categories: this.allPages(page => this.categoryApi.listCategories({ page, pageSize: 100 })),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.branches.set(result.branches); this.categories.set(result.categories); this.optionsLoading.set(false); },
      error: error => { this.optionsError.set(this.errors.resolve(error, { fallback: 'No pudimos cargar sucursales y categorías.' })); this.optionsLoading.set(false); },
    });
  }
  private allPages<T>(fetch: (page: number) => Observable<OptionPage<T>>): Observable<T[]> {
    return fetch(1).pipe(
      expand(result => result.pagination.page < result.pagination.total_pages ? fetch(result.pagination.page + 1) : EMPTY),
      reduce((all, result) => [...all, ...result.data], [] as T[]),
    );
  }
}
