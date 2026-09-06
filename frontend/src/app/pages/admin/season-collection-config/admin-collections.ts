import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, input, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, Subscription } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminCollection,
  AdminCollectionFields,
  AdminCollectionPagination,
  AdminCollectionsService,
} from '../../../core/services/admin-collections.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminCollectionPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-collections',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-collections.html',
  styleUrl: './admin-collections.scss',
})
export class AdminCollections implements OnInit {
  readonly active = input(true);
  private readonly destroyRef = inject(DestroyRef);
  private listRequest?: Subscription;
  private listVersion = 0;
  private readonly collectionsService = inject(AdminCollectionsService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly collections = signal<AdminCollection[]>([]);
  protected readonly pagination = signal<AdminCollectionPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailCollection = signal<AdminCollection | null>(null);
  protected readonly collectionModalOpen = signal(false);
  protected readonly editingCollection = signal<AdminCollection | null>(null);
  protected readonly statusCollection = signal<AdminCollection | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
  });
  protected readonly collectionForm = this.formBuilder.nonNullable.group({
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
    this.loadCollections();
  }

  protected applyFilters(): void {
    this.loadCollections(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadCollections(1);
  }

  protected loadCollections(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    const version = ++this.listVersion;
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.collectionsService
      .listCollections({
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
            this.loadCollections(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.collections.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las colecciones.',
            }),
          );
        },
      });
  }

  protected openCollectionModal(collection: AdminCollection | null = null): void {
    this.clearMessages();
    this.editingCollection.set(collection);
    this.collectionForm.reset({
      nombre: collection?.nombre ?? '',
      descripcion: collection?.descripcion ?? '',
    });
    this.modalErrorMessage.set(null);
    this.collectionModalOpen.set(true);
  }

  protected closeCollectionModal(): void {
    if (this.saving()) return;
    this.collectionModalOpen.set(false);
    this.editingCollection.set(null);
    this.collectionForm.reset({ nombre: '', descripcion: '' });
    this.modalErrorMessage.set(null);
  }

  protected submitCollection(): void {
    if (this.saving()) return;

    this.modalErrorMessage.set(null);
    if (this.collectionForm.invalid) {
      this.collectionForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los campos y sus longitudes máximas.');
      return;
    }

    const name = this.collectionForm.controls.nombre.value.trim();
    const currentCollection = this.editingCollection();
    const optional = this.collectionForm.controls.descripcion.value.trim() || null;
    const fields: AdminCollectionFields = { nombre: name, descripcion: optional };
    const changes: Partial<AdminCollectionFields> = {};
    if (currentCollection) {
      if (name !== currentCollection.nombre) changes.nombre = name;
      if (optional !== currentCollection.descripcion) changes.descripcion = optional;
      if (Object.keys(changes).length === 0) {
        this.closeCollectionModal();
        return;
      }
    }
    const request = currentCollection
      ? this.collectionsService.updateCollection(currentCollection.id_coleccion, changes)
      : this.collectionsService.createCollection(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentCollection !== null;
          this.closeCollectionModalAfterSave();
          this.successMessage.set(response.message);
          this.loadCollections(wasEditing ? this.pagination().page : 1);
          if (this.detailCollection()?.id_coleccion === response.data.id_coleccion) {
            this.detailCollection.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La colección que intentas editar ya no existe.',
              fallback: currentCollection
                ? 'No pudimos actualizar la colección.'
                : 'No pudimos crear la colección.',
            }),
          );
        },
      });
  }

  protected viewDetail(collectionId: number): void {
    this.detailCollection.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.collectionsService
      .getCollection(collectionId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailCollection.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La colección solicitada ya no existe.',
              fallback: 'No pudimos cargar el detalle de la colección.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(collection: AdminCollection): void {
    this.clearMessages();
    this.statusCollection.set(collection);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusCollection.set(null);
  }

  protected confirmStatusChange(): void {
    const collection = this.statusCollection();
    if (!collection || this.saving()) return;

    this.saving.set(true);
    this.collectionsService
      .updateStatus(collection.id_coleccion, !collection.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusCollection.set(null);
          this.successMessage.set(response.message);
          this.loadCollections(this.pagination().page);
          if (this.detailCollection()?.id_coleccion === response.data.id_coleccion) {
            this.detailCollection.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusCollection.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'La colección solicitada ya no existe.',
              fallback: 'No pudimos actualizar el estado de la colección.',
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
    if (this.canGoPrevious()) this.loadCollections(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadCollections(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  protected isNameInvalid(): boolean {
    const control = this.collectionForm.controls.nombre;
    return control.invalid && (control.touched || control.dirty);
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (!this.active() || this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusCollection.set(null);
    if (this.collectionModalOpen()) this.closeCollectionModal();
  }

  private closeCollectionModalAfterSave(): void {
    this.collectionModalOpen.set(false);
    this.editingCollection.set(null);
    this.collectionForm.reset({ nombre: '', descripcion: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailCollection.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
