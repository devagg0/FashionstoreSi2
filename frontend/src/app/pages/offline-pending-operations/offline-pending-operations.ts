import { CommonModule, DatePipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import {
  OfflineConflictDetail,
  OfflineOperationConflictDiagnosis,
  OfflineOperationResolutionInput,
  OfflineResolutionAction,
  OfflineSyncOperationInputDto,
} from '../../core/models/offline.model';
import { OfflineConflictsService } from '../../core/services/offline-conflicts.service';
import {
  OfflinePendingOperationItem,
  OfflinePendingOperationsService,
} from '../../core/services/offline-pending-operations.service';
import { OfflineSyncService } from '../../core/services/offline-sync.service';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-offline-pending-operations',
  standalone: true,
  imports: [CommonModule, DatePipe, FormsModule, Icon, RouterLink],
  templateUrl: './offline-pending-operations.html',
  styleUrl: './offline-pending-operations.scss',
})
export class OfflinePendingOperations implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly operationsService = inject(OfflinePendingOperationsService);
  private readonly syncService = inject(OfflineSyncService);
  private readonly conflictsService = inject(OfflineConflictsService);
  private readonly offlineService = inject(OfflineService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  protected readonly user = this.session.currentUser;
  protected readonly isOnline = this.offlineService.isOnline;
  protected readonly isSyncing = this.syncService.isSyncing;
  protected readonly isDiagnosing = this.conflictsService.isDiagnosing;
  protected readonly isResolving = this.conflictsService.isResolving;
  protected readonly operations = signal<OfflinePendingOperationItem[]>([]);
  protected readonly loading = signal(true);
  protected readonly verifying = signal(false);
  protected readonly feedbackMessage = signal<string | null>(null);
  protected readonly expandedUuids = signal<Set<string>>(new Set());

  // PK08 - CU14: Estado de diagnósticos y resoluciones
  protected readonly diagnosesByUuid = signal<Record<string, OfflineOperationConflictDiagnosis>>({});
  protected readonly activeConflictUuid = signal<string | null>(null);
  protected readonly diagnosingUuids = signal<Set<string>>(new Set());

  // Formulario interactivo de resolución
  protected readonly selectedAction = signal<OfflineResolutionAction | null>(null);
  protected readonly consentAccepted = signal<boolean>(false);
  protected readonly newSchedule = signal<string>('');
  protected readonly stockAdjustments = signal<Record<number, number>>({});

  // Filtros
  protected readonly filterTipo = signal<string>('TODOS');
  protected readonly filterEstadoSync = signal<string>('TODOS');

  protected readonly isClient = computed(
    () => this.user()?.rol?.toUpperCase() === 'CLIENTE',
  );
  protected readonly isStaff = computed(() => {
    const role = this.user()?.rol?.toUpperCase();
    return role === 'CAJERO' || role === 'ENCARGADO_SUCURSAL';
  });

  protected readonly totalPending = computed(
    () => this.operations().filter((o) => o.estado_sincronizacion === 'PENDIENTE').length,
  );
  protected readonly totalSynced = computed(
    () =>
      this.operations().filter(
        (o) => o.estado_sincronizacion === 'SINCRONIZADA' || o.confirmada_en_servidor,
      ).length,
  );
  protected readonly totalConflicts = computed(
    () =>
      this.operations().filter(
        (o) =>
          o.estado_sincronizacion === 'CONFLICTO' ||
          o.estado_sincronizacion === 'RECHAZADA',
      ).length,
  );

  /**
   * Determina si el botón «Sincronizar pendientes» debe mostrarse en la barra de herramientas:
   * 1. Rol autorizado: CLIENTE o CAJERO (o encargado de sucursal).
   * 2. Existen operaciones pendientes locales (o la sincronización está en curso).
   * 3. Cuenta con conectividad en línea con el servidor central FastAPI.
   */
  protected readonly canShowSync = computed(() => {
    const role = this.user()?.rol?.toUpperCase();
    const isAllowedRole = role === 'CLIENTE' || role === 'CAJERO' || role === 'ENCARGADO_SUCURSAL';
    const hasPendingOps = this.totalPending() > 0 || this.isSyncing();
    return Boolean(isAllowedRole && hasPendingOps && this.isOnline());
  });

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const items = await this.operationsService.loadLocalOperations({
        tipo: this.filterTipo(),
        estadoSync: this.filterEstadoSync(),
      });
      this.operations.set(items);
    } catch {
      this.operations.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  onFilterChange(): void {
    void this.load();
  }

  toggleDetails(uuid: string): void {
    this.expandedUuids.update((set) => {
      const copy = new Set(set);
      if (copy.has(uuid)) {
        copy.delete(uuid);
      } else {
        copy.add(uuid);
      }
      return copy;
    });
  }

  isExpanded(uuid: string): boolean {
    return this.expandedUuids().has(uuid);
  }

  /**
   * PK08 - CU13: Sincronización manual de operaciones pendientes desde la bandeja de operaciones offline.
   * Con protección contra doble clic, indicador de progreso y actualización automática de contadores y estados.
   */
  async syncNow(): Promise<void> {
    if (this.isSyncing() || this.loading() || this.verifying()) {
      return;
    }

    if (!this.isOnline()) {
      this.feedbackMessage.set(
        'Modo sin conexión: para sincronizar operaciones con el servidor central requieres conexión a internet.',
      );
      return;
    }

    const role = this.user()?.rol?.toUpperCase();
    const isAllowedRole = role === 'CLIENTE' || role === 'CAJERO' || role === 'ENCARGADO_SUCURSAL';
    if (!isAllowedRole) {
      this.feedbackMessage.set('El rol actual no tiene autorización para sincronizar operaciones offline.');
      return;
    }

    this.feedbackMessage.set(null);
    try {
      const resp = await this.syncService.syncPendingOperations({ manual: true });
      if (resp.total_operaciones === 0) {
        this.feedbackMessage.set('No hay operaciones pendientes de sincronización en este momento.');
      } else {
        this.feedbackMessage.set(resp.mensaje);
      }
      await this.load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error durante la sincronización';
      this.feedbackMessage.set(`Error al sincronizar: ${msg}`);
      await this.load();
    }
  }

  verifyWithServer(): void {
    if (!this.isOnline()) {
      this.feedbackMessage.set(
        'Modo sin conexión: para contrastar con el servidor central requieres conexión a internet.',
      );
      return;
    }

    const currentOps = this.operations();
    if (currentOps.length === 0) return;

    this.verifying.set(true);
    this.feedbackMessage.set(null);

    const uuids = currentOps.map((o) => o.uuid_operacion);
    this.operationsService
      .verifyBatchStatuses(uuids)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.verifying.set(false);
          if (!resp || !resp.success) {
            this.feedbackMessage.set(
              'No fue posible verificar estados con el servidor central en este momento.',
            );
            return;
          }

          const serverMap = resp.operaciones || {};
          let verifiedCount = 0;

          const updated = currentOps.map((op) => {
            const serverInfo = serverMap[op.uuid_operacion];
            if (!serverInfo) {
              // Regla CU12: si el servidor no la encuentra, sigue PENDIENTE
              return op;
            }

            if (serverInfo.confirmada) {
              verifiedCount++;
              return {
                ...op,
                confirmada_en_servidor: true,
                estado_sincronizacion: 'SINCRONIZADA' as const,
                codigo_servidor: serverInfo.codigo_servidor ?? op.codigo_servidor,
              };
            }

            if (serverInfo.estado_sincronizacion === 'CONFLICTO') {
              return {
                ...op,
                estado_sincronizacion: 'CONFLICTO' as const,
                motivo_servidor: serverInfo.motivo ?? 'Conflicto detectado en servidor',
              };
            }

            if (serverInfo.estado_sincronizacion === 'RECHAZADA') {
              return {
                ...op,
                estado_sincronizacion: 'RECHAZADA' as const,
                motivo_servidor: serverInfo.motivo ?? 'Operación rechazada en servidor',
              };
            }

            return op;
          });

          this.operations.set(updated);
          this.feedbackMessage.set(
            `Verificación completada: ${verifiedCount} de ${resp.total_consultados} operaciones confirmadas en el servidor.`,
          );
        },
        error: () => {
          this.verifying.set(false);
          this.feedbackMessage.set(
            'Error de comunicación al consultar el estado de sincronización.',
          );
        },
      });
  }

  typeLabel(type: string): string {
    switch (type) {
      case 'RESERVA':
        return 'Reserva de prendas';
      case 'COMPRA':
        return 'Compra digital';
      case 'VENTA':
        return 'Venta presencial POS';
      case 'TRANSICION_RESERVA':
        return 'Atención de reserva';
      default:
        return type;
    }
  }

  syncStatusLabel(status: string): string {
    switch (status) {
      case 'PENDIENTE':
        return 'Pendiente de sincronización';
      case 'SINCRONIZADA':
        return 'Sincronizada con éxito';
      case 'CONFLICTO':
        return 'Conflicto detectado';
      case 'RECHAZADA':
        return 'Rechazada por servidor';
      default:
        return status;
    }
  }

  formatMoney(val?: number | string | null): string {
    if (val === undefined || val === null || val === '') return '—';
    const num = Number(val);
    if (isNaN(num)) return '—';
    return `Bs ${num.toLocaleString('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  dismissNotice(): void {
    this.feedbackMessage.set(null);
  }

  // =========================================================================
  // PK08 - CU14: MÉTODOS DE DIAGNÓSTICO Y RESOLUCIÓN DE CONFLICTOS
  // =========================================================================

  hasConflict(op: OfflinePendingOperationItem): boolean {
    return (
      op.estado_sincronizacion === 'CONFLICTO' ||
      op.estado_sincronizacion === 'RECHAZADA' ||
      Boolean(op.motivo_servidor && op.estado_sincronizacion !== 'SINCRONIZADA')
    );
  }

  isDiagnosingOp(uuid: string): boolean {
    return this.diagnosingUuids().has(uuid);
  }

  getDiagnosis(uuid: string): OfflineOperationConflictDiagnosis | undefined {
    return this.diagnosesByUuid()[uuid];
  }

  isOperationBlocked(op: OfflinePendingOperationItem): boolean {
    const diag = this.diagnosesByUuid()[op.uuid_operacion];
    if (diag?.bloqueada_por_dependencia) return true;

    if (op.depende_de_uuid) {
      const parent = this.operations().find(
        (o) => o.uuid_operacion === op.depende_de_uuid || o.uuid_entidad === op.depende_de_uuid,
      );
      if (parent && parent.estado_sincronizacion !== 'SINCRONIZADA' && !parent.confirmada_en_servidor) {
        return true;
      }
    }
    return false;
  }

  getBlockedReason(op: OfflinePendingOperationItem): string | null {
    if (this.isOperationBlocked(op)) {
      return 'Operación bloqueada: la reserva o transición antecedente aún no está sincronizada o presenta un conflicto que debes resolver primero.';
    }
    return null;
  }

  async manageConflict(op: OfflinePendingOperationItem): Promise<void> {
    if (this.activeConflictUuid() === op.uuid_operacion) {
      this.closeConflictPanel();
      return;
    }

    const cached = this.diagnosesByUuid()[op.uuid_operacion];
    if (cached) {
      this.setupResolutionForm(op, cached);
      this.activeConflictUuid.set(op.uuid_operacion);
      return;
    }

    await this.diagnoseOperation(op);
  }

  async diagnoseOperation(op: OfflinePendingOperationItem): Promise<void> {
    if (!this.isOnline()) {
      this.feedbackMessage.set(
        'Modo sin conexión: para diagnosticar conflictos contra el estado actual de PostgreSQL requieres conexión.',
      );
      return;
    }

    this.diagnosingUuids.update((s) => new Set(s).add(op.uuid_operacion));
    this.feedbackMessage.set(null);

    let tipoOp = op.tipo as any;
    if (tipoOp === 'VENTA' && op.rol === 'CLIENTE') {
      tipoOp = 'COMPRA';
    }

    const dto: OfflineSyncOperationInputDto = {
      uuid_operacion: op.uuid_operacion,
      uuid_entidad: op.uuid_entidad,
      tipo_operacion: tipoOp,
      codigo_local: op.codigo_provisional,
      depende_de_uuid: op.depende_de_uuid,
      payload: op.payload || {},
    };

    try {
      const resp = await this.conflictsService.diagnose([dto]);
      const diag = resp.diagnosticos_por_uuid[op.uuid_operacion] || resp.diagnosticos[0];
      if (diag) {
        this.diagnosesByUuid.update((m) => ({ ...m, [op.uuid_operacion]: diag }));
        op.diagnostico_cu14 = diag;
        this.setupResolutionForm(op, diag);
        this.activeConflictUuid.set(op.uuid_operacion);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al diagnosticar conflicto';
      this.feedbackMessage.set(`Error de diagnóstico: ${msg}`);
    } finally {
      this.diagnosingUuids.update((s) => {
        const copy = new Set(s);
        copy.delete(op.uuid_operacion);
        return copy;
      });
    }
  }

  async diagnoseAllConflicts(): Promise<void> {
    if (!this.isOnline()) {
      this.feedbackMessage.set(
        'Modo sin conexión: para diagnosticar conflictos contra PostgreSQL requieres conexión.',
      );
      return;
    }

    const conflictedOps = this.operations().filter((o) => this.hasConflict(o));
    if (conflictedOps.length === 0) {
      this.feedbackMessage.set('No se encontraron operaciones en conflicto para diagnosticar.');
      return;
    }

    const dtos: OfflineSyncOperationInputDto[] = conflictedOps.map((op) => {
      let tipoOp = op.tipo as any;
      if (tipoOp === 'VENTA' && op.rol === 'CLIENTE') {
        tipoOp = 'COMPRA';
      }
      return {
        uuid_operacion: op.uuid_operacion,
        uuid_entidad: op.uuid_entidad,
        tipo_operacion: tipoOp,
        codigo_local: op.codigo_provisional,
        depende_de_uuid: op.depende_de_uuid,
        payload: op.payload || {},
      };
    });

    try {
      const resp = await this.conflictsService.diagnose(dtos);
      this.diagnosesByUuid.update((m) => ({ ...m, ...resp.diagnosticos_por_uuid }));
      this.feedbackMessage.set(
        `Diagnóstico completado: ${resp.en_conflicto} en conflicto, ${resp.rechazadas} rechazadas, ${resp.listas_para_sincronizar} listas para sincronizar.`,
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al diagnosticar conflictos';
      this.feedbackMessage.set(`Error de diagnóstico masivo: ${msg}`);
    }
  }

  setupResolutionForm(op: OfflinePendingOperationItem, diag: OfflineOperationConflictDiagnosis): void {
    const allowed = diag.acciones_permitidas || [];
    this.selectedAction.set(allowed[0] || 'REINTENTAR_SIN_CAMBIOS');
    this.consentAccepted.set(false);

    if (diag.datos_actuales_servidor?.horarios_sugeridos?.length > 0) {
      this.newSchedule.set(diag.datos_actuales_servidor.horarios_sugeridos[0]);
    } else {
      this.newSchedule.set('');
    }

    const stockMap: Record<number, number> = {};
    for (const v of diag.datos_actuales_servidor?.variantes || []) {
      stockMap[v.id_variante_producto] = Math.min(v.cantidad_solicitada, v.stock_disponible);
    }
    this.stockAdjustments.set(stockMap);
  }

  closeConflictPanel(): void {
    this.activeConflictUuid.set(null);
    this.selectedAction.set(null);
    this.consentAccepted.set(false);
  }

  selectAction(action: OfflineResolutionAction): void {
    this.selectedAction.set(action);
  }

  updateStockAdjustment(variantId: number, qty: number): void {
    this.stockAdjustments.update((m) => ({
      ...m,
      [variantId]: Math.max(0, qty),
    }));
  }

  async applyResolution(op: OfflinePendingOperationItem): Promise<void> {
    if (this.isResolving()) return;

    if (!this.isOnline()) {
      this.feedbackMessage.set(
        'Modo sin conexión: para resolver conflictos y confirmar cambios en PostgreSQL requieres conexión a internet.',
      );
      return;
    }

    if (!this.consentAccepted()) {
      this.feedbackMessage.set(
        'Consentimiento requerido: debes marcar la casilla de confirmación para autorizar la resolución.',
      );
      return;
    }

    if (this.isOperationBlocked(op)) {
      this.feedbackMessage.set(
        this.getBlockedReason(op) || 'Operación bloqueada por antecedentes no resueltos.',
      );
      return;
    }

    const action = this.selectedAction();
    if (!action) {
      this.feedbackMessage.set('Debes seleccionar una acción de resolución permitida.');
      return;
    }

    let tipoOp = op.tipo as any;
    if (tipoOp === 'VENTA' && op.rol === 'CLIENTE') {
      tipoOp = 'COMPRA';
    }

    const resolutionInput: OfflineOperationResolutionInput = {
      uuid_operacion: op.uuid_operacion,
      uuid_entidad: op.uuid_entidad,
      tipo_operacion: tipoOp,
      codigo_local: op.codigo_provisional,
      depende_de_uuid: op.depende_de_uuid,
      accion_resolucion: action,
      consentimiento_usuario: true,
      payload: op.payload || {},
      nueva_fecha_atencion_programada:
        action === 'REPROGRAMAR_HORARIO' ? this.newSchedule() : undefined,
      cantidades_ajustadas:
        action === 'AJUSTAR_CANTIDAD_STOCK' ? this.stockAdjustments() : undefined,
    };

    try {
      const response = await this.conflictsService.resolve([resolutionInput]);
      const resItem = response.resultados_por_uuid[op.uuid_operacion] || response.resultados[0];

      if (resItem?.confirmada) {
        const code = resItem.codigo_servidor ? `(Código oficial: ${resItem.codigo_servidor})` : '';
        this.feedbackMessage.set(`Resolución confirmada con éxito en el servidor central. ${code}`);
      } else if (resItem?.descartada_por_usuario) {
        this.feedbackMessage.set('Operación descartada correctamente sin eliminar su comprobante local.');
      } else {
        this.feedbackMessage.set(response.mensaje);
      }

      this.closeConflictPanel();
      await this.load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error al procesar la resolución';
      this.feedbackMessage.set(`Error al resolver: ${msg}`);
      await this.load();
    }
  }

  actionLabel(action: OfflineResolutionAction): string {
    return this.conflictsService.actionLabel(action);
  }

  conflictTypeLabel(code?: string | null): string {
    return this.conflictsService.conflictTypeLabel(code);
  }
}
