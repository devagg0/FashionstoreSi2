import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminBranch {
  id_sucursal: number;
  id_ciudad: number;
  direccion: string;
  telefono: string | null;
  hora_apertura: string | null;
  hora_cierre: string | null;
  created_at: string;
  updated_at: string;
  nombre: string;
  estado: boolean;
}

export interface AdminBranchPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminBranchFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminBranchListResponse {
  success: true;
  data: AdminBranch[];
  pagination: AdminBranchPagination;
}

export interface AdminBranchResponse {
  success: true;
  data: AdminBranch;
}

export interface AdminBranchMutationResponse extends AdminBranchResponse {
  message: string;
}

export interface BranchFields {
  id_ciudad: number;
  nombre: string;
  direccion: string;
  telefono?: string | null;
  hora_apertura?: string | null;
  hora_cierre?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminBranchesService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly branchesUrl = `${environment.apiUrl}/api/admin/branches`;

  listBranches(filters: AdminBranchFilters = {}): Observable<AdminBranchListResponse> {
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

    return this.http.get<AdminBranchListResponse>(this.branchesUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getBranch(branchId: number): Observable<AdminBranchResponse> {
    return this.http.get<AdminBranchResponse>(`${this.branchesUrl}/${branchId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createBranch(fields: BranchFields): Observable<AdminBranchMutationResponse> {
    return this.http.post<AdminBranchMutationResponse>(this.branchesUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateBranch(
    branchId: number,
    fields: Partial<BranchFields>,
  ): Observable<AdminBranchMutationResponse> {
    return this.http.patch<AdminBranchMutationResponse>(`${this.branchesUrl}/${branchId}`, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateStatus(branchId: number, estado: boolean): Observable<AdminBranchMutationResponse> {
    return this.http.patch<AdminBranchMutationResponse>(
      `${this.branchesUrl}/${branchId}/status`,
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
