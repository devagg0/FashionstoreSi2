import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { EMPTY, Observable, Subscription, expand, finalize, forkJoin, reduce } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminBranch, AdminBranchesService } from '../../../core/services/admin-branches.service';
import { AdminCity, AdminCitiesService } from '../../../core/services/admin-cities.service';
import {
  AdminCategory,
  AdminCategoriesService,
} from '../../../core/services/admin-categories.service';
import { AdminSize, AdminSizesService } from '../../../core/services/admin-sizes.service';
import { AdminColor, AdminColorsService } from '../../../core/services/admin-colors.service';
import {
  AdminProduct,
  AdminProductVariant,
  AdminProductsService,
} from '../../../core/services/admin-products.service';
import {
  AdminInventoryService,
  Inventory,
  InventoryFilters,
  InventoryPagination,
} from '../../../core/services/admin-inventory.service';
import { Icon } from '../../../shared/components/icon/icon';

function allPages<T>(
  fetch: (page: number) => Observable<{ data: T[]; pagination: InventoryPagination }>,
): Observable<T[]> {
  return fetch(1).pipe(
    expand((response) =>
      response.pagination.page < response.pagination.total_pages
        ? fetch(response.pagination.page + 1)
        : EMPTY,
    ),
    reduce((rows, response) => [...rows, ...response.data], [] as T[]),
  );
}
const minimumValidators = [Validators.required, Validators.min(0), Validators.pattern(/^\d+$/)];

@Component({
  selector: 'app-admin-inventory',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  templateUrl: './admin-inventory.html',
  styleUrl: './admin-inventory.scss',
})
export class AdminInventory implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(AdminInventoryService);
  private readonly branchesService = inject(AdminBranchesService);
  private readonly productsService = inject(AdminProductsService);
  private readonly citiesService = inject(AdminCitiesService);
  private readonly categoriesService = inject(AdminCategoriesService);
  private readonly sizesService = inject(AdminSizesService);
  private readonly colorsService = inject(AdminColorsService);
  private readonly errors = inject(AdminApiErrorService);
  protected readonly inventory = signal<Inventory[]>([]);
  protected readonly pagination = signal<InventoryPagination>({
    page: 1,
    page_size: 10,
    total: 0,
    total_pages: 0,
  });
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly optionsLoading = signal(false);
  protected readonly detailLoading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly optionsError = signal<string | null>(null);
  protected readonly modalError = signal<string | null>(null);
  protected readonly mode = signal<'create' | 'detail' | 'edit' | null>(null);
  protected readonly detail = signal<Inventory | null>(null);
  protected readonly branches = signal<AdminBranch[]>([]);
  protected readonly products = signal<AdminProduct[]>([]);
  protected readonly cities = signal<AdminCity[]>([]);
  protected readonly categories = signal<AdminCategory[]>([]);
  protected readonly sizes = signal<AdminSize[]>([]);
  protected readonly colors = signal<AdminColor[]>([]);
  protected readonly variants = signal<Record<number, AdminProductVariant[]>>({});
  protected readonly variantLoading = signal<Record<number, boolean>>({});
  protected readonly filters = this.fb.group({
    search: ['', Validators.maxLength(200)],
    id_sucursal: this.fb.control<number | null>(null),
    id_ciudad: this.fb.control<number | null>(null),
    id_categoria: this.fb.control<number | null>(null),
    id_producto: this.fb.control<number | null>(null),
    id_variante_producto: this.fb.control<number | null>(null),
    id_talla: this.fb.control<number | null>(null),
    id_color: this.fb.control<number | null>(null),
  });
  protected readonly form = this.fb.group({
    id_sucursal: this.fb.control<number | null>(null, Validators.required),
    id_categoria: this.fb.control<number | null>(null, Validators.required),
    id_producto: this.fb.control<number | null>(null, Validators.required),
    id_variante_producto: this.fb.control<number | null>(null, Validators.required),
    stock_minimo: [0, minimumValidators],
  });
  protected readonly minimumForm = this.fb.group({ stock_minimo: [0, minimumValidators] });
  private appliedFilters: InventoryFilters = {};
  private listRequest?: Subscription;
  private detailRequest?: Subscription;

  ngOnInit(): void {
    this.loadInventory();
    this.loadOptions();
    this.form.controls.id_categoria.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        // El cambio de producto también limpia la variante mediante su suscripción.
        this.form.controls.id_producto.reset();
      });
    for (const group of [this.form, this.filters]) {
      group.controls.id_producto.valueChanges
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((id) => {
          group.controls.id_variante_producto.reset();
          if (id) this.loadVariants(id);
        });
    }
  }
  protected loadOptions(): void {
    this.optionsLoading.set(true);
    this.optionsError.set(null);
    forkJoin({
      branches: allPages((page) => this.branchesService.listBranches({ page, pageSize: 100 })),
      products: allPages((page) => this.productsService.listProducts({ page, pageSize: 100 })),
      cities: allPages((page) => this.citiesService.listCities({ page, pageSize: 100 })),
      categories: allPages((page) =>
        this.categoriesService.listCategories({ page, pageSize: 100 }),
      ),
      sizes: allPages((page) => this.sizesService.listSizes({ page, pageSize: 100 })),
      colors: allPages((page) => this.colorsService.listColors({ page, pageSize: 100 })),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.optionsLoading.set(false)),
      )
      .subscribe({
        next: (data) => {
          this.branches.set(data.branches);
          this.products.set(data.products);
          this.cities.set(data.cities);
          this.categories.set(data.categories);
          this.sizes.set(data.sizes);
          this.colors.set(data.colors);
        },
        error: (error: HttpErrorResponse) => this.optionsError.set(this.resolveError(error)),
      });
  }
  protected cityName(id: number): string {
    return this.cities().find((city) => city.id_ciudad === id)?.nombre ?? 'Ciudad no disponible';
  }
  protected createProductOptions(): AdminProduct[] {
    const categoryId = this.form.controls.id_categoria.value;
    if (
      !this.categories().some((category) => category.id_categoria === categoryId && category.estado)
    ) {
      return [];
    }
    return this.products().filter(
      (product) => product.estado && product.id_categoria === categoryId,
    );
  }
  protected loadVariants(id: number): void {
    if (this.variants()[id] || this.variantLoading()[id]) return;
    this.variantLoading.update((value) => ({ ...value, [id]: true }));
    this.productsService
      .getProduct(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.variantLoading.update((value) => ({ ...value, [id]: false }))),
      )
      .subscribe({
        next: ({ data }) => this.variants.update((value) => ({ ...value, [id]: data.variantes })),
        error: (error: HttpErrorResponse) => {
          const message = this.resolveError(error);
          this.modalError.set(message);
          this.errorMessage.set(message);
        },
      });
  }
  protected variantOptions(id: number | null, activeOnly = false): AdminProductVariant[] {
    return (id ? (this.variants()[id] ?? []) : []).filter(
      (variant) => !activeOnly || variant.estado,
    );
  }
  protected applyFilters(): void {
    if (this.filters.invalid) {
      this.errorMessage.set('La búsqueda admite hasta 200 caracteres.');
      return;
    }
    this.appliedFilters = {};
    const raw = this.filters.getRawValue();
    for (const key of [
      'id_sucursal',
      'id_ciudad',
      'id_categoria',
      'id_producto',
      'id_variante_producto',
      'id_talla',
      'id_color',
    ] as const) {
      if (raw[key] != null) this.appliedFilters[key] = raw[key];
    }
    this.appliedFilters.search = raw.search?.trim() || undefined;
    this.loadInventory();
  }
  protected clearFilters(): void {
    this.filters.reset();
    this.appliedFilters = {};
    this.loadInventory();
  }
  protected loadInventory(page = 1): void {
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.service
      .listInventory({ ...this.appliedFilters, page, pageSize: 10 })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          if (page > 1 && !response.data.length) {
            this.loadInventory(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.inventory.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => this.errorMessage.set(this.resolveError(error)),
      });
  }
  protected openCreate(): void {
    this.form.reset({ stock_minimo: 0 });
    this.modalError.set(null);
    this.successMessage.set(null);
    this.detail.set(null);
    this.mode.set('create');
  }
  protected openDetail(id: number, edit = false): void {
    this.detailRequest?.unsubscribe();
    this.detail.set(null);
    this.modalError.set(null);
    this.successMessage.set(null);
    this.mode.set(edit ? 'edit' : 'detail');
    this.detailLoading.set(true);
    this.detailRequest = this.service
      .getInventory(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: ({ data }) => {
          this.detail.set(data);
          this.minimumForm.reset({ stock_minimo: data.stock_minimo });
        },
        error: (error: HttpErrorResponse) => this.modalError.set(this.resolveError(error)),
      });
  }
  protected submitCreate(): void {
    if (this.saving()) return;
    this.form.markAllAsTouched();
    if (this.form.invalid) {
      this.modalError.set(
        'Selecciona sucursal, categoría, producto y variante. El stock mínimo debe ser un entero mayor o igual a cero.',
      );
      return;
    }
    const raw = this.form.getRawValue();
    if (
      !this.branches().some((b) => b.id_sucursal === raw.id_sucursal && b.estado) ||
      !this.createProductOptions().some((p) => p.id_producto === raw.id_producto) ||
      !this.variantOptions(raw.id_producto, true).some(
        (v) => v.id_variante_producto === raw.id_variante_producto,
      )
    ) {
      this.modalError.set(
        'Selecciona una sucursal, una categoría y una variante activos, y un producto activo de esa categoría.',
      );
      return;
    }
    this.saving.set(true);
    this.modalError.set(null);
    this.service
      .createInventory({
        id_sucursal: raw.id_sucursal!,
        id_variante_producto: raw.id_variante_producto!,
        stock_minimo: raw.stock_minimo!,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: () => {
          this.mode.set(null);
          this.successMessage.set('Producto registrado en el inventario de la sucursal.');
          this.loadInventory();
        },
        error: (error: HttpErrorResponse) => this.modalError.set(this.resolveError(error)),
      });
  }
  protected submitMinimum(): void {
    if (this.saving() || !this.detail()) return;
    this.minimumForm.markAllAsTouched();
    if (this.minimumForm.invalid) {
      this.modalError.set('El stock mínimo debe ser un entero mayor o igual a cero.');
      return;
    }
    this.saving.set(true);
    this.modalError.set(null);
    this.service
      .updateInventory(this.detail()!.id_inventario_sucursal, {
        stock_minimo: this.minimumForm.getRawValue().stock_minimo!,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: () => {
          this.mode.set(null);
          this.successMessage.set('Stock mínimo actualizado correctamente.');
          this.loadInventory(this.pagination().page);
        },
        error: (error: HttpErrorResponse) => this.modalError.set(this.resolveError(error)),
      });
  }
  @HostListener('document:keydown.escape') protected closeModal(): void {
    if (!this.saving()) {
      this.detailRequest?.unsubscribe();
      this.mode.set(null);
    }
  }
  protected formatDate(value: string): string {
    return new Intl.DateTimeFormat('es-BO', { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`),
    );
  }
  protected resolveError(error: HttpErrorResponse): string {
    const message =
      [400, 404, 409].includes(error.status) && typeof error.error?.message === 'string'
        ? error.error.message
        : undefined;
    const duplicate = error.status === 409 && /ya existe|duplicado/i.test(message ?? '');
    return this.errors.resolve(error, {
      notFound: message,
      conflict: duplicate
        ? 'Esta variante ya está registrada en la sucursal seleccionada.'
        : message,
      fallback: message ?? 'No pudimos procesar el inventario. Inténtalo nuevamente.',
    });
  }
}
