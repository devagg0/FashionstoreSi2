import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface CompanyAdminData {
  id_empresa: number;
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo: string;
  telefono: string | null;
  rol: string;
  estado: string;
  es_propietario: boolean;
  created_at: string;
  updated_at: string;
}

export interface CompanyAdminResponse {
  success: true;
  message: string;
  data: CompanyAdminData;
}

export interface AssignCompanyAdminRequest {
  id_usuario: number;
  estado?: 'ACTIVO' | 'INVITADO';
}

export interface CreateAndAssignCompanyAdminRequest {
  nombre: string;
  apellido: string;
  correo: string;
  password: string;
  telefono?: string | null;
  estado?: 'ACTIVO' | 'INVITADO';
}

export interface AssignCompanyAdminResponse {
  success: true;
  message: string;
  data: CompanyAdminData;
}

export interface AvailableUserData {
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo: string;
  telefono: string | null;
  rol_global: string;
  estado: boolean;
  created_at: string;
}

export interface AvailableUsersPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AvailableUsersResponse {
  success: true;
  message: string;
  data: AvailableUserData[];
  pagination: AvailableUsersPagination;
}

export interface AvailableUsersFilters {
  search?: string;
  empresaId?: number;
  page?: number;
  pageSize?: number;
}

@Injectable({ providedIn: 'root' })
export class SaasCompanyAdminService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly baseUrl = `${environment.apiUrl}/api/saas`;

  getCompanyAdmin(companyId: number): Observable<CompanyAdminResponse> {
    return this.http.get<CompanyAdminResponse>(
      `${this.baseUrl}/empresas/${companyId}/administrador`,
      { headers: this.authHeaders() },
    );
  }

  getAvailableUsers(
    filters: AvailableUsersFilters = {},
  ): Observable<AvailableUsersResponse> {
    let params = new HttpParams()
      .set('page', String(filters.page ?? 1))
      .set('page_size', String(filters.pageSize ?? 10));

    const search = filters.search?.trim();
    if (search) {
      params = params.set('search', search);
    }

    if (filters.empresaId) {
      params = params.set('empresa_id', String(filters.empresaId));
    }

    return this.http.get<AvailableUsersResponse>(
      `${this.baseUrl}/usuarios-disponibles`,
      {
        headers: this.authHeaders(),
        params,
      },
    );
  }

  assignCompanyAdmin(
    companyId: number,
    payload: AssignCompanyAdminRequest,
  ): Observable<AssignCompanyAdminResponse> {
    return this.http.post<AssignCompanyAdminResponse>(
      `${this.baseUrl}/empresas/${companyId}/administrador`,
      payload,
      { headers: this.authHeaders() },
    );
  }

  createAndAssignCompanyAdmin(
    companyId: number,
    payload: CreateAndAssignCompanyAdminRequest,
  ): Observable<AssignCompanyAdminResponse> {
    return this.http.post<AssignCompanyAdminResponse>(
      `${this.baseUrl}/empresas/${companyId}/administrador/nuevo`,
      payload,
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
