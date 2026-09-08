import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type ProductSection = 'HOMBRE' | 'MUJER' | 'UNISEX';

export interface AdminProduct {
  id_producto: number;
  id_categoria: number;
  categoria: string;
  id_temporada: number | null;
  temporada: string | null;
  nombre: string;
  seccion: ProductSection;
  descripcion: string | null;
  precio: string;
  estado: boolean;
  imagen_principal: string | null;
  total_variantes: number;
  created_at: string;
  updated_at: string;
}

export interface AdminProductVariant {
  id_variante_producto: number;
  id_talla: number;
  talla: string;
  id_color: number;
  color: string;
  sku: string;
  estado: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminProductCollection {
  id_producto_coleccion: number;
  id_coleccion: number;
  coleccion: string;
  estado_coleccion: boolean;
}

export interface AdminProductSupplier {
  id_producto_proveedor: number;
  id_proveedor: number;
  proveedor: string;
  costo_referencia: string | null;
  estado: boolean;
  estado_proveedor: boolean;
}

export interface AdminProductImage {
  id_imagen_producto: number;
  url_imagen: string;
  es_principal: boolean;
  created_at: string;
}

export interface AdminProductDetail extends AdminProduct {
  variantes: AdminProductVariant[];
  colecciones: AdminProductCollection[];
  proveedores: AdminProductSupplier[];
  imagenes: AdminProductImage[];
}

export interface AdminProductPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminProductFilters {
  search?: string;
  estado?: boolean;
  idCategoria?: number;
  page?: number;
  pageSize?: number;
}

export interface AdminProductFields {
  id_categoria: number;
  id_temporada: number | null;
  nombre: string;
  seccion: ProductSection;
  descripcion: string | null;
  precio: number;
}

export interface AdminProductVariantFields {
  id_talla: number;
  id_color: number;
  sku: string;
}

export interface AdminProductSupplierFields {
  id_proveedor: number;
  costo_referencia: number | null;
}

export interface AdminProductListResponse {
  success: true;
  data: AdminProduct[];
  pagination: AdminProductPagination;
}

export interface AdminProductResponse {
  success: true;
  data: AdminProductDetail;
}

export interface AdminProductMutationResponse extends AdminProductResponse {
  message: string;
}

export interface AdminProductVariantResponse {
  success: true;
  message: string;
  data: AdminProductVariant;
}

export interface AdminProductCollectionsResponse {
  success: true;
  message: string;
  data: AdminProductCollection[];
}

export interface AdminProductSuppliersResponse {
  success: true;
  message: string;
  data: AdminProductSupplier[];
}

export interface AdminProductSupplierResponse {
  success: true;
  message: string;
  data: AdminProductSupplier;
}

export interface AdminProductImageResponse {
  success: true;
  message: string;
  data: AdminProductImage;
}

@Injectable({ providedIn: 'root' })
export class AdminProductsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly productsUrl = `${environment.apiUrl}/api/admin/products`;

  listProducts(filters: AdminProductFilters = {}): Observable<AdminProductListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);

    const search = filters.search?.trim();
    if (search) params = params.set('search', search);
    if (filters.estado !== undefined) params = params.set('estado', filters.estado);
    if (filters.idCategoria !== undefined) {
      params = params.set('id_categoria', filters.idCategoria);
    }

    return this.http.get<AdminProductListResponse>(this.productsUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getProduct(productId: number): Observable<AdminProductResponse> {
    return this.http.get<AdminProductResponse>(`${this.productsUrl}/${productId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createProduct(fields: AdminProductFields): Observable<AdminProductMutationResponse> {
    return this.http.post<AdminProductMutationResponse>(this.productsUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateProduct(
    productId: number,
    fields: Partial<AdminProductFields>,
  ): Observable<AdminProductMutationResponse> {
    return this.http.patch<AdminProductMutationResponse>(
      `${this.productsUrl}/${productId}`,
      fields,
      { headers: this.authenticatedHeaders() },
    );
  }

  updateStatus(productId: number, estado: boolean): Observable<AdminProductMutationResponse> {
    return this.http.patch<AdminProductMutationResponse>(
      `${this.productsUrl}/${productId}/status`,
      { estado },
      { headers: this.authenticatedHeaders() },
    );
  }

  createVariant(
    productId: number,
    fields: AdminProductVariantFields,
  ): Observable<AdminProductVariantResponse> {
    return this.http.post<AdminProductVariantResponse>(
      `${this.productsUrl}/${productId}/variants`,
      fields,
      { headers: this.authenticatedHeaders() },
    );
  }

  updateVariant(
    productId: number,
    variantId: number,
    fields: Partial<AdminProductVariantFields>,
  ): Observable<AdminProductVariantResponse> {
    return this.http.patch<AdminProductVariantResponse>(
      `${this.productsUrl}/${productId}/variants/${variantId}`,
      fields,
      { headers: this.authenticatedHeaders() },
    );
  }

  updateVariantStatus(
    productId: number,
    variantId: number,
    estado: boolean,
  ): Observable<AdminProductVariantResponse> {
    return this.http.patch<AdminProductVariantResponse>(
      `${this.productsUrl}/${productId}/variants/${variantId}/status`,
      { estado },
      { headers: this.authenticatedHeaders() },
    );
  }

  addCollections(
    productId: number,
    collectionIds: number[],
  ): Observable<AdminProductCollectionsResponse> {
    return this.http.post<AdminProductCollectionsResponse>(
      `${this.productsUrl}/${productId}/collections`,
      { id_colecciones: collectionIds },
      { headers: this.authenticatedHeaders() },
    );
  }

  addSuppliers(
    productId: number,
    suppliers: AdminProductSupplierFields[],
  ): Observable<AdminProductSuppliersResponse> {
    return this.http.post<AdminProductSuppliersResponse>(
      `${this.productsUrl}/${productId}/suppliers`,
      { proveedores: suppliers },
      { headers: this.authenticatedHeaders() },
    );
  }

  updateSupplierCost(
    productId: number,
    associationId: number,
    referenceCost: number | null,
  ): Observable<AdminProductSupplierResponse> {
    return this.http.patch<AdminProductSupplierResponse>(
      `${this.productsUrl}/${productId}/suppliers/${associationId}`,
      { costo_referencia: referenceCost },
      { headers: this.authenticatedHeaders() },
    );
  }

  updateSupplierStatus(
    productId: number,
    associationId: number,
    estado: boolean,
  ): Observable<AdminProductSupplierResponse> {
    return this.http.patch<AdminProductSupplierResponse>(
      `${this.productsUrl}/${productId}/suppliers/${associationId}/status`,
      { estado },
      { headers: this.authenticatedHeaders() },
    );
  }

  uploadImage(
    productId: number,
    file: File,
    isPrimary: boolean,
  ): Observable<AdminProductImageResponse> {
    const formData = new FormData();
    formData.append('archivo', file, file.name);
    formData.append('es_principal', String(isPrimary));
    return this.http.post<AdminProductImageResponse>(
      `${this.productsUrl}/${productId}/images/upload`,
      formData,
      { headers: this.authenticatedHeaders() },
    );
  }

  updateImage(
    productId: number,
    imageId: number,
    fields: { es_principal: boolean },
  ): Observable<AdminProductImageResponse> {
    return this.http.patch<AdminProductImageResponse>(
      `${this.productsUrl}/${productId}/images/${imageId}`,
      fields,
      { headers: this.authenticatedHeaders() },
    );
  }

  private authenticatedHeaders(): HttpHeaders {
    const accessToken = this.sessionService.getAccessToken();
    return accessToken
      ? new HttpHeaders({ Authorization: `Bearer ${accessToken}` })
      : new HttpHeaders();
  }
}
