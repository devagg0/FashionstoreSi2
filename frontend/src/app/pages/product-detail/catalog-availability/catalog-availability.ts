import { HttpErrorResponse } from '@angular/common/http';
import { Component, effect, inject, input, output, signal } from '@angular/core';
import { BranchAvailability, CatalogAvailabilityService } from '../../../core/services/catalog-availability.service';

@Component({
  selector: 'app-catalog-availability',
  templateUrl: './catalog-availability.html',
  styleUrl: './catalog-availability.scss',
})
export class CatalogAvailability {
  readonly productId = input.required<number>();
  readonly variantId = input<number | null>(null);
  readonly branchId = input<number>();
  readonly cityId = input<number>();
  readonly refreshKey = input(0);
  readonly availabilityChange = output<BranchAvailability[]>();
  private readonly service = inject(CatalogAvailabilityService);
  private readonly attempt = signal(0);
  protected readonly rows = signal<BranchAvailability[]>([]);
  protected readonly loading = signal(false);
  protected readonly errorMessage = signal('');

  constructor() {
    effect((onCleanup) => {
      const productId = this.productId();
      const variantId = this.variantId();
      const branchId = this.branchId();
      const cityId = this.cityId();
      this.refreshKey();
      this.attempt();
      this.rows.set([]);
      this.availabilityChange.emit([]);
      this.errorMessage.set('');
      this.loading.set(false);
      if (variantId === null) return;
      this.loading.set(true);
      const subscription = this.service.getProductAvailability(productId, {
        id_variante_producto: variantId, id_sucursal: branchId, id_ciudad: cityId,
      }).subscribe({
        next: (response) => {
          this.rows.set(response.data.disponibilidad);
          this.availabilityChange.emit(response.data.disponibilidad);
          this.loading.set(false);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(error.status === 404
            ? 'Este producto o la variante seleccionada ya no está disponible.'
            : 'No se pudo consultar la disponibilidad. Inténtalo nuevamente.');
          this.loading.set(false);
        },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }

  protected retry(): void {
    this.attempt.update((value) => value + 1);
  }

}
