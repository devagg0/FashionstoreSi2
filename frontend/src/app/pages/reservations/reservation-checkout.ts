import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { finalize, forkJoin } from 'rxjs';
import {
  BranchAvailability,
  CatalogAvailabilityService,
} from '../../core/services/catalog-availability.service';
import { ClientReservationsService } from '../../core/services/client-reservations.service';
import {
  ReservationContext,
  ReservationSelectionService,
} from '../../core/services/reservation-selection.service';
import { SessionService } from '../../core/services/session.service';
import {
  isReservationDateAllowed,
  reservationTimestamp,
  reservationTimeSlots,
} from '../../core/utils/reservation-schedule';
import { Icon } from '../../shared/components/icon/icon';
import {
  ReservationSchedulePicker,
  ReservationScheduleSelection,
} from '../../shared/components/reservation-schedule-picker/reservation-schedule-picker';

@Component({
  selector: 'app-reservation-checkout',
  imports: [RouterLink, Icon, ReservationSchedulePicker],
  templateUrl: './reservation-checkout.html',
  styleUrl: './reservation-checkout.scss',
})
export class ReservationCheckout implements OnInit {
  private readonly selection = inject(ReservationSelectionService);
  private readonly availabilityService = inject(CatalogAvailabilityService);
  private readonly reservationService = inject(ClientReservationsService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly items = this.selection.items;
  protected readonly context = this.selection.context;
  protected readonly branches = signal<BranchAvailability[]>([]);
  protected readonly loadingAvailability = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal('');
  protected readonly branchesWithoutSchedule = signal(0);
  protected readonly editingContext = signal(false);
  protected readonly pendingSchedule = signal<ReservationScheduleSelection | null>(null);
  protected readonly previewTotal = computed(() =>
    this.items().reduce(
      (total, item) => total + Number(item.precio_referencia) * item.cantidad,
      0,
    ),
  );
  protected readonly contextHasAvailability = computed(() => {
    const context = this.context();
    return Boolean(
      context && this.branches().some((branch) => branch.id_sucursal === context.id_sucursal),
    );
  });
  protected readonly contextScheduleValid = computed(() => {
    const context = this.context();
    return Boolean(
      context &&
        isReservationDateAllowed(context.fecha) &&
        reservationTimeSlots(
          context.hora_apertura,
          context.hora_cierre,
          context.fecha,
        ).includes(context.horario),
    );
  });

  ngOnInit(): void {
    this.loadAvailability();
  }

  protected loadAvailability(): void {
    const items = this.items();
    this.branches.set([]);
    this.branchesWithoutSchedule.set(0);
    this.errorMessage.set('');
    if (!items.length) return;

    this.loadingAvailability.set(true);
    forkJoin(
      items.map((item) =>
        this.availabilityService.getProductAvailability(item.id_producto, {
          id_variante_producto: item.id_variante_producto,
        }),
      ),
    )
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loadingAvailability.set(false)),
      )
      .subscribe({
        next: (responses) => {
          const eligible = responses[0].data.disponibilidad.filter((branch) =>
            responses.every((response, index) =>
              response.data.disponibilidad.some(
                (row) =>
                  row.id_sucursal === branch.id_sucursal &&
                  row.stock_disponible >= items[index].cantidad,
              ),
            ),
          );
          const invalidSchedule = eligible.filter(
            (branch) => !this.hasUsableSchedule(branch),
          );
          this.branchesWithoutSchedule.set(invalidSchedule.length);
          this.branches.set(eligible.filter((branch) => this.hasUsableSchedule(branch)));
          if (!this.contextHasAvailability()) {
            this.errorMessage.set(
              'La reserva actual ya no tiene disponibilidad completa en la sucursal elegida. Cambia la sucursal o ajusta las cantidades.',
            );
          }
        },
        error: () =>
          this.errorMessage.set(
            'No pudimos comprobar la disponibilidad de todas las prendas.',
          ),
      });
  }

  protected updateQuantity(variantId: number, event: Event): void {
    const quantity = Number((event.target as HTMLInputElement).value);
    if (!Number.isInteger(quantity) || quantity < 1) return;
    this.selection.updateQuantity(variantId, quantity);
    this.loadAvailability();
  }

  protected remove(variantId: number): void {
    this.selection.remove(variantId);
    this.editingContext.set(false);
    this.loadAvailability();
  }

  protected beginContextChange(): void {
    this.pendingSchedule.set(null);
    this.editingContext.set(true);
    this.errorMessage.set('');
  }

  protected scheduleChanged(selection: ReservationScheduleSelection | null): void {
    this.pendingSchedule.set(selection);
  }

  protected applyContextChange(): void {
    const schedule = this.pendingSchedule();
    if (
      !schedule ||
      !this.branches().some(
        (branch) => branch.id_sucursal === schedule.branch.id_sucursal,
      )
    ) {
      this.errorMessage.set('Selecciona una sucursal, fecha y horario válidos.');
      return;
    }
    this.selection.changeContext(this.contextFromSchedule(schedule));
    this.editingContext.set(false);
    this.errorMessage.set('');
  }

  protected canSubmit(): boolean {
    return (
      this.items().length > 0 &&
      Boolean(this.context()) &&
      this.contextHasAvailability() &&
      this.contextScheduleValid() &&
      !this.loadingAvailability() &&
      !this.saving() &&
      !this.editingContext()
    );
  }

  protected confirm(): void {
    const context = this.context();
    if (!context || !this.canSubmit()) {
      this.errorMessage.set('Revisa el contexto y la disponibilidad antes de confirmar.');
      return;
    }
    this.saving.set(true);
    this.errorMessage.set('');
    this.reservationService
      .createReservation({
        id_sucursal: context.id_sucursal,
        fecha_atencion_programada: reservationTimestamp(context.fecha, context.horario),
        items: this.items().map((item) => ({
          id_variante_producto: item.id_variante_producto,
          cantidad: item.cantidad,
        })),
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: ({ data }) => {
          this.selection.clear();
          void this.router.navigate(['/mis-reservas', data.id_reserva], {
            queryParams: { creada: 1 },
          });
        },
        error: (error: HttpErrorResponse) => {
          if (error.status === 401) {
            this.session.logout();
            void this.router.navigateByUrl('/login');
            return;
          }
          if (error.status === 409) this.loadAvailability();
          this.errorMessage.set(
            typeof error.error?.message === 'string'
              ? error.error.message
              : 'No pudimos crear la reserva. Inténtalo nuevamente.',
          );
        },
      });
  }

  protected formatContextDate(context: ReservationContext): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'long',
      timeZone: 'UTC',
    }).format(new Date(`${context.fecha}T12:00:00Z`));
  }

  protected formatMoney(value: number | string): string {
    return `Bs ${Number(value).toLocaleString('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  private hasUsableSchedule(branch: BranchAvailability): boolean {
    return Boolean(
      branch.hora_apertura &&
        branch.hora_cierre &&
        branch.hora_apertura !== branch.hora_cierre,
    );
  }

  private contextFromSchedule(selection: ReservationScheduleSelection): ReservationContext {
    return {
      id_sucursal: selection.branch.id_sucursal,
      nombre_sucursal: selection.branch.nombre_sucursal,
      nombre_ciudad: selection.branch.nombre_ciudad,
      direccion: selection.branch.direccion,
      hora_apertura: selection.branch.hora_apertura!,
      hora_cierre: selection.branch.hora_cierre!,
      fecha: selection.date,
      horario: selection.time,
    };
  }
}
