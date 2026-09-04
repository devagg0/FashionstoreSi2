import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, HostListener, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import {
  AdminPagination,
  AdminRole,
  AdminUser,
  AdminUserCreateRequest,
  AdminUsersService,
  InternalUserRole,
} from '../../../core/services/admin-users.service';
import { SessionService } from '../../../core/services/session.service';
import { Icon } from '../../../shared/components/icon/icon';
import {
  matchingFieldsValidator,
  optionalPhoneValidator,
  PASSWORD_REQUIREMENTS,
  PasswordRequirement,
  passwordStrengthValidator,
  trimmedLengthValidator,
} from '../../../shared/validators/auth.validators';

type CreateControlName =
  | 'nombre'
  | 'apellido'
  | 'correo'
  | 'telefono'
  | 'rol'
  | 'password'
  | 'confirmPassword';

const EMPTY_PAGINATION: AdminPagination = {
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
};

@Component({
  selector: 'app-admin-users',
  imports: [Icon, ReactiveFormsModule, RouterLink],
  templateUrl: './admin-users.html',
  styleUrl: './admin-users.scss',
})
export class AdminUsers implements OnInit {
  private readonly adminUsersService = inject(AdminUsersService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly sessionService = inject(SessionService);

  protected readonly currentUser = this.sessionService.currentUser;
  protected readonly users = signal<AdminUser[]>([]);
  protected readonly roles = signal<AdminRole[]>([]);
  protected readonly pagination = signal<AdminPagination>(EMPTY_PAGINATION);
  protected readonly loading = signal(true);
  protected readonly detailLoading = signal(false);
  protected readonly saving = signal(false);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly successMessage = signal<string | null>(null);
  protected readonly detailModalOpen = signal(false);
  protected readonly detailUser = signal<AdminUser | null>(null);
  protected readonly statusUser = signal<AdminUser | null>(null);
  protected readonly roleUser = signal<AdminUser | null>(null);
  protected readonly createModalOpen = signal(false);
  protected readonly createErrorMessage = signal<string | null>(null);
  protected readonly showCreatePassword = signal(false);
  protected readonly showCreateConfirmation = signal(false);
  protected readonly passwordRequirements = PASSWORD_REQUIREMENTS;
  protected readonly internalRoles: readonly InternalUserRole[] = [
    'CAJERO',
    'ENCARGADO_SUCURSAL',
  ];
  protected readonly assignableRoles = computed(() =>
    this.roles().filter((role) => role.nombre.toUpperCase() !== 'ADMINISTRADOR'),
  );
  protected readonly roleControl = new FormControl('', { nonNullable: true });
  protected readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    rol: '',
    estado: '',
  });
  protected readonly createForm = this.formBuilder.nonNullable.group(
    {
      nombre: ['', [Validators.required, trimmedLengthValidator(2, 100)]],
      apellido: ['', [Validators.required, trimmedLengthValidator(2, 100)]],
      correo: ['', [Validators.required, Validators.email]],
      telefono: ['', optionalPhoneValidator()],
      rol: ['CAJERO' as InternalUserRole, Validators.required],
      password: [
        '',
        [Validators.required, Validators.minLength(8), passwordStrengthValidator()],
      ],
      confirmPassword: ['', Validators.required],
    },
    { validators: matchingFieldsValidator('password', 'confirmPassword') },
  );

  ngOnInit(): void {
    this.loadRoles();
    this.loadUsers();
  }

  protected applyFilters(): void {
    this.loadUsers(1);
  }

  protected openCreateModal(): void {
    this.clearMessages();
    this.createErrorMessage.set(null);
    this.createModalOpen.set(true);
  }

  protected closeCreateModal(): void {
    if (this.saving()) return;
    this.resetCreateForm();
    this.createModalOpen.set(false);
  }

  protected submitCreateUser(): void {
    if (this.saving()) return;

    this.createErrorMessage.set(null);
    if (this.createForm.invalid) {
      this.createForm.markAllAsTouched();
      this.createErrorMessage.set('Revisa los datos ingresados.');
      return;
    }

    const value = this.createForm.getRawValue();
    const phone = value.telefono.trim();
    const payload: AdminUserCreateRequest = {
      nombre: value.nombre.trim(),
      apellido: value.apellido.trim(),
      correo: value.correo.trim().toLowerCase(),
      telefono: phone || null,
      rol: value.rol,
      password: value.password,
      confirm_password: value.confirmPassword,
    };

    this.saving.set(true);
    this.adminUsersService
      .createUser(payload)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => {
          this.resetCreateForm();
          this.createModalOpen.set(false);
          this.successMessage.set('Usuario creado correctamente');
          this.loadUsers(1);
        },
        error: (error: HttpErrorResponse) => {
          if (error.status === 409) {
            const emailControl = this.createForm.controls.correo;
            emailControl.setErrors({ ...emailControl.errors, emailTaken: true });
            emailControl.markAsTouched();
            this.createErrorMessage.set('El correo ya se encuentra registrado.');
            return;
          }

          this.createErrorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos crear el usuario. Inténtalo nuevamente.',
            }),
          );
        },
      });
  }

  protected isCreateInvalid(controlName: CreateControlName): boolean {
    const control = this.createForm.controls[controlName];
    return control.invalid && (control.touched || control.dirty);
  }

  protected hasCreateError(controlName: CreateControlName, errorName: string): boolean {
    return this.createForm.controls[controlName].hasError(errorName);
  }

  protected createConfirmationMismatch(): boolean {
    const confirmation = this.createForm.controls.confirmPassword;
    return (
      this.createForm.hasError('passwordMismatch') &&
      (confirmation.touched || confirmation.dirty)
    );
  }

  protected createPasswordMeets(requirement: PasswordRequirement): boolean {
    return requirement.test(this.createForm.controls.password.value);
  }

  protected clearFilters(): void {
    this.filters.reset({ search: '', rol: '', estado: '' });
    this.loadUsers(1);
  }

  protected loadUsers(page = 1): void {
    const filters = this.filters.getRawValue();
    const state = filters.estado === '' ? undefined : filters.estado === 'true';

    this.loading.set(true);
    this.errorMessage.set(null);
    this.adminUsersService
      .listUsers({
        search: filters.search,
        rol: filters.rol,
        estado: state,
        page,
        pageSize: 10,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (response) => {
          this.users.set(response.data);
          this.pagination.set(response.pagination);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar los usuarios.',
            }),
          );
        },
      });
  }

  protected viewDetail(userId: number): void {
    this.detailUser.set(null);
    this.detailModalOpen.set(true);
    this.detailLoading.set(true);
    this.errorMessage.set(null);

    this.adminUsersService
      .getUser(userId)
      .pipe(finalize(() => this.detailLoading.set(false)))
      .subscribe({
        next: (response) => this.detailUser.set(response.data),
        error: (error: HttpErrorResponse) => {
          this.closeDetail();
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El usuario solicitado ya no existe.',
              fallback: 'No pudimos cargar el detalle del usuario.',
            }),
          );
        },
      });
  }

  protected openStatusModal(user: AdminUser): void {
    if (this.isOwnUser(user)) return;
    this.clearMessages();
    this.statusUser.set(user);
  }

  protected confirmStatusChange(): void {
    const user = this.statusUser();
    if (!user || this.saving() || this.isOwnUser(user)) return;

    this.saving.set(true);
    this.adminUsersService
      .updateStatus(user.id_usuario, !user.estado)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (response) => {
          this.replaceUser(response.data);
          this.statusUser.set(null);
          this.successMessage.set(
            response.data.estado
              ? 'Usuario activado correctamente.'
              : 'Usuario desactivado correctamente.',
          );
        },
        error: (error: HttpErrorResponse) => {
          this.statusUser.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El usuario solicitado ya no existe.',
              conflict: 'No puedes desactivar tu propia cuenta administrativa.',
              fallback: 'No pudimos actualizar el estado del usuario.',
            }),
          );
        },
      });
  }

  protected openRoleModal(user: AdminUser): void {
    if (this.isOwnUser(user)) return;
    this.clearMessages();
    this.roleControl.setValue(user.rol);
    this.roleUser.set(user);
  }

  protected confirmRoleChange(): void {
    const user = this.roleUser();
    const role = this.roleControl.value;
    if (!user || !role || role === user.rol || this.saving() || this.isOwnUser(user)) return;

    this.saving.set(true);
    this.adminUsersService
      .updateRole(user.id_usuario, role)
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (response) => {
          this.replaceUser(response.data);
          this.roleUser.set(null);
          this.successMessage.set('Rol actualizado correctamente.');
        },
        error: (error: HttpErrorResponse) => {
          this.roleUser.set(null);
          this.errorMessage.set(
            this.errorService.resolve(error, {
              notFound: 'El usuario o el rol seleccionado ya no existe.',
              conflict: 'El usuario no cumple los requisitos para asumir este rol.',
              fallback: 'No pudimos actualizar el rol del usuario.',
            }),
          );
        },
      });
  }

  protected closeDetail(): void {
    if (this.detailLoading()) return;
    this.detailModalOpen.set(false);
    this.detailUser.set(null);
  }

  protected closeStatusModal(): void {
    if (!this.saving()) this.statusUser.set(null);
  }

  protected closeRoleModal(): void {
    if (!this.saving()) this.roleUser.set(null);
  }

  protected isOwnUser(user: AdminUser): boolean {
    return user.id_usuario === this.currentUser()?.id_usuario;
  }

  protected canGoPrevious(): boolean {
    return !this.loading() && this.pagination().page > 1;
  }

  protected canGoNext(): boolean {
    const pagination = this.pagination();
    return !this.loading() && pagination.page < pagination.total_pages;
  }

  protected previousPage(): void {
    if (this.canGoPrevious()) this.loadUsers(this.pagination().page - 1);
  }

  protected nextPage(): void {
    if (this.canGoNext()) this.loadUsers(this.pagination().page + 1);
  }

  protected dismissMessage(): void {
    this.clearMessages();
  }

  @HostListener('document:keydown.escape')
  protected closeOpenModal(): void {
    if (this.saving() || this.detailLoading()) return;
    this.detailModalOpen.set(false);
    this.detailUser.set(null);
    this.statusUser.set(null);
    this.roleUser.set(null);
    if (this.createModalOpen()) {
      this.resetCreateForm();
      this.createModalOpen.set(false);
    }
  }

  private loadRoles(): void {
    this.adminUsersService.listRoles().subscribe({
      next: (response) => this.roles.set(response.data),
      error: (error: HttpErrorResponse) => {
        this.errorMessage.set(
          this.errorService.resolve(error, {
            fallback: 'No pudimos cargar los roles disponibles.',
          }),
        );
      },
    });
  }

  private replaceUser(updatedUser: AdminUser): void {
    this.users.update((users) =>
      users.map((user) => (user.id_usuario === updatedUser.id_usuario ? updatedUser : user)),
    );
    if (this.detailUser()?.id_usuario === updatedUser.id_usuario) {
      this.detailUser.set(updatedUser);
    }
  }

  private clearMessages(): void {
    this.errorMessage.set(null);
    this.successMessage.set(null);
  }

  private resetCreateForm(): void {
    this.createForm.reset({
      nombre: '',
      apellido: '',
      correo: '',
      telefono: '',
      rol: 'CAJERO',
      password: '',
      confirmPassword: '',
    });
    this.createErrorMessage.set(null);
    this.showCreatePassword.set(false);
    this.showCreateConfirmation.set(false);
  }
}
