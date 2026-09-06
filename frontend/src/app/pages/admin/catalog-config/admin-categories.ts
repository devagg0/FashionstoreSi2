import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, Subscription } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminCategory,
  AdminCategoryFields,
  AdminCategoryPagination,
  AdminCategoriesService,
} from '../../../core/services/admin-categories.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminCategoryPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-categories',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-categories.html',
  styleUrl: './admin-categories.scss',
})
export class AdminCategories implements OnInit {
  readonly active = input(true);
  private readonly destroyRef = inject(DestroyRef);
  private listRequest?: Subscription;
  private listVersion = 0;
  private readonly categoriesService = inject(AdminCategoriesService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly categories = signal<AdminCategory[]>([]);
  protected readonly pagination = signal<AdminCategoryPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailCategory = signal<AdminCategory | null>(null);
  protected readonly categoryModalOpen = signal(false);
  protected readonly editingCategory = signal<AdminCategory | null>(null);
  protected readonly statusCategory = signal<AdminCategory | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly categoryForm = this.formBuilder.nonNullable.group({
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
    this.loadCategories();
  }

  protected applyFilters(): void {
    this.loadCategories(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadCategories(1);
  }

  protected loadCategories(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    const version = ++this.listVersion;
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.categoriesService
      .listCategories({
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
            this.loadCategories(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.categories.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las categorías.',
            }),
          );
        },
      });
  }

  protected openCategoryModal(category: AdminCategory | null = null): void {
    this.clearMessages();
    this.editingCategory.set(category);
    this.categoryForm.reset({
      nombre: category?.nombre ?? '',
      descripcion: category?.descripcion ?? '',
    });
    this.modalErrorMessage.set(null);
    this.categoryModalOpen.set(true);
  }

  protected closeCategoryModal(): void {
    if (this.saving()) return;
    this.categoryModalOpen.set(false);
    this.editingCategory.set(null);
    this.categoryForm.reset({ nombre: '', descripcion: '' });
    this.modalErrorMessage.set(null);
  }

  protected clearNameConflict(): void {
    const control = this.categoryForm.controls.nombre;
    if (!control.hasError('duplicate')) return;
    control.setErrors(null);
    control.updateValueAndValidity({ emitEvent: false });
    this.modalErrorMessage.set(null);
  }

  protected submitCategory(): void {
    if (this.saving()) return;

    this.modalErrorMessage.set(null);
    if (this.categoryForm.invalid) {
      this.categoryForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los campos y sus longitudes máximas.');
      return;
    }

    const name = this.categoryForm.controls.nombre.value.trim();
    const currentCategory = this.editingCategory();
    const optional = this.categoryForm.controls.descripcion.value.trim() || null;
    const fields: AdminCategoryFields = { nombre: name, descripcion: optional };
    const changes: Partial<AdminCategoryFields> = {};
    if (currentCategory) {
      if (name !== currentCategory.nombre) changes.nombre = name;
      if (optional !== currentCategory.descripcion) changes.descripcion = optional;
      if (Object.keys(changes).length === 0) {
        this.closeCategoryModal();
        return;
      }
    }
    const request = currentCategory
      ? this.categoriesService.updateCategory(currentCategory.id_categoria, changes)
      : this.categoriesService.createCategory(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentCategory !== null;
          this.closeCategoryModalAfterSave();
          this.successMessage.set(response.message);
          this.loadCategories(wasEditing ? this.pagination().page : 1);
          if (this.detailCategory()?.id_categoria === response.data.id_categoria) {
            this.detailCategory.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          if (error.status === 409) {
            const control = this.categoryForm.controls.nombre;
            control.setErrors({ ...control.errors, duplicate: true });
            control.markAsTouched();
            this.modalErrorMessage.set(this.errorService.resolve(error));
            return;
          }

          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La categoría que intentas editar ya no existe.',
              fallback: currentCategory
                ? 'No pudimos actualizar la categoría.'
                : 'No pudimos crear la categoría.',
            }),
          );
        },
      });
  }

  protected viewDetail(categoryId: number): void {
    this.detailCategory.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.categoriesService
      .getCategory(categoryId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailCategory.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La categoría solicitada ya no existe.',
              fallback: 'No pudimos cargar el detalle de la categoría.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(category: AdminCategory): void {
    this.clearMessages();
    this.statusCategory.set(category);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusCategory.set(null);
  }

  protected confirmStatusChange(): void {
    const category = this.statusCategory();
    if (!category || this.saving()) return;

    this.saving.set(true);
    this.categoriesService
      .updateStatus(category.id_categoria, !category.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusCategory.set(null);
          this.successMessage.set(response.message);
          this.loadCategories(this.pagination().page);
          if (this.detailCategory()?.id_categoria === response.data.id_categoria) {
            this.detailCategory.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusCategory.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La categoría solicitada ya no existe.',
              fallback: 'No pudimos actualizar el estado de la categoría.',
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
    if (this.canGoPrevious()) this.loadCategories(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadCategories(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  protected isNameInvalid(): boolean {
    const control = this.categoryForm.controls.nombre;
    return control.invalid && (control.touched || control.dirty);
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (!this.active() || this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusCategory.set(null);
    if (this.categoryModalOpen()) this.closeCategoryModal();
  }

  private closeCategoryModalAfterSave(): void {
    this.categoryModalOpen.set(false);
    this.editingCategory.set(null);
    this.categoryForm.reset({ nombre: '', descripcion: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailCategory.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
