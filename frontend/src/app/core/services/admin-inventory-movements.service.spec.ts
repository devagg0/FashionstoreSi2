import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import {
  AdminInventoryMovementsService,
  MovementCreateRequest,
} from './admin-inventory-movements.service';

const url = `${environment.apiUrl}/api/admin/inventory-movements`;
describe('AdminInventoryMovementsService CU15', () => {
  let service: AdminInventoryMovementsService;
  let http: HttpTestingController;
  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminInventoryMovementsService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => {
    http.verify();
    localStorage.clear();
  });
  it('lists with default pagination and omits empty filters', () => {
    service.listMovements({ search: '  ', fecha_desde: '' }).subscribe();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys()).toEqual(['page', 'page_size']);
    expect(req.request.params.get('page')).toBe('1');
    expect(req.request.params.get('page_size')).toBe('20');
    req.flush({
      success: true,
      data: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
    });
  });
  it('sends all backend filters and Bearer authorization', () => {
    service
      .listMovements({
        search: ' ajuste ',
        tipo_movimiento: 'ENTRADA',
        estado: 'PENDIENTE',
        id_sucursal: 2,
        id_variante_producto: 3,
        fecha_desde: '2026-09-01T00:00:00Z',
        fecha_hasta: '2026-09-09T00:00:00Z',
        page: 2,
        pageSize: 10,
      })
      .subscribe();
    const req = http.expectOne((r) => r.url === url);
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    for (const [key, value] of Object.entries({
      search: 'ajuste',
      tipo_movimiento: 'ENTRADA',
      estado: 'PENDIENTE',
      id_sucursal: '2',
      id_variante_producto: '3',
      fecha_desde: '2026-09-01T00:00:00Z',
      fecha_hasta: '2026-09-09T00:00:00Z',
      page: '2',
      page_size: '10',
    }))
      expect(req.request.params.get(key)).toBe(value);
    req.flush({ success: true, data: [], pagination: {} });
  });
  it('gets detail with authorization', () => {
    service.getMovement(7).subscribe();
    const req = http.expectOne(`${url}/7`);
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    req.flush({ success: true, data: {} });
  });
  it('creates using the exact request contract', () => {
    const fields: MovementCreateRequest = {
      tipo_movimiento: 'ENTRADA',
      id_sucursal_destino: 2,
      id_empleado_sucursal: 4,
      motivo: null,
      detalles: [{ id_variante_producto: 3, cantidad: 2, costo_unitario: 0 }],
    };
    service.createMovement(fields).subscribe();
    const req = http.expectOne(url);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(fields);
    expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
    req.flush({ success: true, data: {} });
  });
  for (const operation of ['confirm', 'cancel'] as const) {
    it(`${operation} uses PATCH and authorization`, () => {
      (operation === 'confirm'
        ? service.confirmMovement(7)
        : service.cancelMovement(7)
      ).subscribe();
      const req = http.expectOne(`${url}/7/${operation}`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.headers.get('Authorization')).toBe('Bearer admin-token');
      expect(req.request.body).toEqual({});
      req.flush({ success: true, data: {} });
    });
  }
  it('preserves 409 backend errors for the administrative error handler', () => {
    const error = vi.fn();
    service.confirmMovement(7).subscribe({ error });
    http
      .expectOne(`${url}/7/confirm`)
      .flush(
        { success: false, message: 'Stock disponible insuficiente' },
        { status: 409, statusText: 'Conflict' },
      );
    expect(error.mock.calls[0][0].status).toBe(409);
    expect(error.mock.calls[0][0].error.message).toBe('Stock disponible insuficiente');
  });
  it('omits authorization when no token exists', () => {
    localStorage.clear();
    service.getMovement(7).subscribe();
    const req = http.expectOne(`${url}/7`);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({ success: true, data: {} });
  });
});
