import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { environment } from '../../../environments/environment';
import { Profile } from './profile';

describe('Profile password change', () => {
  beforeEach(async () => {
    localStorage.setItem('fashionstore_access_token', 'signed-token');
    localStorage.setItem(
      'fashionstore_user',
      JSON.stringify({
        id_usuario: 42,
        nombre: 'Marcelo',
        apellido: 'Perez',
        correo: 'marcelo@example.com',
        rol: 'CLIENTE',
      }),
    );

    await TestBed.configureTestingModule({
      imports: [Profile],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    localStorage.clear();
  });

  it('sends the bearer token and logs out after a successful change', () => {
    const router = TestBed.inject(Router);
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Profile);
    fixture.detectChanges();

    submitValidPasswordForm(fixture);

    const request = TestBed.inject(HttpTestingController).expectOne(
      `${environment.apiUrl}/api/auth/change-password`,
    );
    expect(request.request.method).toBe('PUT');
    expect(request.request.headers.get('Authorization')).toBe('Bearer signed-token');
    expect(request.request.body).toEqual({
      current_password: 'Actual@2026',
      new_password: 'Nueva@2026',
      confirm_password: 'Nueva@2026',
    });

    request.flush({ success: true, message: 'Contraseña actualizada correctamente' });
    fixture.detectChanges();

    expect(localStorage.getItem('fashionstore_access_token')).toBeNull();
    expect(localStorage.getItem('fashionstore_user')).toBeNull();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/login', {
      state: {
        successMessage: 'Contraseña actualizada. Inicia sesión nuevamente.',
      },
    });
  });

  it('shows the expected message when the current password is wrong', () => {
    const fixture = TestBed.createComponent(Profile);
    fixture.detectChanges();
    submitValidPasswordForm(fixture);

    const request = TestBed.inject(HttpTestingController).expectOne(
      `${environment.apiUrl}/api/auth/change-password`,
    );
    request.flush(
      { success: false, message: 'La contraseña actual es incorrecta' },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain(
      'La contraseña actual es incorrecta.',
    );
    expect(localStorage.getItem('fashionstore_access_token')).toBe('signed-token');
  });

  it('clears the session and redirects when the token is invalid', () => {
    const router = TestBed.inject(Router);
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(Profile);
    fixture.detectChanges();
    submitValidPasswordForm(fixture);

    const request = TestBed.inject(HttpTestingController).expectOne(
      `${environment.apiUrl}/api/auth/change-password`,
    );
    request.flush(
      { success: false, message: 'Token inválido o expirado' },
      { status: 401, statusText: 'Unauthorized' },
    );
    fixture.detectChanges();

    expect(localStorage.getItem('fashionstore_access_token')).toBeNull();
    expect(localStorage.getItem('fashionstore_user')).toBeNull();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/login');
  });
});

function submitValidPasswordForm(fixture: ComponentFixture<Profile>): void {
  fixture.nativeElement.querySelector('.security-card__toggle').click();
  fixture.detectChanges();

  setInputValue(fixture.nativeElement.querySelector('#current-password'), 'Actual@2026');
  setInputValue(fixture.nativeElement.querySelector('#new-password'), 'Nueva@2026');
  setInputValue(fixture.nativeElement.querySelector('#confirm-new-password'), 'Nueva@2026');
  fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
}

function setInputValue(input: HTMLInputElement, value: string): void {
  input.value = value;
  input.dispatchEvent(new Event('input'));
}
