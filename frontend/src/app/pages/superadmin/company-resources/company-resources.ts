import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AdminCitiesService, AdminCity } from '../../../core/services/admin-cities.service';
import {
  SaasCompaniesService,
  SaasCompany,
} from '../../../core/services/saas-companies.service';
import {
  AvailableUserData,
  SaasCompanyAdminService,
} from '../../../core/services/saas-company-admin.service';
import {
  AssociateExistingBranchRequest,
  AssociateUserRequest,
  CompanyBranchData,
  CompanyUserData,
  CreateCompanyBranchRequest,
  SaasCompanyResourcesService,
} from '../../../core/services/saas-company-resources.service';
import { Icon } from '../../../shared/components/icon/icon';

export type ActiveTab = 'usuarios' | 'sucursales';

@Component({
  selector: 'app-company-resources',
  imports: [DatePipe, Icon, ReactiveFormsModule, RouterLink],
  templateUrl: './company-resources.html',
  styleUrl: './company-resources.scss',
})
export class CompanyResources implements OnInit {
  private readonly companiesService = inject(SaasCompaniesService);
  private readonly resourcesService = inject(SaasCompanyResourcesService);
  private readonly citiesService = inject(AdminCitiesService);
  private readonly adminService = inject(SaasCompanyAdminService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly formBuilder = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  // Pestaña activa
  protected readonly activeTab = signal<ActiveTab>('usuarios');

  // Empresas
  protected readonly companies = signal<SaasCompany[]>([]);
  protected readonly companiesLoading = signal(false);
  protected readonly selectedCompanyId = signal<number | null>(null);
  protected readonly selectedCompany = computed(() => {
    const id = this.selectedCompanyId();
    if (!id) return null;
    return this.companies().find((c) => c.id_empresa === id) ?? null;
  });

  // Usuarios asociados
  protected readonly users = signal<CompanyUserData[]>([]);
  protected readonly usersLoading = signal(false);
  protected readonly userSearch = signal('');
  protected readonly userRoleFilter = signal('');
  protected readonly userStateFilter = signal('');

  // Sucursales asociadas
  protected readonly branches = signal<CompanyBranchData[]>([]);
  protected readonly branchesLoading = signal(false);
  protected readonly branchSearch = signal('');
  protected readonly branchStateFilter = signal<boolean | null>(null);

  // Ciudades activas para creación de sucursales
  protected readonly cities = signal<AdminCity[]>([]);
  protected readonly citiesLoading = signal(false);

  // Usuarios candidatos disponibles para asociación
  protected readonly candidateUsers = signal<AvailableUserData[]>([]);
  protected readonly candidatesLoading = signal(false);
  protected readonly candidateSearch = signal('');
  protected readonly selectedCandidate = signal<AvailableUserData | null>(null);

  // Estados de notificación y envíos
  protected readonly feedbackSuccess = signal<string | null>(null);
  protected readonly feedbackError = signal<string | null>(null);
  protected readonly isSubmitting = signal(false);

  // Modales
  protected readonly associateUserModalOpen = signal(false);
  protected readonly associateUserError = signal<string | null>(null);
  protected readonly associateUserForm = this.formBuilder.nonNullable.group({
    id_usuario: [0, [Validators.required, Validators.min(1)]],
    rol: ['CAJERO', [Validators.required]],
    estado: ['ACTIVO', [Validators.required]],
  });

  protected readonly createBranchModalOpen = signal(false);
  protected readonly createBranchError = signal<string | null>(null);
  protected readonly createBranchForm = this.formBuilder.nonNullable.group({
    id_ciudad: [0, [Validators.required, Validators.min(1)]],
    nombre: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(150)]],
    direccion: ['', [Validators.required, Validators.minLength(5), Validators.maxLength(200)]],
    telefono: ['', [Validators.maxLength(30)]],
    hora_apertura: ['08:30'],
    hora_cierre: ['20:00'],
  });

  protected readonly associateBranchModalOpen = signal(false);
  protected readonly associateBranchError = signal<string | null>(null);
  protected readonly associateBranchForm = this.formBuilder.nonNullable.group({
    id_sucursal: [0, [Validators.required, Validators.min(1)]],
  });

  ngOnInit(): void {
    this.loadCompanies();
    this.loadCities();

    // Sincronizar parámetro de ruta ?empresaId=
    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        const idParam = params.get('empresaId');
        if (idParam) {
          const parsed = Number(idParam);
          if (!isNaN(parsed) && parsed > 0 && parsed !== this.selectedCompanyId()) {
            this.selectCompany(parsed, false);
          }
        }
      });
  }

  // --- Cargas iniciales ---
  protected loadCompanies(): void {
    this.companiesLoading.set(true);
    this.companiesService
      .listCompanies({ estado: 'ACTIVA', pageSize: 100 })
      .pipe(
        finalize(() => this.companiesLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (response) => {
          this.companies.set(response.data);
          const currentId = this.selectedCompanyId();
          if (!currentId && response.data.length > 0) {
            this.selectCompany(response.data[0].id_empresa, true);
          }
        },
        error: (err: HttpErrorResponse) => {
          this.feedbackError.set(
            err.error?.message ?? 'No fue posible cargar el listado de empresas activas.',
          );
        },
      });
  }

  protected loadCities(): void {
    this.citiesLoading.set(true);
    this.citiesService
      .listCities({ estado: true, pageSize: 100 })
      .pipe(
        finalize(() => this.citiesLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (response) => {
          this.cities.set(response.data);
          if (
            this.createBranchModalOpen() &&
            this.createBranchForm.get('id_ciudad')?.value === 0 &&
            response.data.length > 0
          ) {
            this.createBranchForm.patchValue({ id_ciudad: response.data[0].id_ciudad });
          }
        },
        error: () => {
          // Si falla listado de ciudades, no bloquea toda la pantalla
        },
      });
  }

  protected onCompanySelectChange(event: Event): void {
    const target = event.target as HTMLSelectElement;
    const value = Number(target.value);
    if (!isNaN(value) && value > 0) {
      this.selectCompany(value, true);
    }
  }

  protected selectCompany(companyId: number, updateUrl = true): void {
    this.selectedCompanyId.set(companyId);
    this.feedbackSuccess.set(null);
    this.feedbackError.set(null);

    if (updateUrl) {
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: { empresaId: companyId },
        queryParamsHandling: 'merge',
      });
    }

    this.loadCompanyUsers();
    this.loadCompanyBranches();
  }

  // --- Carga de usuarios asociados ---
  protected loadCompanyUsers(): void {
    const companyId = this.selectedCompanyId();
    if (!companyId) {
      this.users.set([]);
      return;
    }

    this.usersLoading.set(true);
    this.resourcesService
      .getCompanyUsers(companyId, {
        role: this.userRoleFilter() || undefined,
        estado: this.userStateFilter() || undefined,
        search: this.userSearch() || undefined,
      })
      .pipe(
        finalize(() => this.usersLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (response) => {
          this.users.set(response.data);
        },
        error: (err: HttpErrorResponse) => {
          this.feedbackError.set(
            err.error?.message ?? 'Error al cargar usuarios de la empresa.',
          );
        },
      });
  }

  // --- Carga de sucursales asociadas ---
  protected loadCompanyBranches(): void {
    const companyId = this.selectedCompanyId();
    if (!companyId) {
      this.branches.set([]);
      return;
    }

    this.branchesLoading.set(true);
    this.resourcesService
      .getCompanyBranches(companyId, {
        estado: this.branchStateFilter() !== null ? this.branchStateFilter()! : undefined,
        search: this.branchSearch() || undefined,
      })
      .pipe(
        finalize(() => this.branchesLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (response) => {
          this.branches.set(response.data);
        },
        error: (err: HttpErrorResponse) => {
          this.feedbackError.set(
            err.error?.message ?? 'Error al cargar sucursales de la empresa.',
          );
        },
      });
  }

  // --- Filtros ---
  protected applyUserSearch(term: string): void {
    this.userSearch.set(term);
    this.loadCompanyUsers();
  }

  protected applyUserRoleFilter(role: string): void {
    this.userRoleFilter.set(role);
    this.loadCompanyUsers();
  }

  protected applyUserStateFilter(state: string): void {
    this.userStateFilter.set(state);
    this.loadCompanyUsers();
  }

  protected applyBranchSearch(term: string): void {
    this.branchSearch.set(term);
    this.loadCompanyBranches();
  }

  protected applyBranchStateFilter(stateStr: string): void {
    if (stateStr === 'true') this.branchStateFilter.set(true);
    else if (stateStr === 'false') this.branchStateFilter.set(false);
    else this.branchStateFilter.set(null);
    this.loadCompanyBranches();
  }

  // --- Modal: Asociar Usuario ---
  protected openAssociateUserModal(): void {
    this.associateUserError.set(null);
    this.selectedCandidate.set(null);
    this.candidateSearch.set('');
    this.associateUserForm.reset({
      id_usuario: 0,
      rol: 'CAJERO',
      estado: 'ACTIVO',
    });
    this.loadCandidates();
    this.associateUserModalOpen.set(true);
  }

  protected closeAssociateUserModal(): void {
    this.associateUserModalOpen.set(false);
    this.associateUserError.set(null);
  }

  protected loadCandidates(): void {
    this.candidatesLoading.set(true);
    this.adminService
      .getAvailableUsers({
        search: this.candidateSearch() || undefined,
        pageSize: 15,
      })
      .pipe(
        finalize(() => this.candidatesLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resp) => {
          this.candidateUsers.set(resp.data);
        },
        error: () => {
          this.candidateUsers.set([]);
        },
      });
  }

  protected selectCandidate(user: AvailableUserData): void {
    this.selectedCandidate.set(user);
    this.associateUserForm.patchValue({ id_usuario: user.id_usuario });
  }

  protected submitAssociateUser(): void {
    if (this.isSubmitting() || this.associateUserForm.invalid) {
      this.associateUserForm.markAllAsTouched();
      return;
    }
    const companyId = this.selectedCompanyId();
    if (!companyId) return;

    const val = this.associateUserForm.getRawValue();
    const payload: AssociateUserRequest = {
      id_usuario: Number(val.id_usuario),
      rol: val.rol,
      estado: val.estado as 'ACTIVO' | 'INVITADO',
      es_propietario: false,
    };

    this.isSubmitting.set(true);
    this.associateUserError.set(null);

    this.resourcesService
      .associateUser(companyId, payload)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resp) => {
          this.feedbackSuccess.set(
            `Usuario ${resp.data.nombre} ${resp.data.apellido} asociado con rol ${resp.data.rol}.`,
          );
          this.closeAssociateUserModal();
          this.loadCompanyUsers();
        },
        error: (err: HttpErrorResponse) => {
          this.associateUserError.set(
            this.extractErrorMessage(err, 'No se pudo asociar el usuario a la empresa.'),
          );
        },
      });
  }

  // --- Modal: Crear Sucursal ---
  protected openCreateBranchModal(): void {
    this.createBranchError.set(null);
    if (this.cities().length === 0) {
      this.loadCities();
    }
    const defaultCity = this.cities().length > 0 ? this.cities()[0].id_ciudad : 0;
    this.createBranchForm.reset({
      id_ciudad: defaultCity,
      nombre: '',
      direccion: '',
      telefono: '',
      hora_apertura: '08:30',
      hora_cierre: '20:00',
    });
    this.createBranchModalOpen.set(true);
  }

  protected closeCreateBranchModal(): void {
    this.createBranchModalOpen.set(false);
    this.createBranchError.set(null);
  }

  protected submitCreateBranch(): void {
    if (this.isSubmitting() || this.createBranchForm.invalid) {
      this.createBranchForm.markAllAsTouched();
      return;
    }
    const companyId = this.selectedCompanyId();
    if (!companyId) return;

    const val = this.createBranchForm.getRawValue();
    const cleanTime = (t: string | null | undefined): string | null => {
      if (!t) return null;
      const trimmed = t.trim();
      if (!trimmed) return null;
      const parts = trimmed.split(':');
      if (parts.length === 2) {
        return `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}:00`;
      }
      return trimmed;
    };
    const payload: CreateCompanyBranchRequest = {
      id_ciudad: Number(val.id_ciudad),
      nombre: val.nombre.trim(),
      direccion: val.direccion.trim(),
      telefono: val.telefono.trim() || null,
      hora_apertura: cleanTime(val.hora_apertura),
      hora_cierre: cleanTime(val.hora_cierre),
    };

    this.isSubmitting.set(true);
    this.createBranchError.set(null);

    this.resourcesService
      .createBranch(companyId, payload)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resp) => {
          this.feedbackSuccess.set(
            `Sucursal «${resp.data.nombre}» creada y asociada con propiedad exclusiva.`,
          );
          this.closeCreateBranchModal();
          this.loadCompanyBranches();
        },
        error: (err: HttpErrorResponse) => {
          this.createBranchError.set(
            this.extractErrorMessage(err, 'No se pudo crear la sucursal para esta empresa.'),
          );
        },
      });
  }

  // --- Modal: Asociar Sucursal Existente ---
  protected openAssociateBranchModal(): void {
    this.associateBranchError.set(null);
    this.associateBranchForm.reset({
      id_sucursal: 0,
    });
    this.associateBranchModalOpen.set(true);
  }

  protected closeAssociateBranchModal(): void {
    this.associateBranchModalOpen.set(false);
    this.associateBranchError.set(null);
  }

  protected submitAssociateBranch(): void {
    if (this.isSubmitting() || this.associateBranchForm.invalid) {
      this.associateBranchForm.markAllAsTouched();
      return;
    }
    const companyId = this.selectedCompanyId();
    if (!companyId) return;

    const val = this.associateBranchForm.getRawValue();
    const payload: AssociateExistingBranchRequest = {
      id_sucursal: Number(val.id_sucursal),
    };

    this.isSubmitting.set(true);
    this.associateBranchError.set(null);

    this.resourcesService
      .associateExistingBranch(companyId, payload)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resp) => {
          this.feedbackSuccess.set(
            `Sucursal «${resp.data.nombre}» asociada/reactivada correctamente.`,
          );
          this.closeAssociateBranchModal();
          this.loadCompanyBranches();
        },
        error: (err: HttpErrorResponse) => {
          this.associateBranchError.set(
            this.extractErrorMessage(err, 'No se pudo asociar la sucursal.'),
          );
        },
      });
  }

  private extractErrorMessage(err: HttpErrorResponse, fallback: string): string {
    if (!err?.error) return fallback;

    if (typeof err.error.message === 'string' && err.error.message.trim()) {
      return err.error.message;
    }

    if (Array.isArray(err.error.detail)) {
      const messages = err.error.detail
        .map((item: any) => {
          const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : '';
          const msg = item.msg || 'Dato no válido';
          return field ? `${field}: ${msg}` : msg;
        })
        .filter(Boolean);
      if (messages.length > 0) {
        return messages.join('. ');
      }
    }

    if (typeof err.error.detail === 'string' && err.error.detail.trim()) {
      return err.error.detail;
    }

    return fallback;
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (this.associateUserModalOpen()) this.closeAssociateUserModal();
    if (this.createBranchModalOpen()) this.closeCreateBranchModal();
    if (this.associateBranchModalOpen()) this.closeAssociateBranchModal();
  }
}
