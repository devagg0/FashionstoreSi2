import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { CatalogColor, CatalogSize } from './catalog.service';

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

  getProductAvailability(idProducto: number, filters: CatalogAvailabilityFilters = {}) {
    let params = new HttpParams();
    for (const key of ['id_variante_producto', 'id_sucursal', 'id_ciudad', 'id_talla', 'id_color'] as const) {
      const value = filters[key];
      if (value !== undefined) params = params.set(key, value);
    }
    return this.http.get<CatalogAvailabilityResponse>(
      `${environment.apiUrl}/api/catalog/products/${idProducto}/availability`, { params },
    );
  }
}
