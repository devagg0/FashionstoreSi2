import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize, forkJoin } from 'rxjs';
import { BranchAvailability, CatalogAvailabilityService } from '../../core/services/catalog-availability.service';
import { CartData, ClientCartService } from '../../core/services/client-cart.service';
import { ClientCheckoutService, DigitalSale, SalePresentation, checkoutErrorMessage } from '../../core/services/client-checkout.service';
import { formatBs } from '../../core/utils/money';
import { PaymentsService } from '../../core/services/payments.service';

@Component({
  selector: 'app-checkout', imports: [RouterLink], templateUrl: './checkout.html',
  styleUrls: ['../cart/cart.scss', './checkout.scss'],
})
export class Checkout {
  private readonly payments = inject(PaymentsService);
  private readonly carts = inject(ClientCartService);
  private readonly checkout = inject(ClientCheckoutService);
  private readonly availability = inject(CatalogAvailabilityService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly cart = signal<CartData | null>(null);
  protected readonly sale = signal<DigitalSale | null>(null);
  protected readonly presentation = signal<SalePresentation | null>(null);
  protected readonly branches = signal<BranchAvailability[]>([]);
  protected readonly branchId = signal<number | null>(null);
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal('');
  protected readonly sessionExpired = signal(false);
  // Tras respuesta incierta se mantiene el mismo carrito/sucursal para reintentar.
  protected readonly uncertain = signal(false);
  protected readonly money = formatBs;
  protected readonly canConfirm = computed(() => !this.loading() && !this.saving() && !this.sale()
    && !this.sessionExpired() && this.cart()?.estado === 'ACTIVO' && !!this.cart()?.items.length
    && this.branches().some(branch => branch.id_sucursal === this.branchId()));
  protected readonly saleRows = computed(() => this.sale()?.items.map(item => {
    const label = this.presentation()?.items.find(row => row.id_variante_producto === item.id_variante_producto);
    return { ...item, nombre: label?.nombre ?? `Variante #${item.id_variante_producto}`,
      talla: label?.talla, color: label?.color, imagen: label?.imagen };
  }) ?? []);
  protected readonly branchName = computed(() => {
    const sale = this.sale();
    return this.presentation()?.id_sucursal === sale?.id_sucursal
      ? this.presentation()!.sucursal : `Sucursal #${sale?.id_sucursal}`;
  });

  constructor() { this.load(); }

  protected load(): void {
    if (this.loading() || this.saving() || this.uncertain()) return;
    this.error.set(''); this.loading.set(true);
    const id = this.route.snapshot.paramMap.get('id');
    if (id !== null) {
      if (!/^[1-9]\d*$/.test(id) || Number(id) > 2147483647) {
        this.error.set('La venta solicitada no es válida.'); this.loading.set(false); return;
      }
      this.checkout.getPendingSale(Number(id)).pipe(takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false))).subscribe({
        next: response => { this.sale.set(response.data); this.presentation.set(this.checkout.presentation(response.data.id_venta)); },
        error: error => this.fail(error),
      });
      return;
    }
    this.branchId.set(null); this.branches.set([]);
    this.carts.getCart().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        this.cart.set(response.data);
        const items = response.data.items;
        if (!items.length) { this.loading.set(false); return; }
        if (items.some(item => !item.estado_producto || !item.estado_variante)) {
          this.error.set('Hay productos o variantes no disponibles. Ajusta tu carrito antes de continuar.');
          this.loading.set(false); return;
        }
        forkJoin(items.map(item => this.availability.getProductAvailability(item.id_producto, {
          id_variante_producto: item.id_variante_producto,
        }))).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
          next: responses => {
            const eligible = responses[0].data.disponibilidad.filter(branch => responses.every((response, index) =>
              response.data.producto.estado && response.data.disponibilidad.some(row =>
                row.id_sucursal === branch.id_sucursal && row.variante.estado
                && row.variante.id_variante_producto === items[index].id_variante_producto
                && row.stock_disponible >= items[index].cantidad)));
            this.branches.set(eligible);
            if (!eligible.length) this.error.set('Ninguna sucursal tiene stock suficiente para todas las prendas. Ajusta tu carrito.');
          }, error: error => this.fail(error),
        });
      }, error: error => { this.loading.set(false); this.fail(error); },
    });
  }
  protected chooseBranch(event: Event): void {
    if (this.saving() || this.uncertain()) return;
    const id = Number((event.target as HTMLSelectElement).value);
    this.branchId.set(this.branches().some(branch => branch.id_sucursal === id) ? id : null);
  }
  protected confirm(): void {
    if (!this.canConfirm()) return;
    const cart = this.cart()!;
    const branch = this.branches().find(row => row.id_sucursal === this.branchId())!;
    if (!cart.id_carrito) return;
    const presentation: SalePresentation = {
      id_sucursal: branch.id_sucursal, sucursal: `${branch.nombre_sucursal} · ${branch.nombre_ciudad}`,
      items: cart.items.map(item => ({ id_variante_producto: item.id_variante_producto,
        nombre: item.nombre_producto, talla: item.talla.nombre, color: item.color.nombre, imagen: item.imagen_principal })),
    };
    this.saving.set(true); this.error.set('');
    this.checkout.confirm(cart.id_carrito, branch.id_sucursal).pipe(takeUntilDestroyed(this.destroyRef),
      finalize(() => this.saving.set(false))).subscribe({
      next: response => {
        this.sale.set(response.data); this.presentation.set(presentation); this.uncertain.set(false);
        this.checkout.savePresentation(response.data.id_venta, presentation);
        void this.router.navigate(['/compra', response.data.id_venta], { replaceUrl: true });
      },
      error: (error: HttpErrorResponse) => {
        this.uncertain.set(error.status === 0 || error.status >= 500);
        this.fail(error);
      },
    });
  }
  protected expiration(value: string): string {
    const date = new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`);
    return Number.isNaN(date.getTime()) ? 'No disponible' : new Intl.DateTimeFormat('es-BO', {
      dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/La_Paz',
    }).format(date);
  }
  private fail(error: HttpErrorResponse): void {
    this.sessionExpired.set(error.status === 401);
    this.error.set(checkoutErrorMessage(error));
  }
  protected pay(): void {
    const sale = this.sale();
    if (!sale || this.saving()) return;
    try {
      this.payments.saveSale({ id: sale.id_venta, numero: sale.numero_venta, sucursal: this.branchName(),
        canal: 'DIGITAL', estado: sale.estado, fecha: null, subtotal: sale.subtotal,
        descuento: sale.descuento_total, total: sale.total,
        items: this.saleRows().map(item => ({ id: item.id_variante_producto, nombre: item.nombre,
          talla: item.talla, color: item.color, imagen: item.imagen, cantidad: item.cantidad, precio: item.precio_unitario,
          subtotal: item.subtotal_linea })) });
      void this.router.navigate(['/compra', sale.id_venta, 'pago']);
    } catch { this.error.set('Habilita el almacenamiento de esta pestaña para continuar al pago.'); }
  }
}
