import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface CompanyCreateRequest {
  codigo: string;
  nombre: string;
  nit: string | null;
  zona_horaria: string;
}

export type CompanyState = 'ACTIVA' | 'SUSPENDIDA' | 'CANCELADA';

export interface SaasCompany {
  id_empresa: number;
  codigo: string;
  nombre: string;
  nit: string | null;
  zona_horaria: string;
  estado: CompanyState;
  created_at: string;
  updated_at: string;
}

export interface CompanyCreateResponse {
  success: true;
  message: string;
  data: SaasCompany;
}

export interface CompanyUpdateRequest {
  codigo?: string;
  nombre?: string;
  nit?: string | null;
  zona_horaria?: string;
}

export interface CompanyPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface CompanyListResponse {
  success: true;
  data: SaasCompany[];
  pagination: CompanyPagination;
}

export interface CompanyDetailResponse {
  success: true;
  data: SaasCompany;
  message?: string;
}

export interface CompanyListFilters {
  search?: string;
  estado?: CompanyState;
  page?: number;
  pageSize?: number;
}

@Injectable({ providedIn: 'root' })
export class SaasCompaniesService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly companiesUrl = `${environment.apiUrl}/api/saas/empresas`;

  listCompanies(filters: CompanyListFilters = {}): Observable<CompanyListResponse> {
    let params = new HttpParams()
      .set('page', String(filters.page ?? 1))
      .set('page_size', String(filters.pageSize ?? 10));
    const search = filters.search?.trim();
    if (search) params = params.set('search', search);
    if (filters.estado) params = params.set('estado', filters.estado);
    return this.http.get<CompanyListResponse>(this.companiesUrl, {
      headers: this.authHeaders(),
      params,
    });
  }

  getCompany(companyId: number): Observable<CompanyDetailResponse> {
    return this.http.get<CompanyDetailResponse>(`${this.companiesUrl}/${companyId}`, {
      headers: this.authHeaders(),
    });
  }

  createCompany(payload: CompanyCreateRequest): Observable<CompanyCreateResponse> {
    return this.http.post<CompanyCreateResponse>(this.companiesUrl, payload, {
      headers: this.authHeaders(),
    });
  }

  updateCompany(
    companyId: number,
    payload: CompanyUpdateRequest,
  ): Observable<CompanyDetailResponse> {
    return this.http.patch<CompanyDetailResponse>(`${this.companiesUrl}/${companyId}`, payload, {
      headers: this.authHeaders(),
    });
  }

  updateCompanyState(
    companyId: number,
    estado: CompanyState,
  ): Observable<CompanyDetailResponse> {
    return this.http.patch<CompanyDetailResponse>(
      `${this.companiesUrl}/${companyId}/estado`,
      { estado },
      { headers: this.authHeaders() },
    );
  }

  private authHeaders(): HttpHeaders {
    const token = this.sessionService.getAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }
}
