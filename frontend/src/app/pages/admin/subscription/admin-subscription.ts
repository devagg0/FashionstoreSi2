import { CommonModule } from '@angular/common';
import { Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import {
  CheckoutSessionResponse,
  CommercialPlan,
  SaasSubscriptionsService,
  SubscriptionDetail,
  SubscriptionHistoryItem,
} from '../../../core/services/saas-subscriptions.service';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-admin-subscription',
  standalone: true,
  imports: [CommonModule, Icon],
  templateUrl: './admin-subscription.html',
  styleUrl: './admin-subscription.scss',
})
export class AdminSubscription implements OnInit {
  private readonly subscriptionsService = inject(SaasSubscriptionsService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  // Estados reactivos principales
  readonly loading = signal<boolean>(true);
  readonly verifyingPayment = signal<boolean>(false);
  readonly processingCheckout = signal<boolean>(false);
  readonly currentSub = signal<SubscriptionDetail | null>(null);
  readonly hasActiveSub = signal<boolean>(false);
  readonly commercialPlans = signal<CommercialPlan[]>([]);
  readonly historyItems = signal<SubscriptionHistoryItem[]>([]);
  readonly loadingHistory = signal<boolean>(false);

  // Mensajes y notificaciones
  readonly successMessage = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly checkoutError = signal<string | null>(null);

  // Modales
  readonly checkoutModalOpen = signal<boolean>(false);
  readonly historyModalOpen = signal<boolean>(false);

  // Datos para Checkout
  readonly selectedPlan = signal<CommercialPlan | null>(null);
  readonly selectedOperation = signal<'CONTRATACION' | 'RENOVACION' | 'CAMBIO_PLAN'>(
    'CONTRATACION',
  );
  readonly selectedPaymentMethod = signal<'TARJETA' | 'QR'>('TARJETA');
  readonly activeCheckoutSession = signal<CheckoutSessionResponse | null>(null);

  ngOnInit(): void {
    // Escuchar parámetros de la ruta para detectar retorno desde Stripe Checkout TEST
    if (this.route.queryParamMap && typeof this.route.queryParamMap.subscribe === 'function') {
      this.route.queryParamMap.subscribe((params) => {
        const sessionId = params.get('session_id');
        if (sessionId) {
          this.verifyPaymentFromStripe(sessionId);
        } else {
          this.loadSubscriptionData();
        }
      });
    } else {
      const sessionId = this.route.snapshot?.queryParamMap?.get('session_id');
      if (sessionId) {
        this.verifyPaymentFromStripe(sessionId);
      } else {
        this.loadSubscriptionData();
      }
    }
  }

  loadSubscriptionData(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    // Cargar suscripción vigente y planes comerciales en paralelo
    this.subscriptionsService.getCurrentSubscription().subscribe({
      next: (resp) => {
        this.hasActiveSub.set(resp.tiene_suscripcion_activa);
        this.currentSub.set(resp.data);
        this.loadPlans();
      },
      error: (err) => {
        this.loading.set(false);
        this.errorMessage.set(
          err.error?.message || 'No fue posible cargar la información de tu suscripción actual.',
        );
      },
    });
  }

  private loadPlans(): void {
    this.subscriptionsService.listCommercialPlans().subscribe({
      next: (resp) => {
        this.commercialPlans.set(resp.data);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.errorMessage.set(
          err.error?.message || 'No se pudieron consultar los planes comerciales disponibles.',
        );
      },
    });
  }

  verifyPaymentFromStripe(sessionId: string): void {
    this.verifyingPayment.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);

    this.subscriptionsService.verifyPayment(sessionId).subscribe({
      next: (resp) => {
        this.verifyingPayment.set(false);
        this.successMessage.set(
          resp.message || 'Pago confirmado y suscripción actualizada con éxito.',
        );
        // Limpiar parámetros de la URL para evitar re-verificaciones al refrescar
        this.router.navigate([], {
          relativeTo: this.route,
          queryParams: {},
          replaceUrl: true,
        });
        this.loadSubscriptionData();
      },
      error: (err) => {
        this.verifyingPayment.set(false);
        this.errorMessage.set(
          err.error?.message ||
            'No se pudo verificar el pago con Stripe. Si pagaste, intenta nuevamente.',
        );
        this.loadSubscriptionData();
      },
    });
  }

  openCheckoutModal(
    plan: CommercialPlan,
    operation: 'CONTRATACION' | 'RENOVACION' | 'CAMBIO_PLAN',
  ): void {
    // Si ya existe suscripción activa, bloquear CONTRATACION, RENOVACION y CAMBIO_PLAN
    if (this.hasActiveSub()) {
      this.errorMessage.set(
        'La empresa cuenta con una suscripción vigente. Disponible al finalizar tu suscripción actual.',
      );
      return;
    }
    this.selectedPlan.set(plan);
    this.selectedOperation.set(operation);
    this.selectedPaymentMethod.set('TARJETA');
    this.activeCheckoutSession.set(null);
    this.checkoutError.set(null);
    this.checkoutModalOpen.set(true);
  }

  openRenewalModal(): void {
    if (this.hasActiveSub()) {
      this.errorMessage.set(
        'No es posible renovar anticipadamente mientras exista una suscripción vigente. Disponible al finalizar tu suscripción actual.',
      );
      return;
    }
    const current = this.currentSub();
    const plans = this.commercialPlans();
    const currentPlan = plans.find((p) => p.id_plan_saas === current?.id_plan_saas) || plans[0];
    if (currentPlan) {
      this.openCheckoutModal(currentPlan, 'RENOVACION');
    }
  }

  openPlanChangeModal(): void {
    if (this.hasActiveSub()) {
      this.errorMessage.set(
        'No es posible cambiar de plan mientras exista una suscripción vigente. Disponible al finalizar tu suscripción actual.',
      );
      return;
    }
    const current = this.currentSub();
    const plans = this.commercialPlans();
    const otherPlan = plans.find((p) => p.id_plan_saas !== current?.id_plan_saas) || plans[0];
    if (otherPlan) {
      this.openCheckoutModal(otherPlan, 'CAMBIO_PLAN');
    }
  }

  closeCheckoutModal(): void {
    if (this.processingCheckout()) return;
    this.checkoutModalOpen.set(false);
    this.activeCheckoutSession.set(null);
    this.checkoutError.set(null);
  }

  selectPaymentMethod(method: 'TARJETA' | 'QR'): void {
    this.selectedPaymentMethod.set(method);
    this.activeCheckoutSession.set(null);
    this.checkoutError.set(null);
  }

  initiateStripeCheckout(): void {
    const plan = this.selectedPlan();
    if (!plan || this.processingCheckout()) return;

    this.processingCheckout.set(true);
    this.checkoutError.set(null);

    if (this.hasActiveSub()) {
      this.processingCheckout.set(false);
      this.checkoutError.set(
        'Operación no permitida mientras exista una suscripción vigente. Disponible al finalizar tu suscripción actual.',
      );
      return;
    }

    const payload = {
      id_plan_saas: plan.id_plan_saas,
      tipo_operacion: this.selectedOperation(),
      success_url: `${window.location.origin}/admin/suscripcion?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${window.location.origin}/admin/suscripcion`,
    };

    const checkout$ =
      this.selectedPaymentMethod() === 'TARJETA'
        ? this.subscriptionsService.createCardCheckout(payload)
        : this.subscriptionsService.createQrCheckout(payload);

    checkout$.subscribe({
      next: (resp) => {
        this.processingCheckout.set(false);
        this.activeCheckoutSession.set(resp);
        // Para tarjeta, redirigir inmediatamente en la misma ventana a Stripe Checkout TEST
        if (this.selectedPaymentMethod() === 'TARJETA' && resp.url_checkout) {
          window.location.href = resp.url_checkout;
        }
      },
      error: (err) => {
        this.processingCheckout.set(false);
        this.checkoutError.set(
          err.error?.message || 'Ocurrió un error al contactar con Stripe TEST. Intenta de nuevo.',
        );
      },
    });
  }

  verifyCurrentActiveSession(): void {
    const session = this.activeCheckoutSession();
    if (!session) return;

    this.processingCheckout.set(true);
    this.checkoutError.set(null);

    this.subscriptionsService.verifyPayment(session.id_sesion).subscribe({
      next: (resp) => {
        this.processingCheckout.set(false);
        this.closeCheckoutModal();
        this.successMessage.set(
          resp.message || 'Pago liquidado y suscripción activada correctamente.',
        );
        this.loadSubscriptionData();
      },
      error: (err) => {
        this.processingCheckout.set(false);
        this.checkoutError.set(
          err.error?.message ||
            'El pago aún no figura completado en Stripe. Finaliza la operación en Stripe Checkout.',
        );
      },
    });
  }

  openHistoryModal(): void {
    this.historyModalOpen.set(true);
    this.loadingHistory.set(true);
    this.subscriptionsService.getSubscriptionHistory().subscribe({
      next: (resp) => {
        this.historyItems.set(resp.data);
        this.loadingHistory.set(false);
      },
      error: (err) => {
        this.loadingHistory.set(false);
        this.errorMessage.set(
          err.error?.message || 'No fue posible consultar el historial de suscripciones.',
        );
      },
    });
  }

  closeHistoryModal(): void {
    this.historyModalOpen.set(false);
  }

  getOperationTitle(op: 'CONTRATACION' | 'RENOVACION' | 'CAMBIO_PLAN'): string {
    switch (op) {
      case 'CONTRATACION':
        return 'Contratar Plan SaaS';
      case 'RENOVACION':
        return 'Renovar Suscripción Vigente';
      case 'CAMBIO_PLAN':
        return 'Programar Cambio de Plan';
    }
  }

  isCurrentPlan(planId: number): boolean {
    const current = this.currentSub();
    return current?.id_plan_saas === planId && this.hasActiveSub();
  }
}
