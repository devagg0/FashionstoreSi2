import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { combineLatest, finalize } from 'rxjs';
import {
  CatalogProductDetail,
  CatalogPromotion,
  CatalogService,
  CatalogVariant,
} from '../../core/services/catalog.service';
import { BranchAvailability } from '../../core/services/catalog-availability.service';
import {
  ReservationContext,
  ReservationSelectionService,
} from '../../core/services/reservation-selection.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';
import {
  ReservationSchedulePicker,
  ReservationScheduleSelection,
} from '../../shared/components/reservation-schedule-picker/reservation-schedule-picker';
import { CatalogAvailability } from './catalog-availability/catalog-availability';

@Component({
  selector: 'app-product-detail',
  imports: [Icon, RouterLink, CatalogAvailability, ReservationSchedulePicker],
  templateUrl: './product-detail.html',
  styleUrl: './product-detail.scss',
})
export class ProductDetail {
  private readonly catalogService = inject(CatalogService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly reservationSelection = inject(ReservationSelectionService);
  private readonly session = inject(SessionService);

  protected readonly product = signal<CatalogProductDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly selectedImage = signal<string | null>(null);
  protected readonly selectedColorId = signal<number | null>(null);
  protected readonly selectedSizeId = signal<number | null>(null);
  protected readonly failedImages = signal<Set<string>>(new Set());
  protected readonly branchId = signal<number | undefined>(undefined);
  protected readonly cityId = signal<number | undefined>(undefined);
  protected readonly availabilityRows = signal<BranchAvailability[]>([]);
  protected readonly reservationQuantity = signal(1);
  protected readonly reservationError = signal('');
  protected readonly reservationSuccess = signal('');
  protected readonly scheduleSelection = signal<ReservationScheduleSelection | null>(null);
  protected readonly availabilityRefresh = signal(0);
  protected readonly currentUser = this.session.currentUser;
  protected readonly reservationItemCount = this.reservationSelection.itemCount;
  protected readonly reservationContext = this.reservationSelection.context;

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

  protected readonly reservationMaximum = computed(() => {
    const context = this.reservationContext();
    const variantId = this.selectedVariant()?.id_variante_producto;
    const currentQuantity =
      this.reservationSelection.items().find(
        (item) => item.id_variante_producto === variantId,
      )?.cantidad ?? 0;
    const fixedBranchId = context?.id_sucursal ?? this.scheduleSelection()?.branch.id_sucursal;
    const available = fixedBranchId
      ? (this.availabilityRows().find(
          (branch) => branch.id_sucursal === fixedBranchId,
        )?.stock_disponible ?? 0)
      : this.availabilityRows().reduce(
          (maximum, branch) => Math.max(maximum, branch.stock_disponible),
          0,
        );
    return Math.max(available - currentQuantity, 0);
  });

  protected readonly eligibleReservationBranches = computed(() =>
    this.availabilityRows().filter(
      (branch) =>
        branch.stock_disponible > 0 &&
        Boolean(branch.hora_apertura && branch.hora_cierre) &&
        branch.hora_apertura !== branch.hora_cierre,
    ),
  );

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
    this.resetReservationSelection();
    this.selectedColorId.set(colorId);
    const sizeId = this.selectedSizeId();
    if (sizeId !== null && !this.hasCombination(colorId, sizeId)) this.selectedSizeId.set(null);
  }

  protected selectSize(sizeId: number): void {
    this.resetReservationSelection();
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

  protected availabilityChanged(rows: BranchAvailability[]): void {
    this.availabilityRows.set(rows);
    this.scheduleSelection.set(null);
    this.clampReservationQuantity();
  }

  protected scheduleChanged(selection: ReservationScheduleSelection | null): void {
    this.scheduleSelection.set(selection);
    this.clampReservationQuantity();
    this.reservationError.set('');
  }

  protected updateReservationQuantity(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.reservationQuantity.set(Number.isInteger(value) ? value : 1);
    this.clampReservationQuantity();
  }

  protected isClient(): boolean {
    return this.currentUser()?.rol.toUpperCase() === 'CLIENTE';
  }

  protected addToReservation(): void {
    const variant = this.selectedVariant();
    const product = this.product();
    const quantity = this.reservationQuantity();
    if (!this.isClient()) {
      void this.router.navigate(['/login']);
      return;
    }
    const context = this.reservationContext();
    const schedule = this.scheduleSelection();
    if (!product || !variant || quantity < 1 || quantity > this.reservationMaximum()) {
      this.reservationError.set('Selecciona una variante con disponibilidad y una cantidad válida.');
      return;
    }
    if (!context && !schedule) {
      this.reservationError.set('Selecciona sucursal, fecha y horario para iniciar la reserva.');
      return;
    }
    this.reservationError.set('');
    const item = {
      id_producto: product.id_producto,
      id_variante_producto: variant.id_variante_producto,
      producto: product.nombre,
      imagen_principal: product.imagen_principal,
      sku: variant.sku,
      talla: variant.talla.nombre,
      color: variant.color.nombre,
      precio_referencia: product.precio_final,
      cantidad: quantity,
    };
    if (context) {
      this.reservationSelection.add(item);
    } else if (schedule) {
      this.reservationSelection.start(this.contextFromSchedule(schedule), item);
    }
    this.reservationQuantity.set(1);
    this.reservationSuccess.set(`${product.nombre} se agregó a la reserva actual.`);
  }

  protected formatContextDate(context: ReservationContext): string {
    return new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'long',
      timeZone: 'UTC',
    }).format(new Date(`${context.fecha}T12:00:00Z`));
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
          this.resetReservationSelection();
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

  private resetReservationSelection(): void {
    this.availabilityRows.set([]);
    this.reservationQuantity.set(1);
    this.reservationError.set('');
    this.reservationSuccess.set('');
    this.scheduleSelection.set(null);
  }

  private clampReservationQuantity(): void {
    const maximum = Math.max(this.reservationMaximum(), 1);
    this.reservationQuantity.set(Math.min(Math.max(this.reservationQuantity(), 1), maximum));
  }

  private contextFromSchedule(selection: ReservationScheduleSelection): ReservationContext {
    return {
      id_sucursal: selection.branch.id_sucursal,
      nombre_sucursal: selection.branch.nombre_sucursal,
      nombre_ciudad: selection.branch.nombre_ciudad,
      direccion: selection.branch.direccion,
      hora_apertura: selection.branch.hora_apertura!,
      hora_cierre: selection.branch.hora_cierre!,
      fecha: selection.date,
      horario: selection.time,
    };
  }
}
