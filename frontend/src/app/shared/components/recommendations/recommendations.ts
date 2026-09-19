import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { ClientCartService, cartErrorMessage } from '../../../core/services/client-cart.service';
import {
  ClientRecommendationsService,
  RecommendationItem,
  RecommendationOrigin,
  recommendationErrorMessage,
} from '../../../core/services/client-recommendations.service';
import { SessionService } from '../../../core/services/session.service';
import { formatBs } from '../../../core/utils/money';
import { Icon } from '../icon/icon';

@Component({
  selector: 'app-recommendations',
  imports: [Icon, RouterLink],
  templateUrl: './recommendations.html',
  styleUrl: './recommendations.scss',
})
export class Recommendations implements OnInit {
  readonly limit = input(8);
  readonly idSucursal = input<number | undefined>();
  readonly idCiudad = input<number | undefined>();

  private readonly recommendationsService = inject(ClientRecommendationsService);
  private readonly cartService = inject(ClientCartService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly items = signal<RecommendationItem[]>([]);
  protected readonly origin = signal<RecommendationOrigin>('FALLBACK');
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');
  protected readonly addingProductId = signal<number | null>(null);
  protected readonly feedback = signal('');
  protected readonly feedbackError = signal(false);
  protected readonly skeletons = [1, 2, 3, 4];

  /** La seccion solo existe para clientes autenticados. */
  protected readonly isClient = computed(
    () => this.session.currentUser()?.rol.toUpperCase() === 'CLIENTE',
  );

  protected readonly title = computed(() =>
    this.origin() === 'PERSONALIZADO' ? 'Recomendado para ti' : 'Descubre estas prendas',
  );

  protected readonly subtitle = computed(() =>
    this.origin() === 'PERSONALIZADO'
      ? 'Elegidas a partir de tus compras, reservas y lo que guardaste en el carrito.'
      : 'Una selección de lo más buscado en FashionStore para empezar tu estilo.',
  );

  ngOnInit(): void {
    if (this.isClient()) this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.errorMessage.set('');
    this.feedback.set('');
    this.recommendationsService
      .list({
        limit: this.limit(),
        idSucursal: this.idSucursal(),
        idCiudad: this.idCiudad(),
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (response) => {
          this.items.set(response.data);
          this.origin.set(response.origen);
        },
        error: (error: HttpErrorResponse) => {
          this.items.set([]);
          this.errorMessage.set(recommendationErrorMessage(error));
          if (error.status === 401) this.redirectToLogin();
        },
      });
  }

  protected addToCart(item: RecommendationItem): void {
    const variant = item.variante_sugerida;
    if (!variant || this.addingProductId() !== null) return;
    this.feedback.set('');
    this.addingProductId.set(item.id_producto);
    // Reutiliza el flujo de carrito de CU19: aqui no se replica su logica.
    this.cartService
      .addItem(variant.id_variante_producto, 1)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.addingProductId.set(null)),
      )
      .subscribe({
        next: () => {
          this.feedbackError.set(false);
          this.feedback.set(`${item.nombre} se agregó a tu carrito.`);
        },
        error: (error: HttpErrorResponse) => {
          this.feedbackError.set(true);
          this.feedback.set(cartErrorMessage(error));
          if (error.status === 401) this.redirectToLogin();
        },
      });
  }

  protected discountLabel(item: RecommendationItem): string {
    const promotion = item.promocion;
    if (!promotion) return '';
    if (promotion.tipo_descuento === 'PORCENTAJE') {
      return `-${Number(promotion.valor).toLocaleString('es-BO', { maximumFractionDigits: 2 })}%`;
    }
    return item.monto_descuento ? `-${this.money(item.monto_descuento)}` : 'Oferta';
  }

  protected stockLabel(item: RecommendationItem): string {
    const stock = item.variante_sugerida?.stock_disponible ?? 0;
    if (stock <= 0) return 'Sin stock';
    return stock <= 5 ? `Últimas ${stock} unidades` : 'Disponible';
  }

  protected money(value: string): string {
    return formatBs(value);
  }

  private redirectToLogin(): void {
    void this.router.navigate(['/login']);
  }
}
