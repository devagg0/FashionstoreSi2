import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
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
  protected readonly reservations = signal<ReservationSummary[]>([]);
  protected readonly pagination = signal({ page: 1, page_size: 10, total: 0, total_pages: 0 });
  protected readonly loading = signal(false);
  protected readonly cancelling = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly successMessage = signal('');
  protected readonly pendingCancellation = signal<ReservationSummary | null>(null);

  ngOnInit(): void {
    this.load();
    this.state.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  protected load(page = 1): void {
    this.loading.set(true);
    this.errorMessage.set('');
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
        error: (error: HttpErrorResponse) => this.errorMessage.set(this.resolveError(error)),
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

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/La_Paz',
    }).format(
      new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`),
    );
  }

  protected formatMoney(value: string): string {
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
