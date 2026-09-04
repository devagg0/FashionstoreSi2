import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService, LoginRequest, LoginResponse } from '../../core/services/auth.service';
import { SessionService } from '../../core/services/session.service';
import { AuthLayout } from '../../layout/auth-layout/auth-layout';
import { Icon } from '../../shared/components/icon/icon';
import { PasswordRecoveryModal } from './password-recovery-modal/password-recovery-modal';

const POST_LOGIN_ROUTE_BY_ROLE: Readonly<Record<string, string>> = {
  CLIENTE: '/',
  ADMINISTRADOR: '/admin',
  ENCARGADO_SUCURSAL: '/',
  CAJERO: '/',
  PROVEEDOR: '/',
};

@Component({
  selector: 'app-login',
  imports: [AuthLayout, Icon, PasswordRecoveryModal, ReactiveFormsModule, RouterLink],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private readonly authService = inject(AuthService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);
  private readonly navigationMessage =
    this.router.getCurrentNavigation()?.extras.state?.['successMessage'];

  protected readonly isSubmitting = signal(false);
  protected readonly successMessage = signal(
    typeof this.navigationMessage === 'string' ? this.navigationMessage : null,
  );
  protected readonly serverMessage = signal<string | null>(null);
  protected readonly showPassword = signal(false);
  protected readonly recoveryModalOpen = signal(false);
  protected readonly loginForm = this.formBuilder.nonNullable.group({
    correo: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  protected submitLogin(): void {
    if (this.isSubmitting()) {
      return;
    }

    this.successMessage.set(null);

    const emailControl = this.loginForm.controls.correo;
    const normalizedEmail = emailControl.value.trim().toLowerCase();
    if (normalizedEmail !== emailControl.value) {
      emailControl.setValue(normalizedEmail);
    }

    this.serverMessage.set(null);

    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    const value = this.loginForm.getRawValue();
    const payload: LoginRequest = {
      correo: value.correo,
      password: value.password,
    };

    this.isSubmitting.set(true);
    this.authService
      .login(payload)
      .pipe(finalize(() => this.isSubmitting.set(false)))
      .subscribe({
        next: (response) => this.completeLogin(response),
        error: (error: HttpErrorResponse) => this.handleLoginError(error),
      });
  }

  protected isInvalid(controlName: 'correo' | 'password'): boolean {
    const control = this.loginForm.controls[controlName];
    return control.invalid && (control.touched || control.dirty);
  }

  private completeLogin(response: LoginResponse): void {
    try {
      this.sessionService.saveAccessToken(response.access_token);
      this.sessionService.saveUser(response.usuario);
    } catch {
      this.sessionService.logout();
      this.serverMessage.set('No pudimos iniciar sesión en este momento. Inténtalo nuevamente.');
      return;
    }

    const destination = POST_LOGIN_ROUTE_BY_ROLE[response.usuario.rol] ?? '/';
    void this.router.navigateByUrl(destination);
  }

  private handleLoginError(error: HttpErrorResponse): void {
    if (error.status === 401) {
      this.serverMessage.set('Correo o contraseña incorrectos.');
      return;
    }

    if (error.status === 403) {
      this.serverMessage.set('La cuenta se encuentra inactiva.');
      return;
    }

    if (error.status === 422) {
      this.serverMessage.set('Revisa los datos ingresados.');
      return;
    }

    this.serverMessage.set('No pudimos iniciar sesión en este momento. Inténtalo nuevamente.');
  }
}
