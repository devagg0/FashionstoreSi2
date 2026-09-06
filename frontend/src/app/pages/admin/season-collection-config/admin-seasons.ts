import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, Subscription } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminSeason,
  AdminSeasonFields,
  AdminSeasonPagination,
  AdminSeasonsService,
} from '../../../core/services/admin-seasons.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminSeasonPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-seasons',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-seasons.html',
  styleUrl: './admin-seasons.scss',
})
export class AdminSeasons implements OnInit {
  readonly active = input(true);
  private readonly destroyRef = inject(DestroyRef);
  private listRequest?: Subscription;
  private listVersion = 0;
  private readonly seasonsService = inject(AdminSeasonsService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly seasons = signal<AdminSeason[]>([]);
  protected readonly pagination = signal<AdminSeasonPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailSeason = signal<AdminSeason | null>(null);
  protected readonly seasonModalOpen = signal(false);
  protected readonly editingSeason = signal<AdminSeason | null>(null);
  protected readonly statusSeason = signal<AdminSeason | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly seasonForm = this.formBuilder.nonNullable.group({
    fecha_inicio: '',
    fecha_fin: '',
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 100)]],
    descripcion: [
      '',
      [
        (control: { value: string }) =>
          control.value.trim().length > 200 ? { maxlength: true } : null,
      ],
    ],
  });

  ngOnInit(): void {
    this.loadSeasons();
  }

  protected applyFilters(): void {
    this.loadSeasons(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadSeasons(1);
  }

  protected loadSeasons(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    const version = ++this.listVersion;
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.seasonsService
      .listSeasons({
        search: filters.search,
        estado: state,
        page,
        pageSize: 10,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          if (version === this.listVersion) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (response) => {
          if (page > 1 && response.data.length === 0 && response.pagination.total_pages < page) {
            this.loadSeasons(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.seasons.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las temporadas.',
            }),
          );
        },
      });
  }

  protected openSeasonModal(season: AdminSeason | null = null): void {
    this.clearMessages();
    this.editingSeason.set(season);
    this.seasonForm.reset({
      nombre: season?.nombre ?? '',
      descripcion: season?.descripcion ?? '',
      fecha_inicio: season?.fecha_inicio ?? '',
      fecha_fin: season?.fecha_fin ?? '',
    });
    this.modalErrorMessage.set(null);
    this.seasonModalOpen.set(true);
  }

  protected closeSeasonModal(): void {
    if (this.saving()) return;
    this.seasonModalOpen.set(false);
    this.editingSeason.set(null);
    this.seasonForm.reset({ nombre: '', descripcion: '', fecha_inicio: '', fecha_fin: '' });
    this.modalErrorMessage.set(null);
  }

  protected submitSeason(): void {
    if (this.saving()) return;

    this.modalErrorMessage.set(null);
    if (this.seasonForm.invalid) {
      this.seasonForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los campos y sus longitudes máximas.');
      return;
    }

    const name = this.seasonForm.controls.nombre.value.trim();
    const currentSeason = this.editingSeason();
    const optional = this.seasonForm.controls.descripcion.value.trim() || null;
    const start = this.seasonForm.controls.fecha_inicio.value || null;
    const end = this.seasonForm.controls.fecha_fin.value || null;
    const fields: AdminSeasonFields = {
      nombre: name,
      descripcion: optional,
      fecha_inicio: start,
      fecha_fin: end,
    };
    const changes: Partial<AdminSeasonFields> = {};
    if (currentSeason) {
      if (start !== currentSeason.fecha_inicio) changes.fecha_inicio = start;
      if (end !== currentSeason.fecha_fin) changes.fecha_fin = end;
      if (name !== currentSeason.nombre) changes.nombre = name;
      if (optional !== currentSeason.descripcion) changes.descripcion = optional;
      if (Object.keys(changes).length === 0) {
        this.closeSeasonModal();
        return;
      }
    }
    const request = currentSeason
      ? this.seasonsService.updateSeason(currentSeason.id_temporada, changes)
      : this.seasonsService.createSeason(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentSeason !== null;
          this.closeSeasonModalAfterSave();
          this.successMessage.set(response.message);
          this.loadSeasons(wasEditing ? this.pagination().page : 1);
          if (this.detailSeason()?.id_temporada === response.data.id_temporada) {
            this.detailSeason.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La temporada que intentas editar ya no existe.',
              fallback: currentSeason
                ? 'No pudimos actualizar la temporada.'
                : 'No pudimos crear la temporada.',
            }),
          );
        },
      });
  }

  protected viewDetail(seasonId: number): void {
    this.detailSeason.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.seasonsService
      .getSeason(seasonId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailSeason.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La temporada solicitada ya no existe.',
              fallback: 'No pudimos cargar el detalle de la temporada.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(season: AdminSeason): void {
    this.clearMessages();
    this.statusSeason.set(season);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusSeason.set(null);
  }

  protected confirmStatusChange(): void {
    const season = this.statusSeason();
    if (!season || this.saving()) return;

    this.saving.set(true);
    this.seasonsService
      .updateStatus(season.id_temporada, !season.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusSeason.set(null);
          this.successMessage.set(response.message);
          this.loadSeasons(this.pagination().page);
          if (this.detailSeason()?.id_temporada === response.data.id_temporada) {
            this.detailSeason.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusSeason.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La temporada solicitada ya no existe.',
              fallback: 'No pudimos actualizar el estado de la temporada.',
            }),
          );
        },
      });
  }

  protected canGoPrevious(): boolean {
    return !this.loading() && this.pagination().page > 1;
  }

  protected canGoNext(): boolean {
    const pagination = this.pagination();
    return !this.loading() && pagination.page < pagination.total_pages;
  }

  protected previousPage(): void {
    if (this.canGoPrevious()) this.loadSeasons(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadSeasons(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  protected isNameInvalid(): boolean {
    const control = this.seasonForm.controls.nombre;
    return control.invalid && (control.touched || control.dirty);
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (!this.active() || this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusSeason.set(null);
    if (this.seasonModalOpen()) this.closeSeasonModal();
  }

  private closeSeasonModalAfterSave(): void {
    this.seasonModalOpen.set(false);
    this.editingSeason.set(null);
    this.seasonForm.reset({ nombre: '', descripcion: '', fecha_inicio: '', fecha_fin: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailSeason.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
