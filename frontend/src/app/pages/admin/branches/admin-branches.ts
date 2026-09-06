import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { EMPTY, expand, finalize, forkJoin, reduce } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminBranch,
  AdminBranchPagination,
  AdminBranchesService,
} from '../../../core/services/admin-branches.service';
import { AdminCitiesService, AdminCity } from '../../../core/services/admin-cities.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminBranchPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-branches',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-branches.html',
  styleUrl: './admin-branches.scss',
})
export class AdminBranches implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly branchesService = inject(AdminBranchesService);
  private readonly citiesService = inject(AdminCitiesService);
  protected readonly cityOptions = signal<AdminCity[]>([]);
  protected readonly citiesLoading = signal(false);
  protected readonly citiesError = signal<string | null>(null);

  protected cityName(id: number): string {
    return this.cityOptions().find((city) => city.id_ciudad === id)?.nombre ?? `Ciudad #${id}`;
  }

  protected loadCityOptions(): void {
    if (this.citiesLoading()) return;
    this.citiesLoading.set(true);
    this.citiesError.set(null);
    this.citiesService
      .listCities({ page: 1, pageSize: 100 })
      .pipe(
        expand((response) =>
          response.pagination.page < response.pagination.total_pages
            ? this.citiesService.listCities({
                page: response.pagination.page + 1,
                pageSize: response.pagination.page_size,
              })
            : EMPTY,
        ),
        reduce((cities, response) => [...cities, ...response.data], [] as AdminCity[]),
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.citiesLoading.set(false)),
      )
      .subscribe({
        next: (cities) => this.cityOptions.set(cities),
        error: (error: HttpErrorResponse) =>
          this.citiesError.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las ciudades. Inténtalo nuevamente.',
            }),
          ),
      });
  }

  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly branches = signal<AdminBranch[]>([]);
  protected readonly pagination = signal<AdminBranchPagination>(EMPTY_PAGINATION);
  protected readonly totalBranches = signal(0);
  protected readonly activeBranches = signal(0);
  protected readonly loading = signal(true);
  protected readonly statsLoading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailBranch = signal<AdminBranch | null>(null);
  protected readonly branchModalOpen = signal(false);
  protected readonly editingBranch = signal<AdminBranch | null>(null);
  protected readonly statusBranch = signal<AdminBranch | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly textFields = [
    { name: 'nombre', label: 'Nombre *', max: 150 },
    { name: 'direccion', label: 'Dirección *', max: 200 },
    { name: 'telefono', label: 'Teléfono (opcional)', max: 30 },
  ] as const;

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly branchForm = this.formBuilder.nonNullable.group({
    id_ciudad: [0, [Validators.required, Validators.min(1)]],
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 150)]],
    direccion: ['', [Validators.required, trimmedLengthValidator(1, 200)]],
    telefono: ['', Validators.maxLength(30)],
    hora_apertura: '',
    hora_cierre: '',
  });

  ngOnInit(): void {
    this.loadCityOptions();
    this.loadBranches();
    this.loadStats();
  }

  protected applyFilters(): void {
    this.loadBranches(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadBranches(1);
  }

  protected loadBranches(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    this.loading.set(true);
    this.errorMessage.set(null);
    this.branchesService
      .listBranches({
        search: filters.search,
        estado: state,
        page,
        pageSize: 10,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          if (page > 1 && response.data.length === 0 && response.pagination.total_pages < page) {
            this.loadBranches(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.branches.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las sucursales.',
            }),
          );
        },
      });
  }

  protected openBranchModal(branch: AdminBranch | null = null): void {
    this.clearMessages();
    this.editingBranch.set(branch);
    this.loadCityOptions();
    this.branchForm.reset({
      id_ciudad: branch?.id_ciudad ?? 0,
      nombre: branch?.nombre ?? '',
      direccion: branch?.direccion ?? '',
      telefono: branch?.telefono ?? '',
      hora_apertura: branch?.hora_apertura ?? '',
      hora_cierre: branch?.hora_cierre ?? '',
    });
    this.modalErrorMessage.set(null);
    this.branchModalOpen.set(true);
  }

  protected closeBranchModal(): void {
    if (this.saving()) return;
    this.branchModalOpen.set(false);
    this.editingBranch.set(null);
    this.branchForm.reset({ nombre: '' });
    this.modalErrorMessage.set(null);
  }

  protected submitBranch(): void {
    if (this.saving() || this.citiesLoading() || this.citiesError()) return;

    this.modalErrorMessage.set(null);
    if (this.branchForm.invalid) {
      this.branchForm.markAllAsTouched();
      this.modalErrorMessage.set(
        'Revisa la ciudad, el nombre, la dirección y el teléfono ingresados.',
      );
      return;
    }

    const values = this.branchForm.getRawValue();
    const fields = {
      ...values,
      nombre: values.nombre.trim(),
      direccion: values.direccion.trim(),
      telefono: values.telefono.trim() || null,
      hora_apertura: values.hora_apertura || null,
      hora_cierre: values.hora_cierre || null,
    };
    const currentBranch = this.editingBranch();
    const request = currentBranch
      ? this.branchesService.updateBranch(currentBranch.id_sucursal, fields)
      : this.branchesService.createBranch(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentBranch !== null;
          this.closeBranchModalAfterSave();
          this.successMessage.set(
            wasEditing ? 'Sucursal actualizada correctamente.' : 'Sucursal creada correctamente.',
          );
          this.loadBranches(wasEditing ? this.pagination().page : 1);
          this.loadStats();
          if (this.detailBranch()?.id_sucursal === response.data.id_sucursal) {
            this.detailBranch.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          if (
            error.status === 422 &&
            error.error?.message === 'La ciudad seleccionada está inactiva'
          ) {
            this.modalErrorMessage.set(
              'La ciudad seleccionada está inactiva. Selecciona otra ciudad activa.',
            );
            this.loadCityOptions();
            return;
          }

          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La sucursal o la ciudad seleccionada ya no existe.',
              conflict: 'No se pudo guardar por un conflicto con los datos actuales.',
              fallback: currentBranch
                ? 'No pudimos actualizar la sucursal.'
                : 'No pudimos crear la sucursal.',
            }),
          );
        },
      });
  }

  protected viewDetail(branchId: number): void {
    this.detailBranch.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.branchesService
      .getBranch(branchId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailBranch.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La sucursal solicitada ya no existe.',
              conflict:
                'No se pudo completar la operación por un conflicto con los datos actuales.',
              fallback: 'No pudimos cargar el detalle de la sucursal.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(branch: AdminBranch): void {
    this.clearMessages();
    this.statusBranch.set(branch);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusBranch.set(null);
  }

  protected confirmStatusChange(): void {
    const branch = this.statusBranch();
    if (!branch || this.saving()) return;

    this.saving.set(true);
    this.branchesService
      .updateStatus(branch.id_sucursal, !branch.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusBranch.set(null);
          this.successMessage.set(
            response.data.estado
              ? 'Sucursal activada correctamente.'
              : 'Sucursal desactivada correctamente.',
          );
          this.loadBranches(this.pagination().page);
          this.loadStats();
          if (this.detailBranch()?.id_sucursal === response.data.id_sucursal) {
            this.detailBranch.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusBranch.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La sucursal solicitada ya no existe.',
              conflict:
                'No se pudo completar la operación por un conflicto con los datos actuales.',
              fallback: 'No pudimos actualizar el estado de la sucursal.',
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
    if (this.canGoPrevious()) this.loadBranches(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadBranches(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusBranch.set(null);
    if (this.branchModalOpen()) this.closeBranchModal();
  }

  private loadStats(): void {
    this.statsLoading.set(true);
    forkJoin({
      all: this.branchesService.listBranches({ page: 1, pageSize: 1 }),
      active: this.branchesService.listBranches({ estado: true, page: 1, pageSize: 1 }),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.statsLoading.set(false)),
      )
      .subscribe({
        next: ({ all, active }) => {
          this.totalBranches.set(all.pagination.total);
          this.activeBranches.set(active.pagination.total);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar el resumen de sucursales.',
            }),
          );
        },
      });
  }

  private closeBranchModalAfterSave(): void {
    this.branchModalOpen.set(false);
    this.editingBranch.set(null);
    this.branchForm.reset({ nombre: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailBranch.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
