import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminSupplier {
  id_proveedor: number;
  nombre: string;
  direccion: string | null;
  nit: string | null;
  telefono: string | null;
  correo: string | null;
  id_usuario: number | null;
  created_at: string;
  updated_at: string;
  estado: boolean;
}

export interface AdminSupplierPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminSupplierFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminSupplierListResponse {
  success: true;
  data: AdminSupplier[];
  pagination: AdminSupplierPagination;
}

export interface AdminSupplierResponse {
  success: true;
  data: AdminSupplier;
}

export interface AdminSupplierMutationResponse extends AdminSupplierResponse {
  message: string;
}

export interface AdminSupplierFields {
  nombre: string;
  direccion?: string | null;
  nit?: string | null;
  telefono?: string | null;
  correo?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminSuppliersService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly suppliersUrl = `${environment.apiUrl}/api/admin/suppliers`;

  listSuppliers(filters: AdminSupplierFilters = {}): Observable<AdminSupplierListResponse> {
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

    return this.http.get<AdminSupplierListResponse>(this.suppliersUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getSupplier(supplierId: number): Observable<AdminSupplierResponse> {
    return this.http.get<AdminSupplierResponse>(`${this.suppliersUrl}/${supplierId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createSupplier(fields: AdminSupplierFields): Observable<AdminSupplierMutationResponse> {
    return this.http.post<AdminSupplierMutationResponse>(this.suppliersUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateSupplier(
    supplierId: number,
    fields: Partial<AdminSupplierFields>,
  ): Observable<AdminSupplierMutationResponse> {
    return this.http.patch<AdminSupplierMutationResponse>(`${this.suppliersUrl}/${supplierId}`, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateStatus(supplierId: number, estado: boolean): Observable<AdminSupplierMutationResponse> {
    return this.http.patch<AdminSupplierMutationResponse>(
      `${this.suppliersUrl}/${supplierId}/status`,
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
