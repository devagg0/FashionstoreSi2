import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminCity,
  AdminCityPagination,
  AdminCitiesService,
} from '../../../core/services/admin-cities.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminCityPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-cities',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-cities.html',
  styleUrl: './admin-cities.scss',
})
export class AdminCities implements OnInit {
  private readonly citiesService = inject(AdminCitiesService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly cities = signal<AdminCity[]>([]);
  protected readonly pagination = signal<AdminCityPagination>(EMPTY_PAGINATION);
  protected readonly totalCities = signal(0);
  protected readonly activeCities = signal(0);
  protected readonly loading = signal(true);
  protected readonly statsLoading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailCity = signal<AdminCity | null>(null);
  protected readonly cityModalOpen = signal(false);
  protected readonly editingCity = signal<AdminCity | null>(null);
  protected readonly statusCity = signal<AdminCity | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly cityForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 100)]],
  });

  ngOnInit(): void {
    this.loadCities();
    this.loadStats();
  }

  protected applyFilters(): void {
    this.loadCities(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadCities(1);
  }

  protected loadCities(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    this.loading.set(true);
    this.errorMessage.set(null);
    this.citiesService
      .listCities({
        search: filters.search,
        estado: state,
        page,
        pageSize: 10,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (response) => {
          if (page > 1 && response.data.length === 0 && response.pagination.total_pages < page) {
            this.loadCities(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.cities.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las ciudades.',
            }),
          );
        },
      });
  }

  protected openCityModal(city: AdminCity | null = null): void {
    this.clearMessages();
    this.editingCity.set(city);
    this.cityForm.reset({ nombre: city?.nombre ?? '' });
    this.modalErrorMessage.set(null);
    this.cityModalOpen.set(true);
  }

  protected closeCityModal(): void {
    if (this.saving()) return;
    this.cityModalOpen.set(false);
    this.editingCity.set(null);
    this.cityForm.reset({ nombre: '' });
    this.modalErrorMessage.set(null);
  }

  protected clearNameConflict(): void {
    const control = this.cityForm.controls.nombre;
    if (!control.hasError('duplicate')) return;
    control.setErrors(null);
    control.updateValueAndValidity({ emitEvent: false });
    this.modalErrorMessage.set(null);
  }

  protected submitCity(): void {
    if (this.saving()) return;

    this.modalErrorMessage.set(null);
    if (this.cityForm.invalid) {
      this.cityForm.markAllAsTouched();
      this.modalErrorMessage.set('Ingresa un nombre de ciudad válido.');
      return;
    }

    const name = this.cityForm.controls.nombre.value.trim();
    const currentCity = this.editingCity();
    const request = currentCity
      ? this.citiesService.updateCity(currentCity.id_ciudad, name)
      : this.citiesService.createCity(name);

    this.saving.set(true);
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (response) => {
        const wasEditing = currentCity !== null;
        this.closeCityModalAfterSave();
        this.successMessage.set(
          wasEditing ? 'Ciudad actualizada correctamente.' : 'Ciudad creada correctamente.',
        );
        this.loadCities(wasEditing ? this.pagination().page : 1);
        this.loadStats();
        if (this.detailCity()?.id_ciudad === response.data.id_ciudad) {
          this.detailCity.set(response.data);
        }
      },
      error: (error: HttpErrorResponse) => {
        if (error.status === 409) {
          const control = this.cityForm.controls.nombre;
          control.setErrors({ ...control.errors, duplicate: true });
          control.markAsTouched();
          this.modalErrorMessage.set('Ya existe una ciudad con ese nombre.');
          return;
        }

        this.modalErrorMessage.set(
          this.errorService.resolve(error, {
            notFound: 'La ciudad que intentas editar ya no existe.',
            fallback: currentCity
              ? 'No pudimos actualizar la ciudad.'
              : 'No pudimos crear la ciudad.',
          }),
        );
      },
    });
  }

  protected viewDetail(cityId: number): void {
    this.detailCity.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.citiesService
      .getCity(cityId)
      .pipe(finalize(() => this.detailLoading.set(false)))
      .subscribe({
        next: (response) => this.detailCity.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La ciudad solicitada ya no existe.',
              fallback: 'No pudimos cargar el detalle de la ciudad.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(city: AdminCity): void {
    this.clearMessages();
    this.statusCity.set(city);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusCity.set(null);
  }

  protected confirmStatusChange(): void {
    const city = this.statusCity();
    if (!city || this.saving()) return;

    this.saving.set(true);
    this.citiesService
      .updateStatus(city.id_ciudad, !city.estado)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (response) => {
          this.statusCity.set(null);
          this.successMessage.set(
            response.data.estado
              ? 'Ciudad activada correctamente.'
              : 'Ciudad desactivada correctamente.',
          );
          this.loadCities(this.pagination().page);
          this.loadStats();
          if (this.detailCity()?.id_ciudad === response.data.id_ciudad) {
            this.detailCity.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusCity.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La ciudad solicitada ya no existe.',
              fallback: 'No pudimos actualizar el estado de la ciudad.',
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
    if (this.canGoPrevious()) this.loadCities(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadCities(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  protected isNameInvalid(): boolean {
    const control = this.cityForm.controls.nombre;
    return control.invalid && (control.touched || control.dirty);
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusCity.set(null);
    if (this.cityModalOpen()) this.closeCityModal();
  }

  private loadStats(): void {
    this.statsLoading.set(true);
    forkJoin({
      all: this.citiesService.listCities({ page: 1, pageSize: 1 }),
      active: this.citiesService.listCities({ estado: true, page: 1, pageSize: 1 }),
    })
      .pipe(finalize(() => this.statsLoading.set(false)))
      .subscribe({
        next: ({ all, active }) => {
          this.totalCities.set(all.pagination.total);
          this.activeCities.set(active.pagination.total);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar el resumen de ciudades.',
            }),
          );
        },
      });
  }

  private closeCityModalAfterSave(): void {
    this.cityModalOpen.set(false);
    this.editingCity.set(null);
    this.cityForm.reset({ nombre: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailCity.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
