import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { catchError, Observable, of, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface FeatureItemData {
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  habilitada: boolean;
  limite?: number | null;
}

export interface BranchConsumptionSummary {
  limite_sucursales: number | null;
  sucursales_activas: number;
  sucursales_inactivas: number;
  sucursales_totales: number;
  disponibles_para_crear: number | null;
  limite_alcanzado: boolean;
  puede_crear_sucursal: boolean;
}

export interface PlanSummaryData {
  id_plan_saas: number;
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  precio: number | string;
  moneda: string;
  periodo_meses: number;
}

export interface SubscriptionSummaryData {
  id_suscripcion: number;
  estado: string;
  fecha_inicio: string;
  fecha_fin_periodo: string;
  dias_restantes: number;
  renovacion_automatica: boolean;
  proveedor?: string | null;
}

export interface CompanyPlanLimitsResponse {
  success: true;
  id_empresa: number;
  empresa_codigo: string;
  empresa_nombre: string;
  tiene_suscripcion_activa: boolean;
  suscripcion: SubscriptionSummaryData | null;
  plan: PlanSummaryData | null;
  consumo_sucursales: BranchConsumptionSummary;
  funcionalidades: FeatureItemData[];
  permisos: Record<string, boolean>;
  tiene_ia: boolean;
  puede_crear_sucursal: boolean;
}

export interface CompanyBranchDetailItem {
  id_sucursal: number;
  nombre: string;
  direccion: string;
  telefono?: string | null;
  estado: boolean;
  id_ciudad: number;
  ciudad_nombre?: string | null;
}

export interface CompanyBranchConsumptionResponse {
  success: true;
  id_empresa: number;
  empresa_codigo: string;
  empresa_nombre: string;
  consumo: BranchConsumptionSummary;
  sucursales: CompanyBranchDetailItem[];
}

@Injectable({ providedIn: 'root' })
export class SaasPlanLimitsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly baseUrl = `${environment.apiUrl}/api/saas`;

  /** Estado reactivo del plan y límites de la empresa en sesión */
  readonly currentPlanLimits = signal<CompanyPlanLimitsResponse | null>(null);
  readonly currentBranchConsumption = signal<BranchConsumptionSummary | null>(null);
  readonly loading = signal<boolean>(false);
  readonly error = signal<string | null>(null);

  /** Selectores computados para adaptación reactiva del panel */
  readonly hasActiveSubscription = computed(
    () => this.currentPlanLimits()?.tiene_suscripcion_activa ?? false,
  );

  readonly hasAiReports = computed(
    () => this.currentPlanLimits()?.tiene_ia ?? false,
  );

  readonly canCreateBranch = computed(
    () =>
      this.currentBranchConsumption()?.puede_crear_sucursal ??
      this.currentPlanLimits()?.puede_crear_sucursal ??
      false,
  );

  readonly isBranchLimitReached = computed(
    () =>
      this.currentBranchConsumption()?.limite_alcanzado ??
      this.currentPlanLimits()?.consumo_sucursales?.limite_alcanzado ??
      false,
  );

  readonly branchLimit = computed(
    () =>
      this.currentBranchConsumption()?.limite_sucursales ??
      this.currentPlanLimits()?.consumo_sucursales?.limite_sucursales ??
      null,
  );

  readonly activeBranchesCount = computed(
    () =>
      this.currentBranchConsumption()?.sucursales_activas ??
      this.currentPlanLimits()?.consumo_sucursales?.sucursales_activas ??
      0,
  );

  readonly availableBranchesQuota = computed(
    () =>
      this.currentBranchConsumption()?.disponibles_para_crear ??
      this.currentPlanLimits()?.consumo_sucursales?.disponibles_para_crear ??
      null,
  );

  private authHeaders(): HttpHeaders {
    const token = this.sessionService.getAccessToken();
    if (!token) return new HttpHeaders();
    return new HttpHeaders({ Authorization: `Bearer ${token}` });
  }

  /**
   * Consulta el plan vigente, límites y funcionalidades de la empresa autenticada.
   * Si es SUPERADMIN, puede pasar empresaId como parámetro.
   */
  getCurrentPlanLimits(empresaId?: number | null): Observable<CompanyPlanLimitsResponse> {
    let params = new HttpParams();
    if (empresaId) {
      params = params.set('empresa_id', empresaId.toString());
    }
    this.loading.set(true);
    this.error.set(null);

    return this.http
      .get<CompanyPlanLimitsResponse>(`${this.baseUrl}/plan-vigente`, {
        headers: this.authHeaders(),
        params,
      })
      .pipe(
        tap((response) => {
          this.currentPlanLimits.set(response);
          this.currentBranchConsumption.set(response.consumo_sucursales);
          this.loading.set(false);
        }),
        catchError((err) => {
          this.loading.set(false);
          this.error.set('No fue posible consultar el plan y límites vigentes.');
          throw err;
        }),
      );
  }

  /**
   * Consulta el consumo de sucursales contra el límite parametrizado.
   */
  getCurrentBranchConsumption(
    empresaId?: number | null,
  ): Observable<CompanyBranchConsumptionResponse> {
    let params = new HttpParams();
    if (empresaId) {
      params = params.set('empresa_id', empresaId.toString());
    }

    return this.http
      .get<CompanyBranchConsumptionResponse>(
        `${this.baseUrl}/plan-vigente/consumo-sucursales`,
        {
          headers: this.authHeaders(),
          params,
        },
      )
      .pipe(
        tap((response) => {
          this.currentBranchConsumption.set(response.consumo);
        }),
      );
  }

  /**
   * Consulta administrativa del plan vigente de una empresa específica (SUPERADMIN).
   */
  getCompanyPlanLimitsById(companyId: number): Observable<CompanyPlanLimitsResponse> {
    return this.http.get<CompanyPlanLimitsResponse>(
      `${this.baseUrl}/empresas/${companyId}/plan-vigente`,
      { headers: this.authHeaders() },
    );
  }

  /**
   * Consulta administrativa detallada del consumo de sucursales de una empresa (SUPERADMIN).
   */
  getCompanyBranchConsumptionById(
    companyId: number,
  ): Observable<CompanyBranchConsumptionResponse> {
    return this.http.get<CompanyBranchConsumptionResponse>(
      `${this.baseUrl}/empresas/${companyId}/consumo-sucursales`,
      { headers: this.authHeaders() },
    );
  }

  /**
   * Verifica de manera rápida si una funcionalidad está habilitada en el plan activo.
   */
  hasFeature(featureCode: string): boolean {
    const limits = this.currentPlanLimits();
    if (!limits || !limits.tiene_suscripcion_activa) {
      return false;
    }
    return Boolean(limits.permisos?.[featureCode]);
  }

  /**
   * Refresca los límites en segundo plano.
   */
  refreshCurrentPlan(): void {
    this.getCurrentPlanLimits().subscribe({
      next: () => {},
      error: () => {},
    });
  }
}

