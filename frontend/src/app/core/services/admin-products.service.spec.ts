import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { AdminProductsService } from './admin-products.service';

const url = `${environment.apiUrl}/api/admin/products`;

describe('AdminProductsService CU10', () => {
  let service: AdminProductsService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.setItem('fashionstore_access_token', 'admin-token');
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AdminProductsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('lists with search, state, category, pagination and Bearer token', () => {
    service
      .listProducts({ search: ' camisa ', estado: false, idCategoria: 4, page: 2, pageSize: 10 })
      .subscribe();
    const request = http.expectOne((item) => item.url === url);
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.get('Authorization')).toBe('Bearer admin-token');
    expect(request.request.params.get('search')).toBe('camisa');
    expect(request.request.params.get('estado')).toBe('false');
    expect(request.request.params.get('id_categoria')).toBe('4');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('10');
    request.flush({
      success: true,
      data: [],
      pagination: { page: 2, page_size: 10, total: 0, total_pages: 0 },
    });
  });

  it('creates, reads, edits and changes product status', () => {
    const fields = {
      id_categoria: 1,
      id_temporada: null,
      nombre: 'Camisa',
      seccion: 'HOMBRE' as const,
      descripcion: null,
      precio: 49.9,
    };
    service.createProduct(fields).subscribe();
    let request = http.expectOne(url);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(fields);
    request.flush({ success: true, message: 'ok', data: {} });

    service.getProduct(7).subscribe();
    request = http.expectOne(`${url}/7`);
    expect(request.request.method).toBe('GET');
    request.flush({ success: true, data: {} });

    service.updateProduct(7, { precio: 55 }).subscribe();
    request = http.expectOne(`${url}/7`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ precio: 55 });
    request.flush({ success: true, message: 'ok', data: {} });

    service.updateStatus(7, false).subscribe();
    request = http.expectOne(`${url}/7/status`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ estado: false });
    request.flush({ success: true, message: 'ok', data: {} });
  });

  it('uses the nested variant endpoints without deletion', () => {
    service.createVariant(7, { id_talla: 2, id_color: 3, sku: 'CAM-M-NEG' }).subscribe();
    let request = http.expectOne(`${url}/7/variants`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ id_talla: 2, id_color: 3, sku: 'CAM-M-NEG' });
    request.flush({ success: true, message: 'ok', data: {} });

    service.updateVariant(7, 9, { sku: 'CAM-M-BLA' }).subscribe();
    request = http.expectOne(`${url}/7/variants/9`);
    expect(request.request.method).toBe('PATCH');
    request.flush({ success: true, message: 'ok', data: {} });

    service.updateVariantStatus(7, 9, false).subscribe();
    request = http.expectOne(`${url}/7/variants/9/status`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ estado: false });
    request.flush({ success: true, message: 'ok', data: {} });
  });

  it('uses collection and supplier association endpoints', () => {
    service.addCollections(7, [2, 3]).subscribe();
    let request = http.expectOne(`${url}/7/collections`);
    expect(request.request.body).toEqual({ id_colecciones: [2, 3] });
    request.flush({ success: true, message: 'ok', data: [] });

    service.addSuppliers(7, [{ id_proveedor: 4, costo_referencia: 20 }]).subscribe();
    request = http.expectOne(`${url}/7/suppliers`);
    expect(request.request.body).toEqual({
      proveedores: [{ id_proveedor: 4, costo_referencia: 20 }],
    });
    request.flush({ success: true, message: 'ok', data: [] });

    service.updateSupplierCost(7, 8, null).subscribe();
    request = http.expectOne(`${url}/7/suppliers/8`);
    expect(request.request.body).toEqual({ costo_referencia: null });
    request.flush({ success: true, message: 'ok', data: {} });

    service.updateSupplierStatus(7, 8, false).subscribe();
    request = http.expectOne(`${url}/7/suppliers/8/status`);
    expect(request.request.body).toEqual({ estado: false });
    request.flush({ success: true, message: 'ok', data: {} });
  });

  it('uploads images as multipart and updates their principal state', () => {
    const file = new File(['image'], 'camisa.webp', { type: 'image/webp' });
    service.uploadImage(7, file, true).subscribe();
    let request = http.expectOne(`${url}/7/images/upload`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body instanceof FormData).toBe(true);
    const formData = request.request.body as FormData;
    const uploadedFile = formData.get('archivo') as File;
    expect(uploadedFile.name).toBe(file.name);
    expect(uploadedFile.type).toBe(file.type);
    expect(uploadedFile.size).toBe(file.size);
    expect(formData.get('es_principal')).toBe('true');
    expect(request.request.headers.has('Content-Type')).toBe(false);
    request.flush({ success: true, message: 'ok', data: {} });

    service.updateImage(7, 5, { es_principal: true }).subscribe();
    request = http.expectOne(`${url}/7/images/5`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ es_principal: true });
    request.flush({ success: true, message: 'ok', data: {} });
  });
});
