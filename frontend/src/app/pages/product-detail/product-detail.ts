import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { combineLatest, finalize } from 'rxjs';
import {
  CatalogProductDetail,
  CatalogPromotion,
  CatalogService,
  CatalogVariant,
} from '../../core/services/catalog.service';
import { Icon } from '../../shared/components/icon/icon';
import { CatalogAvailability } from './catalog-availability/catalog-availability';

@Component({
  selector: 'app-product-detail',
  imports: [Icon, RouterLink, CatalogAvailability],
  templateUrl: './product-detail.html',
  styleUrl: './product-detail.scss',
})
export class ProductDetail {
  private readonly catalogService = inject(CatalogService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly product = signal<CatalogProductDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly selectedImage = signal<string | null>(null);
  protected readonly selectedColorId = signal<number | null>(null);
  protected readonly selectedSizeId = signal<number | null>(null);
  protected readonly failedImages = signal<Set<string>>(new Set());
  protected readonly branchId = signal<number | undefined>(undefined);
  protected readonly cityId = signal<number | undefined>(undefined);

  protected readonly selectedVariant = computed(() => {
    const colorId = this.selectedColorId();
    const sizeId = this.selectedSizeId();
    if (colorId === null || sizeId === null) return null;
    return (
      this.product()?.variantes.find(
        (variant) => variant.color.id_color === colorId && variant.talla.id_talla === sizeId,
      ) ?? null
    );
  });

  protected readonly visibleImages = computed(() => {
    const failed = this.failedImages();
    return this.product()?.galeria.filter((image) => !failed.has(image.url_imagen)) ?? [];
  });

  protected readonly selectedColorName = computed(
    () =>
      this.product()?.colores.find((color) => color.id_color === this.selectedColorId())?.nombre ??
      'Selecciona una opción',
  );

  protected readonly selectedSizeName = computed(
    () =>
      this.product()?.tallas.find((size) => size.id_talla === this.selectedSizeId())?.nombre ??
      'Selecciona una opción',
  );

  constructor() {
    combineLatest([this.route.paramMap, this.route.queryParamMap])
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(([params, query]) => {
        const productId = Number(params.get('id'));
        this.branchId.set(this.positiveNumber(query.get('id_sucursal')));
        this.cityId.set(this.positiveNumber(query.get('id_ciudad')));
        if (!Number.isInteger(productId) || productId <= 0) {
          this.loading.set(false);
          this.errorMessage.set('El producto solicitado no es válido.');
          return;
        }
        this.loadProduct(productId);
      });
  }

  protected selectImage(url: string): void {
    this.selectedImage.set(url);
  }

  protected selectColor(colorId: number): void {
    this.selectedColorId.set(colorId);
    const sizeId = this.selectedSizeId();
    if (sizeId !== null && !this.hasCombination(colorId, sizeId)) this.selectedSizeId.set(null);
  }

  protected selectSize(sizeId: number): void {
    this.selectedSizeId.set(sizeId);
    const colorId = this.selectedColorId();
    if (colorId !== null && !this.hasCombination(colorId, sizeId)) this.selectedColorId.set(null);
  }

  protected isSizeEnabled(sizeId: number): boolean {
    const colorId = this.selectedColorId();
    return (
      this.product()?.variantes.some(
        (variant) =>
          variant.talla.id_talla === sizeId &&
          (colorId === null || variant.color.id_color === colorId),
      ) ?? false
    );
  }

  protected isColorEnabled(colorId: number): boolean {
    const sizeId = this.selectedSizeId();
    return (
      this.product()?.variantes.some(
        (variant) =>
          variant.color.id_color === colorId &&
          (sizeId === null || variant.talla.id_talla === sizeId),
      ) ?? false
    );
  }

  protected imageFailed(url: string): void {
    this.failedImages.update((current) => new Set([...current, url]));
    if (this.selectedImage() === url) {
      this.selectedImage.set(this.visibleImages()[0]?.url_imagen ?? null);
    }
  }

  protected availabilityLabel(variant: CatalogVariant): string {
    const quantity = variant.disponibilidad_sucursal?.cantidad_disponible;
    if (quantity === undefined) return 'Selecciona una sucursal';
    if (quantity === 0) return 'Sin stock';
    if (quantity <= 3) return 'Pocas unidades';
    return 'Disponible';
  }

  protected availabilityClass(variant: CatalogVariant): string {
    const quantity = variant.disponibilidad_sucursal?.cantidad_disponible;
    if (!quantity) return 'stock-message--empty';
    return quantity <= 3 ? 'stock-message--low' : 'stock-message--available';
  }

  protected promotionLabel(promotion: CatalogPromotion): string {
    return promotion.tipo_descuento === 'PORCENTAJE'
      ? `-${Number(promotion.valor).toLocaleString('es-BO', { maximumFractionDigits: 2 })}%`
      : `Ahorra ${this.formatMoney(promotion.monto_descuento)}`;
  }

  protected formatMoney(value: string): string {
    return `Bs ${new Intl.NumberFormat('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value))}`;
  }

  protected catalogQueryParams(): Record<string, number> {
    const params: Record<string, number> = {};
    if (this.cityId() !== undefined) params['id_ciudad'] = this.cityId()!;
    if (this.branchId() !== undefined) params['id_sucursal'] = this.branchId()!;
    return params;
  }

  protected retry(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (id > 0) this.loadProduct(id);
  }

  private loadProduct(productId: number): void {
    this.loading.set(true);
    this.errorMessage.set('');
    this.product.set(null);
    this.catalogService
      .getProduct(productId, this.branchId())
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.product.set(response.data);
          this.selectedImage.set(
            response.data.imagen_principal ?? response.data.galeria[0]?.url_imagen ?? null,
          );
          this.failedImages.set(new Set());
          this.selectedColorId.set(null);
          this.selectedSizeId.set(null);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            error.status === 404
              ? 'Este producto ya no está disponible en el catálogo.'
              : 'No pudimos cargar el producto. Inténtalo nuevamente.',
          );
        },
      });
  }

  private hasCombination(colorId: number, sizeId: number): boolean {
    return (
      this.product()?.variantes.some(
        (variant) => variant.color.id_color === colorId && variant.talla.id_talla === sizeId,
      ) ?? false
    );
  }

  private positiveNumber(value: string | null): number | undefined {
    const parsed = Number(value);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
  }
}
