import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminSize {
  id_talla: number;
  nombre: string;
  descripcion: string | null;
  created_at: string;
  updated_at: string;
  estado: boolean;
}

export interface AdminSizePagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminSizeFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminSizeListResponse {
  success: true;
  data: AdminSize[];
  pagination: AdminSizePagination;
}

export interface AdminSizeResponse {
  success: true;
  data: AdminSize;
}

export interface AdminSizeMutationResponse extends AdminSizeResponse {
  message: string;
}

export interface AdminSizeFields {
  nombre: string;
  descripcion?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminSizesService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly sizesUrl = `${environment.apiUrl}/api/admin/sizes`;

  listSizes(filters: AdminSizeFilters = {}): Observable<AdminSizeListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);

    const search = filters.search?.trim();
    if (search) {
      params = params.set('search', search);
    }
    if (filters.estado !== undefined) {
      params = params.set('estado', filters.estado);
    }

    return this.http.get<AdminSizeListResponse>(this.sizesUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getSize(sizeId: number): Observable<AdminSizeResponse> {
    return this.http.get<AdminSizeResponse>(`${this.sizesUrl}/${sizeId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createSize(fields: AdminSizeFields): Observable<AdminSizeMutationResponse> {
    return this.http.post<AdminSizeMutationResponse>(this.sizesUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateSize(
    sizeId: number,
    fields: Partial<AdminSizeFields>,
  ): Observable<AdminSizeMutationResponse> {
    return this.http.patch<AdminSizeMutationResponse>(`${this.sizesUrl}/${sizeId}`, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateStatus(sizeId: number, estado: boolean): Observable<AdminSizeMutationResponse> {
    return this.http.patch<AdminSizeMutationResponse>(
      `${this.sizesUrl}/${sizeId}/status`,
      { estado },
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
