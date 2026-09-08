import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  ValidatorFn,
  Validators,
} from '@angular/forms';
import { finalize, forkJoin, Subscription } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminProduct, AdminProductsService } from '../../../core/services/admin-products.service';
import {
  AdminPromotion,
  AdminPromotionDetail,
  AdminPromotionFields,
  AdminPromotionPagination,
  AdminPromotionProduct,
  AdminPromotionsService,
  PromotionDiscountType,
  PromotionValidity,
} from '../../../core/services/admin-promotions.service';
import { Icon } from '../../../shared/components/icon/icon';
import { trimmedLengthValidator } from '../../../shared/validators/auth.validators';
import { PromotionDetailShell } from './promotion-detail-shell';

const EMPTY_PAGINATION: AdminPromotionPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

const DECIMAL_PATTERN = /^\d{1,8}(?:\.\d{1,2})?$/;

const promotionRulesValidator: ValidatorFn = (
  control: AbstractControl,
): ValidationErrors | null => {
  const type = control.get('tipo_descuento')?.value as PromotionDiscountType | undefined;
  const rawValue = control.get('valor')?.value as string | undefined;
  const start = control.get('fecha_inicio')?.value as string | undefined;
  const end = control.get('fecha_fin')?.value as string | undefined;
  const errors: ValidationErrors = {};
  const value = Number(rawValue);

  if (rawValue && DECIMAL_PATTERN.test(rawValue)) {
    if (value <= 0 || (type === 'PORCENTAJE' && value > 100)) {
      errors['discountValue'] = true;
    }
  }
  if (start && end && end < start) errors['dateRange'] = true;
  return Object.keys(errors).length ? errors : null;
};

@Component({
  selector: 'app-admin-promotions',
  imports: [Icon, PromotionDetailShell, ReactiveFormsModule],
  templateUrl: './admin-promotions.html',
  styleUrl: './admin-promotions.scss',
})
export class AdminPromotions implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly formBuilder = inject(FormBuilder);
  private readonly promotionsService = inject(AdminPromotionsService);
  private readonly productsService = inject(AdminProductsService);
  private readonly errorService = inject(AdminApiErrorService);

  protected readonly promotions = signal<AdminPromotion[]>([]);
  protected readonly pagination = signal<AdminPromotionPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly productsLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly modalErrorMessage = signal<string | null>(null);
  protected readonly detailError = signal<string | null>(null);
  protected readonly detailMessage = signal<string | null>(null);

  protected readonly promotionModalOpen = signal(false);
  protected readonly editingPromotion = signal<AdminPromotion | null>(null);
  protected readonly statusPromotion = signal<AdminPromotion | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailPromotion = signal<AdminPromotionDetail | null>(null);

  protected readonly productOptions = signal<AdminProduct[]>([]);
  protected readonly knownProducts = signal<Record<number, AdminProduct>>({});
  protected readonly selectedProductIds = signal<number[]>([]);
  protected readonly availableProducts = computed(() => {
    const associated = new Set(
      this.detailPromotion()?.productos.map((product) => product.id_producto) ?? [],
    );
    return this.productOptions().filter(
      (product) => product.estado && !associated.has(product.id_producto),
    );
  });

  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    estado: '',
    vigencia: '',
  });
  protected readonly promotionForm = this.formBuilder.nonNullable.group(
    {
      nombre: ['', [Validators.required, trimmedLengthValidator(1, 150)]],
      codigo: ['', Validators.maxLength(50)],
      descripcion: ['', Validators.maxLength(200)],
      tipo_descuento: ['PORCENTAJE' as PromotionDiscountType, Validators.required],
      valor: ['', [Validators.required, Validators.pattern(DECIMAL_PATTERN)]],
      fecha_inicio: ['', Validators.required],
      fecha_fin: ['', Validators.required],
      acumulable: false,
    },
    { validators: promotionRulesValidator },
  );
  protected readonly productSearchForm = this.formBuilder.nonNullable.group({ search: '' });

  private listRequest?: Subscription;

  ngOnInit(): void {
    this.loadPromotions();
  }

  protected applyFilters(): void {
    this.loadPromotions(1);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', estado: '', vigencia: '' });
    this.loadPromotions(1);
  }

  protected loadPromotions(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';
    const validity = (filters.vigencia || undefined) as PromotionValidity | undefined;

    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.listRequest = this.promotionsService
      .listPromotions({
        search: filters.search,
        estado: state,
        vigencia: validity,
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
            this.loadPromotions(Math.max(1, response.pagination.total_pages));
            return;
          }
          this.promotions.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.resolveError(error, { fallback: 'No pudimos cargar las promociones.' }),
          );
        },
      });
  }

  protected openPromotionModal(promotion: AdminPromotion | null = null): void {
    this.clearMessages();
    this.editingPromotion.set(promotion);
    this.promotionForm.reset({
      nombre: promotion?.nombre ?? '',
      codigo: promotion?.codigo ?? '',
      descripcion: promotion?.descripcion ?? '',
      tipo_descuento: promotion?.tipo_descuento ?? 'PORCENTAJE',
      valor: promotion?.valor ?? '',
      fecha_inicio: promotion ? this.toLocalInput(promotion.fecha_inicio) : '',
      fecha_fin: promotion ? this.toLocalInput(promotion.fecha_fin) : '',
      acumulable: promotion?.acumulable ?? false,
    });
    this.modalErrorMessage.set(null);
    this.promotionModalOpen.set(true);
  }

  protected editFromDetail(): void {
    const promotion = this.detailPromotion();
    if (!promotion) return;
    this.closeDetailAfterLoad();
    this.openPromotionModal(promotion);
  }

  protected closePromotionModal(): void {
    if (this.saving()) return;
    this.closePromotionModalAfterSave();
  }

  protected submitPromotion(): void {
    if (this.saving()) return;
    const name = this.promotionForm.controls.nombre.value.trim();
    const code = this.promotionForm.controls.codigo.value.trim().toUpperCase();
    this.promotionForm.controls.nombre.setValue(name);
    this.promotionForm.controls.codigo.setValue(code);
    this.modalErrorMessage.set(null);
    if (this.promotionForm.invalid) {
      this.promotionForm.markAllAsTouched();
      this.modalErrorMessage.set('Revisa los datos ingresados.');
      return;
    }

    const raw = this.promotionForm.getRawValue();
    const fields: AdminPromotionFields = {
      nombre: name,
      codigo: code || null,
      descripcion: raw.descripcion.trim() || null,
      tipo_descuento: raw.tipo_descuento,
      valor: Number(raw.valor),
      fecha_inicio: this.toApiDate(raw.fecha_inicio),
      fecha_fin: this.toApiDate(raw.fecha_fin),
      acumulable: raw.acumulable,
    };
    const current = this.editingPromotion();
    const changes = current ? this.promotionChanges(current, fields) : fields;
    if (current && Object.keys(changes).length === 0) {
      this.modalErrorMessage.set('No hay cambios para guardar.');
      return;
    }

    const request = current
      ? this.promotionsService.updatePromotion(current.id_promocion, changes)
      : this.promotionsService.createPromotion(fields);
    this.saving.set(true);
    request
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          const wasEditing = current !== null;
          this.closePromotionModalAfterSave();
          this.successMessage.set(
            wasEditing
              ? 'Promoción actualizada correctamente.'
              : 'Promoción creada correctamente.',
          );
          this.loadPromotions(wasEditing ? this.pagination().page : 1);
          if (this.detailPromotion()?.id_promocion === response.data.id_promocion) {
            this.detailPromotion.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.modalErrorMessage.set(
            this.resolveError(error, {
              notFound: 'La promoción solicitada ya no existe.',
              conflict: 'El código ya está registrado.',
              fallback: current
                ? 'No pudimos actualizar la promoción.'
                : 'No pudimos crear la promoción.',
            }),
          );
        },
      });
  }

  protected viewDetail(promotionId: number): void {
    this.detailPromotion.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.clearMessages();
    this.clearDetailMessages();
    this.selectedProductIds.set([]);
    this.productSearchForm.reset({ search: '' });

    forkJoin({
      detail: this.promotionsService.getPromotion(promotionId),
      products: this.promotionsService.listProducts(promotionId),
    })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.detailLoading.set(false)),
      )
      .subscribe({
        next: ({ detail, products }) => {
          this.detailPromotion.set({ ...detail.data, productos: products.data });
          this.loadAvailableProducts();
        },
        error: (error: HttpErrorResponse) => {
          this.closeDetailAfterLoad();
          this.errorMessage.set(
            this.resolveError(error, {
              notFound: 'La promoción solicitada ya no existe.',
              fallback: 'No pudimos cargar el detalle de la promoción.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading() || this.saving()) return;
    this.closeDetailAfterLoad();
  }

  protected loadAvailableProducts(): void {
    if (!this.detailPromotion()) return;
    this.productsLoading.set(true);
    this.detailError.set(null);
    this.productsService
      .listProducts({
        search: this.productSearchForm.controls.search.value,
        estado: true,
        page: 1,
        pageSize: 100,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.productsLoading.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.productOptions.set(response.data);
          this.knownProducts.update((current) => ({
            ...current,
            ...Object.fromEntries(response.data.map((product) => [product.id_producto, product])),
          }));
        },
        error: (error: HttpErrorResponse) => {
          this.detailError.set(
            this.resolveError(error, {
              fallback: 'No pudimos consultar los productos activos.',
            }),
          );
        },
      });
  }

  protected toggleProduct(productId: number, checked: boolean): void {
    this.selectedProductIds.update((ids) =>
      checked ? [...new Set([...ids, productId])] : ids.filter((id) => id !== productId),
    );
  }

  protected isProductSelected(productId: number): boolean {
    return this.selectedProductIds().includes(productId);
  }

  protected associateProducts(): void {
    const promotion = this.detailPromotion();
    const productIds = this.selectedProductIds();
    if (!promotion || this.saving()) return;
    if (!productIds.length) {
      this.detailError.set('Selecciona al menos un producto activo.');
      return;
    }

    this.saving.set(true);
    this.clearDetailMessages();
    this.promotionsService
      .addProducts(promotion.id_promocion, productIds)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.detailPromotion.update((current) =>
            current
              ? {
                  ...current,
                  productos: response.data,
                  total_productos: response.data.length,
                }
              : current,
          );
          this.selectedProductIds.set([]);
          this.detailMessage.set('Productos asociados correctamente.');
          this.loadAvailableProducts();
          this.loadPromotions(this.pagination().page);
        },
        error: (error: HttpErrorResponse) => {
          this.detailError.set(
            this.resolveError(error, {
              notFound: 'La promoción o uno de los productos ya no existe.',
              conflict: 'Uno de los productos ya está asociado a la promoción.',
              fallback: 'No pudimos asociar los productos.',
            }),
          );
        },
      });
  }

  protected openStatusModal(promotion: AdminPromotion): void {
    this.clearMessages();
    this.statusPromotion.set(promotion);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusPromotion.set(null);
  }

  protected confirmStatusChange(): void {
    const promotion = this.statusPromotion();
    if (!promotion || this.saving()) return;
    this.saving.set(true);
    this.promotionsService
      .updateStatus(promotion.id_promocion, !promotion.estado)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.statusPromotion.set(null);
          this.successMessage.set(
            response.data.estado
              ? 'Promoción activada correctamente.'
              : 'Promoción desactivada correctamente.',
          );
          this.loadPromotions(this.pagination().page);
          if (this.detailPromotion()?.id_promocion === response.data.id_promocion) {
            this.detailPromotion.set(response.data);
          }
        },
        error: (error: HttpErrorResponse) => {
          this.statusPromotion.set(null);
          this.errorMessage.set(
            this.resolveError(error, {
              notFound: 'La promoción solicitada ya no existe.',
              fallback: 'No pudimos actualizar el estado de la promoción.',
            }),
          );
        },
      });
  }

  protected formatDiscount(promotion: Pick<AdminPromotion, 'tipo_descuento' | 'valor'>): string {
    const value = new Intl.NumberFormat('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(promotion.valor));
    return promotion.tipo_descuento === 'PORCENTAJE' ? `${value}%` : `Bs ${value}`;
  }

  protected formatMoney(value: string | number): string {
    return `Bs ${new Intl.NumberFormat('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value))}`;
  }

  protected formatDate(value: string): string {
    const date = this.parseApiDate(value);
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(date);
  }

  protected validityLabel(validity: PromotionValidity): string {
    return {
      PROGRAMADA: 'Programada',
      VIGENTE: 'Vigente',
      EXPIRADA: 'Expirada',
    }[validity];
  }

  protected productCategory(product: AdminPromotionProduct): string {
    return (
      product.categoria ??
      this.knownProducts()[product.id_producto]?.categoria ??
      'No disponible'
    );
  }

  protected canGoPrevious(): boolean {
    return !this.loading() && this.pagination().page > 1;
  }

  protected canGoNext(): boolean {
    return !this.loading() && this.pagination().page < this.pagination().total_pages;
  }

  protected previousPage(): void {
    if (this.canGoPrevious()) this.loadPromotions(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadPromotions(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (this.saving() || this.detailLoading()) return;
    if (this.statusPromotion()) {
      this.statusPromotion.set(null);
      return;
    }
    if (this.promotionModalOpen()) {
      this.closePromotionModal();
      return;
    }
    if (this.detailModalOpen()) this.closeDetailAfterLoad();
  }

  private promotionChanges(
    current: AdminPromotion,
    fields: AdminPromotionFields,
  ): Partial<AdminPromotionFields> {
    const changes: Partial<AdminPromotionFields> = {};
    if (fields.nombre !== current.nombre) changes.nombre = fields.nombre;
    if (fields.codigo !== current.codigo) changes.codigo = fields.codigo;
    if (fields.descripcion !== current.descripcion) changes.descripcion = fields.descripcion;
    if (fields.tipo_descuento !== current.tipo_descuento) {
      changes.tipo_descuento = fields.tipo_descuento;
    }
    if (fields.valor !== Number(current.valor)) changes.valor = fields.valor;
    if (fields.fecha_inicio !== this.normalizeApiDate(current.fecha_inicio)) {
      changes.fecha_inicio = fields.fecha_inicio;
    }
    if (fields.fecha_fin !== this.normalizeApiDate(current.fecha_fin)) {
      changes.fecha_fin = fields.fecha_fin;
    }
    if (fields.acumulable !== current.acumulable) changes.acumulable = fields.acumulable;
    return changes;
  }

  private toApiDate(value: string): string {
    return new Date(value).toISOString();
  }

  private toLocalInput(value: string): string {
    const date = this.parseApiDate(value);
    const offset = date.getTimezoneOffset() * 60_000;
    return new Date(date.getTime() - offset).toISOString().slice(0, 16);
  }

  private normalizeApiDate(value: string): string {
    return this.parseApiDate(value).toISOString();
  }

  private parseApiDate(value: string): Date {
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  }

  private closePromotionModalAfterSave(): void {
    this.promotionModalOpen.set(false);
    this.editingPromotion.set(null);
    this.modalErrorMessage.set(null);
  }

  private closeDetailAfterLoad(): void {
    this.detailModalOpen.set(false);
    this.detailPromotion.set(null);
    this.productOptions.set([]);
    this.knownProducts.set({});
    this.selectedProductIds.set([]);
    this.clearDetailMessages();
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }

  private clearDetailMessages(): void {
    this.detailError.set(null);
    this.detailMessage.set(null);
  }

  private resolveError(
    error: HttpErrorResponse,
    messages: { notFound?: string; conflict?: string; fallback?: string },
  ): string {
    const fallback = this.errorService.resolve(error, messages);
    const body: unknown = error.error;
    if (typeof body === 'object' && body !== null && 'message' in body) {
      const message = body.message;
      if (typeof message === 'string' && message.trim()) return message;
    }
    return fallback;
  }
}
