import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize, Observable } from 'rxjs';
import { ReservationState } from '../../../core/services/client-reservations.service';
import { StaffApiErrorService } from '../../../core/services/staff-api-error.service';
import {
  StaffReservationListResponse,
  StaffReservationResponse,
  StaffReservationsService,
  StaffReservationSummary,
} from '../../../core/services/staff-reservations.service';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-staff-reservations',
  imports: [Icon, ReactiveFormsModule, RouterLink],
  templateUrl: './staff-reservations.html',
})
export class StaffReservations implements OnInit {
  private readonly service = inject(StaffReservationsService);
  private readonly errors = inject(StaffApiErrorService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private requestSequence = 0;

  protected readonly states: ReservationState[] = [
    'PENDIENTE',
    'CONFIRMADA',
    'ATENDIDA',
    'CANCELADA',
    'EXPIRADA',
  ];
  protected readonly filterForm = this.formBuilder.nonNullable.group({
    codigo: '',
    estado: '' as ReservationState | '',
    fechaProgramada: '',
  });
  protected readonly reservations = signal<StaffReservationSummary[]>([]);
  protected readonly pagination = signal({ page: 1, page_size: 12, total: 0, total_pages: 0 });
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly branch = this.service.branch;
  protected readonly codeSearchActive = signal(false);

  ngOnInit(): void {
    this.load();
  }

  protected applyFilters(): void {
    this.load(1);
  }

  protected clearFilters(): void {
    this.filterForm.reset({ codigo: '', estado: '', fechaProgramada: '' });
    this.load(1);
  }

  protected load(page = 1): void {
    const sequence = ++this.requestSequence;
    const filters = this.filterForm.getRawValue();
    const code = filters.codigo.trim();
    this.loading.set(true);
    this.errorMessage.set('');
    this.codeSearchActive.set(Boolean(code));

    const request: Observable<StaffReservationListResponse | StaffReservationResponse> = code
      ? this.service.getReservationByCode(code)
      : this.service.listReservations({
          estado: filters.estado || undefined,
          fechaProgramada: filters.fechaProgramada || undefined,
          page,
          pageSize: 12,
        });

    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          if (sequence === this.requestSequence) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (response) => {
          if (sequence !== this.requestSequence) return;
          if ('pagination' in response) {
            this.reservations.set(response.data);
            this.pagination.set(response.pagination);
            return;
          }
          const row = response.data;
          const matchesState = !filters.estado || row.estado === filters.estado;
          const matchesDate =
            !filters.fechaProgramada ||
            this.localDate(row.fecha_atencion_programada) === filters.fechaProgramada;
          const data = matchesState && matchesDate ? [row] : [];
          this.reservations.set(data);
          this.pagination.set({
            page: 1,
            page_size: 1,
            total: data.length,
            total_pages: data.length,
          });
        },
        error: (error: HttpErrorResponse) => {
          if (sequence !== this.requestSequence) return;
          this.reservations.set([]);
          this.pagination.set({ page: 1, page_size: 12, total: 0, total_pages: 0 });
          this.errorMessage.set(
            this.errors.resolve(error, 'No pudimos consultar las reservas.'),
          );
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
    }).format(this.utcDate(value));
  }

  protected formatMoney(value: string): string {
    return `Bs ${Number(value).toLocaleString('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  private localDate(value: string): string {
    return new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: 'America/La_Paz',
    }).format(this.utcDate(value));
  }

  private utcDate(value: string): Date {
    return new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
  }
}
