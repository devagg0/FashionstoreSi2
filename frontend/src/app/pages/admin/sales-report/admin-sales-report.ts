import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { EMPTY, Observable, Subscription, expand, forkJoin, reduce } from 'rxjs';
import { AdminSalesReportService, SalesReportData, SalesReportFilters } from '../../../core/services/admin-sales-report.service';
import { AdminBranchesService, AdminBranch } from '../../../core/services/admin-branches.service';
import { AdminCategoriesService, AdminCategory } from '../../../core/services/admin-categories.service';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { GeneratedPdf, ReportPdfService } from '../../../core/services/report-pdf.service';
import { ReportAIAnalysis, ReportAIService } from '../../../core/services/report-ai.service';
import { SpeechRecognitionService } from '../../../core/services/speech-recognition.service';
import { PdfReport } from '../../../core/utils/pdf';
import { formatBs } from '../../../core/utils/money';

interface ChartRow { label: string; value: number; display: string }
interface OptionPage<T> { data: T[]; pagination: { page: number; total_pages: number } }

const integers = new Intl.NumberFormat('es-BO');

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
  private readonly pdfService = inject(ReportPdfService);
  private readonly aiService = inject(ReportAIService);
  private readonly speech = inject(SpeechRecognitionService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  private aiRequest?: Subscription;
  /** Filtros vigentes del reporte en pantalla; la respuesta no los devuelve. */
  private appliedFilters: SalesReportFilters = currentSalesMonth();
  filters = currentSalesMonth();
  readonly report = signal<SalesReportData | null>(null);
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
    this.resetPdf();
    this.resetAiAnalysis();
    this.appliedFilters = { ...this.filters };
    this.request = this.api.report({ ...this.filters }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.report.set(result.data); this.loading.set(false); },
      error: error => { this.error.set(this.errors.resolve(error, { fallback: 'No pudimos cargar el reporte de ventas. Inténtalo nuevamente.' })); this.loading.set(false); },
    });
  }
  clear(): void { this.filters = currentSalesMonth(); this.apply(); }
  width(row: ChartRow, rows: ChartRow[]): number {
    return Math.max(0, row.value) / Math.max(1, ...rows.map(x => x.value)) * 100;
  }

  generatePdf(): void {
    const data = this.report();
    if (!data) return;
    this.pdfError.set('');
    try {
      this.pdf.set(this.pdfService.generate(this.pdfDefinition(data), 'reporte-ventas'));
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

  private resetPdf(): void {
    this.pdf.set(null);
    this.pdfError.set('');
  }

  analyzeWithAI(pregunta?: string): void {
    const data = this.report();
    if (!data) return;
    this.aiRequest?.unsubscribe();
    this.aiLoading.set(true);
    this.aiError.set('');
    this.aiAnalysis.set(null);
    this.aiRequest = this.aiService.analyze('/api/admin/sales-report', data, pregunta)
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

  private resetAiAnalysis(): void {
    this.aiRequest?.unsubscribe();
    this.aiAnalysis.set(null);
    this.aiError.set('');
    this.aiLoading.set(false);
    this.voiceQuery.set('');
  }

  private pdfDefinition(data: SalesReportData): PdfReport {
    const applied = this.appliedFilters;
    const branch = this.branches().find(x => x.id_sucursal === applied.id_sucursal)?.nombre;
    const category = this.categories().find(x => x.id_categoria === applied.id_categoria)?.nombre;
    const totals = (row: { cantidad_ventas: number; unidades_vendidas: number; descuentos: string; importe_vendido: string; ticket_promedio: string | null }) => [
      integers.format(row.cantidad_ventas),
      integers.format(row.unidades_vendidas),
      formatBs(row.descuentos),
      formatBs(row.importe_vendido),
      row.ticket_promedio === null ? '—' : formatBs(row.ticket_promedio),
    ];
    const breakdownColumns = (first: string) => [
      { header: first, width: 3 },
      { header: 'Ventas', width: 1.2, align: 'right' as const },
      { header: 'Unidades', width: 1.3, align: 'right' as const },
      { header: 'Descuentos', width: 1.7, align: 'right' as const },
      { header: 'Importe vendido', width: 2, align: 'right' as const },
      { header: 'Ticket promedio', width: 2, align: 'right' as const },
    ];
    return {
      title: 'Reporte de ventas',
      subtitle: 'FashionStore · Indicadores comerciales del período filtrado.',
      meta: [
        { label: 'Desde', value: applied.fecha_desde || 'Sin límite inferior' },
        { label: 'Hasta', value: applied.fecha_hasta || 'Sin límite superior' },
        { label: 'Sucursal', value: branch ?? 'Todas las sucursales' },
        { label: 'Canal', value: applied.canal === 'DIGITAL' ? 'Digital' : applied.canal === 'PRESENCIAL' ? 'Presencial' : 'Todos los canales' },
        { label: 'Categoría', value: category ?? 'Todas las categorías' },
        { label: 'Moneda', value: `${data.moneda} · ${data.zona_horaria}` },
      ],
      sections: [
        { heading: 'Indicadores principales', kpis: this.kpis().map(kpi => ({ label: kpi.label, value: String(kpi.value) })) },
        {
          heading: 'Ventas por canal',
          table: {
            columns: breakdownColumns('Canal'),
            rows: data.por_canal.map(row => [row.canal === 'DIGITAL' ? 'Digital' : 'Presencial', ...totals(row)]),
            empty: 'Sin ventas en los canales para estos filtros.',
          },
        },
        {
          heading: 'Ventas por sucursal',
          table: {
            columns: breakdownColumns('Sucursal'),
            rows: data.por_sucursal.map(row => [row.nombre_sucursal, ...totals(row)]),
            empty: 'Sin ventas por sucursal para estos filtros.',
          },
        },
        {
          heading: 'Productos más vendidos',
          table: {
            columns: [
              { header: 'Producto', width: 4 },
              { header: 'Unidades', width: 1.4, align: 'right' },
              { header: 'Antes de descuentos', width: 2.1, align: 'right' },
              { header: 'Descuentos', width: 1.8, align: 'right' },
              { header: 'Importe vendido', width: 2.1, align: 'right' },
            ],
            rows: data.productos_mas_vendidos.map(row => [
              row.nombre_producto,
              integers.format(row.unidades_vendidas),
              formatBs(row.importe_antes_descuentos),
              formatBs(row.descuentos),
              formatBs(row.importe_vendido),
            ]),
            empty: 'No hay productos vendidos en este período.',
          },
        },
        {
          heading: 'Evolución diaria',
          description: 'Solo se listan los días con ventas devueltos por la API.',
          table: {
            columns: breakdownColumns('Fecha'),
            rows: [...data.serie_diaria]
              .sort((a, b) => a.fecha.localeCompare(b.fecha))
              .map(row => [row.fecha, ...totals(row)]),
            empty: 'Sin ventas diarias en el período.',
          },
        },
      ],
    };
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
