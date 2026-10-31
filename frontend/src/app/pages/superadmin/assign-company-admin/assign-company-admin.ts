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
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import {
  SaasCompaniesService,
  SaasCompany,
} from '../../../core/services/saas-companies.service';
import {
  AvailableUserData,
  AvailableUsersPagination,
  CompanyAdminData,
  CreateAndAssignCompanyAdminRequest,
  SaasCompanyAdminService,
} from '../../../core/services/saas-company-admin.service';
import { SessionService } from '../../../core/services/session.service';
import { Icon } from '../../../shared/components/icon/icon';

const EMPTY_USERS_PAGINATION: AvailableUsersPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-assign-company-admin',
  imports: [DatePipe, Icon, ReactiveFormsModule, RouterLink],
  templateUrl: './assign-company-admin.html',
  styleUrl: './assign-company-admin.scss',
})
export class AssignCompanyAdmin implements OnInit {
  private readonly companiesService = inject(SaasCompaniesService);
  private readonly adminService = inject(SaasCompanyAdminService);
  private readonly sessionService = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly formBuilder = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  // Estados de empresas
  protected readonly companies = signal<SaasCompany[]>([]);
  protected readonly companiesLoading = signal(false);
  protected readonly selectedCompanyId = signal<number | null>(null);
  protected readonly selectedCompany = computed(() => {
    const id = this.selectedCompanyId();
    if (!id) return null;
    return this.companies().find((c) => c.id_empresa === id) ?? null;
  });

  // Administrador actual
  protected readonly adminLoading = signal(false);
  protected readonly currentAdmin = signal<CompanyAdminData | null>(null);
  protected readonly currentAdminNotFound = signal(false);

  // Usuarios disponibles (exclusivamente rol ADMINISTRADOR elegible no asignado a otra empresa)
  protected readonly availableUsers = signal<AvailableUserData[]>([]);
  protected readonly usersPagination = signal<AvailableUsersPagination>(EMPTY_USERS_PAGINATION);
  protected readonly usersLoading = signal(false);
  protected readonly activeSearch = signal('');

  // Notificaciones y envíos
  protected readonly feedbackSuccess = signal<string | null>(null);
  protected readonly feedbackError = signal<string | null>(null);
  protected readonly isSubmitting = signal(false);

  // Modal de confirmación de asignación / reasignación existente
  protected readonly modalOpen = signal(false);
  protected readonly userToAssign = signal<AvailableUserData | null>(null);
  protected readonly modalError = signal<string | null>(null);
  protected readonly membershipStateControl = new FormControl<'ACTIVO' | 'INVITADO'>('ACTIVO', {
    nonNullable: true,
  });

  // Modal de creación de nuevo administrador
  protected readonly createModalOpen = signal(false);
  protected readonly showPassword = signal(false);
  protected readonly createModalError = signal<string | null>(null);
  protected readonly createAdminForm = this.formBuilder.nonNullable.group({
    nombre: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]],
    apellido: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(100)]],
    correo: ['', [Validators.required, Validators.email, Validators.maxLength(150)]],
    password: [
      '',
      [
        Validators.required,
        Validators.minLength(8),
        Validators.pattern(/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>_\-\\\/\[\]~`+=]).{8,}$/),
      ],
    ],
    telefono: ['', [Validators.maxLength(20), Validators.pattern(/^$|^\+?[0-9\s\-()]{7,20}$/)]],
    estado: ['ACTIVO' as 'ACTIVO' | 'INVITADO', [Validators.required]],
  });

  // Formulario de búsqueda
  protected readonly searchForm = this.formBuilder.nonNullable.group({
    search: ['', [Validators.maxLength(150)]],
  });

  @HostListener('document:keydown.escape')
  protected onEscapeKey(): void {
    if (this.isSubmitting()) return;
    if (this.createModalOpen()) {
      this.closeCreateModal();
    } else if (this.modalOpen()) {
      this.closeModal();
    }
  }

  ngOnInit(): void {
    this.loadCompanies();
    this.loadAvailableUsers(1);

    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => {
        const empresaParam = params.get('empresa') || params.get('id');
        if (empresaParam) {
          const parsed = Number(empresaParam);
          if (!isNaN(parsed) && parsed > 0 && parsed !== this.selectedCompanyId()) {
            this.selectedCompanyId.set(parsed);
            this.loadCurrentAdmin(parsed);
            this.loadAvailableUsers(1);
          }
        }
      });
  }

  protected onCompanySelectChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    const value = select.value ? Number(select.value) : null;
    this.selectCompany(value);
  }

  protected selectCompany(companyId: number | null): void {
    this.selectedCompanyId.set(companyId);
    this.feedbackSuccess.set(null);
    this.feedbackError.set(null);

    if (companyId) {
      this.router.navigate([], {
        relativeTo: this.route,
        queryParams: { empresa: companyId },
        queryParamsHandling: 'merge',
      });
      this.loadCurrentAdmin(companyId);
    } else {
      this.currentAdmin.set(null);
      this.currentAdminNotFound.set(false);
      this.router.navigate([], {
        relativeTo: this.route,
        queryParams: { empresa: null },
        queryParamsHandling: 'merge',
      });
    }
    this.loadAvailableUsers(1);
  }

  protected loadCompanies(): void {
    this.companiesLoading.set(true);
    this.companiesService
      .listCompanies({ estado: 'ACTIVA', pageSize: 100 })
      .pipe(
        finalize(() => this.companiesLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (res) => {
          this.companies.set(res.data);
          const currentId = this.selectedCompanyId();
          if (currentId && !this.currentAdmin() && !this.adminLoading()) {
            this.loadCurrentAdmin(currentId);
          }
        },
        error: (err: HttpErrorResponse) => {
          if (err.status === 401 || err.status === 403) {
            this.sessionService.logout();
            this.router.navigate(['/login']);
          } else {
            this.feedbackError.set('No fue posible cargar el listado de empresas activas');
          }
        },
      });
  }

  protected loadCurrentAdmin(companyId: number): void {
    this.adminLoading.set(true);
    this.currentAdmin.set(null);
    this.currentAdminNotFound.set(false);

    this.adminService
      .getCompanyAdmin(companyId)
      .pipe(
        finalize(() => this.adminLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (res) => {
          this.currentAdmin.set(res.data);
          this.currentAdminNotFound.set(false);
        },
        error: (err: HttpErrorResponse) => {
          if (err.status === 404) {
            this.currentAdmin.set(null);
            this.currentAdminNotFound.set(true);
          } else if (err.status === 401 || err.status === 403) {
            this.sessionService.logout();
            this.router.navigate(['/login']);
          } else {
            this.feedbackError.set('No fue posible consultar el administrador de la empresa');
          }
        },
      });
  }

  protected submitSearch(): void {
    const term = this.searchForm.controls.search.value.trim();
    this.activeSearch.set(term);
    this.loadAvailableUsers(1);
  }

  protected resetSearch(): void {
    this.searchForm.controls.search.setValue('');
    this.activeSearch.set('');
    this.loadAvailableUsers(1);
  }

  protected loadAvailableUsers(page = 1): void {
    this.usersLoading.set(true);
    this.adminService
      .getAvailableUsers({
        search: this.activeSearch() || undefined,
        empresaId: this.selectedCompanyId() || undefined,
        page,
        pageSize: 10,
      })
      .pipe(
        finalize(() => this.usersLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (res) => {
          this.availableUsers.set(res.data);
          this.usersPagination.set(res.pagination);
        },
        error: (err: HttpErrorResponse) => {
          if (err.status === 401 || err.status === 403) {
            this.sessionService.logout();
            this.router.navigate(['/login']);
          } else {
            this.feedbackError.set('No fue posible consultar los usuarios disponibles');
          }
        },
      });
  }

  protected previousUsersPage(): void {
    const current = this.usersPagination().page;
    if (current > 1 && !this.usersLoading()) {
      this.loadAvailableUsers(current - 1);
    }
  }

  protected nextUsersPage(): void {
    const { page, total_pages } = this.usersPagination();
    if (page < total_pages && !this.usersLoading()) {
      this.loadAvailableUsers(page + 1);
    }
  }

  // --- Asignación existente ---
  protected openAssignModal(user: AvailableUserData): void {
    if (!this.selectedCompanyId()) {
      this.feedbackError.set('Por favor, selecciona una empresa activa antes de asignar');
      return;
    }

    if (this.currentAdmin()?.id_usuario === user.id_usuario) {
      this.feedbackError.set('El usuario seleccionado ya es el administrador asignado');
      return;
    }

    this.userToAssign.set(user);
    this.membershipStateControl.setValue('ACTIVO');
    this.modalError.set(null);
    this.modalOpen.set(true);
  }

  protected closeModal(): void {
    if (this.isSubmitting()) return;
    this.modalOpen.set(false);
    this.userToAssign.set(null);
    this.modalError.set(null);
  }

  protected confirmAssignment(): void {
    const company = this.selectedCompany();
    const user = this.userToAssign();
    if (!company || !user || this.isSubmitting()) return;

    this.isSubmitting.set(true);
    this.modalError.set(null);

    const payload = {
      id_usuario: user.id_usuario,
      estado: this.membershipStateControl.value,
    };

    this.adminService
      .assignCompanyAdmin(company.id_empresa, payload)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (res) => {
          this.currentAdmin.set(res.data);
          this.currentAdminNotFound.set(false);
          this.modalOpen.set(false);
          this.userToAssign.set(null);
          this.feedbackSuccess.set(
            `Administrador asignado correctamente a la empresa "${company.nombre}".`,
          );
          this.feedbackError.set(null);
          this.loadAvailableUsers(this.usersPagination().page);
        },
        error: (err: HttpErrorResponse) => {
          if (err.status === 401 || err.status === 403) {
            this.sessionService.logout();
            this.router.navigate(['/login']);
            return;
          }
          const message =
            err.error?.message ||
            (err.status === 409
              ? 'Conflicto: el usuario ya es administrador principal de otra empresa o la empresa está inactiva.'
              : err.status === 404
                ? 'Empresa o usuario no encontrado.'
                : 'Ocurrió un error al procesar la asignación.');
          this.modalError.set(message);
        },
      });
  }

  // --- Creación de nuevo administrador ---
  protected openCreateModal(): void {
    if (!this.selectedCompanyId()) {
      this.feedbackError.set('Por favor, selecciona una empresa activa antes de crear un administrador');
      return;
    }

    this.createAdminForm.reset({
      nombre: '',
      apellido: '',
      correo: '',
      password: '',
      telefono: '',
      estado: 'ACTIVO',
    });
    this.showPassword.set(false);
    this.createModalError.set(null);
    this.createModalOpen.set(true);
  }

  protected closeCreateModal(): void {
    if (this.isSubmitting()) return;
    this.createModalOpen.set(false);
    this.createModalError.set(null);
    this.showPassword.set(false);
  }

  protected toggleShowPassword(): void {
    this.showPassword.update((val) => !val);
  }

  protected submitCreateAdmin(): void {
    const company = this.selectedCompany();
    if (!company) {
      this.createModalError.set('No hay una empresa activa seleccionada');
      return;
    }

    if (this.createAdminForm.invalid) {
      this.createAdminForm.markAllAsTouched();
      this.createModalError.set('Por favor completa todos los campos requeridos con información válida.');
      return;
    }

    this.isSubmitting.set(true);
    this.createModalError.set(null);

    const raw = this.createAdminForm.getRawValue();
    const payload: CreateAndAssignCompanyAdminRequest = {
      nombre: raw.nombre.trim(),
      apellido: raw.apellido.trim(),
      correo: raw.correo.trim().toLowerCase(),
      password: raw.password,
      telefono: raw.telefono.trim() ? raw.telefono.trim() : null,
      estado: raw.estado,
    };

    this.adminService
      .createAndAssignCompanyAdmin(company.id_empresa, payload)
      .pipe(
        finalize(() => this.isSubmitting.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (res) => {
          this.currentAdmin.set(res.data);
          this.currentAdminNotFound.set(false);
          this.createModalOpen.set(false);
          this.feedbackSuccess.set(
            `Nuevo administrador "${res.data.nombre} ${res.data.apellido}" creado y asignado exitosamente a la empresa "${company.nombre}".`,
          );
          this.feedbackError.set(null);
          this.loadAvailableUsers(this.usersPagination().page);
        },
        error: (err: HttpErrorResponse) => {
          if (err.status === 401 || err.status === 403) {
            this.sessionService.logout();
            this.router.navigate(['/login']);
            return;
          }
          const message =
            err.error?.message ||
            (err.status === 409
              ? 'Conflicto: el correo ya se encuentra registrado o la empresa no se encuentra activa.'
              : err.status === 422
                ? 'Los datos del usuario o la contraseña no cumplen los requisitos mínimos de seguridad.'
                : 'Ocurrió un error al crear y asignar el administrador.');
          this.createModalError.set(message);
        },
      });
  }

  protected isUserCurrentlyAssigned(userId: number): boolean {
    return this.currentAdmin()?.id_usuario === userId;
  }
}
