import { CommonModule } from '@angular/common';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  GeneratedReportSummary,
  NaturalLanguageReportData,
  NaturalLanguageReportService,
  ReportChartPoint,
} from '../../../core/services/natural-language-report.service';
import { ReportPdfService } from '../../../core/services/report-pdf.service';
import { PdfEntry, PdfReport, PdfSection } from '../../../core/utils/pdf';
import { SaasPlanLimitsService } from '../../../core/services/saas-plan-limits.service';
import { SpeechRecognitionService } from '../../../core/services/speech-recognition.service';
import { Icon } from '../../../shared/components/icon/icon';

export interface DonutSegment {
  key: string;
  label: string;
  value: number;
  formattedValue: string;
  percent: number;
  dash: number;
  gap: number;
  offset: number;
  color: string;
}

export interface BarRow {
  key: string;
  label: string;
  value: number;
  displayValue: string;
  percent: number;
  meta?: string;
  color?: string;
}

interface LineChartPoint {
  etiqueta: string;
  valor: number;
  x: number;
  y: number;
}

/** Geometría del donut: radio 54 en lienzo 160×160 (circunferencia = 2 * PI * 54). */
const DONUT_CIRCUMFERENCE = 2 * Math.PI * 54;

const PALETTE = [
  'var(--color-terracotta)',
  '#2a6f97',
  '#2b9348',
  '#e07a5f',
  '#81b29a',
  '#f2cc8f',
  '#6b705c',
  '#3d5a80',
  '#b56576',
  '#588157',
];

@Component({
  selector: 'app-admin-natural-language-report',
  imports: [CommonModule, FormsModule, RouterLink, Icon],
  templateUrl: './admin-natural-language-report.html',
  styleUrl: './admin-natural-language-report.scss',
})
export class AdminNaturalLanguageReport implements OnInit {
  private readonly reportService = inject(NaturalLanguageReportService);
  private readonly pdfService = inject(ReportPdfService);
  private readonly planLimitsService = inject(SaasPlanLimitsService);
  private readonly speech = inject(SpeechRecognitionService);
  private readonly destroyRef = inject(DestroyRef);

  readonly hasAiReports = this.planLimitsService.hasAiReports;
  readonly voiceSupported = this.speech.supported;
  readonly voiceListening = this.speech.listening;

  // Control de pestañas CU20 / CU21
  readonly activeTab = signal<'generar' | 'historial'>('generar');

  // Historial CU21
  readonly historyList = signal<GeneratedReportSummary[]>([]);
  readonly loadingHistory = signal(false);
  readonly historyError = signal('');
  readonly historyCount = computed(() => this.historyList().length);

  // Estado del reporte activo / visualizado
  readonly currentReportId = signal<number | null>(null);
  readonly isViewingSavedReport = signal(false);
  readonly savedReportDate = signal<string>('');
  readonly exportingExcel = signal(false);

  readonly queryText = signal('');
  readonly loading = signal(false);
  readonly error = signal('');
  readonly report = signal<NaturalLanguageReportData | null>(null);

  // Vistas dinámicas para los gráficos
  readonly stockDonutView = signal<'estado' | 'grupo'>('estado');
  readonly stockBarView = signal<'grupo' | 'productos'>('grupo');
  readonly barMode = signal<'bar' | 'line'>('bar');

  readonly exampleQueries = [
    'Ventas por canal del último mes',
    'Productos con stock bajo o agotado',
    'Cambios y devoluciones por motivo este mes',
    'Reservas por estado en los últimos 30 días',
    'Ventas por sucursal esta semana',
  ];

  readonly filterEntries = computed(() => {
    const filters = this.report()?.filtros_aplicados;
    if (!filters) return [];
    return Object.entries(filters).map(([clave, valor]) => ({ clave, valor }));
  });

  readonly groupLabel = computed(() => {
    const filters = this.report()?.filtros_aplicados;
    return filters?.['Agrupación'] || filters?.['agrupacion'] || 'Categoría';
  });

  readonly hasMultipleStockGroups = computed(() => {
    const rep = this.report();
    return rep?.tipo === 'STOCK' && (rep.grafico?.puntos?.length ?? 0) > 1;
  });

  readonly hasStockProducts = computed(() => {
    const rep = this.report();
    return rep?.tipo === 'STOCK' && (rep.tabla?.filas?.length ?? 0) > 0;
  });

  readonly isLineAvailable = computed(() => {
    const chart = this.report()?.grafico;
    return chart?.tipo === 'line' || this.linePoints().length > 0;
  });

  ngOnInit(): void {
    this.loadHistory();
  }

  /* -------------------------------------------------------------------------- */
  /*                         1. GRÁFICO DE DONA (CU20)                          */
  /* -------------------------------------------------------------------------- */

  readonly donutSegments = computed<DonutSegment[]>(() => {
    const rep = this.report();
    if (!rep || rep.estado !== 'OK') return [];

    let items: { key: string; label: string; value: number; formattedValue: string; color?: string }[] = [];

    if (rep.tipo === 'VENTAS') {
      const rows = rep.tabla?.filas ?? [];
      if (rows.length > 0) {
        items = rows.map((r, i) => {
          const val = Number(r['importe'] ?? r['unidades'] ?? r['cantidad'] ?? 0);
          return {
            key: String(r['grupo'] ?? i),
            label: String(r['grupo'] ?? 'Sin dato'),
            value: Math.max(0, val),
            formattedValue: `Bs ${val.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (rep.grafico?.puntos?.length) {
        items = rep.grafico.puntos.map((p, i) => {
          const val = Number(p.valor || 0);
          return {
            key: p.etiqueta,
            label: p.etiqueta,
            value: Math.max(0, val),
            formattedValue: `Bs ${val.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      }
    } else if (rep.tipo === 'STOCK') {
      if (this.stockDonutView() === 'grupo' && (rep.grafico?.puntos?.length ?? 0) > 1) {
        items = (rep.grafico?.puntos ?? []).map((p, i) => ({
          key: p.etiqueta,
          label: p.etiqueta,
          value: Math.max(0, Number(p.valor || 0)),
          formattedValue: `${p.valor} ${p.valor === 1 ? 'registro' : 'registros'}`,
          color: PALETTE[i % PALETTE.length],
        }));
      } else {
        const kpiDep = rep.kpis.find((k) => k.etiqueta.toLowerCase().includes('agotad'));
        const kpiLow = rep.kpis.find((k) => k.etiqueta.toLowerCase().includes('bajo'));
        let depleted = kpiDep ? parseInt(kpiDep.valor, 10) || 0 : 0;
        let low = kpiLow ? parseInt(kpiLow.valor, 10) || 0 : 0;

        const filas = rep.tabla?.filas ?? [];
        if (depleted === 0 && low === 0 && filas.length > 0) {
          depleted = filas.filter((f) => f['estado'] === 'AGOTADO').length;
          low = filas.filter((f) => f['estado'] === 'BAJO').length;
        }

        if (depleted > 0) {
          items.push({
            key: 'agotado',
            label: 'Agotado',
            value: depleted,
            formattedValue: `${depleted} ${depleted === 1 ? 'registro crítico' : 'registros críticos'}`,
            color: 'var(--color-terracotta)',
          });
        }
        if (low > 0) {
          items.push({
            key: 'bajo',
            label: 'Bajo stock',
            value: low,
            formattedValue: `${low} ${low === 1 ? 'registro crítico' : 'registros críticos'}`,
            color: '#e07a5f',
          });
        }

        if (items.length === 0 && rep.grafico?.puntos?.length) {
          items = rep.grafico.puntos.map((p, i) => ({
            key: p.etiqueta,
            label: p.etiqueta,
            value: Math.max(0, Number(p.valor || 0)),
            formattedValue: `${p.valor} registros`,
            color: PALETTE[i % PALETTE.length],
          }));
        }
      }
    } else if (rep.tipo === 'RESERVAS') {
      const rows = rep.tabla?.filas ?? [];
      if (rows.length > 0) {
        items = rows.map((r, i) => {
          const val = Number(r['cantidad'] ?? 0);
          return {
            key: String(r['grupo'] ?? i),
            label: String(r['grupo'] ?? 'Sin dato'),
            value: Math.max(0, val),
            formattedValue: `${val} ${val === 1 ? 'reserva' : 'reservas'}`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (rep.grafico?.puntos?.length) {
        items = rep.grafico.puntos.map((p, i) => ({
          key: p.etiqueta,
          label: p.etiqueta,
          value: Math.max(0, Number(p.valor || 0)),
          formattedValue: `${p.valor} reservas`,
          color: PALETTE[i % PALETTE.length],
        }));
      }
    } else if (rep.tipo === 'DEVOLUCIONES') {
      const rows = rep.tabla?.filas ?? [];
      if (rows.length > 0) {
        items = rows.map((r, i) => {
          const val = Number(r['cantidad'] ?? 0);
          return {
            key: String(r['grupo'] ?? i),
            label: String(r['grupo'] ?? 'Sin dato'),
            value: Math.max(0, val),
            formattedValue: `${val} ${val === 1 ? 'solicitud' : 'solicitudes'}`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (rep.grafico?.puntos?.length) {
        items = rep.grafico.puntos.map((p, i) => ({
          key: p.etiqueta,
          label: p.etiqueta,
          value: Math.max(0, Number(p.valor || 0)),
          formattedValue: `${p.valor} solicitudes`,
          color: PALETTE[i % PALETTE.length],
        }));
      }
    } else if (rep.grafico?.puntos?.length) {
      items = rep.grafico.puntos.map((p, i) => ({
        key: p.etiqueta,
        label: p.etiqueta,
        value: Math.max(0, Number(p.valor || 0)),
        formattedValue: `${p.valor.toLocaleString('es-BO')}`,
        color: PALETTE[i % PALETTE.length],
      }));
    }

    const total = items.reduce((acc, it) => acc + it.value, 0);
    if (total <= 0) return [];

    let consumed = 0;
    return items
      .filter((it) => it.value > 0)
      .map((it, idx) => {
        const percent = (it.value / total) * 100;
        const dash = (percent / 100) * DONUT_CIRCUMFERENCE;
        const gap = DONUT_CIRCUMFERENCE - dash;
        const offset = -consumed;
        consumed += dash;
        return {
          key: it.key,
          label: it.label,
          value: it.value,
          formattedValue: it.formattedValue,
          percent,
          dash,
          gap,
          offset,
          color: it.color || PALETTE[idx % PALETTE.length],
        };
      });
  });

  readonly donutTotal = computed(() => {
    return this.donutSegments().reduce((acc, s) => acc + s.value, 0);
  });

  readonly donutTitle = computed(() => {
    const rep = this.report();
    if (!rep) return 'Distribución y porcentajes';
    const group = this.groupLabel().toLowerCase();
    if (rep.tipo === 'VENTAS') return `Distribución de ventas por ${group}`;
    if (rep.tipo === 'STOCK') {
      return this.stockDonutView() === 'grupo'
        ? `Distribución de inventario por ${group}`
        : 'Distribución por estado de stock';
    }
    if (rep.tipo === 'RESERVAS') return `Distribución de reservas por ${group}`;
    if (rep.tipo === 'DEVOLUCIONES') return `Distribución de devoluciones por ${group}`;
    return `Distribución por ${group}`;
  });

  readonly donutUnit = computed(() => {
    const rep = this.report();
    if (rep?.tipo === 'VENTAS') return 'Participación porcentual sobre ventas';
    if (rep?.tipo === 'STOCK') {
      return this.stockDonutView() === 'grupo'
        ? 'Participación de registros críticos'
        : 'Proporción sobre registros críticos';
    }
    if (rep?.tipo === 'RESERVAS') return 'Participación sobre el total de reservas';
    if (rep?.tipo === 'DEVOLUCIONES') return 'Participación sobre solicitudes';
    return 'Distribución porcentual';
  });

  readonly donutTotalDisplay = computed(() => {
    const rep = this.report();
    const total = this.donutTotal();
    if (rep?.tipo === 'VENTAS') {
      return `Bs ${total.toLocaleString('es-BO', { maximumFractionDigits: 0 })}`;
    }
    return total.toLocaleString('es-BO');
  });

  readonly donutCenterLabel = computed(() => {
    const rep = this.report();
    if (rep?.tipo === 'VENTAS') return 'Total ventas';
    if (rep?.tipo === 'STOCK') return this.stockDonutView() === 'grupo' ? 'Registros' : 'Críticos';
    if (rep?.tipo === 'RESERVAS') return 'Reservas';
    if (rep?.tipo === 'DEVOLUCIONES') return 'Solicitudes';
    return 'Total';
  });

  /* -------------------------------------------------------------------------- */
  /*                        2. GRÁFICO DE BARRAS (CU20)                         */
  /* -------------------------------------------------------------------------- */

  readonly barRows = computed<BarRow[]>(() => {
    const rep = this.report();
    if (!rep || rep.estado !== 'OK') return [];

    let rows: BarRow[] = [];

    if (rep.tipo === 'VENTAS') {
      const tableRows = rep.tabla?.filas ?? [];
      if (tableRows.length > 0) {
        const max = Math.max(1, ...tableRows.map((r) => Number(r['importe'] ?? 0)));
        rows = tableRows.map((r, i) => {
          const val = Number(r['importe'] ?? 0);
          const parts: string[] = [];
          if (r['cantidad'] !== undefined) {
            parts.push(`${r['cantidad']} ${r['cantidad'] === 1 ? 'venta' : 'ventas'}`);
          }
          if (r['unidades'] !== undefined) {
            parts.push(`${r['unidades']} ${r['unidades'] === 1 ? 'unidad' : 'unidades'}`);
          }
          return {
            key: String(r['grupo'] ?? i),
            label: String(r['grupo'] ?? 'Sin dato'),
            value: val,
            displayValue: `Bs ${val.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
            percent: Math.min(100, Math.max(0, (val / max) * 100)),
            meta: parts.join(' · '),
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (rep.grafico?.puntos?.length) {
        const points = rep.grafico.puntos;
        const max = Math.max(1, ...points.map((p) => Number(p.valor || 0)));
        rows = points.map((p, i) => ({
          key: p.etiqueta,
          label: p.etiqueta,
          value: Number(p.valor || 0),
          displayValue: `Bs ${Number(p.valor || 0).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
          percent: Math.min(100, Math.max(0, (Number(p.valor || 0) / max) * 100)),
          color: PALETTE[i % PALETTE.length],
        }));
      }
    } else if (rep.tipo === 'STOCK') {
      const filas = rep.tabla?.filas ?? [];
      const puntos = rep.grafico?.puntos ?? [];

      if (this.stockBarView() === 'productos' && filas.length > 0) {
        const topFilas = filas.slice(0, 10);
        const max = Math.max(1, ...topFilas.map((f) => Math.max(Number(f['minimo'] || 0), Number(f['actual'] || 0))));
        rows = topFilas.map((f, i) => {
          const actual = Number(f['actual'] || 0);
          const minimo = Number(f['minimo'] || 0);
          const estado = String(f['estado'] || 'CRÍTICO');
          const isAgotado = estado === 'AGOTADO';
          return {
            key: `${f['sku'] || f['producto']}-${i}`,
            label: `${f['producto']}${f['sku'] ? ' (' + f['sku'] + ')' : ''}`,
            value: actual,
            displayValue: `Actual: ${actual} / Mín: ${minimo}`,
            percent: Math.min(100, Math.max(4, (actual / max) * 100)),
            meta: `Sucursal: ${f['sucursal'] || 'Principal'} · Estado: ${estado}`,
            color: isAgotado ? 'var(--color-terracotta)' : '#e07a5f',
          };
        });
      } else if (puntos.length > 0) {
        const max = Math.max(1, ...puntos.map((p) => Number(p.valor || 0)));
        rows = puntos.map((p, i) => {
          const val = Number(p.valor || 0);
          let meta = '';
          if (filas.length > 0) {
            const matches = filas.filter(
              (f) =>
                f['sucursal'] === p.etiqueta ||
                f['categoria'] === p.etiqueta ||
                f['producto'] === p.etiqueta,
            );
            if (matches.length > 0) {
              const dep = matches.filter((m) => m['estado'] === 'AGOTADO').length;
              const low = matches.filter((m) => m['estado'] === 'BAJO').length;
              meta = `${dep} agotados · ${low} bajo stock`;
            }
          }
          return {
            key: p.etiqueta,
            label: p.etiqueta,
            value: val,
            displayValue: `${val} ${val === 1 ? 'registro' : 'registros'}`,
            percent: Math.min(100, Math.max(0, (val / max) * 100)),
            meta: meta || `${val} registros críticos`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (filas.length > 0) {
        const topFilas = filas.slice(0, 8);
        const max = Math.max(1, ...topFilas.map((f) => Math.max(Number(f['minimo'] || 1), Number(f['actual'] || 0))));
        rows = topFilas.map((f, i) => ({
          key: `${f['sku'] || f['producto']}-${i}`,
          label: `${f['producto']}`,
          value: Number(f['actual'] || 0),
          displayValue: `Actual: ${f['actual']} · Mín: ${f['minimo']}`,
          percent: Math.min(100, Math.max(5, (Number(f['actual'] || 0) / max) * 100)),
          meta: `Estado: ${f['estado']} · ${f['sucursal']}`,
          color: f['estado'] === 'AGOTADO' ? 'var(--color-terracotta)' : '#e07a5f',
        }));
      }
    } else if (rep.tipo === 'RESERVAS') {
      const tableRows = rep.tabla?.filas ?? [];
      if (tableRows.length > 0) {
        const max = Math.max(1, ...tableRows.map((r) => Number(r['cantidad'] ?? 0)));
        rows = tableRows.map((r, i) => {
          const cant = Number(r['cantidad'] ?? 0);
          const units = Number(r['unidades'] ?? 0);
          return {
            key: String(r['grupo'] ?? i),
            label: String(r['grupo'] ?? 'Sin dato'),
            value: cant,
            displayValue: `${cant} ${cant === 1 ? 'reserva' : 'reservas'}`,
            percent: Math.min(100, Math.max(0, (cant / max) * 100)),
            meta: `${units} ${units === 1 ? 'unidad reservada' : 'unidades reservadas'}`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (rep.grafico?.puntos?.length) {
        const points = rep.grafico.puntos;
        const max = Math.max(1, ...points.map((p) => Number(p.valor || 0)));
        rows = points.map((p, i) => ({
          key: p.etiqueta,
          label: p.etiqueta,
          value: Number(p.valor || 0),
          displayValue: `${p.valor} reservas`,
          percent: Math.min(100, Math.max(0, (Number(p.valor || 0) / max) * 100)),
          color: PALETTE[i % PALETTE.length],
        }));
      }
    } else if (rep.tipo === 'DEVOLUCIONES') {
      const tableRows = rep.tabla?.filas ?? [];
      if (tableRows.length > 0) {
        const max = Math.max(1, ...tableRows.map((r) => Number(r['cantidad'] ?? 0)));
        rows = tableRows.map((r, i) => {
          const cant = Number(r['cantidad'] ?? 0);
          const units = Number(r['unidades'] ?? 0);
          return {
            key: String(r['grupo'] ?? i),
            label: String(r['grupo'] ?? 'Sin dato'),
            value: cant,
            displayValue: `${cant} ${cant === 1 ? 'solicitud' : 'solicitudes'}`,
            percent: Math.min(100, Math.max(0, (cant / max) * 100)),
            meta: `${units} ${units === 1 ? 'unidad devuelta' : 'unidades devueltas'}`,
            color: PALETTE[i % PALETTE.length],
          };
        });
      } else if (rep.grafico?.puntos?.length) {
        const points = rep.grafico.puntos;
        const max = Math.max(1, ...points.map((p) => Number(p.valor || 0)));
        rows = points.map((p, i) => ({
          key: p.etiqueta,
          label: p.etiqueta,
          value: Number(p.valor || 0),
          displayValue: `${p.valor} solicitudes`,
          percent: Math.min(100, Math.max(0, (Number(p.valor || 0) / max) * 100)),
          color: PALETTE[i % PALETTE.length],
        }));
      }
    } else if (rep.grafico?.puntos?.length) {
      const points = rep.grafico.puntos;
      const max = Math.max(1, ...points.map((p) => Number(p.valor || 0)));
      rows = points.map((p, i) => ({
        key: p.etiqueta,
        label: p.etiqueta,
        value: Number(p.valor || 0),
        displayValue: `${p.valor.toLocaleString('es-BO')}`,
        percent: Math.min(100, Math.max(0, (Number(p.valor || 0) / max) * 100)),
        color: PALETTE[i % PALETTE.length],
      }));
    }

    return rows;
  });

  readonly barTitle = computed(() => {
    const rep = this.report();
    if (!rep) return 'Comparativa de indicadores';
    const group = this.groupLabel().toLowerCase();
    if (rep.tipo === 'VENTAS') return `Comparativa de ventas por ${group}`;
    if (rep.tipo === 'STOCK') {
      return this.stockBarView() === 'productos'
        ? 'Comparativa de stock: Actual vs. Mínimo'
        : `Comparativa de inventario crítico por ${group}`;
    }
    if (rep.tipo === 'RESERVAS') return `Comparativa de reservas por ${group}`;
    if (rep.tipo === 'DEVOLUCIONES') return 'Comparativa de devoluciones e impacto';
    return `Comparativa por ${group}`;
  });

  readonly barUnit = computed(() => {
    const rep = this.report();
    if (rep?.tipo === 'VENTAS') return 'Importe vendido (BOB) y volumen';
    if (rep?.tipo === 'STOCK') {
      return this.stockBarView() === 'productos'
        ? 'Unidades en inventario vs. stock mínimo'
        : 'Cantidad de registros críticos';
    }
    if (rep?.tipo === 'RESERVAS') return 'Reservas registradas y unidades';
    if (rep?.tipo === 'DEVOLUCIONES') return 'Solicitudes y unidades devueltas';
    return rep?.grafico?.unidad || 'Indicadores';
  });

  /* -------------------------------------------------------------------------- */
  /*                          SOPORTE SERIE TEMPORAL                            */
  /* -------------------------------------------------------------------------- */

  readonly linePoints = computed<LineChartPoint[]>(() => {
    const chart = this.report()?.grafico;
    if (!chart || chart.tipo !== 'line' || !chart.puntos.length) return [];
    const points = chart.puntos;
    const max = Math.max(1, ...points.map((p) => p.valor));
    const min = 0;
    const range = max - min || 1;
    const count = points.length;

    return points.map((p, index) => {
      const x = count === 1 ? 300 : 30 + (index / (count - 1)) * 540;
      const y = 170 - ((p.valor - min) / range) * 140;
      return { etiqueta: p.etiqueta, valor: p.valor, x, y };
    });
  });

  readonly linePolylineAttr = computed(() =>
    this.linePoints()
      .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
      .join(' '),
  );

  /* -------------------------------------------------------------------------- */
  /*                             MÉTODOS DE ACCIÓN                              */
  /* -------------------------------------------------------------------------- */

  setStockDonutView(view: 'estado' | 'grupo'): void {
    this.stockDonutView.set(view);
  }

  setStockBarView(view: 'grupo' | 'productos'): void {
    this.stockBarView.set(view);
  }

  setBarMode(mode: 'bar' | 'line'): void {
    this.barMode.set(mode);
  }

  switchTab(tab: 'generar' | 'historial'): void {
    this.activeTab.set(tab);
    if (tab === 'historial') {
      this.loadHistory();
    }
  }

  loadHistory(): void {
    this.loadingHistory.set(true);
    this.historyError.set('');
    this.reportService
      .getHistory(50)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.historyList.set(res.data || []);
          this.loadingHistory.set(false);
        },
        error: (err) => {
          this.loadingHistory.set(false);
          this.historyError.set(
            err?.error?.message || 'No fue posible cargar el historial de reportes.',
          );
        },
      });
  }

  viewSavedReport(reportId: number): void {
    this.loading.set(true);
    this.error.set('');
    this.reportService
      .getSavedReport(reportId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.loading.set(false);
          const detail = res.data;
          this.currentReportId.set(detail.id_reporte);
          this.isViewingSavedReport.set(true);
          this.savedReportDate.set(detail.creado_en);
          this.queryText.set(detail.consulta);
          this.report.set(detail.resultado);
          this.activeTab.set('generar');
          this.stockDonutView.set('estado');
          this.stockBarView.set('grupo');
          this.barMode.set('bar');
        },
        error: (err) => {
          this.loading.set(false);
          this.error.set(
            err?.error?.message || 'No fue posible cargar el detalle del reporte guardado.',
          );
        },
      });
  }

  backToHistory(): void {
    this.isViewingSavedReport.set(false);
    this.currentReportId.set(null);
    this.switchTab('historial');
  }

  submitQuery(text?: string): void {
    const query = (text ?? this.queryText()).trim();
    if (!query) return;

    this.queryText.set(query);
    this.loading.set(true);
    this.error.set('');
    this.report.set(null);
    this.isViewingSavedReport.set(false);
    this.currentReportId.set(null);
    this.stockDonutView.set('estado');
    this.stockBarView.set('grupo');
    this.barMode.set('bar');

    this.reportService
      .query(query)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.report.set(response.data);
          this.currentReportId.set(response.id_reporte ?? null);
          this.loading.set(false);
          // Refrescar historial en background
          this.loadHistory();
        },
        error: (err) => {
          this.loading.set(false);
          const msg =
            err?.error?.message ||
            (err?.status === 403
              ? 'Tu plan actual no incluye la funcionalidad de Reportes con IA.'
              : err?.status === 502
              ? 'El servicio de IA no está disponible temporalmente. Inténtalo de nuevo.'
              : 'Ocurrió un error al generar el reporte. Verifica tu consulta e inténtalo nuevamente.');
          this.error.set(msg);
        },
      });
  }

  useExample(query: string): void {
    this.queryText.set(query);
    this.submitQuery(query);
  }

  async listenVoice(): Promise<void> {
    if (!this.voiceSupported() || this.voiceListening() || this.loading()) return;
    this.error.set('');

    try {
      const text = await this.speech.listenOnce('es-BO');
      if (text) {
        this.queryText.set(text);
        this.submitQuery(text);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'No se detectó la consulta por voz.';
      this.error.set(msg);
    }
  }

  formatCell(fila: Record<string, any>, clave: string, tipo: string): string {
    const val = fila[clave];
    if (val === null || val === undefined) return '-';
    if (tipo === 'moneda') {
      const num = Number(val);
      return isNaN(num)
        ? String(val)
        : `Bs ${num.toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    if (tipo === 'numero') {
      const num = Number(val);
      return isNaN(num) ? String(val) : num.toLocaleString('es-BO');
    }
    return String(val);
  }

  reset(): void {
    this.queryText.set('');
    this.report.set(null);
    this.error.set('');
    this.currentReportId.set(null);
    this.isViewingSavedReport.set(false);
    this.stockDonutView.set('estado');
    this.stockBarView.set('grupo');
    this.barMode.set('bar');
  }

  /* -------------------------------------------------------------------------- */
  /*                        EXPORTACIONES CU21 (.pdf, .xlsx, .csv, .json)       */
  /* -------------------------------------------------------------------------- */

  getTimestampSlug(): string {
    const now = new Date();
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`;
  }

  exportPdf(): void {
    const rep = this.report();
    if (!rep) return;

    const sections: PdfSection[] = [];

    if (rep.resumen) {
      sections.push({
        heading: 'Resumen ejecutivo generado con IA',
        description: rep.resumen,
        notes: [
          `Modelo utilizado: ${rep.modelo ?? 'DeepSeek'}`,
          `Generado: ${rep.generado_en}`,
        ],
      });
    }

    if (rep.kpis?.length) {
      sections.push({
        heading: 'Indicadores principales (KPIs)',
        kpis: rep.kpis.map((k) => ({
          label: k.etiqueta,
          value: k.unidad ? `${k.valor} ${k.unidad}` : k.valor,
        })),
      });
    }

    if (rep.tabla?.columnas?.length && rep.tabla?.filas?.length) {
      const cols = rep.tabla.columnas;
      sections.push({
        heading: 'Detalle de registros',
        description: `Total de filas: ${rep.tabla.total_filas}${rep.tabla.truncada ? ' (mostrando primeras ' + rep.tabla.filas.length + ')' : ''}`,
        table: {
          columns: cols.map((c) => ({
            header: c.etiqueta,
            width: c.tipo === 'moneda' ? 2 : c.tipo === 'numero' ? 1.4 : 2.6,
            align: c.tipo === 'moneda' || c.tipo === 'numero' ? ('right' as const) : ('left' as const),
          })),
          rows: rep.tabla.filas.map((row) =>
            cols.map((c) => this.formatCell(row, c.clave, c.tipo)),
          ),
        },
      });
    }

    const meta: PdfEntry[] = Object.entries(rep.filtros_aplicados || {}).map(([k, v]) => ({
      label: k,
      value: String(v),
    }));

    if (this.queryText()) {
      meta.unshift({ label: 'Consulta', value: this.queryText() });
    }

    const pdfDef: PdfReport = {
      title: rep.titulo,
      subtitle: 'FashionStore · Reporte empresarial generado con IA',
      meta,
      sections,
      generatedAt: new Date(),
    };

    const file = this.pdfService.generate(pdfDef, `reporte-${rep.tipo.toLowerCase()}`);
    this.pdfService.download(file);
  }

  exportExcel(): void {
    const rep = this.report();
    if (!rep) return;
    this.exportingExcel.set(true);

    const slug = `reporte-${rep.tipo.toLowerCase()}_${this.getTimestampSlug()}`;
    const id = this.currentReportId();

    const handleBlob = (blob: Blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${slug}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      this.exportingExcel.set(false);
    };

    if (id) {
      this.reportService.exportSavedExcel(id).subscribe({
        next: handleBlob,
        error: () => this.exportDirectExcelFallback(rep, slug),
      });
    } else {
      this.exportDirectExcelFallback(rep, slug);
    }
  }

  private exportDirectExcelFallback(rep: NaturalLanguageReportData, slug: string): void {
    this.reportService
      .exportDirectExcel({
        titulo: rep.titulo,
        consulta: this.queryText(),
        resumen: rep.resumen,
        kpis: rep.kpis,
        tabla: rep.tabla,
        filtros: rep.filtros_aplicados,
      })
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${slug}.xlsx`;
          a.click();
          URL.revokeObjectURL(url);
          this.exportingExcel.set(false);
        },
        error: () => {
          this.exportingExcel.set(false);
          this.exportCsv();
        },
      });
  }

  exportCsv(): void {
    const rep = this.report();
    if (!rep || !rep.tabla?.filas?.length) return;

    const cols = rep.tabla.columnas;
    const headers = cols.map((c) => `"${c.etiqueta.replace(/"/g, '""')}"`).join(';');
    const lines = rep.tabla.filas.map((row) =>
      cols
        .map((c) => {
          const val = this.formatCell(row, c.clave, c.tipo);
          return `"${String(val).replace(/"/g, '""')}"`;
        })
        .join(';'),
    );

    const csvContent = '\uFEFF' + [headers, ...lines].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const slug = `reporte-${rep.tipo.toLowerCase()}_${this.getTimestampSlug()}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${slug}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  exportJson(): void {
    const rep = this.report();
    if (!rep) return;

    const exportPayload = {
      id_reporte: this.currentReportId(),
      consulta: this.queryText(),
      exportado_en: new Date().toISOString(),
      reporte: rep,
    };

    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
      type: 'application/json;charset=utf-8;',
    });
    const slug = `reporte-${rep.tipo.toLowerCase()}_${this.getTimestampSlug()}`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${slug}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
}
