import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflineConflictDiagnoseRequest,
  OfflineConflictDiagnoseResponse,
  OfflineConflictResolveRequest,
  OfflineConflictResolveResponse,
  OfflineOperationConflictDiagnosis,
  OfflineOperationResolutionInput,
  OfflineResolutionAction,
  OfflineSyncOperationInputDto,
} from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

@Injectable({ providedIn: 'root' })
export class OfflineConflictsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly storage = inject(OfflineStorageService);
  private readonly offlineService = inject(OfflineService);

  readonly isDiagnosing = signal<boolean>(false);
  readonly isResolving = signal<boolean>(false);
  readonly lastDiagnosis = signal<OfflineConflictDiagnoseResponse | null>(null);
  readonly lastResolution = signal<OfflineConflictResolveResponse | null>(null);
  readonly errorMessage = signal<string | null>(null);

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : new HttpHeaders();
  }

  /**
   * Solicita el diagnóstico detallado de operaciones frente al estado actual en PostgreSQL (CU14).
   * Endpoint de solo lectura sin mutación: POST /api/offline/conflictos/diagnosticar
   */
  async diagnose(
    operations: OfflineSyncOperationInputDto[],
  ): Promise<OfflineConflictDiagnoseResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new Error('Sesión no válida o sin empresa asignada para diagnosticar conflictos.');
    }

    if (!operations || operations.length === 0) {
      const empty: OfflineConflictDiagnoseResponse = {
        success: true,
        empresa_id: empresaId,
        id_usuario: user.id_usuario,
        rol: user.rol,
        total_diagnosticadas: 0,
        ya_sincronizadas: 0,
        en_conflicto: 0,
        rechazadas: 0,
        listas_para_sincronizar: 0,
        diagnosticos: [],
        diagnosticos_por_uuid: {},
        fecha_diagnostico: new Date().toISOString(),
        mensaje: 'Sin operaciones para diagnosticar.',
      };
      this.lastDiagnosis.set(empty);
      return empty;
    }

    this.isDiagnosing.set(true);
    this.errorMessage.set(null);

    try {
      const isClient = user.rol.toUpperCase() === 'CLIENTE';
      let resolvedClientId: number | null = null;
      if (isClient && typeof this.storage.getClients === 'function') {
        try {
          const clients = await this.storage.getClients(empresaId, user.id_usuario);
          const matchedClient = clients?.find((c) => c.id_usuario === user.id_usuario);
          resolvedClientId = matchedClient ? matchedClient.id_cliente : null;
        } catch {
          resolvedClientId = null;
        }
      }

      const normalizedOps = operations.map((op) => {
        if (
          isClient &&
          op.tipo_operacion === 'COMPRA' &&
          op.payload?.id_cliente === user.id_usuario &&
          resolvedClientId !== user.id_usuario
        ) {
          return {
            ...op,
            payload: { ...op.payload, id_cliente: resolvedClientId },
          };
        }
        return op;
      });

      const payload: OfflineConflictDiagnoseRequest = {
        operaciones: normalizedOps,
      };

      const response = await firstValueFrom(
        this.http.post<OfflineConflictDiagnoseResponse>(
          `${environment.apiUrl}/api/offline/conflictos/diagnosticar`,
          payload,
          { headers: this.headers() },
        ),
      );

      this.lastDiagnosis.set(response);
      return response;
    } catch (err: unknown) {
      const msg =
        (err as any)?.error?.message ||
        (err instanceof Error ? err.message : 'Error al diagnosticar conflictos en el servidor.');
      this.errorMessage.set(msg);
      throw new Error(msg);
    } finally {
      this.isDiagnosing.set(false);
    }
  }

  /**
   * Resuelve operaciones en conflicto o rechazadas con consentimiento explícito del usuario (CU14).
   * POST /api/offline/conflictos/resolver
   * Aplica resultados de forma atómica en IndexedDB y propaga códigos oficiales a dependencias.
   */
  async resolve(
    resolutions: OfflineOperationResolutionInput[],
  ): Promise<OfflineConflictResolveResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new Error('Sesión no válida o sin empresa asignada para resolver operaciones.');
    }

    if (!resolutions || resolutions.length === 0) {
      throw new Error('Debe proporcionar al menos una instrucción de resolución.');
    }

    // Verificar que todas las resoluciones tengan consentimiento explícito
    for (const res of resolutions) {
      if (!res.consentimiento_usuario) {
        throw new Error(
          `La operación ${res.uuid_operacion} requiere consentimiento explícito del usuario para aplicar la resolución.`,
        );
      }
    }

    this.isResolving.set(true);
    this.errorMessage.set(null);

    try {
      const isClient = user.rol.toUpperCase() === 'CLIENTE';
      let resolvedClientId: number | null = null;
      if (isClient && typeof this.storage.getClients === 'function') {
        try {
          const clients = await this.storage.getClients(empresaId, user.id_usuario);
          const matchedClient = clients?.find((c) => c.id_usuario === user.id_usuario);
          resolvedClientId = matchedClient ? matchedClient.id_cliente : null;
        } catch {
          resolvedClientId = null;
        }
      }

      const normalizedResolutions = resolutions.map((res) => {
        let updatedPayload = res.payload;
        if (
          isClient &&
          res.tipo_operacion === 'COMPRA' &&
          res.payload?.id_cliente === user.id_usuario &&
          resolvedClientId !== user.id_usuario
        ) {
          updatedPayload = { ...res.payload, id_cliente: resolvedClientId };
        }

        let updatedSchedule = res.nueva_fecha_atencion_programada;
        if (typeof updatedSchedule === 'string' && updatedSchedule.trim().length > 0) {
          const raw = updatedSchedule.trim();
          const hasTz = /(?:Z|[+-]\d{2}:\d{2})$/i.test(raw);
          if (!hasTz) {
            updatedSchedule = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw)
              ? `${raw}:00-04:00`
              : `${raw}-04:00`;
          }
        }

        return {
          ...res,
          payload: updatedPayload,
          nueva_fecha_atencion_programada: updatedSchedule,
        };
      });

      const payload: OfflineConflictResolveRequest = {
        resoluciones: normalizedResolutions,
      };

      const response = await firstValueFrom(
        this.http.post<OfflineConflictResolveResponse>(
          `${environment.apiUrl}/api/offline/conflictos/resolver`,
          payload,
          { headers: this.headers() },
        ),
      );

      // Aplicar resultados en IndexedDB local
      await this.storage.applyConflictResolutionResults(
        empresaId,
        user.id_usuario,
        response.resultados,
        response.vinculaciones_codigos,
      );

      this.lastResolution.set(response);
      return response;
    } catch (err: unknown) {
      const msg =
        (err as any)?.error?.message ||
        (err instanceof Error ? err.message : 'Error al resolver conflictos en el servidor.');
      this.errorMessage.set(msg);
      throw new Error(msg);
    } finally {
      this.isResolving.set(false);
    }
  }

  /**
   * Traduce la acción de resolución a una etiqueta amigable y orientada al usuario.
   */
  actionLabel(action: OfflineResolutionAction): string {
    switch (action) {
      case 'REINTENTAR_SIN_CAMBIOS':
        return 'Reintentar sincronización';
      case 'ACEPTAR_PRECIO_SERVIDOR':
        return 'Aceptar precios actuales del servidor';
      case 'AJUSTAR_CANTIDAD_STOCK':
        return 'Ajustar cantidad al stock disponible';
      case 'QUITAR_PRENDA':
        return 'Retirar prendas agotadas';
      case 'REPROGRAMAR_HORARIO':
        return 'Reprogramar horario de recogida';
      case 'CAMBIAR_SUCURSAL':
        return 'Cambiar a otra sucursal';
      case 'COMPLETAR_TRANSICIONES_RESERVA':
        return 'Completar atención de reserva antecedente';
      case 'CONFIRMAR_Y_ATENDER_RESERVA':
        return 'Confirmar y atender reserva en servidor';
      case 'VINCULAR_OPERACION_EXISTENTE':
        return 'Vincular a operación ya registrada';
      case 'DESCARTAR_OPERACION':
        return 'Descartar operación';
      default:
        return action;
    }
  }

  /**
   * Traduce el código de conflicto a un texto legible para el usuario.
   */
  conflictTypeLabel(code?: string | null): string {
    switch (code) {
      case 'STOCK_INSUFICIENTE':
        return 'Stock insuficiente en sucursal';
      case 'PRECIO_MODIFICADO':
        return 'Precios o descuentos modificados';
      case 'HORARIO_VENCIDO':
        return 'Horario de recogida expirado';
      case 'HORARIO_NO_DISPONIBLE':
        return 'Horario no disponible o fuera de atención de la sucursal';
      case 'RESERVA_CANCELADA':
        return 'La reserva antecedente fue cancelada';
      case 'RESERVA_ESTADO_INVALIDO':
        return 'Estado de reserva no válido para la operación';
      case 'RESERVA_NO_ATENDIDA':
        return 'La reserva no ha sido atendida previamente';
      case 'DEPENDENCIA_BLOQUEADA':
        return 'Bloqueada por fallo en operación previa';
      case 'OPERACION_DUPLICADA':
      case 'RESERVA_VENTA_DUPLICADA':
        return 'Operación ya registrada en el servidor';
      case 'ERROR_REINTENTABLE':
        return 'Error transitorio del servidor (reintentable)';
      case 'CONCURRENCIA':
        return 'Conflicto de concurrencia temporal';
      case 'REGLA_NEGOCIO':
        return 'Validación comercial no superada';
      default:
        return code || 'Conflicto no especificado';
    }
  }
}

