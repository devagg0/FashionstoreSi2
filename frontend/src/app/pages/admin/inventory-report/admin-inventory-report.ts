import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { EMPTY, Observable, Subscription, expand, forkJoin, reduce } from 'rxjs';
import { AdminInventoryReportService, InventoryReportData, InventoryReportFilters } from '../../../core/services/admin-inventory-report.service';
import { AdminBranchesService, AdminBranch } from '../../../core/services/admin-branches.service';
import { AdminCategoriesService, AdminCategory } from '../../../core/services/admin-categories.service';
import { AdminProductsService, AdminProduct } from '../../../core/services/admin-products.service';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';

interface OptionPage<T> { data: T[]; pagination: { page: number; total_pages: number } }
interface ChartRow { label: string; value: number }

@Component({
  selector: 'app-admin-inventory-report', imports: [FormsModule],
  templateUrl: './admin-inventory-report.html', styleUrl: './admin-inventory-report.scss',
})
export class AdminInventoryReport {
  private readonly api = inject(AdminInventoryReportService);
  private readonly branchApi = inject(AdminBranchesService);
  private readonly categoryApi = inject(AdminCategoriesService);
  private readonly productApi = inject(AdminProductsService);
  private readonly errors = inject(AdminApiErrorService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  private optionsRequest?: Subscription;
  private applied: InventoryReportFilters = { page: 1, page_size: 20 };
  filters: InventoryReportFilters = {};
  readonly report = signal<InventoryReportData | null>(null);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly optionsError = signal('');
  readonly optionsLoading = signal(false);
  readonly branches = signal<AdminBranch[]>([]);
  readonly categories = signal<AdminCategory[]>([]);
  readonly products = signal<AdminProduct[]>([]);
  readonly kpis = computed(() => {
    const k = this.report()?.kpis;
    return k ? [
      { label: 'Total productos', value: k.total_productos },
      { label: 'Total variantes', value: k.total_variantes },
      { label: 'Unidades actuales', value: k.unidades_actuales },
      { label: 'Unidades reservadas', value: k.unidades_reservadas },
      { label: 'Unidades disponibles', value: k.unidades_disponibles },
      { label: 'Registros agotados', value: k.registros_agotados },
      { label: 'Registros bajo stock', value: k.registros_bajo_stock },
      { label: 'Productos con faltantes', value: k.productos_con_agotados },
      { label: 'Productos con bajo stock', value: k.productos_con_bajo_stock },
      { label: 'Mínimos en cero', value: k.registros_con_stock_minimo_cero },
    ] : [];
  });
  readonly charts = computed(() => {
    const r = this.report();
    if (!r) return [];
    // Las advertencias ignoran estado_stock; restar negativos solo sin ese filtro.
    const negative = r.filtros.estado_stock ? 0 : r.advertencias.reduce((n, w) => n + w.registros, 0);
    const states = [
      { label: 'NORMAL', value: r.kpis.total_registros_inventario - r.kpis.registros_agotados - r.kpis.registros_bajo_stock - negative },
      { label: 'BAJO STOCK', value: r.kpis.registros_bajo_stock },
      { label: 'AGOTADO', value: r.kpis.registros_agotados },
    ];
    if (negative) states.push({ label: 'INCONSISTENCIA', value: negative });
    return [
      { title: 'Inventario por sucursal', unit: 'Unidades disponibles', rows: r.por_sucursal.map(x => ({ label: x.nombre + (x.estado ? '' : ' (inactiva)'), value: x.unidades_disponibles })) },
      { title: 'Inventario por categoría', unit: 'Unidades disponibles', rows: r.por_categoria.map(x => ({ label: x.nombre + (x.estado ? '' : ' (inactiva)'), value: x.unidades_disponibles })) },
      { title: 'Distribución de estados', unit: 'Registros de sucursal + variante', rows: states },
    ];
  });

  constructor() { this.loadOptions(); this.apply(); }

  apply(): void {
    this.applied = { ...this.filters, page: 1, page_size: this.applied.page_size };
    this.load();
  }
  clear(): void { this.filters = {}; this.applied = { page: 1, page_size: 20 }; this.apply(); }
  retry(): void { this.load(); }
  goToPage(page: number): void {
    const pagination = this.report()?.detalle.pagination;
    if (this.loading() || !pagination || page < 1 || page > pagination.total_pages) return;
    this.applied = { ...this.applied, page };
    this.load();
  }
  resize(size: number): void {
    if (![10, 20, 50, 100].includes(size)) return;
    this.applied = { ...this.applied, page: 1, page_size: size };
    this.load();
  }
  width(row: ChartRow, rows: ChartRow[]): number {
    return Math.abs(row.value) / Math.max(1, ...rows.map(x => Math.abs(x.value))) * 100;
  }
  private load(): void {
    this.request?.unsubscribe();
    this.loading.set(true);
    this.error.set('');
    this.report.set(null);
    this.request = this.api.report({ ...this.applied }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.report.set(result.data); this.loading.set(false); },
      error: error => {
        this.error.set(this.errors.resolve(error, { fallback: 'No pudimos cargar el reporte de inventario. Inténtalo nuevamente.' }));
        this.loading.set(false);
      },
    });
  }
  loadOptions(): void {
    this.optionsRequest?.unsubscribe();
    this.optionsLoading.set(true);
    this.optionsError.set('');
    this.optionsRequest = forkJoin({
      branches: this.allPages(page => this.branchApi.listBranches({ page, pageSize: 100 })),
      categories: this.allPages(page => this.categoryApi.listCategories({ page, pageSize: 100 })),
      products: this.allPages(page => this.productApi.listProducts({ page, pageSize: 100 })),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: r => { this.branches.set(r.branches); this.categories.set(r.categories); this.products.set(r.products); this.optionsLoading.set(false); },
      error: error => { this.optionsError.set(this.errors.resolve(error, { fallback: 'No pudimos cargar sucursales, categorías y productos.' })); this.optionsLoading.set(false); },
    });
  }
  private allPages<T>(fetch: (page: number) => Observable<OptionPage<T>>): Observable<T[]> {
    return fetch(1).pipe(
      expand(r => r.pagination.page < r.pagination.total_pages ? fetch(r.pagination.page + 1) : EMPTY),
      reduce((all, r) => [...all, ...r.data], [] as T[]),
    );
  }
}
