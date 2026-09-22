import { DecimalPipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { EMPTY, Observable, Subscription, expand, forkJoin, reduce } from 'rxjs';
import {
  AdminReservationsReportService,
  ReservationState,
  ReservationsReportData,
  ReservationsReportFilters,
} from '../../../core/services/admin-reservations-report.service';
import { AdminBranchesService, AdminBranch } from '../../../core/services/admin-branches.service';
import { AdminCategoriesService, AdminCategory } from '../../../core/services/admin-categories.service';
import { AdminProductsService, AdminProduct } from '../../../core/services/admin-products.service';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { GeneratedPdf, ReportPdfService } from '../../../core/services/report-pdf.service';
import { ReportAIAnalysis, ReportAIService } from '../../../core/services/report-ai.service';
import { SpeechRecognitionService } from '../../../core/services/speech-recognition.service';
import { PdfReport } from '../../../core/utils/pdf';
import { Icon, IconName } from '../../../shared/components/icon/icon';

interface OptionPage<T> { data: T[]; pagination: { page: number; total_pages: number } }
export interface DonutSegment {
  key: string; label: string; value: number; units: number; percent: number;
  dash: number; gap: number; offset: number; tone: string;
}
export interface RankRow {
  key: number | string; label: string; reservations: number; units: number; percent: number;
}

/** Geometría del donut: radio 54 dentro de un lienzo de 160×160. */
const DONUT_CIRCUMFERENCE = 2 * Math.PI * 54;
const STATE_TONES: Record<ReservationState, { label: string; tone: string }> = {
  PENDIENTE: { label: 'Pendientes', tone: 'warn' },
  CONFIRMADA: { label: 'Confirmadas', tone: 'info' },
  ATENDIDA: { label: 'Atendidas', tone: 'ok' },
  CANCELADA: { label: 'Canceladas', tone: 'off' },
  EXPIRADA: { label: 'Expiradas', tone: 'danger' },
};
const CATEGORY_TONES = ['info', 'ok', 'warn', 'danger', 'off'];
const DATE_KIND_LABELS = { CREACION: 'Creación', PROGRAMADA: 'Atención programada', ATENCION: 'Atención real' };
const PERIOD_LABELS = { DIA: 'Día', SEMANA: 'Semana', MES: 'Mes' };
const integers = new Intl.NumberFormat('es-BO');

export function currentReservationsMonth(now = new Date()): ReservationsReportFilters {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/La_Paz', year: 'numeric', month: '2-digit' }).formatToParts(now);
  const year = parts.find(p => p.type === 'year')!.value;
  const month = parts.find(p => p.type === 'month')!.value;
  const last = new Date(Number(year), Number(month), 0).getDate();
  return {
    fecha_desde: `${year}-${month}-01`, fecha_hasta: `${year}-${month}-${last}`,
    tipo_fecha: 'CREACION', periodo: 'DIA',
  };
}

/** Etiqueta del eje X sin desfases de zona horaria: la API ya envía fechas locales. */
export function periodLabel(iso: string, periodo: ReservationsReportFilters['periodo']): string {
  const [year, month, day] = iso.split('-').map(Number);
  const months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const name = months[(month || 1) - 1] ?? '';
  if (periodo === 'MES') return `${name} ${year}`;
  if (periodo === 'SEMANA') return `sem. ${day} ${name}`;
  return `${day} ${name}`;
}

@Component({
  selector: 'app-admin-reservations-report',
  imports: [DecimalPipe, FormsModule, Icon],
  templateUrl: './admin-reservations-report.html',
  styleUrl: './admin-reservations-report.scss',
})
export class AdminReservationsReport {
  private readonly api = inject(AdminReservationsReportService);
  private readonly branchApi = inject(AdminBranchesService);
  private readonly categoryApi = inject(AdminCategoriesService);
  private readonly productApi = inject(AdminProductsService);
  private readonly errors = inject(AdminApiErrorService);
  private readonly pdfService = inject(ReportPdfService);
  private readonly aiService = inject(ReportAIService);
  private readonly speech = inject(SpeechRecognitionService);
  private readonly destroyRef = inject(DestroyRef);
  private request?: Subscription;
  private aiRequest?: Subscription;

  filters: ReservationsReportFilters = currentReservationsMonth();
  readonly report = signal<ReservationsReportData | null>(null);
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
  readonly products = signal<AdminProduct[]>([]);
  readonly states = Object.entries(STATE_TONES).map(([value, meta]) => ({ value: value as ReservationState, label: meta.label }));
  readonly periodLabel = periodLabel;

  readonly kpis = computed<{ label: string; value: number; hint: string; tone: string; icon: IconName }[]>(() => {
    const k = this.report()?.kpis;
    return k ? [
      { label: 'Total de reservas', value: k.total_reservas, hint: 'Reservas en el alcance filtrado', tone: 'neutral', icon: 'dashboard' },
      { label: 'Pendientes', value: k.reservas_pendientes, hint: 'Esperan confirmación', tone: 'warn', icon: 'refresh' },
      { label: 'Confirmadas', value: k.reservas_confirmadas, hint: 'Listas para ser atendidas', tone: 'info', icon: 'check' },
      { label: 'Atendidas', value: k.reservas_atendidas, hint: 'Entregadas al cliente', tone: 'ok', icon: 'circle-check' },
      { label: 'Canceladas', value: k.reservas_canceladas, hint: 'Anuladas antes de atender', tone: 'off', icon: 'close' },
      { label: 'Expiradas', value: k.reservas_expiradas, hint: 'Vencieron sin atención', tone: 'danger', icon: 'ban' },
      { label: 'Unidades reservadas', value: k.unidades_reservadas, hint: 'Suma de cantidades reservadas', tone: 'neutral', icon: 'bag' },
      { label: 'Clientes con reservas', value: k.clientes_con_reservas, hint: 'Clientes distintos del período', tone: 'neutral', icon: 'users' },
    ] : [];
  });

  readonly stateDonut = computed(() => this.donut(
    (this.report()?.por_estado ?? []).map(row => ({
      key: row.estado, label: STATE_TONES[row.estado].label, value: row.total_reservas,
      units: row.unidades_reservadas, tone: STATE_TONES[row.estado].tone,
    })),
  ));
  readonly stateTotal = computed(() => this.stateDonut().reduce((total, segment) => total + segment.value, 0));
  readonly categoryDonut = computed(() => this.donut(
    (this.report()?.categorias_mas_reservadas ?? []).map((row, index) => ({
      key: String(row.id_categoria), label: row.nombre_categoria, value: row.total_reservas,
      units: row.unidades_reservadas, tone: CATEGORY_TONES[index % CATEGORY_TONES.length],
    })),
  ));
  readonly categoryTotal = computed(() => this.categoryDonut().reduce((total, segment) => total + segment.value, 0));

  /** Evolución: reservas (área) y unidades (línea punteada) sobre un lienzo 640×220. */
  readonly series = computed(() => {
    const rows = [...(this.report()?.serie_periodica ?? [])].sort((a, b) => a.inicio_periodo.localeCompare(b.inicio_periodo));
    const max = Math.max(1, ...rows.map(row => Math.max(row.total_reservas, row.unidades_reservadas)));
    const left = 46, right = 620, base = 182, top = 20;
    const step = rows.length > 1 ? (right - left) / (rows.length - 1) : 0;
    const periodo = this.report()?.filtros.periodo ?? this.filters.periodo ?? 'DIA';
    return rows.map((row, index) => ({
      ...row,
      label: periodLabel(row.inicio_periodo, periodo),
      x: rows.length > 1 ? left + index * step : (left + right) / 2,
      y: base - (row.total_reservas / max) * (base - top),
      yUnits: base - (row.unidades_reservadas / max) * (base - top),
    }));
  });
  readonly seriesMax = computed(() => Math.max(1, ...this.series().flatMap(point => [point.total_reservas, point.unidades_reservadas])));
  readonly seriesGrid = computed(() => [4, 3, 2, 1, 0].map(step => ({
    y: 182 - (step / 4) * 162,
    value: Math.round((this.seriesMax() * step) / 4),
  })));
  readonly seriesLine = computed(() => this.series().map(point => `${point.x},${point.y}`).join(' '));
  readonly seriesUnitsLine = computed(() => this.series().map(point => `${point.x},${point.yUnits}`).join(' '));
  readonly seriesArea = computed(() => {
    const points = this.series();
    if (!points.length) return '';
    return `M ${points[0].x},182 L ${points.map(point => `${point.x},${point.y}`).join(' L ')} L ${points.at(-1)!.x},182 Z`;
  });
  /** Muestra como máximo seis etiquetas del eje X para no saturar pantallas pequeñas. */
  readonly seriesTicks = computed(() => {
    const points = this.series();
    const every = Math.ceil(points.length / 6);
    return points.filter((_, index) => index % every === 0 || index === points.length - 1);
  });

  readonly branchRows = computed<RankRow[]>(() => this.rank(
    (this.report()?.por_sucursal ?? []).map(row => ({
      key: row.id_sucursal, label: row.nombre_sucursal,
      reservations: row.total_reservas, units: row.unidades_reservadas,
    })),
  ));
  readonly productRows = computed<RankRow[]>(() => this.rank(
    (this.report()?.productos_mas_reservados ?? []).map(row => ({
      key: row.id_producto, label: row.nombre_producto,
      reservations: row.total_reservas, units: row.unidades_reservadas,
    })), 'units',
  ));
  readonly categoryRows = computed<RankRow[]>(() => this.rank(
    (this.report()?.categorias_mas_reservadas ?? []).map(row => ({
      key: row.id_categoria, label: row.nombre_categoria,
      reservations: row.total_reservas, units: row.unidades_reservadas,
    })), 'units',
  ));
  readonly expiredWarning = computed(() => this.report()?.advertencias.reservas_vencidas_sin_actualizar ?? 0);
  readonly noResults = computed(() => !!this.report() && this.report()!.kpis.total_reservas === 0);

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
    this.pdf.set(null);
    this.pdfError.set('');
    this.aiRequest?.unsubscribe();
    this.aiAnalysis.set(null);
    this.aiError.set('');
    this.aiLoading.set(false);
    this.voiceQuery.set('');
    this.request = this.api.report({ ...this.filters }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.report.set(result.data); this.loading.set(false); },
      error: error => {
        this.error.set(this.errors.resolve(error, { fallback: 'No pudimos cargar el reporte de reservas. Inténtalo nuevamente.' }));
        this.loading.set(false);
      },
    });
  }

  clear(): void { this.filters = currentReservationsMonth(); this.apply(); }

  generatePdf(): void {
    const data = this.report();
    if (!data) return;
    this.pdfError.set('');
    try {
      this.pdf.set(this.pdfService.generate(this.pdfDefinition(data), 'reporte-reservas'));
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
    this.aiRequest = this.aiService.analyze('/api/admin/reservations-report', data, pregunta)
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

  private pdfDefinition(data: ReservationsReportData): PdfReport {
    const applied = data.filtros;
    const branch = this.branches().find(x => x.id_sucursal === applied.id_sucursal)?.nombre;
    const category = this.categories().find(x => x.id_categoria === applied.id_categoria)?.nombre;
    const product = this.products().find(x => x.id_producto === applied.id_producto)?.nombre;
    const ranking = (rows: RankRow[], first: string) => ({
      columns: [
        { header: first, width: 4 },
        { header: 'Reservas', width: 1.5, align: 'right' as const },
        { header: 'Unidades reservadas', width: 2, align: 'right' as const },
      ],
      rows: rows.map(row => [row.label, integers.format(row.reservations), integers.format(row.units)]),
      empty: 'Sin reservas para estos filtros.',
    });
    return {
      title: 'Reporte de reservas y productos',
      subtitle: 'FashionStore · Demanda reservada, avance de atención y productos con mayor tracción.',
      meta: [
        { label: 'Desde', value: applied.fecha_desde || 'Sin límite inferior' },
        { label: 'Hasta', value: applied.fecha_hasta || 'Sin límite superior' },
        { label: 'Tipo de fecha', value: DATE_KIND_LABELS[applied.tipo_fecha] },
        { label: 'Período', value: PERIOD_LABELS[applied.periodo] },
        { label: 'Sucursal', value: branch ?? 'Todas las sucursales' },
        { label: 'Estado', value: applied.estado ? STATE_TONES[applied.estado].label : 'Todos los estados' },
        { label: 'Categoría', value: category ?? 'Todas las categorías' },
        { label: 'Producto', value: product ?? 'Todos los productos' },
      ],
      sections: [
        {
          heading: 'Indicadores principales',
          description: `Estados según el valor persistido. Agrupaciones en ${data.zona_horaria}.`,
          kpis: this.kpis().map(kpi => ({ label: kpi.label, value: integers.format(kpi.value) })),
        },
        {
          heading: 'Reservas por estado',
          table: {
            columns: [
              { header: 'Estado', width: 3 },
              { header: 'Reservas', width: 1.5, align: 'right' },
              { header: 'Unidades reservadas', width: 2, align: 'right' },
              { header: 'Participación', width: 1.6, align: 'right' },
            ],
            rows: this.stateDonut().map(segment => [
              segment.label,
              integers.format(segment.value),
              integers.format(segment.units),
              `${segment.percent.toFixed(1)} %`,
            ]),
            empty: 'Sin reservas en el período filtrado.',
          },
        },
        {
          heading: 'Reservas por sucursal',
          table: {
            columns: [
              { header: 'Sucursal', width: 3.5 },
              { header: 'Reservas', width: 1.5, align: 'right' },
              { header: 'Unidades reservadas', width: 2, align: 'right' },
              { header: 'Clientes', width: 1.3, align: 'right' },
            ],
            rows: data.por_sucursal.map(row => [
              row.nombre_sucursal,
              integers.format(row.total_reservas),
              integers.format(row.unidades_reservadas),
              integers.format(row.clientes_con_reservas),
            ]),
            empty: 'Sin reservas por sucursal para estos filtros.',
          },
        },
        {
          heading: 'Evolución por período',
          description: `Agrupado por ${PERIOD_LABELS[applied.periodo].toLowerCase()}; solo se listan los períodos devueltos por la API.`,
          table: {
            columns: [
              { header: 'Período', width: 2.5 },
              { header: 'Inicio', width: 2 },
              { header: 'Reservas', width: 1.5, align: 'right' },
              { header: 'Unidades reservadas', width: 2, align: 'right' },
            ],
            rows: this.series().map(point => [
              point.label,
              point.inicio_periodo,
              integers.format(point.total_reservas),
              integers.format(point.unidades_reservadas),
            ]),
            empty: 'Sin períodos con reservas.',
          },
        },
        { heading: 'Productos más reservados', table: ranking(this.productRows(), 'Producto') },
        {
          heading: 'Categorías más reservadas',
          table: ranking(this.categoryRows(), 'Categoría'),
          notes: this.expiredWarning()
            ? [`${integers.format(this.expiredWarning())} reserva(s) vencida(s) siguen registradas con un estado anterior a EXPIRADA.`]
            : [],
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
      products: this.allPages(page => this.productApi.listProducts({ page, pageSize: 100 })),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.branches.set(result.branches);
        this.categories.set(result.categories);
        this.products.set(result.products);
        this.optionsLoading.set(false);
      },
      error: error => {
        this.optionsError.set(this.errors.resolve(error, { fallback: 'No pudimos cargar sucursales, categorías y productos.' }));
        this.optionsLoading.set(false);
      },
    });
  }

  private donut(rows: { key: string; label: string; value: number; units: number; tone: string }[]): DonutSegment[] {
    const total = rows.reduce((sum, row) => sum + row.value, 0);
    if (!total) return [];
    let consumed = 0;
    return rows.filter(row => row.value > 0).map(row => {
      const percent = (row.value / total) * 100;
      const dash = (percent / 100) * DONUT_CIRCUMFERENCE;
      const segment = { ...row, percent, dash, gap: DONUT_CIRCUMFERENCE - dash, offset: -consumed };
      consumed += dash;
      return segment;
    });
  }

  private rank(rows: Omit<RankRow, 'percent'>[], by: 'units' | 'reservations' = 'reservations'): RankRow[] {
    const max = Math.max(1, ...rows.map(row => row[by]));
    return rows.map(row => ({ ...row, percent: (row[by] / max) * 100 }));
  }

  private allPages<T>(fetch: (page: number) => Observable<OptionPage<T>>): Observable<T[]> {
    return fetch(1).pipe(
      expand(result => result.pagination.page < result.pagination.total_pages ? fetch(result.pagination.page + 1) : EMPTY),
      reduce((all, result) => [...all, ...result.data], [] as T[]),
    );
  }
}
