import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import type { AuthenticatedUser } from '../../../core/services/auth.service';
import { SessionService } from '../../../core/services/session.service';
import { ClientChatbotFab } from './client-chatbot-fab';

describe('ClientChatbotFab CU27', () => {
  const client: AuthenticatedUser = {
    id_usuario: 1,
    nombre: 'Ana',
    apellido: 'Lopez',
    correo: 'ana@example.com',
    rol: 'CLIENTE',
  };

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [ClientChatbotFab],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => localStorage.clear());

  it('muestra el acceso al cliente y navega a /asistente', async () => {
    const session = TestBed.inject(SessionService);
    session.saveAccessToken('client-token');
    session.saveUser(client);
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ClientChatbotFab);
    fixture.detectChanges();

    const link = fixture.nativeElement.querySelector('a.chatbot-fab') as HTMLAnchorElement;
    expect(link).not.toBeNull();
    expect(link.textContent).toContain('Asistente IA');

    link.click();
    fixture.detectChanges();
    const target = navigate.mock.calls[0]?.[0];
    expect(router.serializeUrl(target as ReturnType<Router['createUrlTree']>)).toBe('/asistente');
  });
});