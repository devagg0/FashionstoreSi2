import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
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
import { AdminProduct, AdminProductsService } from '../../../core/services/admin-products.service';
import {
  AdminGlobalInventoryService,
  GlobalInventory,
  GlobalInventoryDetail,
  GlobalInventoryFilters,
  GlobalInventoryPagination,
} from '../../../core/services/admin-global-inventory.service';

// Solo concatena opciones de los catálogos; los totales de inventario proceden de CU16.
function allPages<T>(
  fetch: (page: number) => Observable<{ data: T[]; pagination: GlobalInventoryPagination }>,
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

@Component({
  selector: 'app-admin-global-inventory',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './admin-global-inventory.html',
  styleUrl: './admin-global-inventory.scss',
})
export class AdminGlobalInventory implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(AdminGlobalInventoryService);
  private readonly branchesService = inject(AdminBranchesService);
  private readonly productsService = inject(AdminProductsService);
  private readonly citiesService = inject(AdminCitiesService);
  private readonly categoriesService = inject(AdminCategoriesService);
  private readonly sizesService = inject(AdminSizesService);
  private readonly colorsService = inject(AdminColorsService);
  private readonly errors = inject(AdminApiErrorService);
  private readonly detailPanel = viewChild<ElementRef<HTMLElement>>('detailPanel');
  private detailTrigger?: HTMLElement;
  private appliedFilters: GlobalInventoryFilters = {};
  private listRequest?: Subscription;
  private detailRequest?: Subscription;
  protected readonly inventory = signal<GlobalInventory[]>([]);
  protected readonly pagination = signal<GlobalInventoryPagination>({
    page: 1,
    page_size: 10,
    total: 0,
    total_pages: 0,
  });
  protected readonly loading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly optionsLoading = signal(false);
  protected readonly optionsError = signal<string | null>(null);
  protected readonly detailId = signal<number | null>(null);
  protected readonly detail = signal<GlobalInventoryDetail | null>(null);
  protected readonly detailLoading = signal(false);
  protected readonly detailError = signal<string | null>(null);
  protected readonly branches = signal<AdminBranch[]>([]);
  protected readonly products = signal<AdminProduct[]>([]);
  protected readonly cities = signal<AdminCity[]>([]);
  protected readonly categories = signal<AdminCategory[]>([]);
  protected readonly sizes = signal<AdminSize[]>([]);
  protected readonly colors = signal<AdminColor[]>([]);
  protected readonly filters = this.fb.group({
    search: ['', Validators.maxLength(200)],
    id_categoria: this.fb.control<number | null>(null),
    id_producto: this.fb.control<number | null>(null),
    id_talla: this.fb.control<number | null>(null),
    id_color: this.fb.control<number | null>(null),
    id_ciudad: this.fb.control<number | null>(null),
    id_sucursal: this.fb.control<number | null>(null),
  });

  constructor() {
    effect(() => this.detailPanel()?.nativeElement.focus());
  }

  ngOnInit(): void {
    this.loadInventory();
    this.loadOptions();
  }

  protected loadOptions(): void {
    if (this.optionsLoading()) return;
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

  protected applyFilters(): void {
    if (this.filters.invalid) {
      this.errorMessage.set('La búsqueda admite hasta 200 caracteres.');
      return;
    }
    const raw = this.filters.getRawValue();
    this.appliedFilters = { search: raw.search?.trim() || undefined };
    for (const key of [
      'id_categoria',
      'id_producto',
      'id_talla',
      'id_color',
      'id_ciudad',
      'id_sucursal',
    ] as const) {
      if (raw[key] != null) this.appliedFilters[key] = raw[key];
    }
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
      .listGlobalInventory({ ...this.appliedFilters, page, pageSize: 10 })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.inventory.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => this.errorMessage.set(this.resolveError(error)),
      });
  }

  protected openDetail(id: number, event?: Event): void {
    if (event?.currentTarget instanceof HTMLElement) this.detailTrigger = event.currentTarget;
    this.detailRequest?.unsubscribe();
    this.detailId.set(id);
    this.detail.set(null);
    this.detailError.set(null);
    this.detailLoading.set(true);
    this.detailRequest = this.service
      .getGlobalInventoryDetail(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: ({ data }) => this.detail.set(data),
        error: (error: HttpErrorResponse) => this.detailError.set(this.resolveError(error)),
      });
  }

  protected closeDetail(): void {
    this.detailRequest?.unsubscribe();
    this.detailId.set(null);
    this.detail.set(null);
    this.detailTrigger?.focus();
  }

  private resolveError(error: HttpErrorResponse): string {
    const message = typeof error.error?.message === 'string' ? error.error.message : undefined;
    const resolved = this.errors.resolve(error, {
      notFound: message ?? 'La variante no existe.',
      fallback: message ?? 'No pudimos consultar el inventario global. Inténtalo nuevamente.',
    });
    return error.status === 422
      ? (message ?? 'Los filtros no son válidos. Revisa los valores seleccionados.')
      : resolved;
  }
}
