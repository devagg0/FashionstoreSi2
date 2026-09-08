import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  computed,
  DestroyRef,
  ElementRef,
  HostListener,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { EMPTY, expand, finalize, forkJoin, Observable, reduce, Subscription } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminCategoriesService,
  AdminCategory,
} from '../../../core/services/admin-categories.service';
import {
  AdminCollection,
  AdminCollectionsService,
} from '../../../core/services/admin-collections.service';
import { AdminColor, AdminColorsService } from '../../../core/services/admin-colors.service';
import {
  AdminProduct,
  AdminProductDetail,
  AdminProductFields,
  AdminProductImage,
  AdminProductPagination,
  AdminProductSupplier,
  AdminProductVariant,
  AdminProductsService,
  ProductSection,
} from '../../../core/services/admin-products.service';
import { AdminSeason, AdminSeasonsService } from '../../../core/services/admin-seasons.service';
import { AdminSize, AdminSizesService } from '../../../core/services/admin-sizes.service';
import {
  AdminSupplier,
  AdminSuppliersService,
} from '../../../core/services/admin-suppliers.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';
import { ProductDetailShell } from './product-detail-shell';

interface PagedResponse<T> {
  data: T[];
  pagination: { page: number; page_size: number; total_pages: number };
}

interface RelatedStatusChange {
  kind: 'variant' | 'supplier';
  id: number;
  label: string;
  estado: boolean;
}

const EMPTY_PAGINATION: AdminProductPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

const MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const ALLOWED_IMAGE_EXTENSION = /\.(?:jpe?g|png|webp)$/i;

@Component({
  selector: 'app-admin-products',
  imports: [Icon, ProductDetailShell, ReactiveFormsModule],
  templateUrl: './admin-products.html',
  styleUrl: './admin-products.scss',
})
export class AdminProducts implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly productsService = inject(AdminProductsService);
  private readonly categoriesService = inject(AdminCategoriesService);
  private readonly sizesService = inject(AdminSizesService);
  private readonly colorsService = inject(AdminColorsService);
  private readonly seasonsService = inject(AdminSeasonsService);
  private readonly collectionsService = inject(AdminCollectionsService);
  private readonly suppliersService = inject(AdminSuppliersService);
  private readonly errorService = inject(AdminApiErrorService);

  protected readonly products = signal<AdminProduct[]>([]);
  protected readonly pagination = signal<AdminProductPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly optionsLoading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly optionsError = signal<string | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);
  protected readonly detailMessage = signal<string | null>(null);
  protected readonly detailError = signal<string | null>(null);

  protected readonly productModalOpen = signal(false);
  protected readonly editingProduct = signal<AdminProduct | null>(null);
  protected readonly statusProduct = signal<AdminProduct | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailProduct = signal<AdminProductDetail | null>(null);

  protected readonly editingVariant = signal<AdminProductVariant | null>(null);
  protected readonly editingSupplier = signal<AdminProductSupplier | null>(null);
  protected readonly selectedImageFile = signal<File | null>(null);
  protected readonly imagePreviewUrl = signal<string | null>(null);
  protected readonly relatedStatus = signal<RelatedStatusChange | null>(null);

  protected readonly categoryOptions = signal<AdminCategory[]>([]);
  protected readonly sizeOptions = signal<AdminSize[]>([]);
  protected readonly colorOptions = signal<AdminColor[]>([]);
  protected readonly seasonOptions = signal<AdminSeason[]>([]);
  protected readonly collectionOptions = signal<AdminCollection[]>([]);
  protected readonly supplierOptions = signal<AdminSupplier[]>([]);

  protected readonly activeCategories = computed(() =>
    this.categoryOptions().filter((item) => item.estado),
  );
  protected readonly availableCollections = computed(() => {
    const associated = new Set(
      this.detailProduct()?.colecciones.map((item) => item.id_coleccion) ?? [],
    );
    return this.collectionOptions().filter(
      (item) => item.estado && !associated.has(item.id_coleccion),
    );
  });
  protected readonly availableSuppliers = computed(() => {
    const activeAssociations = new Set(
      this.detailProduct()
        ?.proveedores.filter((item) => item.estado)
        .map((item) => item.id_proveedor) ?? [],
    );
    return this.supplierOptions().filter(
      (item) => item.estado && !activeAssociations.has(item.id_proveedor),
    );
  });

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
    id_categoria: 0,
  });
  protected readonly productForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, trimmedLengthValidator(1, 150)]],
    descripcion: [''],
    precio: ['', [Validators.required, Validators.pattern(/^\d{1,8}(?:\.\d{1,2})?$/)]],
    seccion: ['UNISEX'],
    id_categoria: [0, [Validators.required, Validators.min(1)]],
    id_temporada: 0,
  });
  protected readonly variantForm = this.formBuilder.nonNullable.group({
    id_talla: [0, [Validators.required, Validators.min(1)]],
    id_color: [0, [Validators.required, Validators.min(1)]],
    sku: ['', [Validators.required, trimmedLengthValidator(1, 100)]],
  });
  protected readonly collectionForm = this.formBuilder.nonNullable.group({
    id_coleccion: [0, [Validators.required, Validators.min(1)]],
  });
  protected readonly supplierForm = this.formBuilder.nonNullable.group({
    id_proveedor: [0, [Validators.required, Validators.min(1)]],
    costo_referencia: ['', Validators.pattern(/^\d{1,8}(?:\.\d{1,2})?$/)],
  });
  protected readonly imageForm = this.formBuilder.nonNullable.group({
    es_principal: false,
  });
  protected readonly imageInput = viewChild<ElementRef<HTMLInputElement>>('imageInput');

  private listRequest?: Subscription;

  ngOnInit(): void {
    this.loadOptions();
    this.loadProducts();
  }

  protected loadOptions(): void {
    if (this.optionsLoading() && this.categoryOptions().length) return;
    this.optionsLoading.set(true);
    this.optionsError.set(null);
    forkJoin({
      categories: this.allPages((page) =>
        this.categoriesService.listCategories({ page, pageSize: 100 }),
      ),
      sizes: this.allPages((page) => this.sizesService.listSizes({ page, pageSize: 100 })),
      colors: this.allPages((page) => this.colorsService.listColors({ page, pageSize: 100 })),
      seasons: this.allPages((page) => this.seasonsService.listSeasons({ page, pageSize: 100 })),
      collections: this.allPages((page) =>
        this.collectionsService.listCollections({ page, pageSize: 100 }),
      ),
      suppliers: this.allPages((page) =>
        this.suppliersService.listSuppliers({ page, pageSize: 100 }),
      ),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.optionsLoading.set(false)),
      )
      .subscribe({
        next: ({ categories, sizes, colors, seasons, collections, suppliers }) => {
          this.categoryOptions.set(categories);
          this.sizeOptions.set(sizes);
          this.colorOptions.set(colors);
          this.seasonOptions.set(seasons);
          this.collectionOptions.set(collections);
          this.supplierOptions.set(suppliers);
        },
        error: (error: HttpErrorResponse) => {
          this.optionsError.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar las opciones para gestionar productos.',
            }),
          );
        },
      });
  }

  protected applyFilters(): void {
    this.loadProducts(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '', id_categoria: 0 });
    this.loadProducts(1);
  }

  protected loadProducts(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';
    const categoryId = filters.id_categoria > 0 ? filters.id_categoria : undefined;

    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.productsService
      .listProducts({
        search: filters.search,
        estado: state,
        idCategoria: categoryId,
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
            this.loadProducts(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.products.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar los productos.',
            }),
          );
        },
      });
  }

  protected openProductModal(product: AdminProduct | null = null): void {
    this.clearMessages();
    this.editingProduct.set(product);
    this.productForm.reset({
      nombre: product?.nombre ?? '',
      descripcion: product?.descripcion ?? '',
      precio: product?.precio ?? '',
      seccion: product?.seccion ?? 'UNISEX',
      id_categoria: product?.id_categoria ?? 0,
      id_temporada: product?.id_temporada ?? 0,
    });
    this.modalErrorMessage.set(null);
    this.productModalOpen.set(true);
  }

  protected editFromDetail(): void {
    const product = this.detailProduct();
    if (!product) return;
    this.closeDetailAfterLoad();
    this.openProductModal(product);
  }

  protected closeProductModal(): void {
    if (this.saving()) return;
    this.productModalOpen.set(false);
    this.editingProduct.set(null);
    this.productForm.reset({
      nombre: '',
      descripcion: '',
      precio: '',
      seccion: 'UNISEX',
      id_categoria: 0,
      id_temporada: 0,
    });
    this.modalErrorMessage.set(null);
  }

  protected submitProduct(): void {
    if (this.saving() || this.optionsLoading() || this.optionsError()) return;
    const name = this.productForm.controls.nombre.value.trim();
    this.productForm.controls.nombre.setValue(name);
    this.modalErrorMessage.set(null);
    if (this.productForm.invalid) {
      this.productForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los datos ingresados.');
      return;
    }

    const raw = this.productForm.getRawValue();
    const fields: AdminProductFields = {
      id_categoria: raw.id_categoria,
      id_temporada: raw.id_temporada > 0 ? raw.id_temporada : null,
      nombre: name,
      seccion: raw.seccion as ProductSection,
      descripcion: raw.descripcion.trim() || null,
      precio: Number(raw.precio),
    };
    const current = this.editingProduct();
    const changes = current ? this.productChanges(current, fields) : fields;
    if (current && Object.keys(changes).length === 0) {
      this.modalErrorMessage.set('No hay cambios para guardar.');
      return;
    }

    const request = current
      ? this.productsService.updateProduct(current.id_producto, changes)
      : this.productsService.createProduct(fields);
    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = current !== null;
          this.closeProductModalAfterSave();
          this.successMessage.set(
            wasEditing ? 'Producto actualizado correctamente.' : 'Producto creado correctamente.',
          );
          this.loadProducts(wasEditing ? this.pagination().page : 1);
          if (this.detailProduct()?.id_producto === response.data.id_producto) {
            this.detailProduct.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.modalErrorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El producto o una referencia seleccionada ya no existe.',
              conflict: 'No fue posible guardar el producto por un conflicto de datos.',
              fallback: current
                ? 'No pudimos actualizar el producto.'
                : 'No pudimos crear el producto.',
            }),
          );
        },
      });
  }

  protected viewDetail(productId: number): void {
    this.detailProduct.set(null);
    this.detailModalOpen.set(true);
    this.loadProductDetail(productId, true);
  }

  protected closeDetail(): void {
    if (this.detailLoading() || this.saving()) return;
    this.closeDetailAfterLoad();
  }

  protected openStatusModal(product: AdminProduct): void {
    this.clearMessages();
    this.statusProduct.set(product);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusProduct.set(null);
  }

  protected confirmStatusChange(): void {
    const product = this.statusProduct();
    if (!product || this.saving()) return;
    this.saving.set(true);
    this.productsService
      .updateStatus(product.id_producto, !product.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusProduct.set(null);
          this.successMessage.set(
            response.data.estado
              ? 'Producto activado correctamente.'
              : 'Producto desactivado correctamente.',
          );
          this.loadProducts(this.pagination().page);
          if (this.detailProduct()?.id_producto === response.data.id_producto) {
            this.detailProduct.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusProduct.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El producto solicitado ya no existe.',
              fallback: 'No pudimos actualizar el estado del producto.',
            }),
          );
        },
      });
  }

  protected startVariantEdit(variant: AdminProductVariant | null = null): void {
    this.editingVariant.set(variant);
    this.variantForm.reset({
      id_talla: variant?.id_talla ?? 0,
      id_color: variant?.id_color ?? 0,
      sku: variant?.sku ?? '',
    });
    this.clearDetailMessages();
  }

  protected cancelVariantEdit(): void {
    if (this.saving()) return;
    this.editingVariant.set(null);
    this.variantForm.reset({ id_talla: 0, id_color: 0, sku: '' });
  }

  protected submitVariant(): void {
    const product = this.detailProduct();
    if (!product || this.saving()) return;
    const sku = this.variantForm.controls.sku.value.trim().toUpperCase();
    this.variantForm.controls.sku.setValue(sku);
    if (this.variantForm.invalid) {
      this.variantForm.markAllAsTouched();
      this.detailError.set('Revisa los datos de la variante.');
      return;
    }
    const raw = this.variantForm.getRawValue();
    const fields = { id_talla: raw.id_talla, id_color: raw.id_color, sku };
    const current = this.editingVariant();
    const changes = current
      ? {
          ...(fields.id_talla !== current.id_talla ? { id_talla: fields.id_talla } : {}),
          ...(fields.id_color !== current.id_color ? { id_color: fields.id_color } : {}),
          ...(fields.sku !== current.sku ? { sku: fields.sku } : {}),
        }
      : fields;
    if (current && Object.keys(changes).length === 0) {
      this.detailError.set('No hay cambios en la variante.');
      return;
    }
    const request = current
      ? this.productsService.updateVariant(
          product.id_producto,
          current.id_variante_producto,
          changes,
        )
      : this.productsService.createVariant(product.id_producto, fields);
    this.runDetailAction(
      product.id_producto,
      request,
      current ? 'Variante actualizada correctamente.' : 'Variante creada correctamente.',
      () => this.cancelVariantEditAfterSave(),
    );
  }

  protected submitCollection(): void {
    const product = this.detailProduct();
    if (!product || this.saving()) return;
    if (this.collectionForm.invalid) {
      this.collectionForm.markAllAsTouched();
      this.detailError.set('Selecciona una colección activa.');
      return;
    }
    this.runDetailAction(
      product.id_producto,
      this.productsService.addCollections(product.id_producto, [
        this.collectionForm.controls.id_coleccion.value,
      ]),
      'Colección asociada correctamente.',
      () => this.collectionForm.reset({ id_coleccion: 0 }),
    );
  }

  protected startSupplierEdit(association: AdminProductSupplier | null = null): void {
    this.editingSupplier.set(association);
    this.supplierForm.reset({
      id_proveedor: association?.id_proveedor ?? 0,
      costo_referencia: association?.costo_referencia ?? '',
    });
    this.clearDetailMessages();
  }

  protected cancelSupplierEdit(): void {
    if (this.saving()) return;
    this.cancelSupplierEditAfterSave();
  }

  protected submitSupplier(): void {
    const product = this.detailProduct();
    if (!product || this.saving()) return;
    if (this.supplierForm.invalid) {
      this.supplierForm.markAllAsTouched();
      this.detailError.set('Revisa el proveedor y el costo de referencia.');
      return;
    }
    const raw = this.supplierForm.getRawValue();
    const referenceCost = raw.costo_referencia === '' ? null : Number(raw.costo_referencia);
    const current = this.editingSupplier();
    if (current && referenceCost === this.numberOrNull(current.costo_referencia)) {
      this.detailError.set('No hay cambios en el costo de referencia.');
      return;
    }
    const request = current
      ? this.productsService.updateSupplierCost(
          product.id_producto,
          current.id_producto_proveedor,
          referenceCost,
        )
      : this.productsService.addSuppliers(product.id_producto, [
          { id_proveedor: raw.id_proveedor, costo_referencia: referenceCost },
        ]);
    this.runDetailAction(
      product.id_producto,
      request,
      current ? 'Costo de referencia actualizado.' : 'Proveedor asociado correctamente.',
      () => this.cancelSupplierEditAfterSave(),
    );
  }

  protected openImagePicker(): void {
    if (!this.saving()) this.imageInput()?.nativeElement.click();
  }

  protected onImageSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.clearDetailMessages();
    this.selectedImageFile.set(null);
    this.imagePreviewUrl.set(null);
    if (!file) return;
    if (!ALLOWED_IMAGE_EXTENSION.test(file.name) || !ALLOWED_IMAGE_TYPES.has(file.type)) {
      input.value = '';
      this.detailError.set('Selecciona una imagen JPG, JPEG, PNG o WEBP válida.');
      return;
    }
    if (file.size === 0) {
      input.value = '';
      this.detailError.set('La imagen seleccionada está vacía.');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE_BYTES) {
      input.value = '';
      this.detailError.set('La imagen no puede superar 5 MB.');
      return;
    }
    this.selectedImageFile.set(file);
    const reader = new FileReader();
    reader.onload = () => this.imagePreviewUrl.set(String(reader.result));
    reader.onerror = () => {
      input.value = '';
      this.selectedImageFile.set(null);
      this.detailError.set('No pudimos generar la vista previa de la imagen.');
    };
    reader.readAsDataURL(file);
  }

  protected submitImage(): void {
    const product = this.detailProduct();
    const file = this.selectedImageFile();
    if (!product || this.saving()) return;
    if (!file) {
      this.detailError.set('Selecciona una imagen para subir.');
      return;
    }
    this.runDetailAction(
      product.id_producto,
      this.productsService.uploadImage(
        product.id_producto,
        file,
        this.imageForm.controls.es_principal.value,
      ),
      'Imagen subida correctamente.',
      () => this.resetImageUpload(),
    );
  }

  protected selectMainImage(image: AdminProductImage): void {
    const product = this.detailProduct();
    if (!product || image.es_principal || this.saving()) return;
    this.runDetailAction(
      product.id_producto,
      this.productsService.updateImage(product.id_producto, image.id_imagen_producto, {
        es_principal: true,
      }),
      'Imagen principal actualizada.',
    );
  }

  protected openRelatedStatus(
    kind: 'variant' | 'supplier',
    id: number,
    label: string,
    estado: boolean,
  ): void {
    this.relatedStatus.set({ kind, id, label, estado });
    this.clearDetailMessages();
  }

  protected closeRelatedStatus(): void {
    if (!this.saving()) this.relatedStatus.set(null);
  }

  protected confirmRelatedStatus(): void {
    const product = this.detailProduct();
    const pending = this.relatedStatus();
    if (!product || !pending || this.saving()) return;
    const request =
      pending.kind === 'variant'
        ? this.productsService.updateVariantStatus(product.id_producto, pending.id, !pending.estado)
        : this.productsService.updateSupplierStatus(
            product.id_producto,
            pending.id,
            !pending.estado,
          );
    this.runDetailAction(
      product.id_producto,
      request,
      `${pending.kind === 'variant' ? 'Variante' : 'Proveedor'} ${
        pending.estado ? 'desactivado' : 'activado'
      } correctamente.`,
      () => this.relatedStatus.set(null),
    );
  }

  protected categoryName(id: number): string {
    return (
      this.categoryOptions().find((item) => item.id_categoria === id)?.nombre ?? `Categoría #${id}`
    );
  }

  protected formatMoney(value: string | number | null): string {
    if (value === null || value === '') return 'Sin costo';
    return `Bs ${new Intl.NumberFormat('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value))}`;
  }

  protected canGoPrevious(): boolean {
    return !this.loading() && this.pagination().page > 1;
  }

  protected canGoNext(): boolean {
    const pagination = this.pagination();
    return !this.loading() && pagination.page < pagination.total_pages;
  }

  protected previousPage(): void {
    if (this.canGoPrevious()) this.loadProducts(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadProducts(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (this.saving() || this.detailLoading()) return;
    if (this.relatedStatus()) {
      this.relatedStatus.set(null);
      return;
    }
    if (this.statusProduct()) {
      this.statusProduct.set(null);
      return;
    }
    if (this.productModalOpen()) {
      this.closeProductModal();
      return;
    }
    if (this.detailModalOpen()) this.closeDetailAfterLoad();
  }

  private allPages<T>(request: (page: number) => Observable<PagedResponse<T>>): Observable<T[]> {
    return request(1).pipe(
      expand((response) =>
        response.pagination.page < response.pagination.total_pages
          ? request(response.pagination.page + 1)
          : EMPTY,
      ),
      reduce((items, response) => [...items, ...response.data], [] as T[]),
    );
  }

  private loadProductDetail(productId: number, showLoading = false): void {
    if (showLoading) this.detailLoading.set(true);
    this.clearDetailMessages();
    this.productsService
      .getProduct(productId)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: (response) => this.detailProduct.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El producto solicitado ya no existe.',
              fallback: 'No pudimos cargar el detalle del producto.',
            }),
          );
        },
      });
  }

  private runDetailAction(
    productId: number,
    request: Observable<unknown>,
    message: string,
    reset?: () => void,
  ): void {
    this.saving.set(true);
    this.clearDetailMessages();
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: () => {
          reset?.();
          this.detailMessage.set(message);
          this.loadProductDetailAfterMutation(productId, message);
          this.loadProducts(this.pagination().page);
        },
        error: (error: HttpErrorResponse) => {
          this.relatedStatus.set(null);
          this.detailError.set(
            this.errorService.resolve(error, {
              notFound: 'El producto o la referencia seleccionada ya no existe.',
              conflict: 'Ese SKU o asociación ya se encuentra registrado.',
              fallback: 'No pudimos completar la operación del producto.',
            }),
          );
        },
      });
  }

  private loadProductDetailAfterMutation(productId: number, message: string): void {
    this.productsService
      .getProduct(productId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.detailProduct.set(response.data);
          this.detailMessage.set(message);
        },
        error: (error: HttpErrorResponse) => {
          this.detailError.set(
            this.errorService.resolve(error, {
              notFound: 'El producto solicitado ya no existe.',
              fallback: 'La operación se guardó, pero no pudimos actualizar el detalle.',
            }),
          );
        },
      });
  }

  private productChanges(
    current: AdminProduct,
    fields: AdminProductFields,
  ): Partial<AdminProductFields> {
    const changes: Partial<AdminProductFields> = {};
    if (fields.nombre !== current.nombre) changes.nombre = fields.nombre;
    if (fields.descripcion !== current.descripcion) changes.descripcion = fields.descripcion;
    if (fields.precio !== Number(current.precio)) changes.precio = fields.precio;
    if (fields.seccion !== current.seccion) changes.seccion = fields.seccion;
    if (fields.id_categoria !== current.id_categoria) changes.id_categoria = fields.id_categoria;
    if (fields.id_temporada !== current.id_temporada) changes.id_temporada = fields.id_temporada;
    return changes;
  }

  private numberOrNull(value: string | null): number | null {
    return value === null ? null : Number(value);
  }

  private cancelVariantEditAfterSave(): void {
    this.editingVariant.set(null);
    this.variantForm.reset({ id_talla: 0, id_color: 0, sku: '' });
  }

  private cancelSupplierEditAfterSave(): void {
    this.editingSupplier.set(null);
    this.supplierForm.reset({ id_proveedor: 0, costo_referencia: '' });
  }

  private resetImageUpload(): void {
    this.selectedImageFile.set(null);
    this.imagePreviewUrl.set(null);
    this.imageForm.reset({ es_principal: false });
    const input = this.imageInput()?.nativeElement;
    if (input) input.value = '';
  }

  private closeProductModalAfterSave(): void {
    this.productModalOpen.set(false);
    this.editingProduct.set(null);
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailProduct.set(null);
    this.relatedStatus.set(null);
    this.cancelVariantEditAfterSave();
    this.cancelSupplierEditAfterSave();
    this.resetImageUpload();
    this.clearDetailMessages();
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }

  private clearDetailMessages(): void {
    this.detailMessage.set(null);
    this.detailError.set(null);
  }
}
