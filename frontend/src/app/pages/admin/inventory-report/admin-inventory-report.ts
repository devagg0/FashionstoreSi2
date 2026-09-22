import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { EMPTY, Observable, Subscription, expand, forkJoin, reduce } from 'rxjs';
import { AdminInventoryReportService, InventoryReportData, InventoryReportFilters } from '../../../core/services/admin-inventory-report.service';
import { AdminBranchesService, AdminBranch } from '../../../core/services/admin-branches.service';
import { AdminCategoriesService, AdminCategory } from '../../../core/services/admin-categories.service';
import { AdminProductsService, AdminProduct } from '../../../core/services/admin-products.service';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { GeneratedPdf, ReportPdfService } from '../../../core/services/report-pdf.service';
import { ReportAIAnalysis, ReportAIService } from '../../../core/services/report-ai.service';
import { SpeechRecognitionService } from '../../../core/services/speech-recognition.service';
import { PdfReport } from '../../../core/utils/pdf';

interface OptionPage<T> { data: T[]; pagination: { page: number; total_pages: number } }
interface ChartRow { label: string; value: number }

const integers = new Intl.NumberFormat('es-BO');
const STOCK_LABELS: Record<string, string> = { NORMAL: 'Normal', BAJO_STOCK: 'Bajo stock', AGOTADO: 'Agotado' };

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
  private readonly pdfService = inject(ReportPdfService);
  private readonly aiService = inject(ReportAIService);
  private readonly speech = inject(SpeechRecognitionService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  private optionsRequest?: Subscription;
  private aiRequest?: Subscription;
  private applied: InventoryReportFilters = { page: 1, page_size: 20 };
  filters: InventoryReportFilters = {};
  readonly report = signal<InventoryReportData | null>(null);
  readonly pdf = signal<GeneratedPdf | null>(null);
  readonly pdfError = signal('');
  readonly aiAnalysis = signal<ReportAIAnalysis | null>(null);
  readonly aiLoading = signal(false);
  readonly aiError = signal('');
  readonly voiceQuery = signal('');
  readonly voiceSupported = this.speech.supported;
  readonly voiceListening = this.speech.listening;
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

  generatePdf(): void {
    const data = this.report();
    if (!data) return;
    this.pdfError.set('');
    try {
      this.pdf.set(this.pdfService.generate(this.pdfDefinition(data), 'reporte-inventario'));
    } catch {
      this.pdf.set(null);
      this.pdfError.set('No pudimos generar el PDF del reporte. Inténtalo nuevamente.');
    }
  }

  downloadPdf(): void {
    const file = this.pdf();
    if (!file) return;
    this.pdfError.set('');
    try {
      this.pdfService.download(file);
    } catch {
      this.pdfError.set('No pudimos descargar el PDF. Inténtalo nuevamente.');
    }
  }

  analyzeWithAI(pregunta?: string): void {
    const data = this.report();
    if (!data) return;
    this.aiRequest?.unsubscribe();
    this.aiLoading.set(true);
    this.aiError.set('');
    this.aiAnalysis.set(null);
    this.aiRequest = this.aiService.analyze('/api/admin/inventory-report', data, pregunta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => { this.aiAnalysis.set(result.data); this.aiLoading.set(false); },
        error: error => {
          this.aiError.set(this.errors.resolve(error, { fallback: 'No pudimos generar el análisis con IA. Inténtalo nuevamente.' }));
          this.aiLoading.set(false);
        },
      });
  }

  /** Escucha una consulta hablada y la envia al mismo flujo de analisis con IA. */
  async analyzeWithVoice(): Promise<void> {
    if (!this.report() || this.voiceListening()) return;
    this.aiError.set('');
    try {
      const transcript = await this.speech.listenOnce();
      this.voiceQuery.set(transcript);
      this.analyzeWithAI(transcript);
    } catch (error) {
      this.aiError.set(error instanceof Error ? error.message : 'No fue posible reconocer la consulta por voz.');
    }
  }

  private pdfDefinition(data: InventoryReportData): PdfReport {
    const branch = this.branches().find(x => x.id_sucursal === data.filtros.id_sucursal)?.nombre;
    const category = this.categories().find(x => x.id_categoria === data.filtros.id_categoria)?.nombre;
    const product = this.products().find(x => x.id_producto === data.filtros.id_producto)?.nombre;
    const pagination = data.detalle.pagination;
    const breakdown = (rows: { nombre: string; estado: boolean; unidades_actuales: number; unidades_reservadas: number; unidades_disponibles: number; registros_agotados: number; registros_bajo_stock: number }[], first: string) => ({
      columns: [
        { header: first, width: 3 },
        { header: 'Actuales', width: 1.3, align: 'right' as const },
        { header: 'Reservadas', width: 1.5, align: 'right' as const },
        { header: 'Disponibles', width: 1.5, align: 'right' as const },
        { header: 'Agotados', width: 1.3, align: 'right' as const },
        { header: 'Bajo stock', width: 1.4, align: 'right' as const },
      ],
      rows: rows.map(row => [
        row.nombre + (row.estado ? '' : ' (inactiva)'),
        integers.format(row.unidades_actuales),
        integers.format(row.unidades_reservadas),
        integers.format(row.unidades_disponibles),
        integers.format(row.registros_agotados),
        integers.format(row.registros_bajo_stock),
      ]),
      empty: 'Sin registros para estos filtros.',
    });
    return {
      title: 'Reporte de inventario',
      subtitle: 'FashionStore · Existencias, reservas y necesidades de reposición.',
      meta: [
        { label: 'Sucursal', value: branch ?? 'Todas las sucursales' },
        { label: 'Categoría', value: category ?? 'Todas las categorías' },
        { label: 'Producto', value: product ?? 'Todos los productos' },
        { label: 'Estado de stock', value: data.filtros.estado_stock ? STOCK_LABELS[data.filtros.estado_stock] : 'Todos los estados' },
        { label: 'Página del detalle', value: `${pagination.page} de ${pagination.total_pages || 1} · ${integers.format(pagination.total)} registros` },
      ],
      sections: [
        {
          heading: 'Indicadores principales',
          description: 'Indicadores sobre todos los resultados filtrados, incluidos los registros inactivos.',
          kpis: this.kpis().map(kpi => ({ label: kpi.label, value: integers.format(kpi.value) })),
        },
        { heading: 'Inventario por sucursal', table: breakdown(data.por_sucursal, 'Sucursal') },
        { heading: 'Inventario por categoría', table: breakdown(data.por_categoria, 'Categoría') },
        {
          heading: 'Detalle de existencias',
          description: `Página ${pagination.page} de ${pagination.total_pages || 1}. Disponible = actual − reservado.`,
          table: {
            columns: [
              { header: 'Sucursal', width: 2 },
              { header: 'Producto', width: 2.6 },
              { header: 'SKU', width: 1.7 },
              { header: 'Talla', width: 1 },
              { header: 'Color', width: 1.2 },
              { header: 'Actual', width: 1, align: 'right' },
              { header: 'Reserv.', width: 1.1, align: 'right' },
              { header: 'Dispon.', width: 1.1, align: 'right' },
              { header: 'Mínimo', width: 1, align: 'right' },
              { header: 'Estado', width: 1.5 },
            ],
            rows: data.detalle.items.map(item => [
              item.sucursal.nombre,
              item.producto.nombre,
              item.variante.sku,
              item.variante.talla,
              item.variante.color,
              integers.format(item.stock_actual),
              integers.format(item.stock_reservado),
              integers.format(item.stock_disponible),
              integers.format(item.stock_minimo),
              item.estado_stock === null ? 'Inconsistencia' : STOCK_LABELS[item.estado_stock],
            ]),
            empty: 'No hay registros en esta página.',
          },
          notes: data.advertencias.map(warning => `${integers.format(warning.registros)} registro(s) con inconsistencia. ${warning.mensaje}`),
        },
      ],
    };
  }

  private load(): void {
    this.request?.unsubscribe();
    this.loading.set(true);
    this.error.set('');
    this.report.set(null);
    this.pdf.set(null);
    this.pdfError.set('');
    this.aiRequest?.unsubscribe();
    this.aiAnalysis.set(null);
    this.aiError.set('');
    this.aiLoading.set(false);
    this.voiceQuery.set('');
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
