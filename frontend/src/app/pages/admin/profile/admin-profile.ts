import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminUsersService } from '../../../core/services/admin-users.service';
import { SessionService } from '../../../core/services/session.service';
import { Profile } from '../../profile/profile';

@Component({
  selector: 'app-admin-profile',
  imports: [Profile],
  templateUrl: './admin-profile.html',
  styleUrl: './admin-profile.scss',
})
export class AdminProfile implements OnInit {
  private readonly adminUsersService = inject(AdminUsersService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly sessionService = inject(SessionService);

  protected readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    const currentUser = this.sessionService.getUser();
    if (!currentUser) return;

    this.adminUsersService.getUser(currentUser.id_usuario).subscribe({
      next: (response) => {
        this.sessionService.saveUser({ ...currentUser, ...response.data });
      },
      error: (error: HttpErrorResponse) => {
        this.errorMessage.set(
          this.errorService.resolve(error, {
            notFound: 'No encontramos la información de tu cuenta.',
            fallback: 'No pudimos actualizar la información de tu perfil.',
          }),
        );
      },
    });
  }
}
