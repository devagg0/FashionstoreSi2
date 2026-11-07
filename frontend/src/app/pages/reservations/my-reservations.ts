import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { OfflineReceiptData } from '../../core/models/offline.model';
import { OfflineService } from '../../core/services/offline.service';
import {
  ClientReservationsService,
  ReservationState,
  ReservationSummary,
} from '../../core/services/client-reservations.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-my-reservations',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  templateUrl: './my-reservations.html',
  styleUrl: './my-reservations.scss',
})
export class MyReservations implements OnInit {
  private readonly service = inject(ClientReservationsService);
  private readonly session = inject(SessionService);
  private readonly offlineService = inject(OfflineService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly states: ReservationState[] = [
    'PENDIENTE',
    'CONFIRMADA',
    'ATENDIDA',
    'CANCELADA',
    'EXPIRADA',
  ];
  protected readonly state = new FormControl<ReservationState | ''>('', { nonNullable: true });
  protected readonly selectedState = toSignal(this.state.valueChanges, { initialValue: this.state.value });
  protected readonly reservations = signal<ReservationSummary[]>([]);
  protected readonly pagination = signal({ page: 1, page_size: 10, total: 0, total_pages: 0 });
  protected readonly loading = signal(false);
  protected readonly cancelling = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly successMessage = signal('');
  protected readonly pendingCancellation = signal<ReservationSummary | null>(null);
  /** Reservas guardadas sin internet (CU10/CU13) y su estado de sincronización local. */
  protected readonly pendingLocal = signal<OfflineReceiptData[]>([]);

  /**
   * Reservas locales que coinciden con el filtro actual, evitando duplicados cuando
   * una reserva ya sincronizada viene incluida en el listado oficial del servidor.
   */
  protected readonly filteredPendingLocal = computed(() => {
    const selectedState = this.selectedState();
    const serverRows = this.reservations();
    const serverIds = new Set(serverRows.map((r) => r.id_reserva));
    const serverCodes = new Set(serverRows.map((r) => r.codigo));
    const offline = this.isOffline();

    const deduped = this.pendingLocal().filter((local) => {
      if (local.id_reserva && serverIds.has(local.id_reserva)) {
        return false;
      }
      if (local.codigo_servidor && serverCodes.has(local.codigo_servidor)) {
        return false;
      }
      if (local.estado === 'SINCRONIZADA' && !offline) {
        return false;
      }
      return true;
    });

    if (!selectedState) {
      return deduped;
    }
    if (selectedState === 'PENDIENTE') {
      return deduped.filter(
        (local) =>
          local.estado === 'REGISTRADA_LOCAL' ||
          local.estado === 'ENVIADA' ||
          local.estado === 'SINCRONIZADA',
      );
    }
    if (selectedState === 'CANCELADA') {
      return deduped.filter(
        (local) => local.estado === 'RECHAZADA' || local.estado === 'EN_CONFLICTO',
      );
    }
    return [];
  });

  /** Total combinado de reservas del servidor y pendientes locales. */
  protected readonly totalCount = computed(() => {
    return this.pagination().total + this.filteredPendingLocal().length;
  });

  protected isOffline(): boolean {
    return (
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine)
    );
  }

  ngOnInit(): void {
    if (typeof window !== 'undefined') {
      const handleOnline = () => this.load();
      const handleOffline = () => this.load();
      window.addEventListener('online', handleOnline);
      window.addEventListener('offline', handleOffline);
      this.destroyRef.onDestroy(() => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
      });
    }

    this.load();
    this.state.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  protected load(page = 1): void {
    this.errorMessage.set('');
    void this.offlineService
      .getPendingClientReservations()
      .then((rows) => this.pendingLocal.set(rows));

    if (this.isOffline()) {
      this.loading.set(false);
      this.reservations.set([]);
      this.pagination.set({ page: 1, page_size: 10, total: 0, total_pages: 0 });
      return;
    }

    this.loading.set(true);
    this.service
      .listReservations({ estado: this.state.value || undefined, page, pageSize: 10 })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: ({ data, pagination }) => {
          this.reservations.set(data);
          this.pagination.set(pagination);
        },
        error: (error: HttpErrorResponse) => {
          if (error.status === 0 || this.isOffline()) {
            this.reservations.set([]);
            this.errorMessage.set('');
            return;
          }
          this.errorMessage.set(this.resolveError(error));
        },
      });
  }

  protected askCancel(reservation: ReservationSummary): void {
    if (reservation.cancelable) {
      this.successMessage.set('');
      this.errorMessage.set('');
      this.pendingCancellation.set(reservation);
    }
  }

  protected cancel(): void {
    const reservation = this.pendingCancellation();
    if (!reservation || this.cancelling()) return;
    this.cancelling.set(true);
    this.service
      .cancelReservation(reservation.id_reserva)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.cancelling.set(false)),
      )
      .subscribe({
        next: ({ data }) => {
          this.pendingCancellation.set(null);
          this.reservations.update((rows) =>
            rows.map((row) => (row.id_reserva === data.id_reserva ? data : row)),
          );
          this.successMessage.set('La reserva fue cancelada y el stock quedó liberado.');
        },
        error: (error: HttpErrorResponse) => {
          this.pendingCancellation.set(null);
          this.errorMessage.set(this.resolveError(error));
          this.load(this.pagination().page);
        },
      });
  }

  protected stateLabel(state: ReservationState): string {
    return state.charAt(0) + state.slice(1).toLowerCase();
  }

  protected localStateAttr(local: OfflineReceiptData): string {
    if (local.estado === 'RECHAZADA' || local.estado === 'EN_CONFLICTO') {
      return 'CANCELADA';
    }
    if (local.estado === 'SINCRONIZADA') {
      return 'CONFIRMADA';
    }
    return 'PENDIENTE';
  }

  protected localStateLabel(local: OfflineReceiptData): string {
    if (local.estado === 'RECHAZADA') {
      return 'Rechazada por servidor';
    }
    if (local.estado === 'EN_CONFLICTO') {
      return 'En conflicto de sincronización';
    }
    if (local.estado === 'SINCRONIZADA') {
      return 'Sincronizada';
    }
    return 'Pendiente de sincronización';
  }

  protected localStateNotice(local: OfflineReceiptData): string {
    if (local.estado === 'RECHAZADA' || local.estado === 'EN_CONFLICTO') {
      return local.motivo_servidor || 'No pudo registrarse en el servidor central.';
    }
    if (local.estado === 'SINCRONIZADA') {
      return local.codigo_servidor
        ? `Confirmada con código oficial ${local.codigo_servidor}.`
        : 'Confirmada en el servidor central.';
    }
    return (
      local.motivo_servidor ||
      'Guardada en este dispositivo; aún no confirmada por el servidor.'
    );
  }

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/La_Paz',
    }).format(
      new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`),
    );
  }

  protected formatLocalDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/La_Paz',
    }).format(new Date(value));
  }

  protected formatMoney(value: string | number): string {
    return `Bs ${Number(value).toLocaleString('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  @HostListener('document:keydown.escape')
  protected closeConfirmation(): void {
    if (!this.cancelling()) this.pendingCancellation.set(null);
  }

  private resolveError(error: HttpErrorResponse): string {
    if (error.status === 401) {
      this.session.logout();
      void this.router.navigateByUrl('/login');
      return 'Tu sesión expiró. Inicia sesión nuevamente.';
    }
    if (typeof error.error?.message === 'string' && [404, 409, 422].includes(error.status)) {
      return error.error.message;
    }
    return 'No pudimos procesar tus reservas. Inténtalo nuevamente.';
  }
}
