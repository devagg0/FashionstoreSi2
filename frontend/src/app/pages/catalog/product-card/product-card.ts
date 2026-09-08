import { Component, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CatalogProduct } from '../../../core/services/catalog.service';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-catalog-product-card',
  imports: [Icon, RouterLink],
  templateUrl: './product-card.html',
  styleUrl: './product-card.scss',
})
export class CatalogProductCard {
  readonly product = input.required<CatalogProduct>();
  readonly cityId = input<number | undefined>();
  readonly branchId = input<number | undefined>();
  protected readonly imageFailed = signal(false);

  protected detailQueryParams(): Record<string, number> {
    const params: Record<string, number> = {};
    if (this.cityId() !== undefined) params['id_ciudad'] = this.cityId()!;
    if (this.branchId() !== undefined) params['id_sucursal'] = this.branchId()!;
    return params;
  }

  protected promotionLabel(): string {
    const promotion = this.product().promocion_destacada;
    if (!promotion) return '';
    if (promotion.tipo_descuento === 'PORCENTAJE') {
      return `-${this.cleanNumber(promotion.valor)}%`;
    }
    return 'Oferta';
  }

  protected formatMoney(value: string): string {
    return `Bs ${new Intl.NumberFormat('es-BO', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value))}`;
  }

  private cleanNumber(value: string): string {
    return Number(value).toLocaleString('es-BO', { maximumFractionDigits: 2 });
  }
}
