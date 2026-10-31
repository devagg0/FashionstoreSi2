import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface CompanyUserData {
  id_empresa: number;
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo: string;
  telefono: string | null;
  id_rol: number;
  rol: string;
  estado: string;
  es_propietario: boolean;
  created_at: string;
  updated_at: string;
}

export interface CompanyUsersListResponse {
  success: true;
  data: CompanyUserData[];
  total: number;
}

export interface AssociateUserRequest {
  id_usuario: number;
  rol: string;
  estado?: 'INVITADO' | 'ACTIVO' | 'SUSPENDIDO' | 'RETIRADO';
  es_propietario?: boolean;
}

export interface CompanyUserResponse {
  success: true;
  message: string;
  data: CompanyUserData;
}

export interface CompanyBranchData {
  id_sucursal: number;
  empresa_id: number;
  id_ciudad: number;
  ciudad_nombre: string | null;
  nombre: string;
  direccion: string;
  telefono: string | null;
  hora_apertura: string | null;
  hora_cierre: string | null;
  estado: boolean;
  created_at: string;
  updated_at: string;
}

export interface CompanyBranchesListResponse {
  success: true;
  data: CompanyBranchData[];
  total: number;
}

export interface CreateCompanyBranchRequest {
  id_ciudad: number;
  nombre: string;
  direccion: string;
  telefono?: string | null;
  hora_apertura?: string | null;
  hora_cierre?: string | null;
}

export interface AssociateExistingBranchRequest {
  id_sucursal: number;
}

export interface CompanyBranchResponse {
  success: true;
  message: string;
  data: CompanyBranchData;
}

export interface CompanyResourcesData {
  id_empresa: number;
  empresa_nombre: string;
  empresa_codigo: string;
  usuarios: CompanyUserData[];
  sucursales: CompanyBranchData[];
}

export interface CompanyResourcesResponse {
  success: true;
  data: CompanyResourcesData;
}

export interface CompanyUsersFilters {
  role?: string;
  estado?: string;
  search?: string;
}

export interface CompanyBranchesFilters {
  estado?: boolean;
  search?: string;
}

@Injectable({ providedIn: 'root' })
export class SaasCompanyResourcesService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly baseUrl = `${environment.apiUrl}/api/saas`;

  getCompanyUsers(
    companyId: number,
    filters: CompanyUsersFilters = {},
  ): Observable<CompanyUsersListResponse> {
    let params = new HttpParams();
    if (filters.role) params = params.set('role', filters.role);
    if (filters.estado) params = params.set('estado', filters.estado);
    if (filters.search?.trim()) params = params.set('search', filters.search.trim());

    return this.http.get<CompanyUsersListResponse>(
      `${this.baseUrl}/empresas/${companyId}/usuarios`,
      { headers: this.authHeaders(), params },
    );
  }

  getCompanyBranches(
    companyId: number,
    filters: CompanyBranchesFilters = {},
  ): Observable<CompanyBranchesListResponse> {
    let params = new HttpParams();
    if (filters.estado !== undefined) params = params.set('estado', String(filters.estado));
    if (filters.search?.trim()) params = params.set('search', filters.search.trim());

    return this.http.get<CompanyBranchesListResponse>(
      `${this.baseUrl}/empresas/${companyId}/sucursales`,
      { headers: this.authHeaders(), params },
    );
  }

  getCompanyResources(companyId: number): Observable<CompanyResourcesResponse> {
    return this.http.get<CompanyResourcesResponse>(
      `${this.baseUrl}/empresas/${companyId}/asociaciones`,
      { headers: this.authHeaders() },
    );
  }

  associateUser(
    companyId: number,
    payload: AssociateUserRequest,
  ): Observable<CompanyUserResponse> {
    return this.http.post<CompanyUserResponse>(
      `${this.baseUrl}/empresas/${companyId}/usuarios`,
      payload,
      { headers: this.authHeaders() },
    );
  }

  createBranch(
    companyId: number,
    payload: CreateCompanyBranchRequest,
  ): Observable<CompanyBranchResponse> {
    return this.http.post<CompanyBranchResponse>(
      `${this.baseUrl}/empresas/${companyId}/sucursales`,
      payload,
      { headers: this.authHeaders() },
    );
  }

  associateExistingBranch(
    companyId: number,
    payload: AssociateExistingBranchRequest,
  ): Observable<CompanyBranchResponse> {
    return this.http.post<CompanyBranchResponse>(
      `${this.baseUrl}/empresas/${companyId}/sucursales/asociar`,
      payload,
      { headers: this.authHeaders() },
    );
  }

  private authHeaders(): HttpHeaders {
    const token = this.sessionService.getAccessToken();
    if (!token) return new HttpHeaders();
    return new HttpHeaders({ Authorization: `Bearer ${token}` });
  }
}

