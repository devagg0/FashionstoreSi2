import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface PlanFeatureSummary {
  codigo: string;
  nombre: string;
  habilitada: boolean;
  limite?: number | null;
}

export interface CommercialPlan {
  id_plan_saas: number;
  codigo: string;
  nombre: string;
  descripcion?: string | null;
  precio: number | string;
  moneda: string;
  periodo_meses: number;
  limite_sucursales?: number | null;
  tiene_ia: boolean;
  funcionalidades: PlanFeatureSummary[];
}

export interface ScheduledChange {
  id_plan_saas: number;
  codigo_plan: string;
  nombre_plan: string;
  fecha_programada: string;
  monto_pagado: number | string;
  moneda: string;
  estado: string;
}

export interface SubscriptionDetail {
  id_suscripcion: number;
  id_empresa: number;
  empresa_codigo?: string | null;
  empresa_nombre?: string | null;
  id_plan_saas: number;
  plan_codigo: string;
  plan_nombre: string;
  plan_precio: number | string;
  plan_moneda: string;
  plan_periodo_meses: number;
  limite_sucursales?: number | null;
  tiene_ia: boolean;
  estado: string;
  fecha_inicio: string;
  fecha_fin_periodo: string;
  fecha_cancelacion?: string | null;
  dias_restantes: number;
  renovacion_automatica: boolean;
  proveedor?: string | null;
  referencia_externa?: string | null;
  cambio_programado?: ScheduledChange | null;
}

export interface CurrentSubscriptionResponse {
  success: true;
  tiene_suscripcion_activa: boolean;
  data: SubscriptionDetail | null;
}

export interface SubscriptionHistoryItem {
  id_suscripcion: number;
  id_plan_saas: number;
  plan_codigo: string;
  plan_nombre: string;
  estado: string;
  fecha_inicio: string;
  fecha_fin_periodo: string;
  fecha_cancelacion?: string | null;
  proveedor?: string | null;
  referencia_externa?: string | null;
  created_at: string;
}

export interface SubscriptionHistoryResponse {
  success: true;
  total: number;
  data: SubscriptionHistoryItem[];
}

export interface CommercialPlansResponse {
  success: true;
  total: number;
  data: CommercialPlan[];
}

export interface CreateCheckoutPayload {
  id_plan_saas: number;
  tipo_operacion: 'CONTRATACION' | 'RENOVACION' | 'CAMBIO_PLAN';
  empresa_id?: number | null;
  success_url?: string | null;
  cancel_url?: string | null;
}

export interface CheckoutSessionResponse {
  success: true;
  message: string;
  id_sesion: string;
  url_checkout: string;
  qr_data?: string | null;
  tipo_operacion: string;
  metodo_pago: string;
  monto: number | string;
  moneda: string;
  id_plan_saas: number;
  plan_codigo: string;
  plan_nombre: string;
}

export interface VerifyPaymentResponse {
  success: true;
  message: string;
  id_suscripcion: number;
  estado: string;
  plan_codigo: string;
  tipo_operacion: string;
  fecha_inicio: string;
  fecha_fin_periodo: string;
  dias_restantes: number;
  referencia_pago?: string | null;
  cambio_programado?: ScheduledChange | null;
}

export interface SubscriptionFilters {
  empresa_id?: number | null;
  estado?: string | null;
  plan_id?: number | null;
}

export interface SubscriptionAdminListResponse {
  success: true;
  total: number;
  data: SubscriptionDetail[];
}

export interface UpdateSubscriptionStatusPayload {
  nuevo_estado: 'ACTIVA' | 'SUSPENDIDA' | 'CANCELADA' | 'EXPIRADA';
  motivo?: string | null;
}

@Injectable({ providedIn: 'root' })
export class SaasSubscriptionsService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly baseUrl = `${environment.apiUrl}/api/saas/suscripciones`;

  /** Obtiene planes comerciales BÁSICO y PROFESIONAL desde la API */
  listCommercialPlans(): Observable<CommercialPlansResponse> {
    return this.http.get<CommercialPlansResponse>(`${this.baseUrl}/planes`, {
      headers: this.authHeaders(),
    });
  }

  /** Consulta la suscripción vigente con días restantes y cambios programados */
  getCurrentSubscription(empresaId?: number): Observable<CurrentSubscriptionResponse> {
    let params = new HttpParams();
    if (empresaId) {
      params = params.set('empresa_id', String(empresaId));
    }
    return this.http.get<CurrentSubscriptionResponse>(`${this.baseUrl}/actual`, {
      headers: this.authHeaders(),
      params,
    });
  }

  /** Historial completo de suscripciones de la empresa */
  getSubscriptionHistory(empresaId?: number): Observable<SubscriptionHistoryResponse> {
    let params = new HttpParams();
    if (empresaId) {
      params = params.set('empresa_id', String(empresaId));
    }
    return this.http.get<SubscriptionHistoryResponse>(`${this.baseUrl}/historial`, {
      headers: this.authHeaders(),
      params,
    });
  }

  /** Inicia Checkout para pago con tarjeta */
  createCardCheckout(payload: CreateCheckoutPayload): Observable<CheckoutSessionResponse> {
    return this.http.post<CheckoutSessionResponse>(`${this.baseUrl}/checkout/tarjeta`, payload, {
      headers: this.authHeaders(),
    });
  }

  /** Inicia Checkout para escaneo QR (mismo Stripe Checkout) */
  createQrCheckout(payload: CreateCheckoutPayload): Observable<CheckoutSessionResponse> {
    return this.http.post<CheckoutSessionResponse>(`${this.baseUrl}/checkout/qr`, payload, {
      headers: this.authHeaders(),
    });
  }

  /** Concilia y verifica la sesión de Stripe en el backend */
  verifyPayment(sessionId: string): Observable<VerifyPaymentResponse> {
    return this.http.post<VerifyPaymentResponse>(
      `${this.baseUrl}/verificar-pago/${encodeURIComponent(sessionId)}`,
      {},
      { headers: this.authHeaders() },
    );
  }

  /** Listado multiempresa de suscripciones exclusivo para SUPERADMIN */
  adminListSubscriptions(filters: SubscriptionFilters = {}): Observable<SubscriptionAdminListResponse> {
    let params = new HttpParams();
    if (filters.empresa_id) {
      params = params.set('empresa_id', String(filters.empresa_id));
    }
    if (filters.estado?.trim()) {
      params = params.set('estado', filters.estado.trim());
    }
    if (filters.plan_id) {
      params = params.set('plan_id', String(filters.plan_id));
    }
    return this.http.get<SubscriptionAdminListResponse>(this.baseUrl, {
      headers: this.authHeaders(),
      params,
    });
  }

  /** Actualización administrativa del estado (SUPERADMIN) */
  adminUpdateSubscriptionStatus(
    subscriptionId: number,
    payload: UpdateSubscriptionStatusPayload,
  ): Observable<{ success: true; data: SubscriptionDetail }> {
    return this.http.patch<{ success: true; data: SubscriptionDetail }>(
      `${this.baseUrl}/${subscriptionId}/estado`,
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

