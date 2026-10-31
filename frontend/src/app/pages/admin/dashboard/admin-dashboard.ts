import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { finalize, forkJoin } from 'rxjs';
import { AdminApiErrorService } from '../../../core/services/admin-api-error.service';
import { AdminUsersService } from '../../../core/services/admin-users.service';
import { SaasPlanLimitsService } from '../../../core/services/saas-plan-limits.service';
import { Icon, IconName } from '../../../shared/components/icon/icon';

interface SummaryCard {
  label: string;
  value: number;
  icon: IconName;
  helper: string;
}

@Component({
  selector: 'app-admin-dashboard',
  imports: [DatePipe, Icon, RouterLink],
  templateUrl: './admin-dashboard.html',
  styleUrl: './admin-dashboard.scss',
})
export class AdminDashboard implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly adminUsersService = inject(AdminUsersService);
  private readonly errorService = inject(AdminApiErrorService);
  private readonly planLimitsService = inject(SaasPlanLimitsService);

  protected readonly loading = signal(true);
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly cards = signal<SummaryCard[]>([]);

  // Estado del plan SaaS
  protected readonly planLimits = this.planLimitsService.currentPlanLimits;
  protected readonly planLoading = this.planLimitsService.loading;

  protected readonly branchUsagePercent = computed(() => {
    const limits = this.planLimits();
    const limit = limits?.consumo_sucursales?.limite_sucursales;
    const active = limits?.consumo_sucursales?.sucursales_activas ?? 0;
    if (!limit || limit <= 0) return 0;
    return Math.min(100, Math.round((active / limit) * 100));
  });

  ngOnInit(): void {
    this.loadSummary();
    this.loadPlanLimits();
  }

  protected loadPlanLimits(): void {
    this.planLimitsService
      .getCurrentPlanLimits()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        error: () => {},
      });
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
