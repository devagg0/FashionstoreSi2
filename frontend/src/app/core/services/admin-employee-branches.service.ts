import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface Assignment {
  id_empleado_sucursal: number;
  id_empleado: number;
  nombre_empleado: string;
  correo: string;
  rol: string;
  id_sucursal: number;
  nombre_sucursal: string;
  fecha_asignacion: string;
  estado: boolean;
}
export interface EmployeeOption {
  id_empleado: number;
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo: string;
  rol: string;
  estado: boolean;
}
export interface AssignmentPagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}
export interface AssignmentPage<T> {
  success: true;
  data: T[];
  pagination: AssignmentPagination;
}
export interface AssignmentResponse { success: true; data: Assignment; }
export interface AssignmentMutation extends AssignmentResponse { message: string; }
export interface AssignmentFields { id_empleado: number; id_sucursal: number; }
export interface AssignmentFilters {
  id_empleado?: number;
  id_sucursal?: number;
  estado?: boolean;
  page?: number;
  pageSize?: number;
}

@Injectable({ providedIn: 'root' })
export class AdminEmployeeBranchesService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/admin/employee-branches`;

  listAssignments(filters: AssignmentFilters = {}) {
    let params = this.pagination(filters.page ?? 1, filters.pageSize ?? 20);
    for (const key of ['id_empleado', 'id_sucursal', 'estado'] as const) {
      if (filters[key] !== undefined) params = params.set(key, filters[key]);
    }
    return this.http.get<AssignmentPage<Assignment>>(this.url, { headers: this.headers(), params });
  }
  listEmployees(page = 1, pageSize = 100) {
    return this.http.get<AssignmentPage<EmployeeOption>>(`${this.url}/options/employees`, {
      headers: this.headers(), params: this.pagination(page, pageSize),
    });
  }
  getAssignment(id: number) {
    return this.http.get<AssignmentResponse>(`${this.url}/${id}`, { headers: this.headers() });
  }
  createAssignment(fields: AssignmentFields) {
    return this.http.post<AssignmentMutation>(this.url, fields, {
      headers: this.headers(), observe: 'response',
    });
  }
  updateStatus(id: number, estado: boolean) {
    return this.http.patch<AssignmentMutation>(`${this.url}/${id}/status`, { estado }, { headers: this.headers() });
  }
  private pagination(page: number, pageSize: number) {
    return new HttpParams().set('page', page).set('page_size', pageSize);
  }
  private headers() {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }
}
