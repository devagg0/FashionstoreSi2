import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import {
  ClientReservationsService,
  ReservationDetail,
  ReservationState,
} from '../../core/services/client-reservations.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-reservation-detail-page',
  imports: [RouterLink, Icon],
  templateUrl: './reservation-detail.html',
  styleUrl: './reservation-detail.scss',
})
export class ReservationDetailPage implements OnInit {
  private readonly service = inject(ClientReservationsService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly reservation = signal<ReservationDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly cancelling = signal(false);
  protected readonly confirmCancel = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly successMessage = signal('');
  protected readonly failedImages = signal<Set<number>>(new Set());

  ngOnInit(): void {
    if (this.route.snapshot.queryParamMap.get('creada') === '1') {
      this.successMessage.set('Tu reserva fue creada correctamente.');
    }
    this.load();
  }

  protected load(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (!Number.isInteger(id) || id <= 0) {
      this.loading.set(false);
      this.errorMessage.set('La reserva solicitada no es válida.');
      return;
    }
    this.loading.set(true);
    this.errorMessage.set('');
    this.service
      .getReservation(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: ({ data }) => this.reservation.set(data),
        error: (error: HttpErrorResponse) => this.errorMessage.set(this.resolveError(error)),
      });
  }

  protected cancel(): void {
    const reservation = this.reservation();
    if (!reservation?.cancelable || this.cancelling()) return;
    this.cancelling.set(true);
    this.errorMessage.set('');
    this.service
      .cancelReservation(reservation.id_reserva)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.cancelling.set(false)),
      )
      .subscribe({
        next: ({ data }) => {
          this.reservation.set(data);
          this.confirmCancel.set(false);
          this.successMessage.set('La reserva fue cancelada y el stock quedó liberado.');
        },
        error: (error: HttpErrorResponse) => {
          this.confirmCancel.set(false);
          this.errorMessage.set(this.resolveError(error));
          this.load();
        },
      });
  }

  protected imageFailed(id: number): void {
    this.failedImages.update((current) => new Set([...current, id]));
  }

  protected stateLabel(state: ReservationState): string {
    return state.charAt(0) + state.slice(1).toLowerCase();
  }

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'long',
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
    if (!this.cancelling()) this.confirmCancel.set(false);
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
    return 'No pudimos consultar la reserva. Inténtalo nuevamente.';
  }
}
