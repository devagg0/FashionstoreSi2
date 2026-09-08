import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export type CatalogSection = 'HOMBRE' | 'MUJER' | 'UNISEX';
export type CatalogSort = 'recientes' | 'precio_asc' | 'precio_desc' | 'nombre';
export type AvailabilityStatus = 'DISPONIBLE' | 'AGOTADO';
export type DiscountType = 'PORCENTAJE' | 'MONTO_FIJO';

export interface CatalogColor {
  id_color: number;
  nombre: string;
  codigo_hex: string | null;
}

export interface CatalogSize {
  id_talla: number;
  nombre: string;
}

export interface CatalogCollection {
  id_coleccion: number;
  nombre: string;
}

export interface CatalogImage {
  id_imagen_producto: number;
  url_imagen: string;
  es_principal: boolean;
}

export interface CatalogPromotion {
  id_promocion: number;
  nombre: string;
  codigo: string | null;
  descripcion: string | null;
  tipo_descuento: DiscountType;
  valor: string;
  porcentaje_descuento: string | null;
  monto_descuento: string;
  precio_resultante: string;
  fecha_inicio: string;
  fecha_fin: string;
  acumulable: boolean;
}

export interface CatalogProductAvailability {
  id_sucursal: number;
  sucursal: string;
  estado: AvailabilityStatus;
  cantidad_disponible: number;
}

export interface CatalogVariantAvailability {
  id_sucursal: number;
  estado: AvailabilityStatus;
  cantidad_disponible: number;
}

export interface CatalogProduct {
  id_producto: number;
  nombre: string;
  descripcion_corta: string | null;
  seccion: CatalogSection;
  id_categoria: number;
  categoria: string;
  precio_base: string;
  precio_final: string;
  tiene_promocion: boolean;
  promocion_destacada: CatalogPromotion | null;
  porcentaje_descuento: string | null;
  monto_descuento: string | null;
  imagen_principal: string | null;
  colores_disponibles: CatalogColor[];
  tallas_disponibles: CatalogSize[];
  disponibilidad_sucursal: CatalogProductAvailability | null;
}

export interface CatalogVariant {
  id_variante_producto: number;
  sku: string;
  talla: CatalogSize;
  color: CatalogColor;
  disponibilidad_sucursal: CatalogVariantAvailability | null;
}

export interface CatalogProductDetail {
  id_producto: number;
  nombre: string;
  descripcion: string | null;
  seccion: CatalogSection;
  id_categoria: number;
  categoria: string;
  id_temporada: number | null;
  temporada: string | null;
  precio_base: string;
  precio_final: string;
  tiene_promocion: boolean;
  promociones_vigentes: CatalogPromotion[];
  promocion_destacada: CatalogPromotion | null;
  porcentaje_descuento: string | null;
  monto_descuento: string | null;
  imagen_principal: string | null;
  galeria: CatalogImage[];
  variantes: CatalogVariant[];
  tallas: CatalogSize[];
  colores: CatalogColor[];
  colecciones: CatalogCollection[];
}

export interface CatalogPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CatalogFilters {
  search?: string;
  seccion?: CatalogSection;
  idCategoria?: number;
  idTalla?: number;
  idColor?: number;
  precioMin?: number;
  precioMax?: number;
  enPromocion?: boolean;
  idSucursal?: number;
  idCiudad?: number;
  sort?: CatalogSort;
  page?: number;
  pageSize?: number;
}

export interface CatalogProductListResponse {
  success: true;
  data: CatalogProduct[];
  pagination: CatalogPagination;
}

export interface CatalogProductResponse {
  success: true;
  data: CatalogProductDetail;
}

@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly http = inject(HttpClient);
  private readonly productsUrl = `${environment.apiUrl}/api/catalog/products`;

  listProducts(filters: CatalogFilters = {}): Observable<CatalogProductListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 12)
      .set('sort', filters.sort ?? 'recientes');

    const search = filters.search?.trim();
    if (search) params = params.set('search', search);
    if (filters.seccion) params = params.set('seccion', filters.seccion);
    if (filters.idCategoria !== undefined) {
      params = params.set('id_categoria', filters.idCategoria);
    }
    if (filters.idTalla !== undefined) params = params.set('id_talla', filters.idTalla);
    if (filters.idColor !== undefined) params = params.set('id_color', filters.idColor);
    if (filters.precioMin !== undefined) params = params.set('precio_min', filters.precioMin);
    if (filters.precioMax !== undefined) params = params.set('precio_max', filters.precioMax);
    if (filters.enPromocion !== undefined) {
      params = params.set('en_promocion', filters.enPromocion);
    }
    if (filters.idSucursal !== undefined) {
      params = params.set('id_sucursal', filters.idSucursal);
    }
    if (filters.idCiudad !== undefined) params = params.set('id_ciudad', filters.idCiudad);

    return this.http.get<CatalogProductListResponse>(this.productsUrl, { params });
  }

  getProduct(productId: number, branchId?: number): Observable<CatalogProductResponse> {
    let params = new HttpParams();
    if (branchId !== undefined) params = params.set('id_sucursal', branchId);
    return this.http.get<CatalogProductResponse>(`${this.productsUrl}/${productId}`, {
      params,
    });
  }
}
