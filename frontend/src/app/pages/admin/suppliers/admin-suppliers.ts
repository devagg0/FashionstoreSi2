import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin, Subscription } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminSupplier,
  AdminSupplierPagination,
  AdminSuppliersService,
} from '../../../core/services/admin-suppliers.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';

const EMPTY_PAGINATION: AdminSupplierPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-suppliers',
  imports: [Icon, ReactiveFormsModule],
  templateUrl: './admin-suppliers.html',
  styleUrl: './admin-suppliers.scss',
})
export class AdminSuppliers implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly suppliersService = inject(AdminSuppliersService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);

  protected readonly suppliers = signal<AdminSupplier[]>([]);
  protected readonly pagination = signal<AdminSupplierPagination>(EMPTY_PAGINATION);
  protected readonly totalSuppliers = signal(0);
  protected readonly activeSuppliers = signal(0);
  protected readonly loading = signal(true);
  protected readonly statsLoading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailSupplier = signal<AdminSupplier | null>(null);
  protected readonly supplierModalOpen = signal(false);
  protected readonly editingSupplier = signal<AdminSupplier | null>(null);
  protected readonly statusSupplier = signal<AdminSupplier | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);

  private listRequest?: Subscription;
  protected readonly textFields = [
    { name: 'nombre', label: 'Nombre *', max: 150 },
    { name: 'nit', label: 'NIT', max: 30 },
    { name: 'telefono', label: 'Teléfono', max: 30 },
    { name: 'correo', label: 'Correo', max: 150 },
    { name: 'direccion', label: 'Dirección', max: 200 },
  ] as const;

  protected readonly filters = this.formBuilder.nonNullable.group({ search: '', estado: '' });
  protected readonly supplierForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 150)]],
    nit: ['', Validators.maxLength(30)],
    telefono: ['', Validators.maxLength(30)],
    correo: ['', [Validators.email, Validators.maxLength(150)]],
    direccion: ['', Validators.maxLength(200)],
  });

  ngOnInit(): void {
    this.loadSuppliers();
    this.loadStats();
  }

  protected applyFilters(): void {
    this.loadSuppliers(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '' });
    this.loadSuppliers(1);
  }

  protected loadSuppliers(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.suppliersService
      .listSuppliers({
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
            this.loadSuppliers(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.suppliers.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar los proveedores.',
            }),
          );
        },
      });
  }

  protected openSupplierModal(supplier: AdminSupplier | null = null): void {
    this.clearMessages();
    this.editingSupplier.set(supplier);
    this.supplierForm.reset({
      nit: supplier?.nit ?? '',
      correo: supplier?.correo ?? '',
      nombre: supplier?.nombre ?? '',
      direccion: supplier?.direccion ?? '',
      telefono: supplier?.telefono ?? '',
    });
    this.modalErrorMessage.set(null);
    this.supplierModalOpen.set(true);
  }

  protected closeSupplierModal(): void {
    if (this.saving()) return;
    this.supplierModalOpen.set(false);
    this.editingSupplier.set(null);
    this.supplierForm.reset({ nombre: '' });
    this.modalErrorMessage.set(null);
  }

  protected submitSupplier(): void {
    if (this.saving()) return;
    for (const field of this.textFields) {
      const control = this.supplierForm.controls[field.name];
      control.setValue(control.value.trim());
    }

    this.modalErrorMessage.set(null);
    if (this.supplierForm.invalid) {
      this.supplierForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los datos ingresados.');
      return;
    }

    const values = this.supplierForm.getRawValue();
    const fields = {
      nombre: values.nombre.trim(),
      nit: values.nit.trim() || null,
      telefono: values.telefono.trim() || null,
      correo: values.correo.trim() || null,
      direccion: values.direccion.trim() || null,
    };
    const currentSupplier = this.editingSupplier();
    const changes = Object.fromEntries(
      Object.entries(fields).filter(([key, value]) => {
        const original = currentSupplier?.[key as keyof typeof fields];
        const normalized = key === 'nombre' ? original?.trim() : original?.trim() || null;
        return value !== normalized;
      }),
    );
    if (currentSupplier && Object.keys(changes).length === 0) {
      this.modalErrorMessage.set('No hay cambios para guardar.');
      return;
    }
    const request = currentSupplier
      ? this.suppliersService.updateSupplier(currentSupplier.id_proveedor, changes)
      : this.suppliersService.createSupplier(fields);

    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = currentSupplier !== null;
          this.closeSupplierModalAfterSave();
          this.successMessage.set(
            wasEditing ? 'Proveedor actualizado correctamente.' : 'Proveedor creado correctamente.',
          );
          this.loadSuppliers(wasEditing ? this.pagination().page : 1);
          this.loadStats();
          if (this.detailSupplier()?.id_proveedor === response.data.id_proveedor) {
            this.detailSupplier.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El proveedor solicitado ya no existe.',
              fallback: currentSupplier
                ? 'No pudimos actualizar el proveedor.'
                : 'No pudimos crear el proveedor.',
            }),
          );
        },
      });
  }

  protected viewDetail(supplierId: number): void {
    this.detailSupplier.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();

    this.suppliersService
      .getSupplier(supplierId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailSupplier.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El proveedor solicitado ya no existe.',
              fallback: 'No pudimos cargar el detalle del proveedor.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(supplier: AdminSupplier): void {
    this.clearMessages();
    this.statusSupplier.set(supplier);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusSupplier.set(null);
  }

  protected confirmStatusChange(): void {
    const supplier = this.statusSupplier();
    if (!supplier || this.saving()) return;

    this.saving.set(true);
    this.suppliersService
      .updateStatus(supplier.id_proveedor, !supplier.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusSupplier.set(null);
          this.successMessage.set(
            response.data.estado
              ? 'Proveedor activado correctamente.'
              : 'Proveedor desactivado correctamente.',
          );
          this.loadSuppliers(this.pagination().page);
          this.loadStats();
          if (this.detailSupplier()?.id_proveedor === response.data.id_proveedor) {
            this.detailSupplier.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusSupplier.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El proveedor solicitado ya no existe.',
              fallback: 'No pudimos actualizar el estado del proveedor.',
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
    if (this.canGoPrevious()) this.loadSuppliers(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadSuppliers(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (this.saving() || this.detailLoading()) return;
    this.closeDetailAfterLoad();
    this.statusSupplier.set(null);
    if (this.supplierModalOpen()) this.closeSupplierModal();
  }

  private loadStats(): void {
    this.statsLoading.set(true);
    forkJoin({
      all: this.suppliersService.listSuppliers({ page: 1, pageSize: 1 }),
      active: this.suppliersService.listSuppliers({ estado: true, page: 1, pageSize: 1 }),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.statsLoading.set(false)),
      )
      .subscribe({
        next: ({ all, active }) => {
          this.totalSuppliers.set(all.pagination.total);
          this.activeSuppliers.set(active.pagination.total);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar el resumen de proveedores.',
            }),
          );
        },
      });
  }

  private closeSupplierModalAfterSave(): void {
    this.supplierModalOpen.set(false);
    this.editingSupplier.set(null);
    this.supplierForm.reset({ nombre: '' });
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailSupplier.set(null);
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }
}
