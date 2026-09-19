import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CatalogSection, DiscountType } from './catalog.service';
import { SessionService } from './session.service';

export type RecommendationOrigin = 'PERSONALIZADO' | 'FALLBACK';

export interface RecommendationPromotion {
  id_promocion: number;
  nombre: string;
  codigo: string | null;
  descripcion: string | null;
  tipo_descuento: DiscountType;
  valor: string;
  fecha_inicio: string;
  fecha_fin: string;
  acumulable: boolean;
}

export interface RecommendationVariant {
  id_variante_producto: number;
  sku: string;
  id_talla: number;
  talla: string;
  id_color: number;
  color: string;
  codigo_hex: string | null;
  stock_disponible: number;
}

export interface RecommendationItem {
  id_producto: number;
  nombre: string;
  descripcion_corta: string | null;
  seccion: CatalogSection;
  id_categoria: number;
  categoria: string;
  id_temporada: number | null;
  temporada: string | null;
  precio_base: string;
  precio_final: string;
  tiene_promocion: boolean;
  promocion: RecommendationPromotion | null;
  monto_descuento: string | null;
  porcentaje_descuento: string | null;
  imagen_principal: string | null;
  variante_sugerida: RecommendationVariant | null;
  /** Interno de CU26: nunca se muestra al cliente. */
  score: number;
  motivo: string;
  ya_comprado: boolean;
}

export interface RecommendationListResponse {
  success: true;
  data: RecommendationItem[];
  origen: RecommendationOrigin;
  message: string;
}

export interface RecommendationFilters {
  limit?: number;
  idSucursal?: number;
  idCiudad?: number;
}

export function recommendationErrorMessage(error: HttpErrorResponse): string {
  if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
  if (error.status === 0) {
    return 'No pudimos conectar con FashionStore. Revisa tu conexión.';
  }
  if (error.status >= 500) {
    return 'No fue posible generar tus recomendaciones. Inténtalo nuevamente.';
  }
  if ([403, 404, 422].includes(error.status) && typeof error.error?.message === 'string') {
    return error.error.message;
  }
  const messages: Record<number, string> = {
    403: 'Las recomendaciones están disponibles para cuentas de cliente.',
    404: 'No encontramos la sucursal o ciudad seleccionada.',
    422: 'La sucursal o ciudad seleccionada no está disponible.',
  };
  return messages[error.status] ?? 'No fue posible generar tus recomendaciones.';
}

@Injectable({ providedIn: 'root' })
export class ClientRecommendationsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/client/recommendations`;

  list(filters: RecommendationFilters = {}): Observable<RecommendationListResponse> {
    let params = new HttpParams().set('limit', filters.limit ?? 12);
    if (filters.idSucursal !== undefined) {
      params = params.set('id_sucursal', filters.idSucursal);
    }
    if (filters.idCiudad !== undefined) params = params.set('id_ciudad', filters.idCiudad);
    return this.http.get<RecommendationListResponse>(this.url, {
      params,
      headers: this.headers(),
    });
  }

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
}
