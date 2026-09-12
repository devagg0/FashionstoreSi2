import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { AuthenticatedUser } from '../../../core/services/auth.service';
import { SessionService } from '../../../core/services/session.service';
import { StaffApiErrorService } from '../../../core/services/staff-api-error.service';
import { StaffReservationsService } from '../../../core/services/staff-reservations.service';
import { Icon } from '../../../shared/components/icon/icon';

interface StaffUser extends AuthenticatedUser {
  cargo?: string | null;
}

@Component({
  selector: 'app-staff-profile',
  imports: [Icon],
  templateUrl: './staff-profile.html',
})
export class StaffProfile implements OnInit {
  private readonly session = inject(SessionService);
  private readonly reservations = inject(StaffReservationsService);
  private readonly errors = inject(StaffApiErrorService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly user = this.session.currentUser;
  protected readonly branch = this.reservations.branch;
  protected readonly loading = signal(true);
  protected readonly errorMessage = signal('');

  ngOnInit(): void {
    this.reservations
      .loadBranchContext()
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        error: (error: HttpErrorResponse) => {
          this.errorMessage.set(
            this.errors.resolve(error, 'No pudimos cargar el contexto de sucursal.'),
          );
        },
      });
  }

  protected cargo(user: AuthenticatedUser): string | null {
    return (user as StaffUser).cargo ?? null;
  }
}
