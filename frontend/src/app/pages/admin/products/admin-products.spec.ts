import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { routes } from '../../../app.routes';
import { adminChildGuard, adminGuard } from '../../../core/guards/admin.guard';
import { AdminProductDetail } from '../../../core/services/admin-products.service';
import { environment } from '../../../../environments/environment';
import { AdminProducts } from './admin-products';

const api = `${environment.apiUrl}/api/admin`;
const product: AdminProductDetail = {
  id_producto: 7,
  id_categoria: 1,
  categoria: 'Camisas',
  id_temporada: 1,
  temporada: 'Verano',
  nombre: 'Camisa lino',
  seccion: 'HOMBRE',
  descripcion: 'Camisa ligera',
  precio: '49.90',
  estado: true,
  imagen_principal: 'https://cdn.test/camisa.jpg',
  total_variantes: 1,
  created_at: '2026-09-08T10:00:00',
  updated_at: '2026-09-08T10:00:00',
  variantes: [
    {
      id_variante_producto: 2,
      id_talla: 1,
      talla: 'M',
      id_color: 1,
      color: 'Negro',
      sku: 'CAM-M-NEG',
      estado: true,
      created_at: '2026-09-08T10:00:00',
      updated_at: '2026-09-08T10:00:00',
    },
  ],
  colecciones: [
    { id_producto_coleccion: 1, id_coleccion: 1, coleccion: 'Esenciales', estado_coleccion: true },
  ],
  proveedores: [
    {
      id_producto_proveedor: 1,
      id_proveedor: 1,
      proveedor: 'Textiles Bolivia',
      costo_referencia: '20.00',
      estado: true,
      estado_proveedor: true,
    },
  ],
  imagenes: [
    {
      id_imagen_producto: 1,
      url_imagen: 'https://cdn.test/camisa.jpg',
      es_principal: true,
      created_at: '2026-09-08T10:00:00',
    },
  ],
};

const paged = <T>(data: T[], pageSize: number) => ({
  success: true,
  data,
  pagination: {
    page: 1,
    page_size: pageSize,
    total: data.length,
    total_pages: data.length ? 1 : 0,
  },
});

describe('AdminProducts CU10', () => {
  let fixture: ComponentFixture<AdminProducts>;
  let page: AdminProducts;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AdminProducts);
    page = fixture.componentInstance;
    fixture.detectChanges();
    flushOptions();
    flushProductLists();
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    fixture.destroy();
  });

  function flushOptions(): void {
    const options = [
      ['categories', { id_categoria: 1, nombre: 'Camisas', estado: true }],
      ['sizes', { id_talla: 1, nombre: 'M', estado: true }],
      ['colors', { id_color: 1, nombre: 'Negro', estado: true }],
      ['seasons', { id_temporada: 1, nombre: 'Verano', estado: true }],
      ['collections', { id_coleccion: 1, nombre: 'Esenciales', estado: true }],
      ['suppliers', { id_proveedor: 1, nombre: 'Textiles Bolivia', estado: true }],
    ] as const;
    for (const [resource, item] of options) {
      const request = http.expectOne((candidate) => candidate.url === `${api}/${resource}`);
      expect(request.request.params.get('page_size')).toBe('100');
      request.flush(paged([item], 100));
    }
  }

  function flushProductLists(): void {
    const requests = http.match((candidate) => candidate.url === `${api}/products`);
    expect(requests.length).toBe(1);
    for (const request of requests) {
      request.flush(paged([product], Number(request.request.params.get('page_size'))));
    }
  }

  it('renders the server product list and filters', () => {
    expect(fixture.nativeElement.textContent).toContain('Camisa lino');
    expect(fixture.nativeElement.textContent).toContain('Camisas');
    expect(fixture.nativeElement.textContent).toContain('Bs 49,90');

    page['filters'].setValue({ search: ' CAM-M ', estado: 'true', id_categoria: 1 });
    page['applyFilters']();
    const request = http.expectOne((candidate) => candidate.url === `${api}/products`);
    expect(request.request.params.get('search')).toBe('CAM-M');
    expect(request.request.params.get('estado')).toBe('true');
    expect(request.request.params.get('id_categoria')).toBe('1');
    request.flush(paged([product], 10));
  });

  it('loads complete detail and exposes related management sections', () => {
    page['viewDetail'](7);
    http.expectOne(`${api}/products/7`).flush({ success: true, data: product });
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent;
    expect(content).toContain('CAM-M-NEG');
    expect(content).toContain('Esenciales');
    expect(content).toContain('Textiles Bolivia');
    expect(fixture.nativeElement.querySelector('.image-card--primary')).toBeTruthy();
  });

  it('uploads a selected product image with principal state as multipart', () => {
    page['viewDetail'](7);
    http.expectOne(`${api}/products/7`).flush({ success: true, data: product });
    fixture.detectChanges();
    const file = new File(['image'], 'camisa.png', { type: 'image/png' });
    page['selectedImageFile'].set(file);
    page['imageForm'].setValue({ es_principal: true });

    page['submitImage']();

    const upload = http.expectOne(`${api}/products/7/images/upload`);
    expect(upload.request.method).toBe('POST');
    const formData = upload.request.body as FormData;
    const uploadedFile = formData.get('archivo') as File;
    expect(uploadedFile.name).toBe(file.name);
    expect(uploadedFile.type).toBe(file.type);
    expect(uploadedFile.size).toBe(file.size);
    expect(formData.get('es_principal')).toBe('true');
    upload.flush({ success: true, message: 'ok', data: product.imagenes[0] });
    http.expectOne(`${api}/products/7`).flush({ success: true, data: product });
    flushProductLists();
    expect(page['selectedImageFile']()).toBeNull();
  });

  it('registers a product using live option identifiers', () => {
    page['openProductModal']();
    page['productForm'].setValue({
      nombre: ' Nueva camisa ',
      descripcion: '',
      precio: '59.90',
      seccion: 'MUJER',
      id_categoria: 1,
      id_temporada: 1,
    });
    page['submitProduct']();
    const request = http.expectOne(`${api}/products`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      nombre: 'Nueva camisa',
      descripcion: null,
      precio: 59.9,
      seccion: 'MUJER',
      id_categoria: 1,
      id_temporada: 1,
    });
    request.flush({ success: true, message: 'ok', data: { ...product, nombre: 'Nueva camisa' } });
    flushProductLists();
    expect(page['productModalOpen']()).toBe(false);
  });

  it('registers the lazy route under the existing admin guards', async () => {
    const admin = routes.find((route) => route.path === 'admin')!;
    expect(admin.canActivate).toContain(adminGuard);
    expect(admin.canActivateChild).toContain(adminChildGuard);
    const route = admin.children!.find((item) => item.path === 'productos')!;
    expect(await (route.loadComponent! as () => Promise<unknown>)()).toBe(AdminProducts);
  });
});
