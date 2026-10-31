import { CommonModule } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  SaasCompaniesService,
  SaasCompany,
} from '../../../core/services/saas-companies.service';
import {
  SaasSubscriptionsService,
  SubscriptionDetail,
} from '../../../core/services/saas-subscriptions.service';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-manage-subscriptions',
  standalone: true,
  imports: [CommonModule, FormsModule, Icon],
  templateUrl: './manage-subscriptions.html',
  styleUrl: './manage-subscriptions.scss',
})
export class ManageSubscriptions implements OnInit {
  private readonly subscriptionsService = inject(SaasSubscriptionsService);
  private readonly companiesService = inject(SaasCompaniesService);

  readonly loading = signal<boolean>(true);
  readonly updatingStatus = signal<boolean>(false);
  readonly subscriptions = signal<SubscriptionDetail[]>([]);
  readonly companies = signal<SaasCompany[]>([]);

  // Filtros
  readonly selectedCompanyId = signal<number | null>(null);
  readonly selectedStatus = signal<string>('TODOS');

  // Mensajes
  readonly successMessage = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly modalError = signal<string | null>(null);

  // Modal para cambio de estado
  readonly statusModalOpen = signal<boolean>(false);
  readonly targetSubscription = signal<SubscriptionDetail | null>(null);
  readonly targetNewStatus = signal<'ACTIVA' | 'SUSPENDIDA' | 'CANCELADA' | 'EXPIRADA'>('SUSPENDIDA');
  statusChangeReason = '';

  ngOnInit(): void {
    this.loadCompanies();
    this.loadSubscriptions();
  }

  loadCompanies(): void {
    this.companiesService.listCompanies({ pageSize: 100 }).subscribe({
      next: (resp) => {
        this.companies.set(resp.data);
      },
      error: () => {
        // No bloqueante si falla la lista de filtros de empresas
      },
    });
  }

  loadSubscriptions(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    const filters: { empresa_id?: number | null; estado?: string | null } = {};
    if (this.selectedCompanyId()) {
      filters.empresa_id = this.selectedCompanyId();
    }
    if (this.selectedStatus() !== 'TODOS') {
      filters.estado = this.selectedStatus();
    }

    this.subscriptionsService.adminListSubscriptions(filters).subscribe({
      next: (resp) => {
        this.subscriptions.set(resp.data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.errorMessage.set(
          err.error?.message || 'No fue posible consultar las suscripciones empresariales.',
        );
      },
    });
  }

  onFilterChange(): void {
    this.loadSubscriptions();
  }

  openStatusModal(
    sub: SubscriptionDetail,
    newStatus: 'ACTIVA' | 'SUSPENDIDA' | 'CANCELADA' | 'EXPIRADA',
  ): void {
    this.targetSubscription.set(sub);
    this.targetNewStatus.set(newStatus);
    this.statusChangeReason = '';
    this.modalError.set(null);
    this.statusModalOpen.set(true);
  }

  closeStatusModal(): void {
    if (this.updatingStatus()) return;
    this.statusModalOpen.set(false);
    this.targetSubscription.set(null);
    this.modalError.set(null);
  }

  confirmStatusChange(): void {
    const sub = this.targetSubscription();
    if (!sub || this.updatingStatus()) return;

    this.updatingStatus.set(true);
    this.modalError.set(null);

    this.subscriptionsService
      .adminUpdateSubscriptionStatus(sub.id_suscripcion, {
        nuevo_estado: this.targetNewStatus(),
        motivo: this.statusChangeReason.trim() || undefined,
      })
      .subscribe({
        next: (resp) => {
          this.updatingStatus.set(false);
          this.closeStatusModal();
          this.successMessage.set(
            `Estado de la suscripción actualizado exitosamente a ${resp.data.estado}.`,
          );
          this.loadSubscriptions();
        },
        error: (err) => {
          this.updatingStatus.set(false);
          this.modalError.set(
            err.error?.message || 'No fue posible actualizar el estado de la suscripción.',
          );
        },
      });
  }

  getStatusActionLabel(status: string): string {
    switch (status) {
      case 'SUSPENDIDA':
        return 'Suspender suscripción';
      case 'ACTIVA':
        return 'Reactivar suscripción';
      case 'CANCELADA':
        return 'Cancelar suscripción';
      case 'EXPIRADA':
        return 'Marcar como expirada';
      default:
        return 'Cambiar estado';
    }
  }
}
