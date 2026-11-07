import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, from, Observable, switchMap, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

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
  fromOffline?: boolean;
}

export interface CatalogProductResponse {
  success: true;
  data: CatalogProductDetail;
  fromOffline?: boolean;
}

@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly http = inject(HttpClient);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly offlineService = inject(OfflineService);
  private readonly session = inject(SessionService);
  private readonly productsUrl = `${environment.apiUrl}/api/catalog/products`;

  listProducts(filters: CatalogFilters = {}): Observable<CatalogProductListResponse> {
    const isOffline =
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine);

    if (isOffline) {
      return from(this.loadLocalCatalogList(filters)).pipe(
        switchMap((localResp) => {
          if (!localResp) {
            return throwError(
              () =>
                new HttpErrorResponse({
                  error: {
                    message:
                      'No hay datos del catálogo disponibles sin conexión. Conéctate a internet para sincronizar.',
                  },
                  status: 0,
                  statusText: 'Offline',
                }),
            );
          }
          return from([localResp]);
        }),
      );
    }

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

    return this.http.get<CatalogProductListResponse>(this.productsUrl, { params }).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 0 || (typeof navigator !== 'undefined' && !navigator.onLine)) {
          return from(this.loadLocalCatalogList(filters)).pipe(
            switchMap((localResp) => {
              if (!localResp) return throwError(() => error);
              return from([localResp]);
            }),
          );
        }
        return throwError(() => error);
      }),
    );
  }

  getProduct(productId: number, branchId?: number): Observable<CatalogProductResponse> {
    const isOffline =
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine);

    if (isOffline) {
      return from(this.loadLocalProductDetail(productId, branchId)).pipe(
        switchMap((localDetail) => {
          if (!localDetail) {
            return throwError(
              () =>
                new HttpErrorResponse({
                  error: {
                    message: 'Prenda no encontrada en la base de datos local offline.',
                  },
                  status: 404,
                  statusText: 'Not Found',
                }),
            );
          }
          return from([localDetail]);
        }),
      );
    }

    let params = new HttpParams();
    if (branchId !== undefined) params = params.set('id_sucursal', branchId);
    return this.http
      .get<CatalogProductResponse>(`${this.productsUrl}/${productId}`, {
        params,
      })
      .pipe(
        catchError((error: HttpErrorResponse) => {
          if (error.status === 0 || (typeof navigator !== 'undefined' && !navigator.onLine)) {
            return from(this.loadLocalProductDetail(productId, branchId)).pipe(
              switchMap((localDetail) => {
                if (!localDetail) return throwError(() => error);
                return from([localDetail]);
              }),
            );
          }
          return throwError(() => error);
        }),
      );
  }

  private async loadLocalCatalogList(
    filters: CatalogFilters,
  ): Promise<CatalogProductListResponse | null> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return null;

    const [productos, categorias, tallas, colores, variantes, existencias, sucursales] =
      await Promise.all([
        this.offlineStorage.getCatalogProducts(empresaId, user.id_usuario),
        this.offlineStorage.getCategories(empresaId, user.id_usuario),
        this.offlineStorage.getSizes(empresaId, user.id_usuario),
        this.offlineStorage.getColors(empresaId, user.id_usuario),
        this.offlineStorage.getVariants(empresaId, user.id_usuario),
        this.offlineStorage.getInventory(empresaId, user.id_usuario),
        this.offlineStorage.getBranches(empresaId, user.id_usuario),
      ]);

    if (!productos.length) return null;

    const catMap = new Map(categorias.map((c) => [c.id_categoria, c.nombre]));
    const sizeMap = new Map(tallas.map((s) => [s.id_talla, s]));
    const colorMap = new Map(colores.map((c) => [c.id_color, c]));
    const branchMap = new Map(sucursales.map((b) => [b.id_sucursal, b]));

    const variantsByProduct = new Map<number, typeof variantes>();
    for (const v of variantes) {
      if (!v.estado) continue;
      const list = variantsByProduct.get(v.id_producto);
      if (list) {
        list.push(v);
      } else {
        variantsByProduct.set(v.id_producto, [v]);
      }
    }

    const stockByVariant = new Map<number, typeof existencias>();
    for (const s of existencias) {
      const list = stockByVariant.get(s.id_variante_producto);
      if (list) {
        list.push(s);
      } else {
        stockByVariant.set(s.id_variante_producto, [s]);
      }
    }

    const mapped: CatalogProduct[] = [];
    for (const prod of productos) {
      if (!prod.estado) continue;
      if (filters.seccion && prod.seccion !== filters.seccion) continue;
      if (filters.idCategoria && prod.id_categoria !== filters.idCategoria) continue;

      const hasPromo = Boolean(prod.tiene_promocion);
      if (filters.enPromocion && !hasPromo) continue;

      const prodVariants = variantsByProduct.get(prod.id_producto) || [];
      if (filters.idTalla && !prodVariants.some((v) => v.id_talla === filters.idTalla)) continue;
      if (filters.idColor && !prodVariants.some((v) => v.id_color === filters.idColor)) continue;

      if (filters.search) {
        const q = filters.search.trim().toLowerCase();
        const skuMatches = prodVariants.map((v) => v.sku).join(' ');
        const hay = `${prod.nombre} ${prod.descripcion ?? ''} ${prod.descripcion_corta ?? ''} ${prod.categoria ?? ''} ${skuMatches}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }

      const prodStocks: typeof existencias = [];
      for (const v of prodVariants) {
        const vStocks = stockByVariant.get(v.id_variante_producto);
        if (vStocks) {
          prodStocks.push(...vStocks);
        }
      }

      if (filters.idSucursal !== undefined) {
        const hasBranchStock = prodStocks.some(
          (s) => s.id_sucursal === filters.idSucursal && s.stock_disponible > 0,
        );
        if (!hasBranchStock) continue;
      }

      if (filters.idCiudad !== undefined) {
        const cityBranchIds = new Set(
          sucursales.filter((b) => b.id_ciudad === filters.idCiudad).map((b) => b.id_sucursal),
        );
        const hasCityStock = prodStocks.some(
          (s) => cityBranchIds.has(s.id_sucursal) && s.stock_disponible > 0,
        );
        if (!hasCityStock) continue;
      }

      const priceNum =
        prod.precio_final !== undefined && prod.precio_final !== null
          ? Number(prod.precio_final)
          : Number(prod.precio);

      if (filters.precioMin !== undefined && priceNum < filters.precioMin) continue;
      if (filters.precioMax !== undefined && priceNum > filters.precioMax) continue;

      const sizesOut = new Map<number, CatalogSize>();
      const colorsOut = new Map<number, CatalogColor>();

      if (prod.tallas_disponibles && prod.tallas_disponibles.length > 0) {
        for (const t of prod.tallas_disponibles) {
          sizesOut.set(t.id_talla, { id_talla: t.id_talla, nombre: t.nombre });
        }
      }
      if (prod.colores_disponibles && prod.colores_disponibles.length > 0) {
        for (const c of prod.colores_disponibles) {
          colorsOut.set(c.id_color, {
            id_color: c.id_color,
            nombre: c.nombre,
            codigo_hex: c.codigo_hex ?? null,
          });
        }
      }

      for (const v of prodVariants) {
        if (!sizesOut.has(v.id_talla)) {
          const sObj = sizeMap.get(v.id_talla);
          sizesOut.set(v.id_talla, {
            id_talla: v.id_talla,
            nombre: sObj?.nombre ?? v.talla ?? String(v.id_talla),
          });
        }
        if (!colorsOut.has(v.id_color)) {
          const cObj = colorMap.get(v.id_color);
          colorsOut.set(v.id_color, {
            id_color: v.id_color,
            nombre: cObj?.nombre ?? v.color ?? String(v.id_color),
            codigo_hex: cObj?.codigo_hex ?? v.color_hex ?? null,
          });
        }
      }

      let disponibilidadSucursal: CatalogProductAvailability | null = null;
      if (filters.idSucursal !== undefined) {
        const b = branchMap.get(filters.idSucursal);
        if (b) {
          const qty = prodStocks
            .filter((s) => s.id_sucursal === filters.idSucursal)
            .reduce((acc, s) => acc + s.stock_disponible, 0);
          disponibilidadSucursal = {
            id_sucursal: b.id_sucursal,
            sucursal: b.nombre,
            estado: qty > 0 ? 'DISPONIBLE' : 'AGOTADO',
            cantidad_disponible: qty,
          };
        }
      }

      const baseNum =
        prod.precio_base !== undefined && prod.precio_base !== null
          ? Number(prod.precio_base)
          : priceNum;
      const baseStr = baseNum.toFixed(2);
      const finalStr = priceNum.toFixed(2);

      mapped.push({
        id_producto: prod.id_producto,
        nombre: prod.nombre,
        descripcion_corta: prod.descripcion_corta ?? prod.descripcion ?? null,
        seccion: (['HOMBRE', 'MUJER', 'UNISEX'].includes(prod.seccion)
          ? prod.seccion
          : 'UNISEX') as CatalogSection,
        id_categoria: prod.id_categoria,
        categoria: prod.categoria ?? catMap.get(prod.id_categoria) ?? 'General',
        precio_base: baseStr,
        precio_final: finalStr,
        tiene_promocion: hasPromo,
        promocion_destacada: hasPromo
          ? {
              id_promocion: 1,
              nombre: 'Promoción especial',
              codigo: null,
              descripcion: null,
              tipo_descuento: 'MONTO_FIJO',
              valor: '0',
              porcentaje_descuento: null,
              monto_descuento: baseNum > priceNum ? (baseNum - priceNum).toFixed(2) : '0.00',
              precio_resultante: finalStr,
              fecha_inicio: '',
              fecha_fin: '',
              acumulable: false,
            }
          : null,
        porcentaje_descuento: null,
        monto_descuento: hasPromo && baseNum > priceNum ? (baseNum - priceNum).toFixed(2) : null,
        imagen_principal: prod.imagen_principal ?? null,
        colores_disponibles: [...colorsOut.values()],
        tallas_disponibles: [...sizesOut.values()],
        disponibilidad_sucursal: disponibilidadSucursal,
      });
    }

    const sort = filters.sort ?? 'recientes';
    if (sort === 'precio_asc') {
      mapped.sort((a, b) => Number(a.precio_final) - Number(b.precio_final));
    } else if (sort === 'precio_desc') {
      mapped.sort((a, b) => Number(b.precio_final) - Number(a.precio_final));
    } else if (sort === 'nombre') {
      mapped.sort((a, b) => a.nombre.localeCompare(b.nombre));
    } else {
      mapped.sort((a, b) => b.id_producto - a.id_producto);
    }

    const page = filters.page ?? 1;
    const pageSize = filters.pageSize ?? 12;
    const total = mapped.length;
    const totalPages = total > 0 ? Math.ceil(total / pageSize) : 0;
    const start = (page - 1) * pageSize;

    return {
      success: true,
      fromOffline: true,
      data: mapped.slice(start, start + pageSize),
      pagination: {
        page,
        page_size: pageSize,
        total,
        total_pages: totalPages,
      },
    };
  }

  private async loadLocalProductDetail(
    productId: number,
    branchId?: number,
  ): Promise<CatalogProductResponse | null> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return null;

    const detail = await this.offlineStorage.getProductDetail(
      empresaId,
      user.id_usuario,
      productId,
    );
    if (!detail) return null;

    const prod = detail.producto;
    const priceNum =
      prod.precio_final !== undefined && prod.precio_final !== null
        ? Number(prod.precio_final)
        : Number(prod.precio);
    const baseNum =
      prod.precio_base !== undefined && prod.precio_base !== null
        ? Number(prod.precio_base)
        : priceNum;
    const baseStr = baseNum.toFixed(2);
    const finalStr = priceNum.toFixed(2);
    const hasPromo = Boolean(prod.tiene_promocion);

    const sizesMap = new Map<number, CatalogSize>();
    const colorsMap = new Map<number, CatalogColor>();

    if (prod.tallas_disponibles && prod.tallas_disponibles.length > 0) {
      for (const t of prod.tallas_disponibles) {
        sizesMap.set(t.id_talla, { id_talla: t.id_talla, nombre: t.nombre });
      }
    }
    if (prod.colores_disponibles && prod.colores_disponibles.length > 0) {
      for (const c of prod.colores_disponibles) {
        colorsMap.set(c.id_color, {
          id_color: c.id_color,
          nombre: c.nombre,
          codigo_hex: c.codigo_hex ?? null,
        });
      }
    }

    const variantes: CatalogVariant[] = detail.variantes.map((v, idx) => {
      const sizeId = v.id_talla ?? idx + 1;
      const colorId = v.id_color ?? idx + 1;
      const sizeObj: CatalogSize = { id_talla: sizeId, nombre: v.talla };
      const colorObj: CatalogColor = {
        id_color: colorId,
        nombre: v.color,
        codigo_hex: v.color_hex ?? null,
      };
      if (!sizesMap.has(sizeId)) sizesMap.set(sizeId, sizeObj);
      if (!colorsMap.has(colorId)) colorsMap.set(colorId, colorObj);

      let disp: CatalogVariantAvailability | null = null;
      if (branchId !== undefined) {
        const bStock = v.disponibilidadPorSucursal.find((b) => b.id_sucursal === branchId);
        if (bStock) {
          disp = {
            id_sucursal: bStock.id_sucursal,
            estado: bStock.stock_disponible > 0 ? 'DISPONIBLE' : 'AGOTADO',
            cantidad_disponible: bStock.stock_disponible,
          };
        }
      }

      return {
        id_variante_producto: v.id_variante_producto,
        sku: v.sku,
        talla: sizeObj,
        color: colorObj,
        disponibilidad_sucursal: disp,
      };
    });

    const galeria: CatalogImage[] =
      prod.galeria && prod.galeria.length > 0
        ? prod.galeria.map((g, i) => ({
            id_imagen_producto: g.id_imagen_producto ?? i + 1,
            url_imagen: g.url_imagen,
            es_principal: Boolean(g.es_principal),
          }))
        : (prod.imagenes ?? []).map((url, i) => ({
            id_imagen_producto: i + 1,
            url_imagen: url,
            es_principal: url === prod.imagen_principal || i === 0,
          }));

    if (!galeria.length && prod.imagen_principal) {
      galeria.push({
        id_imagen_producto: 1,
        url_imagen: prod.imagen_principal,
        es_principal: true,
      });
    }

    const colecciones: CatalogCollection[] = (prod.colecciones ?? []).map((c) => ({
      id_coleccion: c.id_coleccion,
      nombre: c.nombre,
    }));

    return {
      success: true,
      fromOffline: true,
      data: {
        id_producto: prod.id_producto,
        nombre: prod.nombre,
        descripcion: prod.descripcion ?? null,
        seccion: (['HOMBRE', 'MUJER', 'UNISEX'].includes(prod.seccion)
          ? prod.seccion
          : 'UNISEX') as CatalogSection,
        id_categoria: prod.id_categoria,
        categoria: detail.categoriaNombre,
        id_temporada: prod.id_temporada ?? null,
        temporada: prod.temporada ?? null,
        precio_base: baseStr,
        precio_final: finalStr,
        tiene_promocion: hasPromo,
        promociones_vigentes: [],
        promocion_destacada: hasPromo
          ? {
              id_promocion: 1,
              nombre: 'Promoción especial',
              codigo: null,
              descripcion: null,
              tipo_descuento: 'MONTO_FIJO',
              valor: '0',
              porcentaje_descuento: null,
              monto_descuento: baseNum > priceNum ? (baseNum - priceNum).toFixed(2) : '0.00',
              precio_resultante: finalStr,
              fecha_inicio: '',
              fecha_fin: '',
              acumulable: false,
            }
          : null,
        porcentaje_descuento: null,
        monto_descuento: hasPromo && baseNum > priceNum ? (baseNum - priceNum).toFixed(2) : null,
        imagen_principal: prod.imagen_principal ?? null,
        galeria,
        variantes,
        tallas: [...sizesMap.values()],
        colores: [...colorsMap.values()],
        colecciones,
      },
    };
  }
}
