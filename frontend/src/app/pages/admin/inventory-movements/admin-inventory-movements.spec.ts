import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { MovementFullData } from '../../../core/services/admin-inventory-movements.service';
import { AdminInventoryMovements } from './admin-inventory-movements';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';

const base = `${environment.apiUrl}/api/admin`;
const url = `${base}/inventory-movements`;
const movement: MovementFullData = {
  id_movimiento_inventario: 7,
  tipo_movimiento: 'ENTRADA',
  estado: 'PENDIENTE',
  fecha_movimiento: '2026-09-09T12:00:00',
  motivo: 'Recepción',
  id_sucursal_origen: null,
  sucursal_origen: null,
  id_sucursal_destino: 2,
  sucursal_destino: 'Centro',
  id_empleado_sucursal: 4,
  id_empleado: 9,
  nombre_empleado: 'Ana Pérez',
  rol: 'CAJERO',
  created_at: '2026-09-09T12:00:00',
  updated_at: '2026-09-09T12:00:00',
  detalles: [
    {
      id_variante_producto: 3,
      sku: 'JEAN-M-AZUL',
      producto: 'Jean',
      talla: 'M',
      color: 'Azul',
      cantidad: 2,
      costo_unitario: '15.00',
    },
  ],
};
const listing = (data: unknown[] = [movement], page = 1, total = data.length) => ({
  success: true,
  data,
  pagination: { page, page_size: 10, total, total_pages: Math.ceil(total / 10) },
});

describe('AdminInventoryMovements CU15', () => {
  let fixture: ComponentFixture<AdminInventoryMovements>;
  let page: AdminInventoryMovements;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminInventoryMovements);
    page = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne((r) => r.url === url).flush(listing());
    http
      .expectOne((r) => r.url === `${base}/branches`)
      .flush(
        listing([
          { id_sucursal: 2, nombre: 'Centro', estado: true },
          { id_sucursal: 5, nombre: 'Norte', estado: true },
        ]),
      );
    http
      .expectOne((r) => r.url === `${base}/products`)
      .flush(listing([{ id_producto: 1, nombre: 'Jean', estado: true }]));
    fixture.detectChanges();
  });
  afterEach(() => {
    http.verify();
    fixture.destroy();
    localStorage.clear();
  });
  function responsible() {
    http
      .expectOne((r) => r.url === `${base}/employee-branches`)
      .flush(
        listing([
          {
            id_empleado_sucursal: 4,
            id_empleado: 9,
            id_sucursal: 2,
            estado: true,
            nombre_empleado: 'Ana Pérez',
            nombre_sucursal: 'Centro',
            rol: 'CAJERO',
          },
          { id_empleado_sucursal: 6, id_empleado: 10, id_sucursal: 2, estado: true, rol: 'CAJERO' },
        ]),
      );
    http
      .expectOne((r) => r.url === `${base}/employee-branches/options/employees`)
      .flush(listing([{ id_empleado: 9, estado: true, rol: 'CAJERO' }]));
    http
      .expectOne(`${base}/roles`)
      .flush({ success: true, data: [{ nombre: 'CAJERO', estado: true }] });
  }
  function validForm() {
    page['openCreate']();
    page['form'].controls.id_sucursal_destino.setValue(2);
    responsible();
    page['form'].controls.id_empleado_sucursal.setValue(4);
    page['details']
      .at(0)
      .patchValue({ id_producto: 1, id_variante_producto: 3, cantidad: 2, costo_unitario: 15 });
  }
  it('renders list, responsible, branches and pending actions', () => {
    expect(fixture.nativeElement.textContent).toContain('Ana Pérez');
    expect(fixture.nativeElement.textContent).toContain('Centro');
    expect(fixture.nativeElement.textContent).toContain('PENDIENTE');
    expect(fixture.nativeElement.textContent).toContain('Confirmar');
  });
  it('keeps applied filters when paging', () => {
    page['filters'].patchValue({ search: ' recepción ', estado: 'PENDIENTE' });
    page['applyFilters']();
    http
      .expectOne(
        (r) =>
          r.url === url && r.params.get('search') === 'recepción' && r.params.get('page') === '1',
      )
      .flush(listing([movement], 1, 11));
    page['filters'].controls.search.setValue('not applied');
    page['loadMovements'](2);
    http
      .expectOne(
        (r) =>
          r.url === url &&
          r.params.get('search') === 'recepción' &&
          r.params.get('estado') === 'PENDIENTE' &&
          r.params.get('page') === '2',
      )
      .flush(listing([movement], 2, 11));
  });
  it('rejects reversed date ranges without requesting', () => {
    page['filters'].patchValue({
      fecha_desde: '2026-09-10T12:00',
      fecha_hasta: '2026-09-09T12:00',
    });
    page['applyFilters']();
    http.expectNone((r) => r.url === url);
    expect(page['errorMessage']()).toContain('rango de fechas');
  });
  it('gets and renders complete detail', () => {
    page['viewDetail'](7);
    http.expectOne(`${url}/7`).flush({ success: true, data: movement });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('JEAN-M-AZUL');
    expect(fixture.nativeElement.textContent).toContain('15.00');
    expect(fixture.nativeElement.textContent).toContain('Recepción');
  });
  it('rejects zero, negative and fractional quantities', () => {
    validForm();
    for (const quantity of [0, -1, 1.5]) {
      page['details'].at(0).controls.cantidad.setValue(quantity);
      page['submitMovement']();
      expect(page['form'].invalid).toBe(true);
    }
    http.expectNone((r) => r.method === 'POST');
  });
  it('rejects duplicate variants across rows', () => {
    validForm();
    page['addDetail']();
    page['details'].at(1).patchValue({ id_producto: 1, id_variante_producto: 3, cantidad: 1 });
    expect(page['form'].hasError('duplicateVariant')).toBe(true);
    page['submitMovement']();
    http.expectNone((r) => r.method === 'POST');
  });
  it('rejects identical origin and destination', () => {
    page['form'].patchValue(
      { tipo_movimiento: 'TRANSFERENCIA', id_sucursal_origen: 2, id_sucursal_destino: 2 },
      { emitEvent: false },
    );
    expect(page['form'].hasError('sameBranch')).toBe(true);
    page['submitMovement']();
    http.expectNone((r) => r.method === 'POST');
  });
  for (const type of [
    'ENTRADA',
    'AJUSTE_POSITIVO',
    'SALIDA',
    'AJUSTE_NEGATIVO',
    'TRANSFERENCIA',
  ] as const) {
    it(`changes fields for ${type}`, () => {
      page['openCreate']();
      page['form'].controls.tipo_movimiento.setValue(type);
      fixture.detectChanges();
      const origin = ['SALIDA', 'AJUSTE_NEGATIVO', 'TRANSFERENCIA'].includes(type);
      const destination = ['ENTRADA', 'AJUSTE_POSITIVO', 'TRANSFERENCIA'].includes(type);
      expect(!!fixture.nativeElement.querySelector('[formControlName="id_sucursal_origen"]')).toBe(
        origin,
      );
      expect(!!fixture.nativeElement.querySelector('[formControlName="id_sucursal_destino"]')).toBe(
        destination,
      );
      expect(page['form'].controls.id_sucursal_origen.disabled).toBe(!origin);
      expect(page['form'].controls.id_sucursal_destino.disabled).toBe(!destination);
    });
  }
  it('requires at least one detail', () => {
    page['openCreate']();
    page['removeDetail'](0);
    expect(page['form'].hasError('noDetails')).toBe(true);
    page['submitMovement']();
    http.expectNone((r) => r.method === 'POST');
  });
  it('validates optional cost, precision and reason length', () => {
    validForm();
    const cost = page['details'].at(0).controls.costo_unitario;
    for (const value of [-1, 1.234, 100000000]) {
      cost.setValue(value);
      expect(cost.invalid).toBe(true);
    }
    cost.setValue(null);
    expect(cost.valid).toBe(true);
    cost.setValue(0);
    expect(cost.valid).toBe(true);
    page['form'].controls.motivo.setValue('x'.repeat(201));
    expect(page['form'].invalid).toBe(true);
  });
  it('creates pending movement, omits UI product id and reloads', () => {
    validForm();
    page['submitMovement']();
    const req = http.expectOne(url);
    expect(req.request.body).toEqual({
      tipo_movimiento: 'ENTRADA',
      id_sucursal_origen: null,
      id_sucursal_destino: 2,
      id_empleado_sucursal: 4,
      motivo: null,
      detalles: [{ id_variante_producto: 3, cantidad: 2, costo_unitario: 15 }],
    });
    req.flush({ success: true, data: movement });
    http.expectOne((r) => r.url === url).flush(listing());
    expect(page['createOpen']()).toBe(false);
    expect(page['successMessage']()).toBe('Movimiento registrado correctamente.');
  });
  for (const kind of ['confirm', 'cancel'] as const) {
    it(`${kind} reloads the list and updates the open detail`, () => {
      page['detail'].set(movement);
      page['detailOpen'].set(true);
      page['openAction'](movement, kind);
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain(
        kind === 'confirm'
          ? 'Esta operación modificará el inventario y no podrá confirmarse nuevamente.'
          : 'El movimiento será anulado y no modificará el stock.',
      );
      page['executeAction']();
      page['executeAction']();
      const updated = { ...movement, estado: kind === 'confirm' ? 'CONFIRMADO' : 'ANULADO' };
      http.expectOne(`${url}/7/${kind}`).flush({ success: true, data: updated });
      http.expectOne((r) => r.url === url).flush(listing([updated]));
      expect(page['detail']()?.estado).toBe(updated.estado);
      expect(page['action']()).toBeNull();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.row-actions').textContent.trim()).toBe('Ver detalle');
    });
  }
  it('shows real 409 conflict, retains modal and does not report success', () => {
    page['openAction'](movement, 'confirm');
    page['executeAction']();
    http
      .expectOne(`${url}/7/confirm`)
      .flush({ message: 'Stock disponible insuficiente' }, { status: 409, statusText: 'Conflict' });
    expect(page['actionError']()).toBe('Stock disponible insuficiente');
    expect(page['saving']()).toBe(false);
    expect(page['successMessage']()).toBeNull();
    expect(page['action']()).not.toBeNull();
  });
  it('uses active CU06 employees and origin assignments for transfers', () => {
    page['openCreate']();
    page['form'].controls.tipo_movimiento.setValue('TRANSFERENCIA');
    page['form'].controls.id_sucursal_origen.setValue(2);
    const req = http.expectOne((r) => r.url === `${base}/employee-branches`);
    expect(req.request.params.get('id_sucursal')).toBe('2');
    expect(req.request.params.get('estado')).toBe('true');
    req.flush(
      listing([
        { id_empleado_sucursal: 4, id_empleado: 9, id_sucursal: 2, estado: true },
        { id_empleado_sucursal: 6, id_empleado: 10, id_sucursal: 2, estado: true },
      ]),
    );
    http
      .expectOne((r) => r.url === `${base}/employee-branches/options/employees`)
      .flush(listing([{ id_empleado: 9, estado: true, rol: 'CAJERO' }]));
    http
      .expectOne(`${base}/roles`)
      .flush({ success: true, data: [{ nombre: 'CAJERO', estado: true }] });
    expect(page['responsibleOptions']().map((r) => r.id_empleado_sucursal)).toEqual([4]);
  });
  it('loads CU10 variants and clears selection when the product changes', () => {
    page['openCreate']();
    const row = page['details'].at(0);
    row.patchValue({ id_producto: 1, id_variante_producto: 99 });
    page['selectProduct'](0);
    expect(row.controls.id_variante_producto.value).toBeNull();
    http.expectOne(`${base}/products/1`).flush({
      success: true,
      data: {
        variantes: [
          { id_variante_producto: 3, sku: 'SKU', talla: 'M', color: 'Azul', estado: true },
          { id_variante_producto: 4, estado: false },
        ],
      },
    });
    expect(page['variantOptions'](1, true).map((r) => r.id_variante_producto)).toEqual([3]);
    expect(page['variantOptions'](1).length).toBe(2);
  });
  it('loads subsequent catalog pages', () => {
    page['loadOptions']();
    http.expectOne((r) => r.url === `${base}/branches`).flush(listing([{ id_sucursal: 2 }], 1, 11));
    http
      .expectOne((r) => r.url === `${base}/branches` && r.params.get('page') === '2')
      .flush(listing([{ id_sucursal: 5 }], 2, 11));
    http.expectOne((r) => r.url === `${base}/products`).flush(listing([]));
    expect(page['branches']().length).toBe(2);
  });
  it('uses AdminApiErrorService for 400, 404, 422, 500 and 401 logout', () => {
    for (const status of [400, 404])
      expect(
        page['resolveError'](
          new HttpErrorResponse({ status, error: { message: 'Recurso inválido' } }),
        ),
      ).toBe('Recurso inválido');
    expect(page['resolveError'](new HttpErrorResponse({ status: 422 }))).toBe(
      'Revisa los datos ingresados.',
    );
    expect(
      page['resolveError'](
        new HttpErrorResponse({ status: 500, error: { message: 'private traceback' } }),
      ),
    ).not.toContain('private');
    localStorage.setItem('fashionstore_access_token', 'expired');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    page['resolveError'](new HttpErrorResponse({ status: 401 }));
    expect(localStorage.getItem('fashionstore_access_token')).toBeNull();
    expect(navigate).toHaveBeenCalledWith('/login');
  });
  it('registers the lazy route under existing admin guards', () => {
    const admin = routes.find((r) => r.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    expect(
      admin.children?.find((r) => r.path === 'movimientos-inventario')?.loadComponent,
    ).toBeDefined();
  });
});
