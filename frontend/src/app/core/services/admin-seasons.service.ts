import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminSeason {
  id_temporada: number;
  nombre: string;
  descripcion: string | null;
  fecha_inicio: string | null;
  fecha_fin: string | null;
  created_at: string;
  updated_at: string;
  estado: boolean;
}

export interface AdminSeasonPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminSeasonFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminSeasonListResponse {
  success: true;
  data: AdminSeason[];
  pagination: AdminSeasonPagination;
}

export interface AdminSeasonResponse {
  success: true;
  data: AdminSeason;
}

export interface AdminSeasonMutationResponse extends AdminSeasonResponse {
  message: string;
}

export interface AdminSeasonFields {
  nombre: string;
  descripcion?: string | null;
  fecha_inicio?: string | null;
  fecha_fin?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminSeasonsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly seasonsUrl = `${environment.apiUrl}/api/admin/seasons`;

  listSeasons(filters: AdminSeasonFilters = {}): Observable<AdminSeasonListResponse> {
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

    return this.http.get<AdminSeasonListResponse>(this.seasonsUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getSeason(seasonId: number): Observable<AdminSeasonResponse> {
    return this.http.get<AdminSeasonResponse>(`${this.seasonsUrl}/${seasonId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createSeason(fields: AdminSeasonFields): Observable<AdminSeasonMutationResponse> {
    return this.http.post<AdminSeasonMutationResponse>(this.seasonsUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateSeason(
    seasonId: number,
    fields: Partial<AdminSeasonFields>,
  ): Observable<AdminSeasonMutationResponse> {
    return this.http.patch<AdminSeasonMutationResponse>(`${this.seasonsUrl}/${seasonId}`, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateStatus(seasonId: number, estado: boolean): Observable<AdminSeasonMutationResponse> {
    return this.http.patch<AdminSeasonMutationResponse>(
      `${this.seasonsUrl}/${seasonId}/status`,
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
