import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import type { AuthenticatedUser } from '../../core/services/auth.service';
import { SessionService } from '../../core/services/session.service';
import { PublicHeader } from './public-header';

describe('PublicHeader', () => {
  const user: AuthenticatedUser = {
    id_usuario: 1,
    nombre: 'Marcelo',
    apellido: 'Perez',
    correo: 'marcelo@example.com',
    rol: 'CLIENTE',
  };

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [PublicHeader],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('reacts to login and logout without reloading the page', () => {
    const sessionService = TestBed.inject(SessionService);
    const router = TestBed.inject(Router);
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    const fixture = TestBed.createComponent(PublicHeader);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.login-link')?.textContent).toContain(
      'Iniciar sesión',
    );

    sessionService.saveAccessToken('test-token');
    sessionService.saveUser(user);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.login-link')).toBeNull();
    expect(fixture.nativeElement.querySelector('.account-trigger')?.textContent).toContain(
      'Marcelo',
    );

    fixture.nativeElement.querySelector('.account-trigger').click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).toContain(
      'Marcelo Perez',
    );
    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).toContain(
      'CLIENTE',
    );

    fixture.nativeElement.querySelector('.account-dropdown button').click();
    fixture.detectChanges();

    expect(localStorage.getItem('fashionstore_access_token')).toBeNull();
    expect(localStorage.getItem('fashionstore_user')).toBeNull();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/');
    expect(fixture.nativeElement.querySelector('.login-link')?.textContent).toContain(
      'Iniciar sesión',
    );
  });
});
