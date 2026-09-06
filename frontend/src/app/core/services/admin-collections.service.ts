import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminCollection {
  id_coleccion: number;
  nombre: string;
  descripcion: string | null;
  created_at: string;
  updated_at: string;
  estado: boolean;
}

export interface AdminCollectionPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminCollectionFilters {
  search?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AdminCollectionListResponse {
  success: true;
  data: AdminCollection[];
  pagination: AdminCollectionPagination;
}

export interface AdminCollectionResponse {
  success: true;
  data: AdminCollection;
}

export interface AdminCollectionMutationResponse extends AdminCollectionResponse {
  message: string;
}

export interface AdminCollectionFields {
  nombre: string;
  descripcion?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminCollectionsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly collectionsUrl = `${environment.apiUrl}/api/admin/collections`;

  listCollections(filters: AdminCollectionFilters = {}): Observable<AdminCollectionListResponse> {
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

    return this.http.get<AdminCollectionListResponse>(this.collectionsUrl, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  getCollection(collectionId: number): Observable<AdminCollectionResponse> {
    return this.http.get<AdminCollectionResponse>(`${this.collectionsUrl}/${collectionId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  createCollection(fields: AdminCollectionFields): Observable<AdminCollectionMutationResponse> {
    return this.http.post<AdminCollectionMutationResponse>(this.collectionsUrl, fields, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateCollection(
    collectionId: number,
    fields: Partial<AdminCollectionFields>,
  ): Observable<AdminCollectionMutationResponse> {
    return this.http.patch<AdminCollectionMutationResponse>(
      `${this.collectionsUrl}/${collectionId}`,
      fields,
      {
        headers: this.authenticatedHeaders(),
      },
    );
  }

  updateStatus(collectionId: number, estado: boolean): Observable<AdminCollectionMutationResponse> {
    return this.http.patch<AdminCollectionMutationResponse>(
      `${this.collectionsUrl}/${collectionId}/status`,
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
