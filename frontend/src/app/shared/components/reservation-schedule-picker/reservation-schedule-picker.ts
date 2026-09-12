import { Component, computed, effect, input, output, signal } from '@angular/core';
import { BranchAvailability } from '../../../core/services/catalog-availability.service';
import { ReservationContext } from '../../../core/services/reservation-selection.service';
import {
  ReservationDay,
  reservationTimeSlots,
  upcomingReservationDays,
} from '../../../core/utils/reservation-schedule';

export interface ReservationScheduleSelection {
  branch: BranchAvailability;
  date: string;
  time: string;
}

@Component({
  selector: 'app-reservation-schedule-picker',
  templateUrl: './reservation-schedule-picker.html',
  styleUrl: './reservation-schedule-picker.scss',
})
export class ReservationSchedulePicker {
  readonly branches = input<BranchAvailability[]>([]);
  readonly initialContext = input<ReservationContext | null>(null);
  readonly selectionChange = output<ReservationScheduleSelection | null>();

  protected readonly days: ReservationDay[] = upcomingReservationDays();
  protected readonly selectedBranchId = signal<number | null>(null);
  protected readonly selectedDate = signal(this.days[0].value);
  protected readonly selectedTime = signal('');
  protected readonly selectedBranch = computed(
    () =>
      this.branches().find(
        (branch) => branch.id_sucursal === this.selectedBranchId(),
      ) ?? null,
  );
  protected readonly slots = computed(() => {
    const branch = this.selectedBranch();
    if (!branch?.hora_apertura || !branch.hora_cierre) return [];
    return reservationTimeSlots(
      branch.hora_apertura,
      branch.hora_cierre,
      this.selectedDate(),
    );
  });

  constructor() {
    effect(() => {
      const branches = this.branches();
      const initial = this.initialContext();
      if (
        this.selectedBranchId() === null &&
        initial &&
        branches.some((branch) => branch.id_sucursal === initial.id_sucursal)
      ) {
        this.selectedBranchId.set(initial.id_sucursal);
        this.selectedDate.set(
          this.days.some((day) => day.value === initial.fecha)
            ? initial.fecha
            : this.days[0].value,
        );
        this.selectedTime.set(initial.horario);
      }
      if (
        this.selectedBranchId() !== null &&
        !branches.some((branch) => branch.id_sucursal === this.selectedBranchId())
      ) {
        this.selectedBranchId.set(null);
        this.selectedTime.set('');
        this.selectionChange.emit(null);
      }
    });
  }

  protected chooseBranch(event: Event): void {
    const id = Number((event.target as HTMLSelectElement).value);
    this.selectedBranchId.set(Number.isInteger(id) && id > 0 ? id : null);
    this.selectedTime.set('');
    this.selectionChange.emit(null);
  }

  protected chooseDay(day: ReservationDay): void {
    this.selectedDate.set(day.value);
    this.selectedTime.set('');
    this.selectionChange.emit(null);
  }

  protected chooseTime(time: string): void {
    const branch = this.selectedBranch();
    if (!branch || !this.slots().includes(time)) return;
    this.selectedTime.set(time);
    this.selectionChange.emit({ branch, date: this.selectedDate(), time });
  }

  protected shortTime(value: string | null): string {
    return value?.slice(0, 5) ?? '--:--';
  }
}

