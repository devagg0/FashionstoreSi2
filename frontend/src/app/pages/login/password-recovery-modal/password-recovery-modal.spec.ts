import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../../environments/environment';
import { PasswordRecoveryModal } from './password-recovery-modal';

describe('PasswordRecoveryModal', () => {
  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [PasswordRecoveryModal],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
  });

  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    localStorage.clear();
  });

  it('completes all three steps without storing sensitive data', () => {
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(PasswordRecoveryModal);
    fixture.detectChanges();

    setInputValue(fixture.nativeElement.querySelector('#recovery-email'), ' Cliente@Gmail.com ');
    submitCurrentForm(fixture.nativeElement);
    fixture.detectChanges();

    expect(currentSubmitButton(fixture.nativeElement).disabled).toBe(true);
    expect(currentSubmitButton(fixture.nativeElement).textContent).toContain('Enviando...');
    const requestEmail = http.expectOne(`${environment.apiUrl}/api/auth/password-recovery/request`);
    expect(requestEmail.request.method).toBe('POST');
    expect(requestEmail.request.body).toEqual({ correo: 'cliente@gmail.com' });
    requestEmail.flush({
      success: true,
      message: 'Si el correo está registrado, recibirás un código de recuperación',
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain(
      'Te enviamos un código de 6 dígitos si el correo está registrado.',
    );
    setInputValue(fixture.nativeElement.querySelector('#recovery-code'), '123456');
    submitCurrentForm(fixture.nativeElement);
    const verifyCode = http.expectOne(`${environment.apiUrl}/api/auth/password-recovery/verify`);
    expect(verifyCode.request.body).toEqual({
      correo: 'cliente@gmail.com',
      codigo: '123456',
    });
    verifyCode.flush({
      success: true,
      message: 'Código verificado correctamente',
      reset_token: 'temporary-reset-token',
    });
    fixture.detectChanges();

    expect(localStorage.length).toBe(0);
    setInputValue(fixture.nativeElement.querySelector('#recovery-new-password'), 'Nueva@2026');
    setInputValue(fixture.nativeElement.querySelector('#recovery-confirm-password'), 'Nueva@2026');
    submitCurrentForm(fixture.nativeElement);
    fixture.detectChanges();

    expect(currentSubmitButton(fixture.nativeElement).disabled).toBe(true);
    expect(currentSubmitButton(fixture.nativeElement).textContent).toContain('Actualizando...');
    const resetPassword = http.expectOne(`${environment.apiUrl}/api/auth/password-recovery/reset`);
    expect(resetPassword.request.body).toEqual({
      reset_token: 'temporary-reset-token',
      new_password: 'Nueva@2026',
      confirm_password: 'Nueva@2026',
    });
    resetPassword.flush({
      success: true,
      message: 'Contraseña restablecida correctamente',
    });
    fixture.detectChanges();

    expect(localStorage.length).toBe(0);
    expect(fixture.nativeElement.textContent).toContain('Contraseña restablecida correctamente.');
    expect(fixture.nativeElement.textContent).toContain(
      'Ya puedes iniciar sesión con tu nueva contraseña.',
    );
  });

  it('shows a friendly message for an invalid or expired code', () => {
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(PasswordRecoveryModal);
    fixture.detectChanges();

    setInputValue(fixture.nativeElement.querySelector('#recovery-email'), 'cliente@gmail.com');
    submitCurrentForm(fixture.nativeElement);
    http
      .expectOne(`${environment.apiUrl}/api/auth/password-recovery/request`)
      .flush({ success: true, message: 'Solicitud recibida' });
    fixture.detectChanges();

    setInputValue(fixture.nativeElement.querySelector('#recovery-code'), '999999');
    submitCurrentForm(fixture.nativeElement);
    http
      .expectOne(`${environment.apiUrl}/api/auth/password-recovery/verify`)
      .flush(
        { success: false, message: 'Código inválido o expirado' },
        { status: 400, statusText: 'Bad Request' },
      );
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain(
      'El código es inválido o expiró.',
    );
  });

  it('clears the current flow before emitting close', () => {
    const fixture = TestBed.createComponent(PasswordRecoveryModal);
    const closed = vi.fn();
    fixture.componentInstance.closed.subscribe(closed);
    fixture.detectChanges();

    setInputValue(fixture.nativeElement.querySelector('#recovery-email'), 'cliente@gmail.com');
    fixture.nativeElement.querySelector('.recovery-modal__close').click();
    fixture.detectChanges();

    expect(closed).toHaveBeenCalledOnce();
    expect(fixture.nativeElement.querySelector('#recovery-email').value).toBe('');
  });
});

function setInputValue(input: HTMLInputElement, value: string): void {
  input.value = value;
  input.dispatchEvent(new Event('input'));
}

function submitCurrentForm(host: HTMLElement): void {
  host.querySelector('form')?.dispatchEvent(new Event('submit'));
}

function currentSubmitButton(host: HTMLElement): HTMLButtonElement {
  return host.querySelector('form button[type="submit"]') as HTMLButtonElement;
}
