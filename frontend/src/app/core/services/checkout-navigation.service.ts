import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class CheckoutNavigationService {
  go(value: string): void {
    const url = new URL(value);
    if (
      url.protocol !== 'https:' ||
      url.hostname !== 'checkout.stripe.com' ||
      url.username ||
      url.password ||
      url.port
    ) {
      throw new Error('La URL de Stripe Checkout no es válida.');
    }
    window.location.assign(url.href);
  }
}
