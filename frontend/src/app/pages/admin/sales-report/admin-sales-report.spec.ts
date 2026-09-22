import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { AdminSalesReport, currentSalesMonth } from './admin-sales-report';
import { SalesReportData, SalesKPIs } from '../../../core/services/admin-sales-report.service';
import { SessionService } from '../../../core/services/session.service';
import { SpeechRecognitionService } from '../../../core/services/speech-recognition.service';
import { formatBs } from '../../../core/utils/money';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';

const kpis: SalesKPIs = { cantidad_ventas: 2, importe_antes_descuentos: '210.00', descuentos: '10.00', importe_vendido: '200.00', ticket_promedio: '100.00', unidades_vendidas: 4, clientes_identificados: 1, ventas_sin_cliente: 1 };
const data: SalesReportData = {
  moneda: 'BOB', zona_horaria: 'America/La_Paz', kpis,
  por_canal: [{ ...kpis, canal: 'DIGITAL' }],
  por_sucursal: [{ ...kpis, id_sucursal: 1, nombre_sucursal: 'Centro' }],
  serie_diaria: [{ ...kpis, fecha: '2026-09-03' }],
  productos_mas_vendidos: [{ id_producto: 1, nombre_producto: 'Camisa', unidades_vendidas: 4, importe_vendido: '200.00', importe_antes_descuentos: '210.00', descuentos: '10.00' }],
};
describe('CU28 Reporte de ventas', () => {
  let fixture: ComponentFixture<AdminSalesReport>;
  let page: AdminSalesReport;
  let http: HttpTestingController;
  let initial: TestRequest;
  const reportRequest = () => http.expectOne(r => r.url.endsWith('/sales-report'));
  const flushReport = (request = reportRequest(), value = data) => { request.flush({ success: true, data: value }); fixture.detectChanges(); };
  const element = () => fixture.nativeElement as HTMLElement;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(SessionService).saveAccessToken('cu28-token');
    fixture = TestBed.createComponent(AdminSalesReport);
    page = fixture.componentInstance;
    fixture.detectChanges();
    initial = reportRequest();
    for (const resource of ['branches', 'categories']) {
      http.expectOne(r => r.url.endsWith('/' + resource)).flush({ data: [{ id_sucursal: 1, id_categoria: 2, nombre: 'Histórica', estado: false }], pagination: { page: 1, total_pages: 2 } });
      http.expectOne(r => r.url.endsWith('/' + resource) && r.params.get('page') === '2').flush({ data: [{ id_sucursal: 3, id_categoria: 4, nombre: 'Actual', estado: true }], pagination: { page: 2, total_pages: 2 } });
    }
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });
  it('usa token, mes de La Paz y skeletons mientras carga', () => {
    expect(initial.request.headers.get('Authorization')).toBe('Bearer cu28-token');
    expect(initial.request.params.get('fecha_desde')).toBe(currentSalesMonth().fecha_desde);
    expect(element().querySelectorAll('.skeleton').length).toBe(10);
    expect(currentSalesMonth(new Date('2026-10-01T01:00:00Z'))).toEqual({ fecha_desde: '2026-09-01', fecha_hasta: '2026-09-30' });
    flushReport(initial);
  });
  it('renderiza seis KPIs, gráficos, tabla y dinero con dos decimales', () => {
    flushReport(initial);
    const cards = element().querySelectorAll('.kpi');
    expect(cards.length).toBe(6);
    expect([...cards].map(x => x.querySelector('strong')?.textContent)).toEqual(['2', formatBs(200), formatBs(100), '4', formatBs(10), '1']);
    expect(element().querySelectorAll('.chart').length).toBe(4);
    expect(element().querySelector('tbody')?.textContent).toContain('Camisa');
    expect(element().textContent).toContain('BOB');
    expect(formatBs('1234.50')).toMatch(/1[.,]234[.,]50/);
  });
  for (const channel of ['PRESENCIAL', 'DIGITAL'] as const) {
    it(`aplica fechas, sucursal, categoría y canal ${channel} desde el formulario`, async () => {
      flushReport(initial);
      await fixture.whenStable();
      const change = (name: string, value: string) => {
        const control = element().querySelector(`[name="${name}"]`) as HTMLInputElement;
        control.value = value; control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input'));
      };
      change('fecha_desde', '2026-01-01'); change('fecha_hasta', '2026-02-28'); change('canal', channel);
      for (const name of ['id_sucursal', 'id_categoria']) {
        const select = element().querySelector(`[name="${name}"]`) as HTMLSelectElement;
        change(name, select.options[1].value);
      }
      element().querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
      const request = reportRequest();
      expect(request.request.params.get('canal')).toBe(channel);
      expect(request.request.params.get('id_sucursal')).toBe('1');
      expect(request.request.params.get('id_categoria')).toBe('2');
      expect(request.request.params.get('fecha_desde')).toBe('2026-01-01');
      expect(request.request.params.get('fecha_hasta')).toBe('2026-02-28');
      flushReport(request);
    });
  }
  it('limpia selectores, restablece el mes y consulta nuevamente', () => {
    flushReport(initial); page.filters = { canal: 'DIGITAL', id_sucursal: 1, id_categoria: 2 }; page.clear();
    const req = reportRequest();
    expect(req.request.params.keys().sort()).toEqual(['fecha_desde', 'fecha_hasta']);
    expect(page.filters).toEqual(currentSalesMonth()); flushReport(req);
  });
  it('permite fechas abiertas y rechaza rangos invertidos', () => {
    flushReport(initial); page.filters = { fecha_desde: '2026-09-20', fecha_hasta: '2026-09-01' }; page.apply();
    http.expectNone(r => r.url.endsWith('/sales-report')); expect(page.validation()).toContain('anterior');
    page.filters = {}; page.apply(); const req = reportRequest(); expect(req.request.params.keys()).toEqual([]); flushReport(req);
  });
  it('carga todas las páginas e incluye opciones inactivas', () => {
    flushReport(initial); expect(page.branches().length).toBe(2); expect(page.categories().length).toBe(2);
    expect(element().textContent).toContain('Histórica (inactiva)');
  });
  it('muestra ceros y listas vacías sin inventar datos', () => {
    flushReport(initial, { ...data, kpis: { cantidad_ventas: 0, importe_antes_descuentos: '0.00', descuentos: '0.00', importe_vendido: '0.00', ticket_promedio: null, unidades_vendidas: 0, clientes_identificados: 0, ventas_sin_cliente: 0 }, por_canal: [], por_sucursal: [], serie_diaria: [], productos_mas_vendidos: [] });
    expect(element().textContent).toContain('Sin resultados'); expect(element().textContent).toContain(formatBs(0));
    expect(element().querySelectorAll('circle, tbody tr').length).toBe(0);
  });
  it('muestra error y reintenta desde el botón', () => {
    initial.flush({}, { status: 500, statusText: 'Error' }); fixture.detectChanges();
    expect(element().querySelector('[role="alert"]')?.textContent).toContain('No pudimos');
    (element().querySelector('[role="alert"] button') as HTMLButtonElement).click(); flushReport();
    expect(page.error()).toBe('');
  });
  it('resuelve 401 cerrando sesión y navegando a login', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    initial.flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(TestBed.inject(SessionService).getAccessToken()).toBeNull(); expect(navigate).toHaveBeenCalledWith('/login');
  });
  it('resuelve 403 con el mensaje administrativo', () => {
    initial.flush({}, { status: 403, statusText: 'Forbidden' }); fixture.detectChanges();
    expect(element().textContent).toContain('Acceso no autorizado.'); expect(page.report()).toBeNull();
  });
  it('permite reintentar errores de los selectores', () => {
    flushReport(initial); page.loadOptions();
    const categories = http.expectOne(r => r.url.endsWith('/categories'));
    http.expectOne(r => r.url.endsWith('/branches')).flush({}, { status: 500, statusText: 'Error' });
    expect(categories.cancelled).toBe(true); fixture.detectChanges(); expect(page.optionsError()).toContain('sucursales');
    page.loadOptions();
    for (const resource of ['branches', 'categories']) http.expectOne(r => r.url.endsWith('/' + resource)).flush({ data: [], pagination: { page: 1, total_pages: 0 } });
    expect(page.optionsError()).toBe('');
  });
  it('cancela consultas anteriores al cambiar los filtros', () => {
    page.filters.canal = 'DIGITAL'; page.apply(); expect(initial.cancelled).toBe(true); flushReport();
  });
  it('conserva guards y carga diferida dentro del administrador', () => {
    flushReport(initial); const admin = routes.find(r => r.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard); expect(admin.canActivateChild).toContain(adminChildGuard);
    expect(admin.children?.find(r => r.path === 'reporte-ventas')?.loadComponent).toBeDefined();
  });
  it('convierte una consulta por voz a texto y la envía al análisis con IA existente', async () => {
    flushReport(initial);
    const speech = TestBed.inject(SpeechRecognitionService);
    vi.spyOn(speech, 'listenOnce').mockResolvedValue('¿cómo estuvieron las ventas del canal digital?');

    await page.analyzeWithVoice();
    const aiRequest = http.expectOne(r => r.url.endsWith('/sales-report/ai-analysis'));
    expect(aiRequest.request.params.get('pregunta')).toBe('¿cómo estuvieron las ventas del canal digital?');
    aiRequest.flush({ success: true, data: { analisis: 'Las ventas digitales crecieron 10%.', modelo: 'gemini-3.6-flash', generado_en: '2026-09-22T00:00:00Z' } });
    fixture.detectChanges();

    expect(page.voiceQuery()).toBe('¿cómo estuvieron las ventas del canal digital?');
    expect(page.aiAnalysis()?.analisis).toBe('Las ventas digitales crecieron 10%.');
    expect(element().textContent).toContain('Las ventas digitales crecieron 10%.');
    expect(element().textContent).toContain('¿cómo estuvieron las ventas del canal digital?');
  });
});
