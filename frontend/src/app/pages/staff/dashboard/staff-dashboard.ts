import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { finalize, forkJoin } from 'rxjs';
import { StaffApiErrorService } from '../../../core/services/staff-api-error.service';
import { StaffReservationsService } from '../../../core/services/staff-reservations.service';
import { Icon, IconName } from '../../../shared/components/icon/icon';

interface StaffSummaryCard {
  label: string;
  value: number;
  helper: string;
  icon: IconName;
}

@Component({
  selector: 'app-staff-dashboard',
  imports: [Icon, RouterLink],
  templateUrl: './staff-dashboard.html',
})
export class StaffDashboard implements OnInit {
  private readonly reservations = inject(StaffReservationsService);
  private readonly errors = inject(StaffApiErrorService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly cards = signal<StaffSummaryCard[]>([]);
  protected readonly branch = this.reservations.branch;

  ngOnInit(): void {
    this.loadSummary();
  }

  protected loadSummary(): void {
    this.loading.set(true);
    this.errorMessage.set('');
    const today = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/La_Paz',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date());

    forkJoin({
      pending: this.reservations.listReservations({ estado: 'PENDIENTE', pageSize: 1 }),
      confirmed: this.reservations.listReservations({ estado: 'CONFIRMADA', pageSize: 1 }),
      today: this.reservations.listReservations({ fechaProgramada: today, pageSize: 1 }),
      attended: this.reservations.listReservations({ estado: 'ATENDIDA', pageSize: 1 }),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: ({ pending, confirmed, today: todayReservations, attended }) => {
          this.cards.set([
            { label: 'Reservas pendientes', value: pending.pagination.total, helper: 'Por preparar', icon: 'bag' },
            { label: 'Reservas confirmadas', value: confirmed.pagination.total, helper: 'Listas para atención', icon: 'circle-check' },
            { label: 'Reservas para hoy', value: todayReservations.pagination.total, helper: 'Agenda de la sucursal', icon: 'dashboard' },
            { label: 'Reservas atendidas', value: attended.pagination.total, helper: 'Historial completado', icon: 'check' },
          ]);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errors.resolve(error, 'No pudimos cargar el resumen de reservas.'),
          );
        },
      });
  }
}
