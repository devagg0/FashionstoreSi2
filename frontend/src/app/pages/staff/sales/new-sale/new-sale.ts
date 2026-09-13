import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import {
  CatalogProduct,
  CatalogProductDetail,
  CatalogService,
  CatalogVariant,
} from '../../../../core/services/catalog.service';
import { SessionService } from '../../../../core/services/session.service';
import {
  StaffReservationDetail,
  StaffReservationsService,
} from '../../../../core/services/staff-reservations.service';
import {
  SaleBranch,
  SaleData,
  SaleQuote,
  SaleRequest,
  StaffSalesService,
} from '../../../../core/services/staff-sales.service';

interface DraftLine {
  id_variante_producto: number;
  producto: string;
  sku: string;
  talla: string;
  color: string;
  imagen: string | null;
  precio: string;
  cantidad: number;
  reservado?: number;
}
interface SaleAttempt {
  key: string;
  payload: SaleRequest;
  duplicate: boolean;
}

@Component({
  selector: 'app-new-sale',
  imports: [FormsModule, DatePipe],
  templateUrl: './new-sale.html',
  styleUrl: './new-sale.scss',
})
export class NewSale implements OnInit {
  private readonly sales = inject(StaffSalesService);
  private readonly catalog = inject(CatalogService);
  private readonly reservations = inject(StaffReservationsService);
  private readonly session = inject(SessionService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly storageKey = `fashionstore-cu20-${this.session.getUser()?.id_usuario}`;
  readonly branches = signal<SaleBranch[]>([]);
  readonly branchId = signal<number | null>(null);
  readonly branch = computed(() => this.branches().find((b) => b.id_sucursal === this.branchId()));
  readonly mode = signal<'direct' | 'reservation'>('direct');
  readonly lines = signal<DraftLine[]>([]);
  readonly products = signal<CatalogProduct[]>([]);
  readonly selectedProduct = signal<CatalogProductDetail | null>(null);
  readonly reservation = signal<StaffReservationDetail | null>(null);
  readonly quote = signal<SaleQuote | null>(null);
  readonly stale = signal(false);
  readonly result = signal<SaleData | null>(null);
  readonly error = signal('');
  readonly notice = signal('');
  readonly loadingBranches = signal(false);
  readonly searchingProducts = signal(false);
  readonly searchingReservation = signal(false);
  readonly quoting = signal(false);
  readonly creatingSale = signal(false);
  readonly consultingSale = signal(false);
  readonly attempt = signal<SaleAttempt | null>(null);
  readonly uncertain = signal(false);
  readonly pendingMode = signal<'direct' | 'reservation' | null>(null);
  readonly busy = computed(
    () =>
      this.loadingBranches() ||
      this.searchingProducts() ||
      this.searchingReservation() ||
      this.quoting() ||
      this.creatingSale() ||
      this.consultingSale(),
  );
  readonly locked = computed(
    () => this.quoting() || this.creatingSale() || this.uncertain() || !!this.result(),
  );
  readonly units = computed(() => this.lines().reduce((n, l) => n + l.cantidad, 0));
  readonly canQuote = computed(
    () =>
      !!this.branch() &&
      this.units() > 0 &&
      !this.busy() &&
      !this.locked() &&
      (this.mode() === 'direct' ||
        (this.reservation()?.estado === 'ATENDIDA' &&
          this.reservation()?.sucursal.id_sucursal === this.branchId())),
  );
  readonly canCreate = computed(() => this.canQuote() && !!this.quote() && !this.stale());
  search = '';
  code = '';
  saleId = '';
  page = 1;
  totalPages = 0;
  private readonly modeDialog = viewChild<ElementRef<HTMLDialogElement>>('modeDialog');

  constructor() {
    effect(() => {
      const dialog = this.modeDialog()?.nativeElement;
      if (!dialog) return;
      if (this.pendingMode() && !dialog.open) dialog.showModal();
      else if (!this.pendingMode() && dialog.open) dialog.close();
    });
  }

  ngOnInit(): void {
    // Persist the intent before POST so a refresh cannot silently create another UUID.
    try {
      const stored = sessionStorage.getItem(this.storageKey);
      if (stored) {
        const value = JSON.parse(stored) as SaleAttempt;
        if (typeof value.key === 'string' && value.payload?.items?.length) {
          this.attempt.set(value);
          this.uncertain.set(true);
        }
      }
    } catch {
      this.error.set(
        'No se pudo recuperar el intento anterior. Verifica las ventas antes de registrar.',
      );
      this.uncertain.set(true);
    }
    this.loadBranches();
  }
  loadBranches(): void {
    if (this.loadingBranches()) return;
    this.loadingBranches.set(true);
    this.sales
      .getBranches()
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loadingBranches.set(false)),
      )
      .subscribe({
        next: (r) => {
          this.branches.set(r.data);
          if (r.data.length === 1) this.branchId.set(r.data[0].id_sucursal);
        },
        error: (e) => this.fail(e),
      });
  }
  changeBranch(value: number | null): void {
    if (this.busy() || this.locked() || (this.mode() === 'reservation' && !!this.reservation()))
      return;
    if (value !== null && !this.branches().some((b) => b.id_sucursal === value)) return;
    this.branchId.set(value);
    this.invalidate();
    this.products.set([]);
    this.selectedProduct.set(null);
  }
  changeMode(mode: 'direct' | 'reservation'): void {
    if (this.busy() || this.locked() || mode === this.mode()) return;
    if (this.lines().length || this.reservation()) {
      this.pendingMode.set(mode);
      return;
    }
    this.applyMode(mode);
  }
  confirmMode(): void {
    const mode = this.pendingMode();
    if (mode && !this.busy() && !this.locked()) this.applyMode(mode);
  }
  private applyMode(mode: 'direct' | 'reservation'): void {
    this.mode.set(mode);
    this.pendingMode.set(null);
    this.lines.set([]);
    this.reservation.set(null);
    this.products.set([]);
    this.selectedProduct.set(null);
    this.code = '';
    this.search = '';
    this.invalidate();
    this.notice.set('');
  }
  searchProducts(page = 1): void {
    if (this.mode() !== 'direct' || this.locked() || this.searchingProducts() || !this.branch())
      return;
    this.searchingProducts.set(true);
    this.error.set('');
    this.selectedProduct.set(null);
    this.catalog
      .listProducts({ search: this.search, idSucursal: this.branchId()!, page, pageSize: 8 })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.searchingProducts.set(false)),
      )
      .subscribe({
        next: (r) => {
          this.products.set(r.data);
          this.page = page;
          this.totalPages = r.pagination.total_pages;
          this.notice.set(r.data.length ? '' : 'No se encontraron productos.');
        },
        error: (e) => this.fail(e),
      });
  }
  selectProduct(id: number): void {
    if (this.mode() !== 'direct' || this.locked() || this.searchingProducts() || !this.branch())
      return;
    this.searchingProducts.set(true);
    this.error.set('');
    this.selectedProduct.set(null);
    this.catalog
      .getProduct(id, this.branchId()!)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.searchingProducts.set(false)),
      )
      .subscribe({
        next: (r) => this.selectedProduct.set(r.data),
        error: (e) => this.fail(e),
      });
  }
  addVariant(variant: CatalogVariant): void {
    const product = this.selectedProduct();
    if (
      this.mode() !== 'direct' ||
      this.locked() ||
      !product ||
      !product.variantes.some((v) => v.id_variante_producto === variant.id_variante_producto)
    )
      return;
    const existing = this.lines().find(
      (l) => l.id_variante_producto === variant.id_variante_producto,
    );
    if (existing) {
      this.setQuantity(existing.id_variante_producto, existing.cantidad + 1);
      return;
    }
    this.lines.update((lines) => [
      ...lines,
      {
        id_variante_producto: variant.id_variante_producto,
        producto: product.nombre,
        sku: variant.sku,
        talla: variant.talla.nombre,
        color: variant.color.nombre,
        imagen: product.imagen_principal,
        precio: product.precio_final,
        cantidad: 1,
      },
    ]);
    this.invalidate();
  }
  setQuantity(id: number, quantity: number): void {
    if (this.locked() || !Number.isInteger(quantity) || quantity > 2147483647) return;
    const line = this.lines().find((l) => l.id_variante_producto === id);
    if (
      !line ||
      quantity < (this.mode() === 'direct' ? 1 : 0) ||
      quantity > (line.reservado ?? 2147483647)
    )
      return;
    this.lines.update((lines) =>
      lines.map((l) => (l.id_variante_producto === id ? { ...l, cantidad: quantity } : l)),
    );
    this.invalidate();
  }
  removeLine(id: number): void {
    if (this.mode() !== 'direct' || this.locked()) return;
    this.lines.update((lines) => lines.filter((l) => l.id_variante_producto !== id));
    this.invalidate();
  }
  searchReservation(): void {
    if (this.mode() !== 'reservation' || this.busy() || this.locked() || !this.code.trim()) return;
    this.searchingReservation.set(true);
    this.reservation.set(null);
    this.lines.set([]);
    this.invalidate();
    this.reservations
      .getReservationByCode(this.code)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.searchingReservation.set(false)),
      )
      .subscribe({
        next: (r) => {
          this.reservation.set(r.data);
          if (r.data.estado !== 'ATENDIDA') {
            this.error.set('Esta reserva todavía no está disponible para procesar una venta.');
            return;
          }
          if (!this.branches().some((b) => b.id_sucursal === r.data.sucursal.id_sucursal)) {
            this.error.set('La sucursal de esta reserva no está autorizada para registrar ventas.');
            return;
          }
          this.branchId.set(r.data.sucursal.id_sucursal);
          this.lines.set(
            r.data.prendas.map((p) => ({
              id_variante_producto: p.id_variante_producto,
              producto: p.producto,
              sku: p.sku,
              talla: p.talla.nombre,
              color: p.color.nombre,
              imagen: p.imagen_principal ?? null,
              precio: p.precio_reservado,
              cantidad: p.cantidad,
              reservado: p.cantidad,
            })),
          );
          // CU18 may omit images; catalog failures (e.g. unpublished garments) must not block sale.
          for (const id of new Set(
            r.data.prendas.filter((p) => !p.imagen_principal).map((p) => p.id_producto),
          )) {
            const reservationId = r.data.id_reserva;
            this.catalog
              .getProduct(id)
              .pipe(takeUntilDestroyed(this.destroyRef))
              .subscribe({
                next: (product) => {
                  if (this.reservation()?.id_reserva !== reservationId) return;
                  const ids = r.data.prendas
                    .filter((p) => p.id_producto === id)
                    .map((p) => p.id_variante_producto);
                  this.lines.update((lines) =>
                    lines.map((l) =>
                      ids.includes(l.id_variante_producto)
                        ? { ...l, imagen: product.data.imagen_principal }
                        : l,
                    ),
                  );
                },
                error: () => undefined,
              });
          }
        },
        error: (e) => this.fail(e),
      });
  }
  payload(): SaleRequest {
    return {
      id_sucursal: this.branchId()!,
      ...(this.mode() === 'reservation' ? { id_reserva: this.reservation()!.id_reserva } : {}),
      items: this.lines()
        .filter((l) => l.cantidad > 0)
        .map((l) => ({ id_variante_producto: l.id_variante_producto, cantidad: l.cantidad })),
    };
  }
  quoteSale(): void {
    if (!this.canQuote()) return;
    this.quote.set(null);
    this.error.set('');
    this.quoting.set(true);
    this.sales
      .quoteSale(this.payload())
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.quoting.set(false)),
      )
      .subscribe({
        next: (r) => {
          this.quote.set(r.data);
          this.stale.set(false);
        },
        error: (e) => this.fail(e),
      });
  }
  createSale(): void {
    if (!this.canCreate()) return;
    const attempt: SaleAttempt = {
      key: crypto.randomUUID(),
      payload: this.payload(),
      duplicate: false,
    };
    if (!this.saveAttempt(attempt)) return;
    this.attempt.set(attempt);
    this.sendAttempt(attempt);
  }
  retryAttempt(): void {
    const attempt = this.attempt();
    if (!attempt || attempt.duplicate || !this.uncertain() || this.busy()) return;
    this.sendAttempt(attempt);
  }
  private sendAttempt(attempt: SaleAttempt): void {
    this.creatingSale.set(true);
    this.error.set('');
    this.sales
      .createSale(attempt.payload, attempt.key)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.creatingSale.set(false)),
      )
      .subscribe({
        next: (r) => this.acceptSale(r.data),
        error: (e: HttpErrorResponse) => {
          this.fail(e);
          const message = typeof e.error?.message === 'string' ? e.error.message : '';
          const duplicate =
            e.status === 409 && /solicitud.*registrada|idempoten|duplicad/i.test(message);
          if (duplicate || e.status === 0 || e.status >= 500 || this.uncertain()) {
            this.uncertain.set(true);
            const saved = { ...attempt, duplicate: duplicate || attempt.duplicate };
            this.attempt.set(saved);
            this.saveAttempt(saved);
          } else {
            this.clearAttempt();
            this.invalidate(false);
          }
        },
      });
  }
  consultSale(): void {
    const id = Number(this.saleId);
    if (!Number.isInteger(id) || id <= 0 || this.busy() || !this.uncertain()) return;
    this.consultingSale.set(true);
    this.error.set('');
    this.sales
      .getSale(id)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.consultingSale.set(false)),
      )
      .subscribe({
        next: (r) => {
          const key = this.attempt()?.key.replaceAll('-', '');
          if (!key || !r.data.numero_venta.endsWith(`-${key}`)) {
            this.error.set(
              'La venta consultada no corresponde a este intento. Verifica el ID de venta.',
            );
            return;
          }
          this.acceptSale(r.data);
        },
        error: (e) => this.fail(e),
      });
  }
  private acceptSale(sale: SaleData): void {
    this.result.set(sale);
    this.uncertain.set(false);
    this.clearAttempt();
  }
  newSale(): void {
    if (this.busy() || this.uncertain()) return;
    this.result.set(null);
    this.applyMode('direct');
    this.quote.set(null);
    this.stale.set(false);
    this.error.set('');
    this.saleId = '';
  }
  private saveAttempt(attempt: SaleAttempt): boolean {
    try {
      sessionStorage.setItem(this.storageKey, JSON.stringify(attempt));
      return true;
    } catch {
      this.error.set(
        'No se pudo guardar la clave del intento. Habilita el almacenamiento de esta pestaña antes de registrar.',
      );
      return false;
    }
  }
  private clearAttempt(): void {
    this.attempt.set(null);
    try {
      sessionStorage.removeItem(this.storageKey);
    } catch {
      /* A retained key remains safe on refresh. */
    }
  }
  private invalidate(clearError = true): void {
    if (this.quote()) this.stale.set(true);
    this.quote.set(null);
    if (clearError) this.error.set('');
  }
  private fail(e: HttpErrorResponse): void {
    const fallback: Record<number, string> = {
      0: 'No se pudo conectar con el servidor.',
      401: 'Tu sesión expiró. Inicia sesión nuevamente.',
      403: 'No tienes permisos de cajero o una sucursal activa asignada.',
      404: 'No se encontró el recurso solicitado.',
      409: 'La operación presenta un conflicto. Verifica stock y estado de la reserva.',
      422: 'Revisa las variantes, cantidades y estado de la reserva.',
      500: 'No fue posible procesar la operación.',
    };
    const message: unknown = e.error?.message;
    this.error.set(
      [403, 404, 409, 422].includes(e.status) &&
        typeof message === 'string' &&
        message.length < 500 &&
        !/[{}<>]/.test(message)
        ? message
        : (fallback[e.status] ?? 'No fue posible procesar la operación.'),
    );
  }
  imageFailed(id: number): void {
    this.lines.update((lines) =>
      lines.map((l) => (l.id_variante_producto === id ? { ...l, imagen: null } : l)),
    );
  }
  money(value: string): string {
    return `Bs ${Number(value).toLocaleString('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}
