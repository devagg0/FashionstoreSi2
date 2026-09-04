import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Login } from './login';

describe('Login recovery access', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Login],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
  });

  it('opens password recovery from the discreet login link', () => {
    const fixture = TestBed.createComponent(Login);
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('.forgot-password-link');
    expect(link.textContent).toContain('¿Olvidaste tu contraseña?');

    link.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-password-recovery-modal')).toBeTruthy();
  });
});
