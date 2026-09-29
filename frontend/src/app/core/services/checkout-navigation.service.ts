import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class CheckoutNavigationService {
  private checkoutWindow: Window | null = null;
  private launched = false;

  prepare(): void {
    this.close();
    const checkoutWindow = window.open('', 'fashionstore-stripe-checkout');
    if (!checkoutWindow) {
      throw new Error('El navegador bloqueó la ventana de Stripe Checkout.');
    }
    checkoutWindow.document.title = 'Stripe Checkout · FashionStore';
    checkoutWindow.document.body.textContent = 'Preparando Stripe Checkout…';
    this.checkoutWindow = checkoutWindow;
    this.launched = false;
  }

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
    if (!this.checkoutWindow || this.checkoutWindow.closed) {
      throw new Error('La ventana de Stripe Checkout no está disponible.');
    }
    this.checkoutWindow.location.replace(url.href);
    this.checkoutWindow.focus();
    this.launched = true;
  }

  isActive(): boolean {
    return this.launched && !!this.checkoutWindow && !this.checkoutWindow.closed;
  }

  close(): void {
    if (this.checkoutWindow && !this.checkoutWindow.closed) this.checkoutWindow.close();
    this.checkoutWindow = null;
    this.launched = false;
    window.focus();
  }
}
