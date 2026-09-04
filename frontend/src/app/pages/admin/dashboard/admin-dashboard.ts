import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { finalize, forkJoin } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminUsersService } from '../../../core/services/admin-users.service';
import { Icon, IconName } from '../../../shared/components/icon/icon';

interface SummaryCard {
  label: string;
  value: number;
  icon: IconName;
  helper: string;
}

@Component({
  selector: 'app-admin-dashboard',
  imports: [Icon, RouterLink],
  templateUrl: './admin-dashboard.html',
  styleUrl: './admin-dashboard.scss',
})
export class AdminDashboard implements OnInit {
  private readonly adminUsersService = inject(AdminUsersService);
  private readonly errorService = inject(AdminApiErrorService);

  protected readonly loading = signal(true);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly cards = signal<SummaryCard[]>([]);

  ngOnInit(): void {
    this.loadSummary();
  }

  protected loadSummary(): void {
    this.loading.set(true);
    this.errorMessage.set(null);

    forkJoin({
      allUsers: this.adminUsersService.listUsers({ page: 1, pageSize: 1 }),
      activeUsers: this.adminUsersService.listUsers({ estado: true, page: 1, pageSize: 1 }),
      inactiveUsers: this.adminUsersService.listUsers({ estado: false, page: 1, pageSize: 1 }),
      roles: this.adminUsersService.listRoles(),
    })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: ({ allUsers, activeUsers, inactiveUsers, roles }) => {
          this.cards.set([
            {
              label: 'Total usuarios',
              value: allUsers.pagination.total,
              icon: 'users',
              helper: 'Cuentas registradas',
            },
            {
              label: 'Usuarios activos',
              value: activeUsers.pagination.total,
              icon: 'circle-check',
              helper: 'Con acceso habilitado',
            },
            {
              label: 'Usuarios inactivos',
              value: inactiveUsers.pagination.total,
              icon: 'ban',
              helper: 'Con acceso deshabilitado',
            },
            {
              label: 'Total roles',
              value: roles.data.length,
              icon: 'shield',
              helper: 'Configurados en el sistema',
            },
          ]);
        },
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errorService.resolve(error, {
              fallback: 'No pudimos cargar el resumen administrativo.',
            }),
          );
        },
      });
  }
}
