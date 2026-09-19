import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { AdminInventoryReport } from './admin-inventory-report';
import { InventoryReportData, InventoryKPIs } from '../../../core/services/admin-inventory-report.service';
import { SessionService } from '../../../core/services/session.service';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';

const kpis: InventoryKPIs = { total_productos: 2, total_variantes: 3, total_registros_inventario: 4, unidades_actuales: 20, unidades_reservadas: 10, unidades_disponibles: 10, registros_agotados: 1, registros_bajo_stock: 1, productos_con_agotados: 1, productos_con_bajo_stock: 1, registros_con_stock_minimo_cero: 1 };
const data: InventoryReportData = {
  generado_en: '2026-09-19T00:00:00Z', filtros: { id_sucursal: null, id_categoria: null, id_producto: null, estado_stock: null, page: 1, page_size: 20 }, kpis,
  por_sucursal: [{ ...kpis, id_sucursal: 1, nombre: 'Centro', estado: false }],
  por_categoria: [{ ...kpis, id_categoria: 2, nombre: 'Camisas', estado: true }],
  detalle: { pagination: { page: 1, page_size: 20, total: 4, total_pages: 2 }, items: ['NORMAL', 'BAJO_STOCK', 'AGOTADO', null].map((state, i) => ({
    id_inventario_sucursal: i + 1, sucursal: { id_sucursal: 1, nombre: 'Centro', estado: false }, categoria: { id_categoria: 2, nombre: 'Camisas', estado: true }, producto: { id_producto: 3, nombre: 'Oxford', estado: false }, variante: { id_variante_producto: i + 1, sku: 'SKU-' + i, talla: 'M', color: 'Azul', estado: false }, stock_actual: 5, stock_reservado: i === 3 ? 7 : 2, stock_disponible: i === 3 ? -2 : 3, stock_minimo: 5, estado_stock: state as 'NORMAL' | 'BAJO_STOCK' | 'AGOTADO' | null, faltante_hasta_minimo: 2,
  })) },
  advertencias: [{ codigo: 'STOCK_DISPONIBLE_NEGATIVO', mensaje: 'Saldo real negativo', registros: 1, alcance: 'FILTROS_SIN_ESTADO_STOCK' }],
};
describe('CU29 inventario web', () => {
  let fixture: ComponentFixture<AdminInventoryReport>;
  let page: AdminInventoryReport;
  let http: HttpTestingController;
  let initial: TestRequest;
  const request = () => http.expectOne(r => r.url.endsWith('/inventory-report'));
  const el = () => fixture.nativeElement as HTMLElement;
  const flush = (req = request(), value = data) => { req.flush({ success: true, data: value }); fixture.detectChanges(); };
  const options = () => {
    for (const resource of ['branches', 'categories', 'products']) {
      http.expectOne(r => r.url.endsWith('/' + resource)).flush({ data: [{ id_sucursal: 1, id_categoria: 2, id_producto: 3, nombre: 'Historico', estado: false }], pagination: { page: 1, total_pages: 2 } });
      http.expectOne(r => r.url.endsWith('/' + resource) && r.params.get('page') === '2').flush({ data: [], pagination: { page: 2, total_pages: 2 } });
    }
  };
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(SessionService).saveAccessToken('cu29-token');
    fixture = TestBed.createComponent(AdminInventoryReport); page = fixture.componentInstance;
    fixture.detectChanges(); initial = request(); options();
  });
  afterEach(() => { fixture.destroy(); http.verify(); localStorage.clear(); });
  it('GET autenticado y carga inicial', () => {
    expect(initial.request.method).toBe('GET'); expect(initial.request.headers.get('Authorization')).toBe('Bearer cu29-token');
    expect(initial.request.params.get('page')).toBe('1'); expect(initial.request.params.get('page_size')).toBe('20');
    expect(el().querySelectorAll('.skeleton').length).toBe(10); flush(initial);
  });
  it('renderiza diez KPIs, tres graficos y todos los badges', () => {
    flush(initial); expect(el().querySelectorAll('.kpi').length).toBe(10); expect(el().querySelectorAll('.chart').length).toBe(3);
    expect([...el().querySelectorAll('.badge')].map(x => x.textContent?.trim())).toEqual(['NORMAL', 'BAJO STOCK', 'AGOTADO', 'INCONSISTENCIA']);
    expect(el().textContent).toContain('Faltan 2'); expect(el().textContent).toContain('Variante inactiva');
    expect(el().querySelector('td.negative')?.textContent).toBe('-2');
    expect(page.charts()[2].rows.map(r => r.value)).toEqual([1, 1, 1, 1]);
  });
  for (const state of ['NORMAL', 'BAJO_STOCK', 'AGOTADO'] as const) {
    it('filtra desde formulario ' + state, async () => {
      flush(initial); await fixture.whenStable();
      for (const name of ['id_sucursal', 'id_categoria', 'id_producto', 'estado_stock']) {
        const control = el().querySelector(`[name="${name}"]`) as HTMLSelectElement;
        control.value = name === 'estado_stock' ? state : control.options[1].value;
        control.dispatchEvent(new Event('change'));
      }
      el().querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
      const req = request();
      expect(req.request.params.get('id_sucursal')).toBe('1'); expect(req.request.params.get('id_categoria')).toBe('2'); expect(req.request.params.get('id_producto')).toBe('3');
      expect(req.request.params.get('estado_stock')).toBe(state); expect(req.request.params.get('page')).toBe('1'); flush(req);
    });
  }
  it('limpia filtros y pagina', () => {
    flush(initial); page.filters = { id_producto: 3, estado_stock: 'NORMAL' }; page.clear();
    const req = request(); expect(req.request.params.keys().sort()).toEqual(['page', 'page_size']); expect(page.filters).toEqual({}); flush(req);
  });
  it('pagina usando filtros aplicados, no cambios pendientes', () => {
    flush(initial); page.filters = { id_producto: 3 }; page.goToPage(2);
    const req = request(); expect(req.request.params.get('page')).toBe('2'); expect(req.request.params.has('id_producto')).toBe(false);
    flush(req, { ...data, detalle: { ...data.detalle, pagination: { ...data.detalle.pagination, page: 2 } } });
    expect(page.report()?.kpis).toEqual(kpis); expect(page.charts()[0].rows[0].value).toBe(10);
    page.resize(100); const resized = request(); expect(resized.request.params.get('page')).toBe('1'); expect(resized.request.params.get('page_size')).toBe('100'); flush(resized);
  });
  it('sin resultados muestra ceros y tabla vacia', () => {
    flush(initial, { ...data, kpis: Object.fromEntries(Object.keys(kpis).map(k => [k, 0])) as unknown as InventoryKPIs, por_sucursal: [], por_categoria: [], detalle: { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } }, advertencias: [] });
    expect(el().textContent).toContain('Sin resultados'); expect(el().querySelectorAll('tbody tr').length).toBe(0);
  });
  it('reintenta error sin aplicar filtros pendientes', () => {
    initial.flush({}, { status: 500, statusText: 'Error' }); fixture.detectChanges(); page.filters = { id_producto: 3 };
    (el().querySelector('[role="alert"] button') as HTMLButtonElement).click();
    const req = request(); expect(req.request.params.has('id_producto')).toBe(false); flush(req); expect(page.error()).toBe('');
  });
  it('401 cierra sesion', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    initial.flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(TestBed.inject(SessionService).getAccessToken()).toBeNull(); expect(navigate).toHaveBeenCalledWith('/login');
  });
  it('403 muestra acceso no autorizado', () => {
    initial.flush({}, { status: 403, statusText: 'Forbidden' }); fixture.detectChanges(); expect(el().textContent).toContain('Acceso no autorizado.');
  });
  it('advertencias fuera del filtro no reducen normales', () => {
    flush(initial, { ...data, filtros: { ...data.filtros, estado_stock: 'NORMAL' }, kpis: { ...kpis, total_registros_inventario: 2, registros_agotados: 0, registros_bajo_stock: 0 } });
    expect(page.charts()[2].rows[0].value).toBe(2); expect(el().textContent).toContain('independientemente');
  });
  it('carga selectores completos sin excluir inactivos', () => {
    flush(initial); expect(page.products().length).toBe(1); expect(page.branches()[0].estado).toBe(false);
  });
  it('cancela solicitud anterior', () => { page.apply(); expect(initial.cancelled).toBe(true); flush(); });
  it('tabla accesible desplazable y guards existentes', () => {
    flush(initial); expect(el().querySelector('.table-scroll')?.getAttribute('tabindex')).toBe('0');
    expect(el().querySelectorAll('th[scope="col"]').length).toBe(11);
    const admin = routes.find(r => r.path === 'admin')!; expect(admin.canActivate).toContain(adminGuard); expect(admin.canActivateChild).toContain(adminChildGuard);
    expect(admin.children?.find(r => r.path === 'reporte-inventario')?.loadComponent).toBeDefined();
  });
});
