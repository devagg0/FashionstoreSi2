import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';
import { AdminProduct } from '../../../core/services/admin-products.service';
import {
  AdminPromotion,
  AdminPromotionProduct,
} from '../../../core/services/admin-promotions.service';
import { environment } from '../../../../environments/environment';
import { AdminPromotions } from './admin-promotions';

const promotionsUrl = `${environment.apiUrl}/api/admin/promotions`;
const productsUrl = `${environment.apiUrl}/api/admin/products`;
const promotion: AdminPromotion = {
  id_promocion: 7,
  nombre: 'Semana Denim',
  codigo: 'DENIM20',
  descripcion: 'Descuento global',
  tipo_descuento: 'PORCENTAJE',
  valor: '20.00',
  fecha_inicio: '2026-09-08T14:00:00',
  fecha_fin: '2026-09-10T14:00:00',
  acumulable: false,
  estado: true,
  vigencia: 'VIGENTE',
  total_productos: 1,
  created_at: '2026-09-01T10:00:00',
  updated_at: '2026-09-01T10:00:00',
};
const associated: AdminPromotionProduct = {
  id_promocion_producto: 30,
  id_producto: 11,
  nombre: 'Jean recto',
  seccion: 'UNISEX',
  precio: '59.90',
  estado: true,
};
const product = (id: number, estado = true): AdminProduct => ({
  id_producto: id,
  id_categoria: 2,
  categoria: 'Jeans',
  id_temporada: null,
  temporada: null,
  nombre: `Producto ${id}`,
  seccion: 'UNISEX',
  descripcion: null,
  precio: '59.90',
  estado,
  imagen_principal: null,
  total_variantes: 0,
  created_at: '2026-09-01T10:00:00',
  updated_at: '2026-09-01T10:00:00',
});
const listing = (data = [promotion], page = 1, total = data.length) => ({
  success: true,
  data,
  pagination: { page, page_size: 10, total, total_pages: Math.ceil(total / 10) },
});

describe('AdminPromotions CU11', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<AdminPromotions>;
  let page: AdminPromotions;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminPromotions);
    page = fixture.componentInstance;
    fixture.detectChanges();
    http.expectOne((request) => request.url === promotionsUrl).flush(listing());
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    fixture.destroy();
  });

  function openDetail(): void {
    page['viewDetail'](7);
    http.expectOne(`${promotionsUrl}/7`).flush({
      success: true,
      data: { ...promotion, productos: [associated] },
    });
    http.expectOne(`${promotionsUrl}/7/products`).flush({ success: true, data: [associated] });
    http.expectOne((request) => request.url === productsUrl).flush({
      success: true,
      data: [product(11), product(12), product(13, false)],
      pagination: { page: 1, page_size: 100, total: 3, total_pages: 1 },
    });
    fixture.detectChanges();
  }

  it('renders discount, state, validity, dates and no destructive actions', () => {
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Semana Denim');
    expect(text).toContain('20,00%');
    expect(text).toContain('Vigente');
    expect(text).toContain('Activa');
    expect(fixture.nativeElement.querySelector('[title*="Eliminar"]')).toBeNull();
    expect(fixture.nativeElement.querySelector('[title*="Desasociar"]')).toBeNull();
  });

  it('filters search, state and validity and resets the page', () => {
    page['filters'].setValue({ search: ' denim ', estado: 'false', vigencia: 'EXPIRADA' });
    page['applyFilters']();
    const request = http.expectOne((item) => item.url === promotionsUrl);
    expect(request.request.params.get('search')).toBe('denim');
    expect(request.request.params.get('estado')).toBe('false');
    expect(request.request.params.get('vigencia')).toBe('EXPIRADA');
    expect(request.request.params.get('page')).toBe('1');
    request.flush(listing());
  });

  it('paginates using backend metadata', () => {
    page['pagination'].set({ page: 1, page_size: 10, total: 11, total_pages: 2 });
    page['nextPage']();
    const next = http.expectOne((item) => item.url === promotionsUrl);
    expect(next.request.params.get('page')).toBe('2');
    next.flush(listing([promotion], 2, 11));
    page['previousPage']();
    const previous = http.expectOne((item) => item.url === promotionsUrl);
    expect(previous.request.params.get('page')).toBe('1');
    previous.flush(listing([promotion], 1, 11));
  });

  it('validates date range and discount according to type', () => {
    page['openPromotionModal']();
    const form = page['promotionForm'];
    form.patchValue({
      nombre: 'Promo',
      tipo_descuento: 'PORCENTAJE',
      valor: '101',
      fecha_inicio: '2026-09-10T10:00',
      fecha_fin: '2026-09-09T10:00',
    });
    expect(form.hasError('discountValue')).toBe(true);
    expect(form.hasError('dateRange')).toBe(true);
    page['submitPromotion']();
    http.expectNone(promotionsUrl);

    form.patchValue({ tipo_descuento: 'MONTO_FIJO', valor: '0' });
    expect(form.hasError('discountValue')).toBe(true);
    form.patchValue({ valor: '10.50', fecha_fin: '2026-09-11T10:00' });
    expect(form.valid).toBe(true);
  });

  it('creates with normalized fields and dates', () => {
    page['openPromotionModal']();
    page['promotionForm'].setValue({
      nombre: ' Promo nueva ',
      codigo: ' promo10 ',
      descripcion: ' Oferta ',
      tipo_descuento: 'MONTO_FIJO',
      valor: '10.50',
      fecha_inicio: '2026-09-10T10:00',
      fecha_fin: '2026-09-11T10:00',
      acumulable: true,
    });
    page['submitPromotion']();
    const request = http.expectOne(promotionsUrl);
    expect(request.request.method).toBe('POST');
    expect(request.request.body.nombre).toBe('Promo nueva');
    expect(request.request.body.codigo).toBe('PROMO10');
    expect(request.request.body.valor).toBe(10.5);
    expect(request.request.body.fecha_inicio).toMatch(/Z$/);
    request.flush({ success: true, message: 'ok', data: { ...promotion, productos: [] } });
    http.expectOne((item) => item.url === promotionsUrl).flush(listing());
    expect(page['promotionModalOpen']()).toBe(false);
  });

  it('does not submit an unchanged patch', () => {
    page['openPromotionModal'](promotion);
    page['submitPromotion']();
    http.expectNone(`${promotionsUrl}/7`);
    expect(page['modalErrorMessage']()).toContain('No hay cambios');
  });

  it('loads detail and only offers active, unassociated products', () => {
    openDetail();
    expect(page['detailPromotion']()?.productos).toEqual([associated]);
    expect(page['availableProducts']().map((item) => item.id_producto)).toEqual([12]);
    expect(page['productCategory'](associated)).toBe('Jeans');
  });

  it('associates multiple selected products and refreshes real data', () => {
    openDetail();
    page['toggleProduct'](12, true);
    page['associateProducts']();
    const request = http.expectOne(`${promotionsUrl}/7/products`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ id_productos: [12] });
    const second = { ...associated, id_promocion_producto: 31, id_producto: 12 };
    request.flush({ success: true, message: 'ok', data: [associated, second] });
    http.expectOne((item) => item.url === productsUrl).flush({
      success: true,
      data: [product(12)],
      pagination: { page: 1, page_size: 100, total: 1, total_pages: 1 },
    });
    http.expectOne((item) => item.url === promotionsUrl).flush(listing());
    expect(page['selectedProductIds']()).toEqual([]);
    expect(page['detailPromotion']()?.productos.length).toBe(2);
  });

  it.each([true, false])('confirms status change from %s without deleting', (estado) => {
    page['openStatusModal']({ ...promotion, estado });
    page['confirmStatusChange']();
    const request = http.expectOne(`${promotionsUrl}/7/status`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ estado: !estado });
    request.flush({
      success: true,
      message: 'ok',
      data: { ...promotion, estado: !estado, productos: [associated] },
    });
    http.expectOne((item) => item.url === promotionsUrl).flush(listing());
    http.expectNone((item) => item.method === 'DELETE');
  });

  it('shows the safe backend message for a rejected association', () => {
    openDetail();
    page['toggleProduct'](12, true);
    page['associateProducts']();
    http.expectOne(`${promotionsUrl}/7/products`).flush(
      { success: false, message: 'El producto 12 esta inactivo' },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    expect(page['detailError']()).toBe('El producto 12 esta inactivo');
    expect(page['saving']()).toBe(false);
  });

  it('registers a lazy route under the existing admin guards', async () => {
    const admin = routes.find((route) => route.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    const route = admin.children!.find((item) => item.path === 'promociones')!;
    expect(await (route.loadComponent! as () => Promise<unknown>)()).toBe(AdminPromotions);
  });

  it('uses AdminApiErrorService session handling', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    page['loadPromotions']();
    http.expectOne((item) => item.url === promotionsUrl).flush(
      { success: false, message: 'Token inválido o expirado' },
      { status: 401, statusText: 'Unauthorized' },
    );
    expect(navigate).toHaveBeenCalledWith('/login');
    expect(page['errorMessage']()).toBe('Token inválido o expirado');
  });
});
