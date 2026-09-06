import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminColor {
  id_color: number;
  nombre: string;
  codigo_hex: string | null;
  created_at: string;
  updated_at: string;
  estado: boolean;
}

export interface AdminColorPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminColorFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminColorListResponse {
  success: true;
  data: AdminColor[];
  pagination: AdminColorPagination;
}

export interface AdminColorResponse {
  success: true;
  data: AdminColor;
}

export interface AdminColorMutationResponse extends AdminColorResponse {
  message: string;
}

export interface AdminColorFields {
  nombre: string;
  codigo_hex?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminColorsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly colorsUrl = `${environment.apiUrl}/api/admin/colors`;

  listColors(filters: AdminColorFilters = {}): Observable<AdminColorListResponse> {
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

    return this.http.get<AdminColorListResponse>(this.colorsUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getColor(colorId: number): Observable<AdminColorResponse> {
    return this.http.get<AdminColorResponse>(`${this.colorsUrl}/${colorId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createColor(fields: AdminColorFields): Observable<AdminColorMutationResponse> {
    return this.http.post<AdminColorMutationResponse>(this.colorsUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateColor(
    colorId: number,
    fields: Partial<AdminColorFields>,
  ): Observable<AdminColorMutationResponse> {
    return this.http.patch<AdminColorMutationResponse>(`${this.colorsUrl}/${colorId}`, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateStatus(colorId: number, estado: boolean): Observable<AdminColorMutationResponse> {
    return this.http.patch<AdminColorMutationResponse>(
      `${this.colorsUrl}/${colorId}/status`,
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
