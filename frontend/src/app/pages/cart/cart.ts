import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, Observable, Subject, catchError, concatMap, defer, finalize, tap } from 'rxjs';
import { CartData, CartItem, CartResponse, ClientCartService, cartErrorMessage } from '../../core/services/client-cart.service';
import { Icon } from '../../shared/components/icon/icon';
import { formatBs } from '../../core/utils/money';
import { Router } from '@angular/router';

@Component({
  selector: 'app-cart', imports: [RouterLink, Icon],
  templateUrl: './cart.html', styleUrl: './cart.scss',
})
export class Cart {
  private readonly service = inject(ClientCartService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly operations = new Subject<{ id: number; run: () => Observable<CartResponse> }>();
  protected readonly cart = signal<CartData | null>(null);
  protected readonly loading = signal(false);
  protected readonly clearing = signal(false);
  protected readonly pending = signal<Record<number, 'updating' | 'removing'>>({});
  protected readonly busy = computed(() => Object.keys(this.pending()).length > 0);
  protected readonly error = signal('');
  protected readonly itemErrors = signal<Record<number, string>>({});
  protected readonly failedImages = signal<Set<number>>(new Set());
  protected readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('clearDialog');
  protected readonly money = formatBs;
  protected continuePurchase(): void {
    if (!this.loading() && !this.busy() && !this.clearing() && this.cart()?.items.length) {
      void this.router.navigate(['/compra']);
    }
  }

  constructor() {
    // Serialize full-cart responses so edits to different rows cannot overwrite newer data.
    this.operations.pipe(concatMap(({ id, run }) => defer(run).pipe(
      tap(response => this.cart.set(response.data)),
      catchError((error: HttpErrorResponse) => {
        this.itemErrors.update(errors => ({ ...errors, [id]: cartErrorMessage(error) }));
        return EMPTY;
      }),
      finalize(() => this.pending.update(current => {
        const next = { ...current }; delete next[id]; return next;
      })),
    )), takeUntilDestroyed(this.destroyRef)).subscribe();
    this.load();
  }

  protected load(): void {
    if (this.loading() || this.busy() || this.clearing()) return;
    this.loading.set(true); this.error.set('');
    this.service.getCart().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      next: response => { this.cart.set(response.data); this.itemErrors.set({}); },
      error: (error: HttpErrorResponse) => this.error.set(cartErrorMessage(error)),
    });
  }
  protected inactive(item: CartItem): boolean { return !item.estado_producto || !item.estado_variante; }
  protected blocked(item: CartItem): boolean { return !!this.pending()[item.id_variante_producto] || this.clearing() || this.loading(); }
  protected availability(item: CartItem): string {
    if (this.inactive(item)) return 'No disponible';
    if (item.disponibilidad_actual === 0) return 'Sin stock actualmente';
    if (item.disponibilidad_actual < item.cantidad) return `Solo quedan ${item.disponibilidad_actual} unidades disponibles`;
    return 'Disponible';
  }
  protected discounted(item: CartItem): boolean { return Number(item.precio_base) !== Number(item.precio_final); }
  protected updateQuantity(item: CartItem, quantity: number): void {
    if (this.blocked(item) || this.inactive(item)) return;
    const id = item.id_variante_producto;
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 2147483647) {
      this.itemErrors.update(errors => ({ ...errors, [id]: 'Ingresa una cantidad entera mayor o igual a 1.' }));
      return;
    }
    if (quantity === item.cantidad) return;
    this.enqueue(item, 'updating', () => this.service.updateQuantity(id, quantity));
  }
  protected quantityChanged(item: CartItem, event: Event): void {
    const input = event.target as HTMLInputElement;
    const quantity = Number(input.value);
    input.value = String(item.cantidad);
    this.updateQuantity(item, quantity);
  }
  protected removeItem(item: CartItem): void {
    if (!this.blocked(item)) this.enqueue(item, 'removing', () => this.service.removeItem(item.id_variante_producto));
  }
  private enqueue(item: CartItem, state: 'updating' | 'removing', run: () => Observable<CartResponse>): void {
    const id = item.id_variante_producto;
    this.itemErrors.update(errors => ({ ...errors, [id]: '' }));
    this.pending.update(current => ({ ...current, [id]: state }));
    this.operations.next({ id, run });
  }
  protected imageFailed(id: number): void { this.failedImages.update(current => new Set([...current, id])); }
  protected askClear(): void {
    if (!this.busy() && !this.clearing() && this.cart()?.items.length) this.dialog().nativeElement.showModal();
  }
  protected closeDialog(): void { if (!this.clearing()) this.dialog().nativeElement.close(); }
  protected clearCart(): void {
    if (!this.dialog().nativeElement.open || this.busy() || this.clearing()) return;
    this.clearing.set(true); this.error.set('');
    this.service.clearCart().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => {
      this.clearing.set(false); this.dialog().nativeElement.close();
    })).subscribe({
      next: response => { this.cart.set(response.data); this.itemErrors.set({}); },
      error: (error: HttpErrorResponse) => this.error.set(cartErrorMessage(error)),
    });
  }
}
