import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, ParamMap, Router } from '@angular/router';
import { finalize } from 'rxjs';
import {
  CatalogColor,
  CatalogFilters,
  CatalogProduct,
  CatalogSection,
  CatalogSize,
  CatalogSort,
  CatalogService,
} from '../../core/services/catalog.service';
import { Icon } from '../../shared/components/icon/icon';
import { CatalogProductCard } from './product-card/product-card';

interface CategoryOption {
  id_categoria: number;
  nombre: string;
}

@Component({
  selector: 'app-catalog',
  imports: [CatalogProductCard, Icon, ReactiveFormsModule],
  templateUrl: './catalog.html',
  styleUrl: './catalog.scss',
})
export class Catalog implements OnInit {
  private readonly catalogService = inject(CatalogService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);
  private requestSequence = 0;

  protected readonly products = signal<CatalogProduct[]>([]);
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly filtersVisible = signal(false);
  protected readonly appliedFilters = signal<CatalogFilters>({});
  protected readonly page = signal(1);
  protected readonly total = signal(0);
  protected readonly totalPages = signal(0);
  protected readonly categoryOptions = signal<CategoryOption[]>([]);
  protected readonly sizeOptions = signal<CatalogSize[]>([]);
  protected readonly colorOptions = signal<CatalogColor[]>([]);
  protected readonly branchName = signal('');

  protected readonly filterForm = this.fb.nonNullable.group({
    search: '',
    seccion: '',
    idCategoria: '',
    idTalla: '',
    idColor: '',
    precioMin: '',
    precioMax: '',
    soloPromociones: false,
    idCiudad: '',
    idSucursal: '',
    sort: 'recientes' as CatalogSort,
  });

  protected readonly title = computed(() => {
    const filters = this.appliedFilters();
    if (filters.idCategoria) {
      return (
        this.categoryOptions().find((item) => item.id_categoria === filters.idCategoria)?.nombre ??
        'Categoría seleccionada'
      );
    }
    const labels: Record<CatalogSection, string> = {
      HOMBRE: 'Hombre',
      MUJER: 'Mujer',
      UNISEX: 'Unisex',
    };
    return filters.seccion ? labels[filters.seccion] : 'Todos los productos';
  });

  protected readonly activeFilterCount = computed(() => {
    const filters = this.appliedFilters();
    return [
      filters.search,
      filters.seccion,
      filters.idCategoria,
      filters.idTalla,
      filters.idColor,
      filters.precioMin,
      filters.precioMax,
      filters.enPromocion,
      filters.idCiudad,
      filters.idSucursal,
    ].filter((value) => value !== undefined && value !== '').length;
  });

  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const filters = this.filtersFromParams(params);
      this.page.set(filters.page ?? 1);
      this.appliedFilters.set(filters);
      this.patchForm(filters);
      this.loadProducts(filters);
    });
  }

  protected applyFilters(): void {
    const filters = this.filtersFromForm();
    if (
      filters.precioMin !== undefined &&
      filters.precioMax !== undefined &&
      filters.precioMin > filters.precioMax
    ) {
      this.errorMessage.set('El precio mínimo no puede ser mayor que el precio máximo.');
      return;
    }
    this.navigateWithFilters(filters, 1);
    this.filtersVisible.set(false);
  }

  protected clearFilters(): void {
    const sort = this.filterForm.controls.sort.value;
    this.filterForm.reset({
      search: '',
      seccion: '',
      idCategoria: '',
      idTalla: '',
      idColor: '',
      precioMin: '',
      precioMax: '',
      soloPromociones: false,
      idCiudad: '',
      idSucursal: '',
      sort,
    });
    this.navigateWithFilters({ sort }, 1);
  }

  protected applySearch(): void {
    this.navigateWithFilters(this.filtersFromForm(), 1);
  }

  protected changeSort(): void {
    this.navigateWithFilters(this.filtersFromForm(), 1);
  }

  protected goToPage(target: number): void {
    if (target < 1 || target > this.totalPages() || target === this.page()) return;
    this.navigateWithFilters(this.filtersFromForm(), target);
    globalThis.scrollTo?.({ top: 0, behavior: 'smooth' });
  }

  protected selectColor(colorId: number): void {
    const control = this.filterForm.controls.idColor;
    control.setValue(control.value === String(colorId) ? '' : String(colorId));
  }

  protected retry(): void {
    this.loadProducts(this.appliedFilters());
  }

  protected toggleFilters(): void {
    this.filtersVisible.update((visible) => !visible);
  }

  private loadProducts(filters: CatalogFilters): void {
    const sequence = ++this.requestSequence;
    this.loading.set(true);
    this.errorMessage.set('');
    this.catalogService
      .listProducts(filters)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => {
          if (sequence === this.requestSequence) this.loading.set(false);
        }),
      )
      .subscribe({
        next: (response) => {
          if (sequence !== this.requestSequence) return;
          this.products.set(response.data);
          this.total.set(response.pagination.total);
          this.totalPages.set(response.pagination.total_pages);
          this.mergeFilterOptions(response.data);
          const located = response.data.find((item) => item.disponibilidad_sucursal);
          this.branchName.set(located?.disponibilidad_sucursal?.sucursal ?? '');
        },
        error: (error: HttpErrorResponse) => {
          if (sequence !== this.requestSequence) return;
          this.products.set([]);
          this.total.set(0);
          this.totalPages.set(0);
          this.errorMessage.set(this.resolveError(error));
        },
      });
  }

  private mergeFilterOptions(products: CatalogProduct[]): void {
    const categories = new Map(this.categoryOptions().map((item) => [item.id_categoria, item]));
    const sizes = new Map(this.sizeOptions().map((item) => [item.id_talla, item]));
    const colors = new Map(this.colorOptions().map((item) => [item.id_color, item]));
    for (const product of products) {
      categories.set(product.id_categoria, {
        id_categoria: product.id_categoria,
        nombre: product.categoria,
      });
      for (const size of product.tallas_disponibles) sizes.set(size.id_talla, size);
      for (const color of product.colores_disponibles) colors.set(color.id_color, color);
    }
    this.categoryOptions.set(
      [...categories.values()].sort((a, b) => a.nombre.localeCompare(b.nombre)),
    );
    this.sizeOptions.set([...sizes.values()].sort((a, b) => a.nombre.localeCompare(b.nombre)));
    this.colorOptions.set([...colors.values()].sort((a, b) => a.nombre.localeCompare(b.nombre)));
  }

  private filtersFromForm(): CatalogFilters {
    const value = this.filterForm.getRawValue();
    return {
      search: value.search.trim() || undefined,
      seccion: this.isSection(value.seccion) ? value.seccion : undefined,
      idCategoria: this.positiveNumber(value.idCategoria),
      idTalla: this.positiveNumber(value.idTalla),
      idColor: this.positiveNumber(value.idColor),
      precioMin: this.nonNegativeNumber(value.precioMin),
      precioMax: this.nonNegativeNumber(value.precioMax),
      enPromocion: value.soloPromociones || undefined,
      idCiudad: this.positiveNumber(value.idCiudad),
      idSucursal: this.positiveNumber(value.idSucursal),
      sort: value.sort,
    };
  }

  private filtersFromParams(params: ParamMap): CatalogFilters {
    const section = params.get('seccion') ?? '';
    const sort = params.get('sort') ?? '';
    return {
      search: params.get('search')?.trim() || undefined,
      seccion: this.isSection(section) ? section : undefined,
      idCategoria: this.positiveNumber(params.get('id_categoria')),
      idTalla: this.positiveNumber(params.get('id_talla')),
      idColor: this.positiveNumber(params.get('id_color')),
      precioMin: this.nonNegativeNumber(params.get('precio_min')),
      precioMax: this.nonNegativeNumber(params.get('precio_max')),
      enPromocion: params.get('en_promocion') === 'true' || undefined,
      idCiudad: this.positiveNumber(params.get('id_ciudad')),
      idSucursal: this.positiveNumber(params.get('id_sucursal')),
      sort: this.isSort(sort) ? sort : 'recientes',
      page: this.positiveNumber(params.get('page')) ?? 1,
      pageSize: 12,
    };
  }

  private patchForm(filters: CatalogFilters): void {
    this.filterForm.patchValue(
      {
        search: filters.search ?? '',
        seccion: filters.seccion ?? '',
        idCategoria: filters.idCategoria ? String(filters.idCategoria) : '',
        idTalla: filters.idTalla ? String(filters.idTalla) : '',
        idColor: filters.idColor ? String(filters.idColor) : '',
        precioMin: filters.precioMin !== undefined ? String(filters.precioMin) : '',
        precioMax: filters.precioMax !== undefined ? String(filters.precioMax) : '',
        soloPromociones: filters.enPromocion ?? false,
        idCiudad: filters.idCiudad ? String(filters.idCiudad) : '',
        idSucursal: filters.idSucursal ? String(filters.idSucursal) : '',
        sort: filters.sort ?? 'recientes',
      },
      { emitEvent: false },
    );
  }

  private navigateWithFilters(filters: CatalogFilters, page: number): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        search: filters.search || null,
        seccion: filters.seccion || null,
        id_categoria: filters.idCategoria ?? null,
        id_talla: filters.idTalla ?? null,
        id_color: filters.idColor ?? null,
        precio_min: filters.precioMin ?? null,
        precio_max: filters.precioMax ?? null,
        en_promocion: filters.enPromocion ? true : null,
        id_ciudad: filters.idCiudad ?? null,
        id_sucursal: filters.idSucursal ?? null,
        sort: filters.sort === 'recientes' ? null : filters.sort,
        page: page > 1 ? page : null,
      },
    });
  }

  private resolveError(error: HttpErrorResponse): string {
    const message =
      typeof error.error === 'object' && error.error && typeof error.error.message === 'string'
        ? error.error.message
        : '';
    if (error.status === 404) return message || 'La ubicación seleccionada ya no está disponible.';
    if (error.status === 422) return message || 'Revisa los filtros seleccionados.';
    return 'No pudimos cargar el catálogo. Inténtalo nuevamente.';
  }

  private positiveNumber(value: string | null): number | undefined {
    const parsed = Number(value);
    return value !== null && value !== '' && Number.isInteger(parsed) && parsed > 0
      ? parsed
      : undefined;
  }

  private nonNegativeNumber(value: string | null): number | undefined {
    const parsed = Number(value);
    return value !== null && value !== '' && Number.isFinite(parsed) && parsed >= 0
      ? parsed
      : undefined;
  }

  private isSection(value: string): value is CatalogSection {
    return ['HOMBRE', 'MUJER', 'UNISEX'].includes(value);
  }

  private isSort(value: string): value is CatalogSort {
    return ['recientes', 'precio_asc', 'precio_desc', 'nombre'].includes(value);
  }
}
