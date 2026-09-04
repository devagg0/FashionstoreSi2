import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminCity {
  id_ciudad: number;
  nombre: string;
  estado: boolean;
}

export interface AdminCityPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminCityFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminCityListResponse {
  success: true;
  data: AdminCity[];
  pagination: AdminCityPagination;
}

export interface AdminCityResponse {
  success: true;
  data: AdminCity;
}

export interface AdminCityMutationResponse extends AdminCityResponse {
  message: string;
}

@Injectable({ providedIn: 'root' })
export class AdminCitiesService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly citiesUrl = `${environment.apiUrl}/api/admin/cities`;

  listCities(filters: AdminCityFilters = {}): Observable<AdminCityListResponse> {
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

    return this.http.get<AdminCityListResponse>(this.citiesUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getCity(cityId: number): Observable<AdminCityResponse> {
    return this.http.get<AdminCityResponse>(`${this.citiesUrl}/${cityId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createCity(nombre: string): Observable<AdminCityMutationResponse> {
    return this.http.post<AdminCityMutationResponse>(
      this.citiesUrl,
      { nombre: nombre.trim() },
      { headers: this.authenticatedHeaders() },
    );
  }

  updateCity(cityId: number, nombre: string): Observable<AdminCityMutationResponse> {
    return this.http.patch<AdminCityMutationResponse>(
      `${this.citiesUrl}/${cityId}`,
      { nombre: nombre.trim() },
      { headers: this.authenticatedHeaders() },
    );
  }

  updateStatus(cityId: number, estado: boolean): Observable<AdminCityMutationResponse> {
    return this.http.patch<AdminCityMutationResponse>(
      `${this.citiesUrl}/${cityId}/status`,
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
