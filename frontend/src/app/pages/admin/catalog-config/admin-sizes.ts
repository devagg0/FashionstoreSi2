import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, Subscription } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminSize,
  AdminSizeFields,
  AdminSizePagination,
  AdminSizesService,
} from '../../../core/services/admin-sizes.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminSizePagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-sizes',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-sizes.html',
  styleUrl: './admin-sizes.scss',
})
export class AdminSizes implements OnInit {
  readonly active = input(true);
  private readonly destroyRef = inject(DestroyRef);
  private listRequest?: Subscription;
  private listVersion = 0;
  private readonly sizesService = inject(AdminSizesService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly sizes = signal<AdminSize[]>([]);
  protected readonly pagination = signal<AdminSizePagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailSize = signal<AdminSize | null>(null);
  protected readonly sizeModalOpen = signal(false);
  protected readonly editingSize = signal<AdminSize | null>(null);
  protected readonly statusSize = signal<AdminSize | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly sizeForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 20)]],
    descripcion: [
      '',
      [
        (control: { value: string }) =>
          control.value.trim().length > 100 ? { maxlength: true } : null,
      ],
    ],
  });

  ngOnInit(): void {
    this.loadSizes();
  }

  protected applyFilters(): void {
    this.loadSizes(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadSizes(1);
  }

  protected loadSizes(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    const version = ++this.listVersion;
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.sizesService
      .listSizes({
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
            this.loadSizes(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.sizes.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las tallas.',
            }),
          );
        },
      });
  }

  protected openSizeModal(size: AdminSize | null = null): void {
    this.clearMessages();
    this.editingSize.set(size);
    this.sizeForm.reset({ nombre: size?.nombre ?? '', descripcion: size?.descripcion ?? '' });
    this.modalErrorMessage.set(null);
    this.sizeModalOpen.set(true);
  }

  protected closeSizeModal(): void {
    if (this.saving()) return;
    this.sizeModalOpen.set(false);
    this.editingSize.set(null);
    this.sizeForm.reset({ nombre: '', descripcion: '' });
    this.modalErrorMessage.set(null);
  }

  protected clearNameConflict(): void {
    const control = this.sizeForm.controls.nombre;
    if (!control.hasError('duplicate')) return;
    control.setErrors(null);
    control.updateValueAndValidity({ emitEvent: false });
    this.modalErrorMessage.set(null);
  }

  protected submitSize(): void {
    if (this.saving()) return;

    this.modalErrorMessage.set(null);
    if (this.sizeForm.invalid) {
      this.sizeForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los campos y sus longitudes máximas.');
      return;
    }

    const name = this.sizeForm.controls.nombre.value.trim();
    const currentSize = this.editingSize();
    const optional = this.sizeForm.controls.descripcion.value.trim() || null;
    const fields: AdminSizeFields = { nombre: name, descripcion: optional };
    const changes: Partial<AdminSizeFields> = {};
    if (currentSize) {
      if (name !== currentSize.nombre) changes.nombre = name;
      if (optional !== currentSize.descripcion) changes.descripcion = optional;
      if (Object.keys(changes).length === 0) {
        this.closeSizeModal();
        return;
      }
    }
    const request = currentSize
      ? this.sizesService.updateSize(currentSize.id_talla, changes)
      : this.sizesService.createSize(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentSize !== null;
          this.closeSizeModalAfterSave();
          this.successMessage.set(response.message);
          this.loadSizes(wasEditing ? this.pagination().page : 1);
          if (this.detailSize()?.id_talla === response.data.id_talla) {
            this.detailSize.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          if (error.status === 409) {
            const control = this.sizeForm.controls.nombre;
            control.setErrors({ ...control.errors, duplicate: true });
            control.markAsTouched();
            this.modalErrorMessage.set(this.errorService.resolve(error));
            return;
          }

          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La talla que intentas editar ya no existe.',
              fallback: currentSize
                ? 'No pudimos actualizar la talla.'
                : 'No pudimos crear la talla.',
            }),
          );
        },
      });
  }

  protected viewDetail(sizeId: number): void {
    this.detailSize.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.sizesService
      .getSize(sizeId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailSize.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La talla solicitada ya no existe.',
              fallback: 'No pudimos cargar el detalle de la talla.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(size: AdminSize): void {
    this.clearMessages();
    this.statusSize.set(size);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusSize.set(null);
  }

  protected confirmStatusChange(): void {
    const size = this.statusSize();
    if (!size || this.saving()) return;

    this.saving.set(true);
    this.sizesService
      .updateStatus(size.id_talla, !size.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusSize.set(null);
          this.successMessage.set(response.message);
          this.loadSizes(this.pagination().page);
          if (this.detailSize()?.id_talla === response.data.id_talla) {
            this.detailSize.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusSize.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La talla solicitada ya no existe.',
              fallback: 'No pudimos actualizar el estado de la talla.',
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
    if (this.canGoPrevious()) this.loadSizes(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadSizes(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  protected isNameInvalid(): boolean {
    const control = this.sizeForm.controls.nombre;
    return control.invalid && (control.touched || control.dirty);
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (!this.active() || this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusSize.set(null);
    if (this.sizeModalOpen()) this.closeSizeModal();
  }

  private closeSizeModalAfterSave(): void {
    this.sizeModalOpen.set(false);
    this.editingSize.set(null);
    this.sizeForm.reset({ nombre: '', descripcion: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailSize.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
