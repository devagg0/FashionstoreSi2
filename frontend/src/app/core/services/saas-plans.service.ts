import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface SaasPlanFeature {
  id_funcionalidad_saas: number;
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  habilitada: boolean;
  limite?: number | null;
}

export interface SaasPlan {
  id_plan_saas: number;
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  precio: number | string;
  moneda: string;
  periodo_meses: number;
  estado: boolean;
  suscripciones_activas: number;
  funcionalidades: SaasPlanFeature[];
  created_at: string;
  updated_at: string;
}

export interface SaasFeatureCatalog {
  id_funcionalidad_saas: number;
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  estado: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PlanFeatureItemInput {
  id_funcionalidad_saas?: number;
  codigo?: string;
  habilitada: boolean;
  limite?: number | null;
}

export interface CreateSaasPlanPayload {
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  precio: number;
  moneda?: string;
  periodo_meses?: number;
  estado?: boolean;
  funcionalidades?: PlanFeatureItemInput[];
}

export interface UpdateSaasPlanPayload {
  nombre?: string | null;
  descripcion?: string | null;
  precio?: number | null;
  periodo_meses?: number | null;
}

export interface UpdateSaasPlanStatusPayload {
  estado: boolean;
}

export interface ConfigurePlanFeaturesPayload {
  funcionalidades: PlanFeatureItemInput[];
}

export interface SaasPlanListResponse {
  success: true;
  data: SaasPlan[];
  total: number;
}

export interface SaasPlanDetailResponse {
  success: true;
  message: string;
  data: SaasPlan;
}

export interface SaasFeaturesListResponse {
  success: true;
  data: SaasFeatureCatalog[];
  total: number;
}

export interface MessageResponse {
  success: true;
  message: string;
}

export interface PlanFilters {
  search?: string;
  estado?: boolean;
}

@Injectable({ providedIn: 'root' })
export class SaasPlansService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly baseUrl = `${environment.apiUrl}/api/saas`;

  listPlans(filters: PlanFilters = {}): Observable<SaasPlanListResponse> {
    let params = new HttpParams();
    if (filters.search?.trim()) {
      params = params.set('search', filters.search.trim());
    }
    if (filters.estado !== undefined) {
      params = params.set('estado', String(filters.estado));
    }

    return this.http.get<SaasPlanListResponse>(`${this.baseUrl}/planes`, {
      headers: this.authHeaders(),
      params,
    });
  }

  getPlan(id: number): Observable<SaasPlanDetailResponse> {
    return this.http.get<SaasPlanDetailResponse>(`${this.baseUrl}/planes/${id}`, {
      headers: this.authHeaders(),
    });
  }

  createPlan(payload: CreateSaasPlanPayload): Observable<SaasPlanDetailResponse> {
    return this.http.post<SaasPlanDetailResponse>(`${this.baseUrl}/planes`, payload, {
      headers: this.authHeaders(),
    });
  }

  updatePlan(id: number, payload: UpdateSaasPlanPayload): Observable<SaasPlanDetailResponse> {
    return this.http.put<SaasPlanDetailResponse>(`${this.baseUrl}/planes/${id}`, payload, {
      headers: this.authHeaders(),
    });
  }

  updatePlanStatus(id: number, payload: UpdateSaasPlanStatusPayload): Observable<SaasPlanDetailResponse> {
    return this.http.patch<SaasPlanDetailResponse>(`${this.baseUrl}/planes/${id}/estado`, payload, {
      headers: this.authHeaders(),
    });
  }

  deletePlan(id: number): Observable<MessageResponse> {
    return this.http.delete<MessageResponse>(`${this.baseUrl}/planes/${id}`, {
      headers: this.authHeaders(),
    });
  }

  configurePlanFeatures(
    id: number,
    payload: ConfigurePlanFeaturesPayload,
  ): Observable<SaasPlanDetailResponse> {
    return this.http.put<SaasPlanDetailResponse>(
      `${this.baseUrl}/planes/${id}/funcionalidades`,
      payload,
      {
        headers: this.authHeaders(),
      },
    );
  }

  listFeatures(estado?: boolean): Observable<SaasFeaturesListResponse> {
    let params = new HttpParams();
    if (estado !== undefined) {
      params = params.set('estado', String(estado));
    }

    return this.http.get<SaasFeaturesListResponse>(`${this.baseUrl}/funcionalidades`, {
      headers: this.authHeaders(),
      params,
    });
  }

  private authHeaders(): HttpHeaders {
    const token = this.sessionService.getAccessToken();
    if (!token) return new HttpHeaders();
    return new HttpHeaders({ Authorization: `Bearer ${token}` });
  }
}

