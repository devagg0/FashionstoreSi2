import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { AdminNaturalLanguageReport } from './admin-natural-language-report';
import { NaturalLanguageReportData } from '../../../core/services/natural-language-report.service';
import { SessionService } from '../../../core/services/session.service';
import { ReportPdfService } from '../../../core/services/report-pdf.service';

const mockSalesData: NaturalLanguageReportData = {
  estado: 'OK',
  tipo: 'VENTAS',
  titulo: 'Ventas por canal',
  filtros_aplicados: { Agrupación: 'Canal', Periodo: '2026-10-01 a 2026-10-31' },
  kpis: [
    { etiqueta: 'Ventas', valor: '2' },
    { etiqueta: 'Importe vendido', valor: 'Bs 280.00', unidad: 'Bs' },
    { etiqueta: 'Unidades vendidas', valor: '3' },
    { etiqueta: 'Ticket promedio', valor: 'Bs 140.00', unidad: 'Bs' },
  ],
  tabla: {
    columnas: [
      { clave: 'grupo', etiqueta: 'Canal', tipo: 'texto' },
      { clave: 'cantidad', etiqueta: 'Ventas', tipo: 'numero' },
      { clave: 'unidades', etiqueta: 'Unidades', tipo: 'numero' },
      { clave: 'importe', etiqueta: 'Importe (Bs)', tipo: 'moneda' },
    ],
    filas: [
      { grupo: 'DIGITAL', cantidad: 1, unidades: 2, importe: 180.0 },
      { grupo: 'PRESENCIAL', cantidad: 1, unidades: 1, importe: 100.0 },
    ],
    total_filas: 2,
  },
  grafico: {
    tipo: 'bar',
    titulo: 'Ventas por canal',
    unidad: 'Bs',
    puntos: [
      { etiqueta: 'DIGITAL', valor: 180.0 },
      { etiqueta: 'PRESENCIAL', valor: 100.0 },
    ],
  },
  resumen: 'Se registraron Bs 280.00 en ventas durante el periodo.',
  modelo: 'DeepSeek',
  generado_en: '2026-11-09T01:00:00Z',
};

describe('CU21 - Consultar y exportar reportes generados', () => {
  let fixture: ComponentFixture<AdminNaturalLanguageReport>;
  let component: AdminNaturalLanguageReport;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(SessionService).saveAccessToken('test-token');
    fixture = TestBed.createComponent(AdminNaturalLanguageReport);
    component = fixture.componentInstance;
    fixture.detectChanges();

    // ngOnInit invoca loadHistory(); consumimos la petición inicial
    const initialHistoryReq = http.expectOne((r) => r.url.includes('/history'));
    initialHistoryReq.flush({ success: true, data: [] });
  });

  afterEach(() => {
    fixture.destroy();
    http.verify();
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  it('Prueba 1: Cargar el historial sin errores', () => {
    // 1. Cambiar a la pestaña "Historial de reportes (CU21)"
    component.switchTab('historial');
    expect(component.activeTab()).toBe('historial');

    // 2. Mock del endpoint de consulta del historial (GET /history)
    const historyReq = http.expectOne((r) => r.url.includes('/history?limit=50'));
    expect(historyReq.request.headers.get('Authorization')).toBe('Bearer test-token');
    historyReq.flush({
      success: true,
      data: [
        {
          id_reporte: 101,
          tipo: 'VENTAS',
          titulo: 'Ventas por canal',
          consulta: 'Ventas por canal del último mes',
          filtros_aplicados: { Agrupación: 'Canal' },
          nombre_usuario: 'Admin FashionStore',
          creado_en: '2026-11-09T01:00:00Z',
        },
      ],
      total: 1,
    });
    fixture.detectChanges();

    // 3. Validar estado interno tras la carga exitosa
    expect(component.loadingHistory()).toBe(false);
    expect(component.historyError()).toBe('');
    expect(component.historyList().length).toBe(1);
    expect(component.historyList()[0].id_reporte).toBe(101);

    // 4. Verificar en el DOM que la tabla y elementos se rendericen sin errores
    const root = fixture.nativeElement as HTMLElement;
    const historyTable = root.querySelector('.history-table');
    expect(historyTable).toBeTruthy();
    expect(historyTable?.textContent).toContain('Ventas por canal');
    expect(historyTable?.textContent).toContain('VENTAS');
    expect(historyTable?.textContent).toContain('«Ventas por canal del último mes»');
    expect(historyTable?.textContent).toContain('Admin FashionStore');

    // Botón de acción con icono profesional Lucide "eye"
    const viewBtn = historyTable?.querySelector('.view-btn');
    expect(viewBtn).toBeTruthy();
    expect(viewBtn?.textContent).toContain('Ver reporte');
    expect(viewBtn?.querySelector('app-icon[name="eye"]')).toBeTruthy();
  });

  it('Prueba 2: Abrir un reporte guardado', () => {
    // 1. Abrir un reporte guardado previamente desde el historial
    component.viewSavedReport(101);
    expect(component.loading()).toBe(true);

    // 2. Mock del endpoint de detalle (GET /history/101)
    const detailReq = http.expectOne((r) => r.url.endsWith('/history/101'));
    expect(detailReq.request.headers.get('Authorization')).toBe('Bearer test-token');
    detailReq.flush({
      success: true,
      data: {
        id_reporte: 101,
        tipo: 'VENTAS',
        titulo: 'Ventas por canal',
        consulta: 'Ventas por canal del último mes',
        filtros_aplicados: { Agrupación: 'Canal', Periodo: '2026-10-01 a 2026-10-31' },
        resultado: mockSalesData,
        creado_en: '2026-11-09T01:00:00Z',
        nombre_usuario: 'Admin FashionStore',
      },
    });
    fixture.detectChanges();

    // 3. Comprobar que cambie automáticamente a la pestaña de generación/visualización
    expect(component.loading()).toBe(false);
    expect(component.activeTab()).toBe('generar');
    expect(component.isViewingSavedReport()).toBe(true);
    expect(component.currentReportId()).toBe(101);
    expect(component.report()).toEqual(mockSalesData);

    const root = fixture.nativeElement as HTMLElement;

    // 4. Banner de reporte guardado visible con ID y botón de retorno
    const banner = root.querySelector('.saved-report-banner');
    expect(banner).toBeTruthy();
    expect(banner?.textContent).toContain('Reporte guardado #101');
    expect(banner?.textContent).toContain('Estás visualizando un reporte guardado del historial');
    expect(banner?.querySelector('app-icon[name="chevron-left"]')).toBeTruthy();

    // 5. Resumen IA conservado
    const summary = root.querySelector('.ai-summary');
    expect(summary).toBeTruthy();
    expect(summary?.textContent).toContain('Se registraron Bs 280.00 en ventas durante el periodo.');
    expect(summary?.textContent).toContain('DeepSeek');

    // 6. Cards de KPIs conservadas
    const kpiCards = root.querySelectorAll('.kpi-card');
    expect(kpiCards.length).toBe(4);
    expect(root.textContent).toContain('Bs 280.00');

    // 7. Gráficos dinámicos conservados (Dona y Barras)
    const donutCard = root.querySelector('.chart-card--donut');
    expect(donutCard).toBeTruthy();
    expect(donutCard?.textContent).toContain('Distribución de ventas por canal');
    const donutSegments = donutCard?.querySelectorAll('.donut-segment');
    expect(donutSegments?.length).toBe(2);

    const barCard = root.querySelector('.chart-card--bars');
    expect(barCard).toBeTruthy();
    expect(barCard?.textContent).toContain('Comparativa de ventas por canal');
    const barItems = barCard?.querySelectorAll('.bar-item');
    expect(barItems?.length).toBe(2);

    // 8. Tabla de detalles conservada
    const table = root.querySelector('.table-card');
    expect(table).toBeTruthy();
    expect(table?.textContent).toContain('DIGITAL');
    expect(table?.textContent).toContain('PRESENCIAL');
  });

  it('Prueba 3: Exportar correctamente los cuatro formatos', async () => {
    // Cargar reporte de ventas en el componente
    component.report.set(mockSalesData);
    component.currentReportId.set(101);
    component.queryText.set('Ventas por canal del último mes');
    fixture.detectChanges();

    // Spies para descargas de archivos en navegador
    const createdBlobs: Blob[] = [];
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;

    URL.createObjectURL = (blob: Blob | MediaSource) => {
      if (blob instanceof Blob) {
        createdBlobs.push(blob);
      }
      return 'blob:mock-url-' + createdBlobs.length;
    };
    URL.revokeObjectURL = () => {};

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    try {
      // 1. EXPORTACIÓN PDF (.pdf)
      const pdfService = TestBed.inject(ReportPdfService);
      const downloadSpy = vi.spyOn(pdfService, 'download');
      component.exportPdf();
      expect(downloadSpy).toHaveBeenCalled();
      const generatedPdfFile = downloadSpy.mock.calls[0][0];
      expect(generatedPdfFile.filename).toContain('reporte-ventas');
      expect(generatedPdfFile.blob.type).toBe('application/pdf');
      expect(generatedPdfFile.blob.size).toBeGreaterThan(0);

      // 2. EXPORTACIÓN EXCEL (.xlsx)
      component.exportExcel();
      expect(component.exportingExcel()).toBe(true);

      const excelReq = http.expectOne((r) => r.url.endsWith('/history/101/export/excel'));
      const excelBytes = new Uint8Array([0x50, 0x4B, 0x03, 0x04, 0x00, 0x00]);
      excelReq.flush(new Blob([excelBytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
      fixture.detectChanges();

      expect(component.exportingExcel()).toBe(false);
      const excelBlob = createdBlobs.find((b) => b.type.includes('spreadsheetml'));
      expect(excelBlob).toBeTruthy();
      expect(excelBlob?.size).toBeGreaterThan(0);

      // 3. EXPORTACIÓN CSV (.csv)
      component.exportCsv();
      const csvBlob = createdBlobs.find((b) => b.type.includes('text/csv'));
      expect(csvBlob).toBeTruthy();
      const buffer = await csvBlob!.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      // Validar presencia de UTF-8 BOM en los bytes binarios (0xEF, 0xBB, 0xBF)
      expect(bytes[0]).toBe(0xEF);
      expect(bytes[1]).toBe(0xBB);
      expect(bytes[2]).toBe(0xBF);
      const csvText = await csvBlob!.text();
      expect(csvText).toContain('Canal');
      expect(csvText).toContain('Ventas');
      expect(csvText).toContain('Importe (Bs)');
      expect(csvText).toContain('DIGITAL');
      expect(csvText).toContain('PRESENCIAL');

      // 4. EXPORTACIÓN JSON (.json)
      component.exportJson();
      const jsonBlob = createdBlobs.find((b) => b.type.includes('application/json'));
      expect(jsonBlob).toBeTruthy();
      const jsonText = await jsonBlob!.text();
      const parsedJson = JSON.parse(jsonText);
      expect(parsedJson.id_reporte).toBe(101);
      expect(parsedJson.consulta).toBe('Ventas por canal del último mes');
      expect(parsedJson.reporte.tipo).toBe('VENTAS');
      expect(parsedJson.reporte.kpis.length).toBe(4);
      expect(parsedJson.reporte.tabla.filas.length).toBe(2);

    } finally {
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
      clickSpy.mockRestore();
    }
  });
});
