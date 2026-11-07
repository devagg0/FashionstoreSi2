import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CatalogColor, CatalogSize } from './catalog.service';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

export interface CatalogAvailabilityFilters {
  id_variante_producto?: number;
  id_sucursal?: number;
  id_ciudad?: number;
  id_talla?: number;
  id_color?: number;
}

export interface BranchAvailability {
  variante: {
    id_variante_producto: number;
    sku: string;
    talla: CatalogSize;
    color: CatalogColor;
    estado: boolean;
  };
  id_sucursal: number;
  nombre_sucursal: string;
  direccion: string;
  hora_apertura: string | null;
  hora_cierre: string | null;
  id_ciudad: number;
  nombre_ciudad: string;
  stock_actual: number;
  stock_reservado: number;
  stock_disponible: number;
}

export interface CatalogAvailabilityResponse {
  success: true;
  data: {
    producto: { id_producto: number; nombre: string; estado: boolean };
    disponibilidad: BranchAvailability[];
  };
  message: string;
}

@Injectable({ providedIn: 'root' })
export class CatalogAvailabilityService {
  private readonly http = inject(HttpClient);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly offlineService = inject(OfflineService);
  private readonly session = inject(SessionService);

  getProductAvailability(idProducto: number, filters: CatalogAvailabilityFilters = {}) {
    const isOffline =
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine);

    if (isOffline) {
      return from(this.buildLocalAvailability(idProducto, filters)).pipe(
        switchMap((result) => {
          if (!result) {
            return throwError(
              () =>
                new HttpErrorResponse({
                  error: {
                    message: 'Disponibilidad offline no disponible para este producto.',
                  },
                  status: 0,
                  statusText: 'Offline',
                }),
            );
          }
          return from([result]);
        }),
      );
    }

    let params = new HttpParams();
    for (const key of [
      'id_variante_producto',
      'id_sucursal',
      'id_ciudad',
      'id_talla',
      'id_color',
    ] as const) {
      const value = filters[key];
      if (value !== undefined) params = params.set(key, value);
    }
    return this.http
      .get<CatalogAvailabilityResponse>(
        `${environment.apiUrl}/api/catalog/products/${idProducto}/availability`,
        { params },
      )
      .pipe(
        catchError((error: HttpErrorResponse) => {
          if (error.status === 0 || (typeof navigator !== 'undefined' && !navigator.onLine)) {
            return from(this.buildLocalAvailability(idProducto, filters)).pipe(
              switchMap((result) => {
                if (!result) return throwError(() => error);
                return from([result]);
              }),
            );
          }
          return throwError(() => error);
        }),
      );
  }

  private async buildLocalAvailability(
    idProducto: number,
    filters: CatalogAvailabilityFilters,
  ): Promise<CatalogAvailabilityResponse | null> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) return null;

    const [productos, variantes, existencias, sucursales, pendingMap] = await Promise.all([
      this.offlineStorage.getCatalogProducts(empresaId, user.id_usuario),
      this.offlineStorage.getVariants(empresaId, user.id_usuario),
      this.offlineStorage.getInventory(empresaId, user.id_usuario),
      this.offlineStorage.getBranches(empresaId, user.id_usuario),
      this.offlineStorage.getPendingReservedQuantities(empresaId, user.id_usuario),
    ]);

    const prod = productos.find((p) => p.id_producto === idProducto);
    if (!prod) return null;

    const branchMap = new Map(sucursales.filter((b) => b.estado).map((b) => [b.id_sucursal, b]));
    const variantMap = new Map(
      variantes
        .filter((v) => v.id_producto === idProducto && v.estado)
        .map((v) => [v.id_variante_producto, v]),
    );

    const rows: BranchAvailability[] = [];
    for (const stock of existencias) {
      const variant = variantMap.get(stock.id_variante_producto);
      if (!variant) continue;
      if (
        filters.id_variante_producto &&
        variant.id_variante_producto !== filters.id_variante_producto
      ) {
        continue;
      }
      if (filters.id_talla && variant.id_talla !== filters.id_talla) continue;
      if (filters.id_color && variant.id_color !== filters.id_color) continue;
      if (filters.id_sucursal && stock.id_sucursal !== filters.id_sucursal) continue;

      const branch = branchMap.get(stock.id_sucursal);
      if (!branch) continue;
      if (filters.id_ciudad && branch.id_ciudad !== filters.id_ciudad) continue;

      const key = `${stock.id_sucursal}_${stock.id_variante_producto}`;
      const pendingReserved = pendingMap.get(key) || 0;
      const reservedEstimated = stock.stock_reservado + pendingReserved;
      const availableEstimated = Math.max(0, stock.stock_disponible - pendingReserved);

      rows.push({
        variante: {
          id_variante_producto: variant.id_variante_producto,
          sku: variant.sku,
          talla: { id_talla: variant.id_talla, nombre: variant.talla ?? String(variant.id_talla) },
          color: {
            id_color: variant.id_color,
            nombre: variant.color ?? String(variant.id_color),
            codigo_hex: variant.color_hex ?? null,
          },
          estado: variant.estado,
        },
        id_sucursal: branch.id_sucursal,
        nombre_sucursal: branch.nombre,
        direccion: branch.direccion,
        hora_apertura: branch.hora_apertura ?? null,
        hora_cierre: branch.hora_cierre ?? null,
        id_ciudad: branch.id_ciudad ?? 0,
        nombre_ciudad: branch.ciudad ?? '',
        stock_actual: stock.stock_actual,
        stock_reservado: reservedEstimated,
        stock_disponible: availableEstimated,
      });
    }

    return {
      success: true,
      data: {
        producto: { id_producto: prod.id_producto, nombre: prod.nombre, estado: prod.estado },
        disponibilidad: rows,
      },
      message: 'Disponibilidad cargada desde paquete offline local.',
    };
  }
}
