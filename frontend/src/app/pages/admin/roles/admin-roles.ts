import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminRole, AdminUsersService } from '../../../core/services/admin-users.service';
import { Icon } from '../../../shared/components/icon/icon';

@Component({
  selector: 'app-admin-roles',
  imports: [Icon, RouterLink],
  templateUrl: './admin-roles.html',
  styleUrl: './admin-roles.scss',
})
export class AdminRoles implements OnInit {
  private readonly adminUsersService = inject(AdminUsersService);
  private readonly errorService = inject(AdminApiErrorService);

  protected readonly roles = signal<AdminRole[]>([]);
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.loadRoles();
  }

  protected loadRoles(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.adminUsersService
      .listRoles()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
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
}
