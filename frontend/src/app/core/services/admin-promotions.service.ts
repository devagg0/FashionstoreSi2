import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export type PromotionDiscountType = 'PORCENTAJE' | 'MONTO_FIJO';
export type PromotionValidity = 'PROGRAMADA' | 'VIGENTE' | 'EXPIRADA';

export interface AdminPromotionProduct {
  id_promocion_producto: number;
  id_producto: number;
  nombre: string;
  categoria?: string;
  seccion: string;
  precio: string;
  estado: boolean;
}

export interface AdminPromotion {
  id_promocion: number;
  nombre: string;
  codigo: string | null;
  descripcion: string | null;
  tipo_descuento: PromotionDiscountType;
  valor: string;
  fecha_inicio: string;
  fecha_fin: string;
  acumulable: boolean;
  estado: boolean;
  vigencia: PromotionValidity;
  total_productos: number;
  created_at: string;
  updated_at: string;
}

export interface AdminPromotionDetail extends AdminPromotion {
  productos: AdminPromotionProduct[];
}

export interface AdminPromotionPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminPromotionFilters {
  search?: string;
  estado?: boolean;
  vigencia?: PromotionValidity;
  page?: number;
  pageSize?: number;
}

export interface AdminPromotionFields {
  nombre: string;
  codigo: string | null;
  descripcion: string | null;
  tipo_descuento: PromotionDiscountType;
  valor: number;
  fecha_inicio: string;
  fecha_fin: string;
  acumulable: boolean;
}

export interface AdminPromotionListResponse {
  success: true;
  data: AdminPromotion[];
  pagination: AdminPromotionPagination;
}

export interface AdminPromotionResponse {
  success: true;
  data: AdminPromotionDetail;
}

export interface AdminPromotionMutationResponse extends AdminPromotionResponse {
  message: string;
}

export interface AdminPromotionProductsResponse {
  success: true;
  message?: string;
  data: AdminPromotionProduct[];
}

@Injectable({ providedIn: 'root' })
export class AdminPromotionsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly promotionsUrl = `${environment.apiUrl}/api/admin/promotions`;

  listPromotions(
    filters: AdminPromotionFilters = {},
  ): Observable<AdminPromotionListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);

    const search = filters.search?.trim();
    if (search) params = params.set('search', search);
    if (filters.estado !== undefined) params = params.set('estado', filters.estado);
    if (filters.vigencia !== undefined) params = params.set('vigencia', filters.vigencia);

    return this.http.get<AdminPromotionListResponse>(this.promotionsUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getPromotion(promotionId: number): Observable<AdminPromotionResponse> {
    return this.http.get<AdminPromotionResponse>(`${this.promotionsUrl}/${promotionId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createPromotion(
    fields: AdminPromotionFields,
  ): Observable<AdminPromotionMutationResponse> {
    return this.http.post<AdminPromotionMutationResponse>(this.promotionsUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updatePromotion(
    promotionId: number,
    fields: Partial<AdminPromotionFields>,
  ): Observable<AdminPromotionMutationResponse> {
    return this.http.patch<AdminPromotionMutationResponse>(
      `${this.promotionsUrl}/${promotionId}`,
      fields,
      { headers: this.authenticatedHeaders() },
    );
  }

  updateStatus(
    promotionId: number,
    estado: boolean,
  ): Observable<AdminPromotionMutationResponse> {
    return this.http.patch<AdminPromotionMutationResponse>(
      `${this.promotionsUrl}/${promotionId}/status`,
      { estado },
      { headers: this.authenticatedHeaders() },
    );
  }

  listProducts(promotionId: number): Observable<AdminPromotionProductsResponse> {
    return this.http.get<AdminPromotionProductsResponse>(
      `${this.promotionsUrl}/${promotionId}/products`,
      { headers: this.authenticatedHeaders() },
    );
  }

  addProducts(
    promotionId: number,
    productIds: number[],
  ): Observable<AdminPromotionProductsResponse> {
    return this.http.post<AdminPromotionProductsResponse>(
      `${this.promotionsUrl}/${promotionId}/products`,
      { id_productos: productIds },
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
