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

  it('CU19 keeps cart accessible in desktop and mobile navigation alongside reservations', () => {
    const fixture = TestBed.createComponent(PublicHeader); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.header-actions a[href="/carrito"]').textContent).toContain('Carrito');
    expect(fixture.nativeElement.querySelector('a[href="/reservar"]')).not.toBeNull();
    fixture.nativeElement.querySelector('.mobile-menu-trigger').click(); fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('.mobile-panel a[href="/carrito"]'); expect(link).not.toBeNull();
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    link.click(); fixture.detectChanges(); expect(fixture.nativeElement.querySelector('.mobile-panel')).toBeNull();
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
    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).toContain(
      'Reservas',
    );
    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).not.toContain(
      'Prendas para reservar',
    );
    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).not.toContain(
      'Mis reservas',
    );
    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).not.toContain(
      'Prendas para reservar',
    );
    expect(fixture.nativeElement.querySelector('.account-dropdown')?.textContent).not.toContain(
      'Mis reservas',
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

  it('CU23 exposes purchases to CLIENTE in desktop and mobile account menus only', () => {
    const session = TestBed.inject(SessionService);
    const fixture = TestBed.createComponent(PublicHeader);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a[href="/mis-compras"]')).toBeNull();
    session.saveUser(user);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.account-dropdown a[href="/mis-compras"]')?.textContent).toContain('Mis compras');
    fixture.nativeElement.querySelector('.mobile-menu-trigger').click();
    fixture.detectChanges();
    fixture.nativeElement.querySelector('.mobile-account__trigger').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.mobile-account a[href="/mis-compras"]')).not.toBeNull();
    session.saveUser({ ...user, rol: 'CAJERO' });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a[href="/mis-compras"]')).toBeNull();
  });
});
