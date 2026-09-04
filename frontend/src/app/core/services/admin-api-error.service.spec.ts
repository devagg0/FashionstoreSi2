import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AdminApiErrorService } from './admin-api-error.service';
import { SessionService } from './session.service';

describe('AdminApiErrorService', () => {
  const router = { navigateByUrl: vi.fn() };
  const sessionService = { logout: vi.fn() };
  let service: AdminApiErrorService;

  beforeEach(() => {
    vi.clearAllMocks();
    TestBed.configureTestingModule({
      providers: [
        AdminApiErrorService,
        { provide: Router, useValue: router },
        { provide: SessionService, useValue: sessionService },
      ],
    });
    service = TestBed.inject(AdminApiErrorService);
  });

  it('closes an invalid session and redirects to login on 401', () => {
    const message = service.resolve(new HttpErrorResponse({ status: 401 }));

    expect(sessionService.logout).toHaveBeenCalledOnce();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/login');
    expect(message).toContain('sesión expiró');
  });

  it('keeps the session and reports unauthorized access on 403', () => {
    const message = service.resolve(new HttpErrorResponse({ status: 403 }));

    expect(sessionService.logout).not.toHaveBeenCalled();
    expect(router.navigateByUrl).not.toHaveBeenCalled();
    expect(message).toBe('Acceso no autorizado.');
  });
});
