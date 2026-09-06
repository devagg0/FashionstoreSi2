import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminCategory {
  id_categoria: number;
  nombre: string;
  descripcion: string | null;
  created_at: string;
  updated_at: string;
  estado: boolean;
}

export interface AdminCategoryPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminCategoryFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminCategoryListResponse {
  success: true;
  data: AdminCategory[];
  pagination: AdminCategoryPagination;
}

export interface AdminCategoryResponse {
  success: true;
  data: AdminCategory;
}

export interface AdminCategoryMutationResponse extends AdminCategoryResponse {
  message: string;
}

export interface AdminCategoryFields {
  nombre: string;
  descripcion?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminCategoriesService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly categoriesUrl = `${environment.apiUrl}/api/admin/categories`;

  listCategories(filters: AdminCategoryFilters = {}): Observable<AdminCategoryListResponse> {
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

    return this.http.get<AdminCategoryListResponse>(this.categoriesUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getCategory(categoryId: number): Observable<AdminCategoryResponse> {
    return this.http.get<AdminCategoryResponse>(`${this.categoriesUrl}/${categoryId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createCategory(fields: AdminCategoryFields): Observable<AdminCategoryMutationResponse> {
    return this.http.post<AdminCategoryMutationResponse>(this.categoriesUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateCategory(
    categoryId: number,
    fields: Partial<AdminCategoryFields>,
  ): Observable<AdminCategoryMutationResponse> {
    return this.http.patch<AdminCategoryMutationResponse>(
      `${this.categoriesUrl}/${categoryId}`,
      fields,
      { headers: this.authenticatedHeaders() },
    );
  }

  updateStatus(categoryId: number, estado: boolean): Observable<AdminCategoryMutationResponse> {
    return this.http.patch<AdminCategoryMutationResponse>(
      `${this.categoriesUrl}/${categoryId}/status`,
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
