import { CommonModule, DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  ClientOperationDetailResponse,
  ClientOperationItem,
  ClientOperationsFilterParams,
  ClientOperationsListResponse,
  ClientOperationsService,
  ClientOperationsSummaryResponse,
} from '../../core/services/client-operations.service';
import { Icon, IconName } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-client-operations',
  standalone: true,
  imports: [CommonModule, RouterLink, DatePipe, DecimalPipe, FormsModule, Icon],
  templateUrl: './client-operations.html',
  styleUrl: './client-operations.scss',
})
export class ClientOperationsPage implements OnInit {
  private readonly operationsService = inject(ClientOperationsService);
  private readonly destroyRef = inject(DestroyRef);

  // Estados de vista
  readonly loading = signal<boolean>(false);
  readonly summaryLoading = signal<boolean>(false);
  readonly detailLoading = signal<boolean>(false);
  readonly error = signal<string>('');

  // Datos
  readonly operations = signal<ClientOperationItem[]>([]);
  readonly localOperations = signal<ClientOperationItem[]>([]);
  readonly summary = signal<ClientOperationsSummaryResponse | null>(null);
  readonly selectedOperation = signal<ClientOperationItem | null>(null);

  // Paginación y totales
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(15);
  readonly totalServerItems = signal<number>(0);
  readonly totalPages = signal<number>(1);
  readonly totalesPorTipo = signal<Record<string, number>>({});
  readonly totalesPorEstado = signal<Record<string, number>>({});

  // Filtros interactivos
  readonly filterTipo = signal<'COMPRA' | 'RESERVA' | 'PAGO' | ''>('');
  readonly filterEstado = signal<string>('');
  readonly filterOrigen = signal<'ONLINE' | 'OFFLINE_SYNC' | 'LOCAL_OFFLINE' | ''>('');

  // Lista combinada de operaciones locales del dispositivo + remotas sincronizadas
  readonly combinedOperations = computed(() => {
    const local = this.localOperations();
    const server = this.operations();

    let combined = [...local, ...server];

    const tipo = this.filterTipo();
    if (tipo) {
      combined = combined.filter((op) => op.tipo === tipo);
    }

    const estado = this.filterEstado();
    if (estado) {
      if (estado === 'CONFIRMADA') {
        combined = combined.filter((op) => op.confirmada);
      } else if (estado === 'PENDIENTE') {
        combined = combined.filter((op) => op.estado === 'PENDIENTE' || op.estado === 'PENDIENTE_SINCRONIZACION');
      } else if (estado === 'RECHAZADA') {
        combined = combined.filter((op) => ['RECHAZADA', 'RECHAZADO', 'ANULADA', 'CANCELADA', 'EXPIRADA', 'CONFLICTO'].includes(op.estado));
      } else {
        combined = combined.filter((op) => op.estado === estado);
      }
    }

    const origen = this.filterOrigen();
    if (origen) {
      combined = combined.filter((op) => op.origen === origen);
    }

    return combined;
  });

  ngOnInit(): void {
    this.loadSummary();
    this.loadOperations(1);
    this.loadLocalPending();
  }

  loadSummary(): void {
    this.summaryLoading.set(true);
    this.operationsService
      .getSummary()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.summary.set(res);
          this.summaryLoading.set(false);
        },
        error: () => {
          this.summaryLoading.set(false);
        },
      });
  }

  loadOperations(page: number = 1): void {
    this.loading.set(true);
    this.error.set('');

    const params: ClientOperationsFilterParams = {
      tipo: this.filterTipo() || undefined,
      estado: this.filterEstado() || undefined,
      page,
      page_size: this.pageSize(),
    };

    this.operationsService
      .getOperations(params)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: ClientOperationsListResponse) => {
          this.operations.set(res.items);
          this.currentPage.set(res.page);
          this.totalServerItems.set(res.total);
          this.totalPages.set(res.total_pages);
          this.totalesPorTipo.set(res.totales_por_tipo || {});
          this.totalesPorEstado.set(res.totales_por_estado || {});
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          const msg =
            err?.error?.message ||
            'No fue posible cargar tus operaciones. Por favor intenta nuevamente.';
          this.error.set(msg);
        },
      });
  }

  loadLocalPending(): void {
    this.operationsService
      .getLocalPendingOperations()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (items) => {
          this.localOperations.set(items);
        },
        error: () => {
          this.localOperations.set([]);
        },
      });
  }

  setTipoFilter(tipo: 'COMPRA' | 'RESERVA' | 'PAGO' | ''): void {
    this.filterTipo.set(tipo);
    this.loadOperations(1);
  }

  onEstadoChange(estado: string): void {
    this.filterEstado.set(estado);
    this.loadOperations(1);
  }

  onOrigenChange(origen: 'ONLINE' | 'OFFLINE_SYNC' | 'LOCAL_OFFLINE' | ''): void {
    this.filterOrigen.set(origen);
  }

  clearFilters(): void {
    this.filterTipo.set('');
    this.filterEstado.set('');
    this.filterOrigen.set('');
    this.loadOperations(1);
  }

  openDetail(op: ClientOperationItem): void {
    if (op.origen === 'LOCAL_OFFLINE') {
      // Operación local del dispositivo; ya contiene los datos básicos
      this.selectedOperation.set(op);
      return;
    }

    this.detailLoading.set(true);
    this.selectedOperation.set(op);

    this.operationsService
      .getOperationDetail(op.tipo, op.id_referencia)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res: ClientOperationDetailResponse) => {
          this.selectedOperation.set(res.data);
          this.detailLoading.set(false);
        },
        error: () => {
          // Mantener la información previa disponible
          this.detailLoading.set(false);
        },
      });
  }

  closeDetail(): void {
    this.selectedOperation.set(null);
  }

  getStatusTone(op: ClientOperationItem): 'good' | 'pending' | 'bad' | 'neutral' {
    if (op.confirmada || op.estado === 'APROBADO' || op.estado === 'COMPLETADA' || op.estado === 'CONFIRMADA' || op.estado === 'ATENDIDA') {
      return 'good';
    }
    if (op.estado === 'PENDIENTE' || op.estado === 'PENDIENTE_SINCRONIZACION') {
      return 'pending';
    }
    if (['RECHAZADA', 'RECHAZADO', 'ANULADA', 'CANCELADA', 'EXPIRADA', 'CONFLICTO'].includes(op.estado)) {
      return 'bad';
    }
    return 'neutral';
  }

  getOriginBadge(origen: string): { label: string; tone: string; icon: IconName } {
    if (origen === 'OFFLINE_SYNC') {
      return {
        label: 'Sincronizada (Offline)',
        tone: 'origin-sync',
        icon: 'refresh',
      };
    }
    if (origen === 'LOCAL_OFFLINE') {
      return {
        label: 'Local en dispositivo (No confirmada)',
        tone: 'origin-local',
        icon: 'alert-circle',
      };
    }
    return {
      label: 'Online',
      tone: 'origin-online',
      icon: 'sparkles',
    };
  }
}
