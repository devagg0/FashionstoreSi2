import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface AdminUser {
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo: string;
  estado: boolean;
  rol: string;
}

export interface AdminRole {
  id_rol: number;
  nombre: string;
  descripcion: string | null;
  estado: boolean;
}

export interface AdminPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface AdminUserFilters {
  search?: string;
  rol?: string;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

export type InternalUserRole = 'CAJERO' | 'ENCARGADO_SUCURSAL';

export interface AdminUserCreateRequest {
  nombre: string;
  apellido: string;
  correo: string;
  telefono: string | null;
  rol: InternalUserRole;
  password: string;
  confirm_password: string;
}

export interface AdminUserListResponse {
  success: true;
  data: AdminUser[];
  pagination: AdminPagination;
}

export interface AdminUserResponse {
  success: true;
  data: AdminUser;
}

export interface AdminUserUpdateResponse extends AdminUserResponse {
  message: string;
}

export interface AdminRoleListResponse {
  success: true;
  data: AdminRole[];
}

@Injectable({ providedIn: 'root' })
export class AdminUsersService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly adminUrl = `${environment.apiUrl}/api/admin`;

  listUsers(filters: AdminUserFilters = {}): Observable<AdminUserListResponse> {
    let params = new HttpParams()
      .set('page', filters.page ?? 1)
      .set('page_size', filters.pageSize ?? 20);

    const search = filters.search?.trim();
    const role = filters.rol?.trim();
    if (search) {
      params = params.set('search', search);
    }
    if (role) {
      params = params.set('rol', role);
    }
    if (filters.estado !== undefined) {
      params = params.set('estado', filters.estado);
    }

    return this.http.get<AdminUserListResponse>(`${this.adminUrl}/users`, {
      headers: this.authenticatedHeaders(),
      params,
    });
  }

  createUser(payload: AdminUserCreateRequest): Observable<AdminUserUpdateResponse> {
    return this.http.post<AdminUserUpdateResponse>(`${this.adminUrl}/users`, payload, {
      headers: this.authenticatedHeaders(),
    });
  }

  getUser(userId: number): Observable<AdminUserResponse> {
    return this.http.get<AdminUserResponse>(`${this.adminUrl}/users/${userId}`, {
      headers: this.authenticatedHeaders(),
    });
  }

  updateStatus(userId: number, estado: boolean): Observable<AdminUserUpdateResponse> {
    return this.http.patch<AdminUserUpdateResponse>(
      `${this.adminUrl}/users/${userId}/status`,
      { estado },
      { headers: this.authenticatedHeaders() },
    );
  }

  updateRole(userId: number, rol: string): Observable<AdminUserUpdateResponse> {
    return this.http.patch<AdminUserUpdateResponse>(
      `${this.adminUrl}/users/${userId}/role`,
      { rol },
      { headers: this.authenticatedHeaders() },
    );
  }

  listRoles(): Observable<AdminRoleListResponse> {
    return this.http.get<AdminRoleListResponse>(`${this.adminUrl}/roles`, {
      headers: this.authenticatedHeaders(),
    });
  }

  private authenticatedHeaders(): HttpHeaders {
    const accessToken = this.sessionService.getAccessToken();
    return accessToken
      ? new HttpHeaders({ Authorization: `Bearer ${accessToken}` })
      : new HttpHeaders();
  }
}
