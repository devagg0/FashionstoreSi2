import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, HostListener, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import {
  ConfigurePlanFeaturesPayload,
  CreateSaasPlanPayload,
  PlanFeatureItemInput,
  SaasFeatureCatalog,
  SaasPlan,
  SaasPlansService,
  UpdateSaasPlanPayload,
} from '../../../core/services/saas-plans.service';
import { SessionService } from '../../../core/services/session.service';
import { Icon } from '../../../shared/components/icon/icon';

type PlanModalType = 'create' | 'edit' | 'status' | 'delete' | 'features' | null;

interface ApiErrorBody {
  message?: string;
  detail?: string | Array<{ msg?: string; message?: string }>;
}

@Component({
  selector: 'app-manage-plans',
  imports: [DecimalPipe, Icon, ReactiveFormsModule],
  templateUrl: './manage-plans.html',
  styleUrl: './manage-plans.scss',
})
export class ManagePlans implements OnInit {
  private readonly plansService = inject(SaasPlansService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);

  // Estados principales de la vista
  protected readonly plans = signal<SaasPlan[]>([]);
  protected readonly featuresCatalog = signal<SaasFeatureCatalog[]>([]);
  protected readonly loading = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);

  // Estados de modales
  protected readonly activeModal = signal<PlanModalType>(null);
  protected readonly selectedPlan = signal<SaasPlan | null>(null);
  protected readonly modalSaving = signal(false);
  protected readonly modalLoading = signal(false);
  protected readonly modalErrorMessage = signal<string | null>(null);

  // Formulario de filtros
  protected readonly filtersForm = this.fb.group({
    search: [''],
    estado: [''],
  });

  // Formulario de creación
  protected readonly createForm = this.fb.group({
    codigo: ['', [Validators.required, Validators.maxLength(50)]],
    nombre: ['', [Validators.required, Validators.maxLength(100)]],
    descripcion: ['', [Validators.maxLength(300)]],
    precio: [199, [Validators.required, Validators.min(0)]],
    moneda: ['BOB', [Validators.required, Validators.minLength(3), Validators.maxLength(3)]],
    periodo_meses: [1, [Validators.required, Validators.min(1)]],
    estado: [true],
    limite_sucursales: [2, [Validators.required, Validators.min(1)]],
    habilitar_ia: [false],
  });

  // Formulario de edición comercial
  protected readonly editForm = this.fb.group({
    nombre: ['', [Validators.required, Validators.maxLength(100)]],
    descripcion: ['', [Validators.maxLength(300)]],
    precio: [0, [Validators.required, Validators.min(0)]],
    periodo_meses: [1, [Validators.required, Validators.min(1)]],
  });

  // Formulario dinámico de configuración de funcionalidades
  protected readonly featuresForm = this.fb.group({
    features: this.fb.array<FormGroup>([]),
  });

  get featuresArray(): FormArray<FormGroup> {
    return this.featuresForm.get('features') as FormArray<FormGroup>;
  }

  ngOnInit(): void {
    this.loadCatalog();
    this.loadPlans();
  }

  @HostListener('document:keydown.escape')
  onEscapeKey(): void {
    if (!this.modalSaving()) {
      this.closeModal();
    }
  }

  loadCatalog(): void {
    this.plansService
      .listFeatures()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (resp) => {
          this.featuresCatalog.set(resp.data ?? []);
        },
        error: () => {
          // Si el catálogo falla, se mantendrán las funcionalidades locales
        },
      });
  }

  loadPlans(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    const { search, estado } = this.filtersForm.value;
    const filterEstado = estado === '' || estado === null ? undefined : estado === 'true';

    this.plansService
      .listPlans({
        search: search?.trim() || undefined,
        estado: filterEstado,
      })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (resp) => {
          this.plans.set(resp.data ?? []);
        },
        error: (err: HttpErrorResponse) => {
          this.handlePageError(err);
        },
      });
  }

  applyFilters(): void {
    this.loadPlans();
  }

  resetFilters(): void {
    this.filtersForm.reset({ search: '', estado: '' });
    this.loadPlans();
  }

  // --- MODAL CREACIÓN ---
  openCreateModal(): void {
    this.modalErrorMessage.set(null);
    this.createForm.reset({
      codigo: '',
      nombre: '',
      descripcion: '',
      precio: 199,
      moneda: 'BOB',
      periodo_meses: 1,
      estado: true,
      limite_sucursales: 2,
      habilitar_ia: false,
    });
    this.activeModal.set('create');
  }

  submitCreate(): void {
    if (this.createForm.invalid || this.modalSaving()) {
      this.createForm.markAllAsTouched();
      return;
    }

    const val = this.createForm.value;
    this.modalSaving.set(true);
    this.modalErrorMessage.set(null);

    const initialFeatures: PlanFeatureItemInput[] = [
      {
        codigo: 'SUCURSALES',
        habilitada: true,
        limite: Number(val.limite_sucursales ?? 2),
      },
      {
        codigo: 'REPORTES_IA',
        habilitada: Boolean(val.habilitar_ia),
      },
    ];

    const payload: CreateSaasPlanPayload = {
      codigo: (val.codigo ?? '').trim().toUpperCase(),
      nombre: (val.nombre ?? '').trim(),
      descripcion: val.descripcion?.trim() || null,
      precio: Number(val.precio ?? 0),
      moneda: (val.moneda ?? 'BOB').trim().toUpperCase(),
      periodo_meses: Number(val.periodo_meses ?? 1),
      estado: Boolean(val.estado),
      funcionalidades: initialFeatures,
    };

    this.plansService
      .createPlan(payload)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.modalSaving.set(false)),
      )
      .subscribe({
        next: (resp) => {
          this.successMessage.set(`Plan "${resp.data.nombre}" creado exitosamente.`);
          this.closeModal();
          this.loadPlans();
        },
        error: (err: HttpErrorResponse) => {
          this.handleModalError(err, 'No se pudo crear el plan SaaS.');
        },
      });
  }

  // --- MODAL EDICIÓN COMERCIAL ---
  openEditModal(plan: SaasPlan): void {
    this.selectedPlan.set(plan);
    this.modalErrorMessage.set(null);
    this.editForm.reset({
      nombre: plan.nombre,
      descripcion: plan.descripcion ?? '',
      precio: Number(plan.precio),
      periodo_meses: plan.periodo_meses,
    });
    this.activeModal.set('edit');
  }

  submitEdit(): void {
    const plan = this.selectedPlan();
    if (!plan || this.editForm.invalid || this.modalSaving()) {
      this.editForm.markAllAsTouched();
      return;
    }

    const val = this.editForm.value;
    this.modalSaving.set(true);
    this.modalErrorMessage.set(null);

    const payload: UpdateSaasPlanPayload = {
      nombre: (val.nombre ?? '').trim(),
      descripcion: val.descripcion?.trim() || null,
      precio: Number(val.precio ?? 0),
      periodo_meses: Number(val.periodo_meses ?? 1),
    };

    this.plansService
      .updatePlan(plan.id_plan_saas, payload)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.modalSaving.set(false)),
      )
      .subscribe({
        next: (resp) => {
          this.successMessage.set(`Plan "${resp.data.nombre}" actualizado correctamente.`);
          this.closeModal();
          this.loadPlans();
        },
        error: (err: HttpErrorResponse) => {
          this.handleModalError(err, 'No se pudieron actualizar los datos del plan.');
        },
      });
  }

  // --- MODAL ACTIVAR / DESACTIVAR ---
  openStatusModal(plan: SaasPlan): void {
    this.selectedPlan.set(plan);
    this.modalErrorMessage.set(null);
    this.activeModal.set('status');
  }

  confirmToggleStatus(): void {
    const plan = this.selectedPlan();
    if (!plan || this.modalSaving()) return;

    const nuevoEstado = !plan.estado;
    this.modalSaving.set(true);
    this.modalErrorMessage.set(null);

    this.plansService
      .updatePlanStatus(plan.id_plan_saas, { estado: nuevoEstado })
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.modalSaving.set(false)),
      )
      .subscribe({
        next: (resp) => {
          const accion = resp.data.estado ? 'activado' : 'desactivado';
          this.successMessage.set(`Plan "${resp.data.nombre}" ${accion} correctamente.`);
          this.closeModal();
          this.loadPlans();
        },
        error: (err: HttpErrorResponse) => {
          this.handleModalError(err, 'No se pudo cambiar el estado del plan.');
        },
      });
  }

  // --- MODAL ELIMINAR PLAN ---
  openDeleteModal(plan: SaasPlan): void {
    this.selectedPlan.set(plan);
    this.modalErrorMessage.set(null);
    this.activeModal.set('delete');
  }

  confirmDelete(): void {
    const plan = this.selectedPlan();
    if (!plan || this.modalSaving()) return;

    this.modalSaving.set(true);
    this.modalErrorMessage.set(null);

    this.plansService
      .deletePlan(plan.id_plan_saas)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.modalSaving.set(false)),
      )
      .subscribe({
        next: (resp) => {
          this.successMessage.set(resp.message || `Plan "${plan.nombre}" eliminado exitosamente.`);
          this.closeModal();
          this.loadPlans();
        },
        error: (err: HttpErrorResponse) => {
          this.handleModalError(err, 'No se pudo eliminar el plan SaaS.');
        },
      });
  }

  // --- MODAL CONFIGURACIÓN DE FUNCIONALIDADES ---
  openFeaturesModal(plan: SaasPlan): void {
    this.selectedPlan.set(plan);
    this.modalErrorMessage.set(null);

    // Si el catálogo está vacío, intentamos cargarlo
    if (this.featuresCatalog().length === 0) {
      this.loadCatalog();
    }

    this.buildFeaturesForm(plan);
    this.activeModal.set('features');
  }

  private buildFeaturesForm(plan: SaasPlan): void {
    this.featuresArray.clear();

    const catalog = this.featuresCatalog();
    const existingFeatures = plan.funcionalidades || [];

    // Combinamos catálogo con asignadas
    const allCodes = new Set<string>([
      'SUCURSALES',
      'REPORTES_IA',
      'PRODUCTOS',
      'VENTAS_POS',
      'RESERVAS',
      'OFFLINE',
      'REPORTES_ESTANDAR',
      ...catalog.map((c) => c.codigo),
      ...existingFeatures.map((f) => f.codigo),
    ]);

    for (const code of allCodes) {
      const assigned = existingFeatures.find((f) => f.codigo.toUpperCase() === code.toUpperCase());
      const catItem = catalog.find((c) => c.codigo.toUpperCase() === code.toUpperCase());

      const nombre = assigned?.nombre || catItem?.nombre || this.getDefaultFeatureName(code);
      const habilitada = assigned ? assigned.habilitada : this.isDefaultEnabled(code);
      const limite = assigned?.limite !== undefined ? assigned.limite : this.getDefaultLimit(code);

      const group = this.fb.group({
        codigo: [code],
        nombre: [nombre],
        habilitada: [habilitada],
        limite: [limite],
      });
      this.featuresArray.push(group);
    }
  }

  submitFeatures(): void {
    const plan = this.selectedPlan();
    if (!plan || this.modalSaving()) return;

    this.modalSaving.set(true);
    this.modalErrorMessage.set(null);

    const items: PlanFeatureItemInput[] = this.featuresArray.controls.map((ctrl) => {
      const val = ctrl.value;
      return {
        codigo: val.codigo,
        habilitada: Boolean(val.habilitada),
        limite: val.codigo === 'SUCURSALES' ? (val.limite !== null && val.limite !== '' ? Number(val.limite) : null) : null,
      };
    });

    const payload: ConfigurePlanFeaturesPayload = {
      funcionalidades: items,
    };

    this.plansService
      .configurePlanFeatures(plan.id_plan_saas, payload)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.modalSaving.set(false)),
      )
      .subscribe({
        next: (resp) => {
          this.successMessage.set(
            `Funcionalidades y límites configurados para el plan "${resp.data.nombre}".`,
          );
          this.closeModal();
          this.loadPlans();
        },
        error: (err: HttpErrorResponse) => {
          this.handleModalError(err, 'No se pudieron guardar las funcionalidades.');
        },
      });
  }

  closeModal(): void {
    this.activeModal.set(null);
    this.selectedPlan.set(null);
    this.modalErrorMessage.set(null);
  }

  // --- HELPERS VISUALES Y DE NEGOCIO ---
  isRecommended(plan: SaasPlan): boolean {
    return plan.codigo.toUpperCase() === 'PROFESIONAL';
  }

  getBranchLimit(plan: SaasPlan): number | string {
    const feature = plan.funcionalidades?.find((f) => f.codigo.toUpperCase() === 'SUCURSALES');
    if (feature && feature.limite !== null && feature.limite !== undefined) {
      return feature.limite;
    }
    if (plan.codigo.toUpperCase() === 'BASICO') return 2;
    if (plan.codigo.toUpperCase() === 'PROFESIONAL') return 10;
    return 'Sin límite';
  }

  hasAiReports(plan: SaasPlan): boolean {
    const feature = plan.funcionalidades?.find((f) => f.codigo.toUpperCase() === 'REPORTES_IA');
    if (feature) return feature.habilitada;
    return plan.codigo.toUpperCase() === 'PROFESIONAL';
  }

  getCustomFeatures(plan: SaasPlan) {
    const standardCodes = ['SUCURSALES', 'REPORTES_IA', 'PRODUCTOS', 'VENTAS_POS', 'RESERVAS', 'OFFLINE', 'REPORTES_ESTANDAR'];
    return (plan.funcionalidades || []).filter(
      (f) => !standardCodes.includes(f.codigo.toUpperCase()),
    );
  }

  private getDefaultFeatureName(codigo: string): string {
    switch (codigo.toUpperCase()) {
      case 'SUCURSALES':
        return 'Límite de Sucursales Activas';
      case 'REPORTES_IA':
        return 'Reportes Generativos con Inteligencia Artificial';
      case 'PRODUCTOS':
        return 'Gestión de Productos e Inventarios';
      case 'VENTAS_POS':
        return 'Punto de Venta y Facturación';
      case 'RESERVAS':
        return 'Gestión de Reservas y Apartados';
      case 'OFFLINE':
        return 'Modo Offline con Sincronización Automática';
      case 'REPORTES_ESTANDAR':
        return 'Reportes y Analíticas Convencionales';
      default:
        return codigo;
    }
  }

  private isDefaultEnabled(codigo: string): boolean {
    return codigo.toUpperCase() !== 'REPORTES_IA';
  }

  private getDefaultLimit(codigo: string): number | null {
    if (codigo.toUpperCase() === 'SUCURSALES') return 2;
    return null;
  }

  // --- MANEJO DE ERRORES ---
  private handlePageError(error: HttpErrorResponse): void {
    if (error.status === 401) {
      this.expireSession();
      return;
    }
    if (error.status === 403) {
      this.errorMessage.set('Tu cuenta no tiene permisos SUPERADMIN para administrar planes SaaS.');
      return;
    }
    this.errorMessage.set('No pudimos cargar los planes SaaS. Inténtalo de nuevo.');
  }

  private handleModalError(error: HttpErrorResponse, fallback: string): void {
    if (error.status === 401) {
      this.expireSession();
      return;
    }
    if (error.status === 403) {
      this.modalErrorMessage.set('Acción restringida: se requiere rol SUPERADMIN.');
      return;
    }

    const body = error.error as ApiErrorBody | null;
    let message: string | null = null;

    if (body) {
      if (typeof body.detail === 'string') {
        message = body.detail;
      } else if (Array.isArray(body.detail) && body.detail.length > 0) {
        message = body.detail[0]?.msg || body.detail[0]?.message || null;
      } else if (typeof body.message === 'string') {
        message = body.message;
      }
    }

    if (error.status === 409) {
      this.modalErrorMessage.set(message || 'Conflicto: la operación no cumple las reglas de suscripciones.');
      return;
    }

    if (error.status === 422) {
      this.modalErrorMessage.set(message || 'Los valores ingresados no son válidos para el plan.');
      return;
    }

    if (error.status === 404) {
      this.modalErrorMessage.set(message || 'El plan SaaS solicitado ya no existe.');
      return;
    }

    this.modalErrorMessage.set(message || fallback);
  }

  private expireSession(): void {
    this.sessionService.logout();
    void this.router.navigateByUrl('/login', {
      state: { successMessage: 'Tu sesión expiró. Inicia sesión nuevamente.' },
    });
  }
}

