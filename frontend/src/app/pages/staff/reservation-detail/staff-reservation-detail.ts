import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { catchError, finalize, forkJoin, of } from 'rxjs';
import { CatalogService } from '../../../core/services/catalog.service';
import { ReservationState } from '../../../core/services/client-reservations.service';
import { StaffApiErrorService } from '../../../core/services/staff-api-error.service';
import {
  StaffReservationDetail,
  StaffReservationsService,
} from '../../../core/services/staff-reservations.service';
import { Icon } from '../../../shared/components/icon/icon';

type StaffAction = 'confirm' | 'attend';

@Component({
  selector: 'app-staff-reservation-detail',
  imports: [Icon, RouterLink],
  templateUrl: './staff-reservation-detail.html',
})
export class StaffReservationDetailPage implements OnInit {
  private readonly service = inject(StaffReservationsService);
  private readonly catalog = inject(CatalogService);
  private readonly errors = inject(StaffApiErrorService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly reservation = signal<StaffReservationDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly processing = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly successMessage = signal('');
  protected readonly pendingAction = signal<StaffAction | null>(null);
  protected readonly productImages = signal<Map<number, string>>(new Map());
  protected readonly failedImages = signal<Set<number>>(new Set());

  ngOnInit(): void {
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
        next: ({ data }) => {
          this.reservation.set(data);
          this.loadProductImages(data);
        },
        error: (error: HttpErrorResponse) => {
          this.reservation.set(null);
          this.errorMessage.set(
            this.errors.resolve(error, 'No pudimos consultar la reserva.'),
          );
        },
      });
  }

  protected askAction(action: StaffAction): void {
    const state = this.reservation()?.estado;
    if ((action === 'confirm' && state === 'PENDIENTE') || (action === 'attend' && state === 'CONFIRMADA')) {
      this.errorMessage.set('');
      this.successMessage.set('');
      this.pendingAction.set(action);
    }
  }

  protected runAction(): void {
    const reservation = this.reservation();
    const action = this.pendingAction();
    if (!reservation || !action || this.processing()) return;
    if (action === 'confirm' && reservation.estado !== 'PENDIENTE') return;
    if (action === 'attend' && reservation.estado !== 'CONFIRMADA') return;

    this.processing.set(true);
    this.errorMessage.set('');
    const request = action === 'confirm'
      ? this.service.confirmReservation(reservation.id_reserva)
      : this.service.attendReservation(reservation.id_reserva);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.processing.set(false)),
      )
      .subscribe({
        next: ({ data }) => {
          this.reservation.set(data);
          this.pendingAction.set(null);
          this.successMessage.set(
            action === 'confirm'
              ? 'La reserva quedó confirmada y lista para preparar.'
              : 'La reserva fue marcada como atendida.',
          );
        },
        error: (error: HttpErrorResponse) => {
          this.pendingAction.set(null);
          this.errorMessage.set(
            this.errors.resolve(error, 'No pudimos actualizar la reserva.'),
          );
          this.load();
        },
      });
  }

  protected actionTitle(): string {
    return this.pendingAction() === 'confirm'
      ? '¿Confirmar la preparación?'
      : '¿Marcar como atendida?';
  }

  protected actionCopy(): string {
    return this.pendingAction() === 'confirm'
      ? 'La reserva pasará a Confirmada. Verifica que las prendas estén listas para el cliente.'
      : 'La reserva quedará como Atendida. El stock comprometido se conservará hasta procesar la venta.';
  }

  protected imageFor(productId: number, fallback?: string | null): string | null {
    return fallback ?? this.productImages().get(productId) ?? null;
  }

  protected imageFailed(variantId: number): void {
    this.failedImages.update((current) => new Set([...current, variantId]));
  }

  protected stateLabel(state: ReservationState): string {
    return state.charAt(0) + state.slice(1).toLowerCase();
  }

  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'long',
      timeStyle: 'short',
      timeZone: 'America/La_Paz',
    }).format(new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`));
  }

  protected formatMoney(value: string): string {
    return `Bs ${Number(value).toLocaleString('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  @HostListener('document:keydown.escape')
  protected closeModal(): void {
    if (!this.processing()) this.pendingAction.set(null);
  }

  private loadProductImages(reservation: StaffReservationDetail): void {
    const productIds = [...new Set(reservation.prendas.map((item) => item.id_producto))];
    if (!productIds.length) return;
    forkJoin(
      productIds.map((id) =>
        this.catalog.getProduct(id, reservation.sucursal.id_sucursal).pipe(
          catchError(() => of(null)),
        ),
      ),
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((responses) => {
        const images = new Map<number, string>();
        responses.forEach((response, index) => {
          if (response?.data.imagen_principal) images.set(productIds[index], response.data.imagen_principal);
        });
        this.productImages.set(images);
      });
  }
}
