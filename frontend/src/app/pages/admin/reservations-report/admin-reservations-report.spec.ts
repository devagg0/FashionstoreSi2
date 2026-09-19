import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { AdminReservationsReport, currentReservationsMonth, periodLabel } from './admin-reservations-report';
import { ReservationsReportData } from '../../../core/services/admin-reservations-report.service';
import { SessionService } from '../../../core/services/session.service';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';

const kpis = {
  total_reservas: 10, unidades_reservadas: 24, reservas_pendientes: 2, reservas_confirmadas: 1,
  reservas_atendidas: 5, reservas_canceladas: 1, reservas_expiradas: 1, clientes_con_reservas: 4,
};
const data: ReservationsReportData = {
  zona_horaria: 'America/La_Paz', generado_en: '2026-09-19T12:00:00Z', criterio_estado: 'PERSISTIDO',
  filtros: { tipo_fecha: 'CREACION', periodo: 'DIA' },
  kpis,
  por_estado: [
    { estado: 'PENDIENTE', total_reservas: 2, unidades_reservadas: 4 },
    { estado: 'CONFIRMADA', total_reservas: 1, unidades_reservadas: 2 },
    { estado: 'ATENDIDA', total_reservas: 5, unidades_reservadas: 12 },
    { estado: 'CANCELADA', total_reservas: 1, unidades_reservadas: 3 },
    { estado: 'EXPIRADA', total_reservas: 1, unidades_reservadas: 3 },
  ],
  por_sucursal: [
    { id_sucursal: 1, nombre_sucursal: 'Centro', total_reservas: 7, unidades_reservadas: 18, clientes_con_reservas: 3 },
    { id_sucursal: 2, nombre_sucursal: 'Norte', total_reservas: 3, unidades_reservadas: 6, clientes_con_reservas: 1 },
  ],
  serie_periodica: [
    { inicio_periodo: '2026-09-02', total_reservas: 4, unidades_reservadas: 9 },
    { inicio_periodo: '2026-09-01', total_reservas: 6, unidades_reservadas: 15 },
  ],
  productos_mas_reservados: [
    { id_producto: 3, nombre_producto: 'Blusa', total_reservas: 6, unidades_reservadas: 14 },
    { id_producto: 1, nombre_producto: 'Camisa', total_reservas: 4, unidades_reservadas: 10 },
  ],
  categorias_mas_reservadas: [{ id_categoria: 1, nombre_categoria: 'Ropa', total_reservas: 10, unidades_reservadas: 24 }],
  advertencias: { reservas_vencidas_sin_actualizar: 0 },
};
const emptyData: ReservationsReportData = {
  ...data,
  kpis: { total_reservas: 0, unidades_reservadas: 0, reservas_pendientes: 0, reservas_confirmadas: 0, reservas_atendidas: 0, reservas_canceladas: 0, reservas_expiradas: 0, clientes_con_reservas: 0 },
  por_estado: data.por_estado.map(row => ({ ...row, total_reservas: 0, unidades_reservadas: 0 })),
  por_sucursal: [], serie_periodica: [], productos_mas_reservados: [], categorias_mas_reservadas: [],
};

describe('CU30 Reporte de reservas y productos', () => {
  let fixture: ComponentFixture<AdminReservationsReport>;
  let page: AdminReservationsReport;
  let http: HttpTestingController;
  let initial: TestRequest;
  const reportRequest = () => http.expectOne(r => r.url.endsWith('/reservations-report'));
  const flushReport = (request = reportRequest(), value = data) => { request.flush({ success: true, data: value }); fixture.detectChanges(); };
  const element = () => fixture.nativeElement as HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(SessionService).saveAccessToken('cu30-token');
    fixture = TestBed.createComponent(AdminReservationsReport);
    page = fixture.componentInstance;
    fixture.detectChanges();
    initial = reportRequest();
    for (const resource of ['branches', 'categories', 'products']) {
      http.expectOne(r => r.url.endsWith('/' + resource)).flush({
        data: [{ id_sucursal: 1, id_categoria: 2, id_producto: 3, nombre: 'Histórica', estado: false }],
        pagination: { page: 1, total_pages: 1 },
      });
    }
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });

  it('consulta con token, mes de La Paz y muestra skeletons mientras carga', () => {
    expect(initial.request.headers.get('Authorization')).toBe('Bearer cu30-token');
    expect(initial.request.params.get('fecha_desde')).toBe(currentReservationsMonth().fecha_desde);
    expect(initial.request.params.get('tipo_fecha')).toBe('CREACION');
    expect(initial.request.params.get('periodo')).toBe('DIA');
    expect(element().querySelectorAll('.skeleton').length).toBe(13);
    expect(currentReservationsMonth(new Date('2026-10-01T01:00:00Z')).fecha_hasta).toBe('2026-09-30');
    flushReport(initial);
  });

  it('renderiza los ocho KPI cards con sus valores y tono semántico', () => {
    flushReport(initial);
    const cards = element().querySelectorAll('.kpi');
    expect(cards.length).toBe(8);
    expect([...cards].map(card => card.querySelector('strong')?.textContent)).toEqual(['10', '2', '1', '5', '1', '1', '24', '4']);
    expect([...cards].map(card => card.className.includes('kpi--'))).not.toContain(false);
    expect(element().textContent).toContain('Clientes con reservas');
  });

  it('dibuja el donut de estados con porcentaje, cantidad, leyenda, tooltip y total al centro', () => {
    flushReport(initial);
    const donut = element().querySelector('.chart--donut')!;
    expect(donut.querySelectorAll('.donut-segment').length).toBe(5);
    expect(donut.querySelector('.donut-center strong')?.textContent).toBe('10');
    expect(donut.querySelector('.donut-segment title')?.textContent).toContain('Pendientes: 2 reservas (20%)');
    expect(donut.querySelectorAll('.legend li').length).toBe(5);
    expect(donut.querySelector('.legend li strong')?.textContent).toBe('20%');
    const segments = page.stateDonut();
    expect(segments.map(s => Math.round(s.percent))).toEqual([20, 10, 50, 10, 10]);
    expect(segments[1].offset).toBeCloseTo(-segments[0].dash, 5);
  });

  it('dibuja la evolución ordenada por período con puntos, grid y segunda serie', () => {
    flushReport(initial);
    const chart = element().querySelector('.chart--series')!;
    expect(page.series().map(point => point.inicio_periodo)).toEqual(['2026-09-01', '2026-09-02']);
    expect(chart.querySelectorAll('.point').length).toBe(2);
    expect(chart.querySelectorAll('.point-units').length).toBe(2);
    expect(chart.querySelectorAll('.grid').length).toBe(5);
    expect(chart.querySelector('.point title')?.textContent).toContain('1 sep: 6 reservas · 15 unidades');
    expect(page.seriesArea()).toContain('Z');
    expect(periodLabel('2026-09-07', 'SEMANA')).toBe('sem. 7 sep');
    expect(periodLabel('2026-09-07', 'MES')).toBe('sep 2026');
  });

  it('muestra sucursales, productos y categorías con contexto relativo', () => {
    flushReport(initial);
    expect(page.branchRows().map(row => Math.round(row.percent))).toEqual([100, 43]);
    expect(page.productRows().map(row => Math.round(row.percent))).toEqual([100, 71]);
    expect(page.categoryRows()[0].units).toBe(24);
    expect(element().querySelectorAll('.bar-row').length).toBe(4);
    expect(element().textContent).toContain('% del líder');
    const rankings = element().querySelectorAll('.ranking');
    expect(rankings.length).toBe(2);
    expect(rankings[0].querySelectorAll('tbody tr').length).toBe(2);
    expect(rankings[0].querySelector('tbody tr')?.textContent).toContain('Blusa');
    expect(rankings[1].querySelector('tbody tr')?.textContent).toContain('Ropa');
    expect(element().querySelectorAll('.chart--donut')[1].querySelectorAll('.donut-segment').length).toBe(1);
  });

  it('envía los ocho filtros desde el formulario y actualiza los gráficos', async () => {
    flushReport(initial);
    await fixture.whenStable();
    const change = (name: string, value: string) => {
      const control = element().querySelector(`[name="${name}"]`) as HTMLInputElement;
      control.value = value;
      control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input'));
    };
    change('fecha_desde', '2026-01-01');
    change('fecha_hasta', '2026-02-28');
    change('tipo_fecha', 'ATENCION');
    change('periodo', 'SEMANA');
    change('estado', 'ATENDIDA');
    for (const name of ['id_sucursal', 'id_categoria', 'id_producto']) {
      const select = element().querySelector(`[name="${name}"]`) as HTMLSelectElement;
      change(name, select.options[1].value);
    }
    element().querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
    const request = reportRequest();
    expect(request.request.params.get('fecha_desde')).toBe('2026-01-01');
    expect(request.request.params.get('fecha_hasta')).toBe('2026-02-28');
    expect(request.request.params.get('tipo_fecha')).toBe('ATENCION');
    expect(request.request.params.get('periodo')).toBe('SEMANA');
    expect(request.request.params.get('estado')).toBe('ATENDIDA');
    expect(request.request.params.get('id_sucursal')).toBe('1');
    expect(request.request.params.get('id_categoria')).toBe('2');
    expect(request.request.params.get('id_producto')).toBe('3');
    flushReport(request, { ...data, kpis: { ...kpis, total_reservas: 1 }, filtros: { tipo_fecha: 'ATENCION', periodo: 'SEMANA' } });
    expect(element().querySelector('.kpi strong')?.textContent).toBe('1');
    expect(element().textContent).toContain('agrupadas por semana');
  });

  it('limpia los filtros y vuelve al estado inicial', () => {
    flushReport(initial);
    page.filters = { fecha_desde: '2026-01-01', tipo_fecha: 'ATENCION', periodo: 'MES', id_sucursal: 1, estado: 'ATENDIDA', id_categoria: 2, id_producto: 3 };
    page.clear();
    const request = reportRequest();
    expect(page.filters).toEqual(currentReservationsMonth());
    expect(request.request.params.keys().sort()).toEqual(['fecha_desde', 'fecha_hasta', 'periodo', 'tipo_fecha']);
    flushReport(request);
  });

  it('rechaza rangos invertidos sin consultar la API', () => {
    flushReport(initial);
    page.filters = { fecha_desde: '2026-09-20', fecha_hasta: '2026-09-01' };
    page.apply();
    http.expectNone(r => r.url.endsWith('/reservations-report'));
    expect(page.validation()).toContain('anterior');
  });

  it('muestra estado vacío elegante y no inventa datos si la respuesta viene en cero', () => {
    flushReport(initial, emptyData);
    expect(element().textContent).toContain('Sin resultados');
    expect(element().querySelectorAll('.donut-segment, .point, .bar-row, tbody tr').length).toBe(0);
    expect(page.stateDonut()).toEqual([]);
    expect(element().textContent).toContain('no hay estados que distribuir');
  });

  it('muestra la advertencia de reservas vencidas sin actualizar', () => {
    flushReport(initial, { ...data, advertencias: { reservas_vencidas_sin_actualizar: 3 } });
    const warning = element().querySelector('.warning');
    expect(warning?.textContent).toContain('Existen 3 reservas vencidas pendientes de actualización');
    expect(page.expiredWarning()).toBe(3);
  });

  it('oculta la advertencia cuando no hay reservas vencidas', () => {
    flushReport(initial);
    expect(element().querySelector('.warning')).toBeNull();
  });

  it('muestra error con botón Reintentar', () => {
    initial.flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(element().querySelector('[role="alert"]')?.textContent).toContain('No pudimos cargar el reporte de reservas');
    (element().querySelector('[role="alert"] button') as HTMLButtonElement).click();
    flushReport();
    expect(page.error()).toBe('');
  });

  it('resuelve 401 cerrando sesión y navegando a login', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    initial.flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(TestBed.inject(SessionService).getAccessToken()).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login');
  });

  it('resuelve 403 con el mensaje administrativo', () => {
    initial.flush({}, { status: 403, statusText: 'Forbidden' });
    fixture.detectChanges();
    expect(element().textContent).toContain('Acceso no autorizado.');
    expect(page.report()).toBeNull();
  });

  it('reutiliza los selectores de sucursales, categorías y productos y permite reintentarlos', () => {
    flushReport(initial);
    expect(page.branches().length).toBe(1);
    expect(page.categories().length).toBe(1);
    expect(page.products().length).toBe(1);
    expect(element().textContent).toContain('Histórica (inactiva)');
    page.loadOptions();
    const categories = http.expectOne(r => r.url.endsWith('/categories'));
    const products = http.expectOne(r => r.url.endsWith('/products'));
    http.expectOne(r => r.url.endsWith('/branches')).flush({}, { status: 500, statusText: 'Error' });
    expect(categories.cancelled && products.cancelled).toBe(true);
    fixture.detectChanges();
    expect(page.optionsError()).toContain('sucursales');
    page.loadOptions();
    for (const resource of ['branches', 'categories', 'products']) {
      http.expectOne(r => r.url.endsWith('/' + resource)).flush({ data: [], pagination: { page: 1, total_pages: 0 } });
    }
    expect(page.optionsError()).toBe('');
  });

  it('cancela la consulta anterior al aplicar filtros nuevos', () => {
    page.filters.estado = 'ATENDIDA';
    page.apply();
    expect(initial.cancelled).toBe(true);
    flushReport();
  });

  it('mantiene la estructura responsive: grids, donut y tablas con scroll controlado', () => {
    flushReport(initial);
    expect(element().querySelector('.kpi-grid')).not.toBeNull();
    expect(element().querySelectorAll('.chart-grid > .chart').length).toBe(5);
    expect(element().querySelectorAll('.ranking-grid > .ranking').length).toBe(2);
    expect(element().querySelectorAll('.table-scroll').length).toBe(2);
    expect([...element().querySelectorAll('svg')].every(svg => svg.getAttribute('viewBox'))).toBe(true);
    expect(element().querySelectorAll('td[data-label]').length).toBeGreaterThan(0);
  });

  it('expone la ruta /admin/reporte-reservas bajo los guards administrativos', () => {
    flushReport(initial);
    const admin = routes.find(route => route.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    expect(admin.children?.find(route => route.path === 'reporte-reservas')?.loadComponent).toBeDefined();
  });
});
