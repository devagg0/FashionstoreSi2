import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, Subscription } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminColor,
  AdminColorFields,
  AdminColorPagination,
  AdminColorsService,
} from '../../../core/services/admin-colors.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminColorPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-colors',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-colors.html',
  styleUrl: './admin-colors.scss',
})
export class AdminColors implements OnInit {
  readonly active = input(true);
  private readonly destroyRef = inject(DestroyRef);
  private listRequest?: Subscription;
  private listVersion = 0;
  private readonly colorsService = inject(AdminColorsService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly colors = signal<AdminColor[]>([]);
  protected readonly pagination = signal<AdminColorPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailColor = signal<AdminColor | null>(null);
  protected readonly colorModalOpen = signal(false);
  protected readonly editingColor = signal<AdminColor | null>(null);
  protected readonly statusColor = signal<AdminColor | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly colorForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 50)]],
    codigo_hex: [
      '',
      [
        (control: { value: string }) =>
          control.value.trim().length > 7 ? { maxlength: true } : null,
      ],
    ],
  });

  ngOnInit(): void {
    this.loadColors();
  }

  protected applyFilters(): void {
    this.loadColors(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadColors(1);
  }

  protected loadColors(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    const version = ++this.listVersion;
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.colorsService
      .listColors({
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
            this.loadColors(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.colors.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar los colores.',
            }),
          );
        },
      });
  }

  protected openColorModal(color: AdminColor | null = null): void {
    this.clearMessages();
    this.editingColor.set(color);
    this.colorForm.reset({ nombre: color?.nombre ?? '', codigo_hex: color?.codigo_hex ?? '' });
    this.modalErrorMessage.set(null);
    this.colorModalOpen.set(true);
  }

  protected closeColorModal(): void {
    if (this.saving()) return;
    this.colorModalOpen.set(false);
    this.editingColor.set(null);
    this.colorForm.reset({ nombre: '', codigo_hex: '' });
    this.modalErrorMessage.set(null);
  }

  protected clearNameConflict(): void {
    const control = this.colorForm.controls.nombre;
    if (!control.hasError('duplicate')) return;
    control.setErrors(null);
    control.updateValueAndValidity({ emitEvent: false });
    this.modalErrorMessage.set(null);
  }

  protected submitColor(): void {
    if (this.saving()) return;

    this.modalErrorMessage.set(null);
    if (this.colorForm.invalid) {
      this.colorForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los campos y sus longitudes máximas.');
      return;
    }

    const name = this.colorForm.controls.nombre.value.trim();
    const currentColor = this.editingColor();
    const optional = this.colorForm.controls.codigo_hex.value.trim() || null;
    const fields: AdminColorFields = { nombre: name, codigo_hex: optional };
    const changes: Partial<AdminColorFields> = {};
    if (currentColor) {
      if (name !== currentColor.nombre) changes.nombre = name;
      if (optional !== currentColor.codigo_hex) changes.codigo_hex = optional;
      if (Object.keys(changes).length === 0) {
        this.closeColorModal();
        return;
      }
    }
    const request = currentColor
      ? this.colorsService.updateColor(currentColor.id_color, changes)
      : this.colorsService.createColor(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentColor !== null;
          this.closeColorModalAfterSave();
          this.successMessage.set(response.message);
          this.loadColors(wasEditing ? this.pagination().page : 1);
          if (this.detailColor()?.id_color === response.data.id_color) {
            this.detailColor.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          if (error.status === 409) {
            const control = this.colorForm.controls.nombre;
            control.setErrors({ ...control.errors, duplicate: true });
            control.markAsTouched();
            this.modalErrorMessage.set(this.errorService.resolve(error));
            return;
          }

          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El color que intentas editar ya no existe.',
              fallback: currentColor
                ? 'No pudimos actualizar el color.'
                : 'No pudimos crear el color.',
            }),
          );
        },
      });
  }

  protected viewDetail(colorId: number): void {
    this.detailColor.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.colorsService
      .getColor(colorId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailColor.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El color solicitado ya no existe.',
              fallback: 'No pudimos cargar el detalle del color.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(color: AdminColor): void {
    this.clearMessages();
    this.statusColor.set(color);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusColor.set(null);
  }

  protected confirmStatusChange(): void {
    const color = this.statusColor();
    if (!color || this.saving()) return;

    this.saving.set(true);
    this.colorsService
      .updateStatus(color.id_color, !color.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusColor.set(null);
          this.successMessage.set(response.message);
          this.loadColors(this.pagination().page);
          if (this.detailColor()?.id_color === response.data.id_color) {
            this.detailColor.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusColor.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El color solicitado ya no existe.',
              fallback: 'No pudimos actualizar el estado del color.',
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
    if (this.canGoPrevious()) this.loadColors(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadColors(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  protected isNameInvalid(): boolean {
    const control = this.colorForm.controls.nombre;
    return control.invalid && (control.touched || control.dirty);
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (!this.active() || this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusColor.set(null);
    if (this.colorModalOpen()) this.closeColorModal();
  }

  private closeColorModalAfterSave(): void {
    this.colorModalOpen.set(false);
    this.editingColor.set(null);
    this.colorForm.reset({ nombre: '', codigo_hex: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailColor.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
