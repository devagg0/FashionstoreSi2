import { Component, computed, DestroyRef, HostListener, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { SessionService } from '../../core/services/session.service';
import { StaffReservationsService } from '../../core/services/staff-reservations.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-staff-layout',
  imports: [Icon, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './staff-layout.html',
})
export class StaffLayout implements OnInit {
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  private readonly reservations = inject(StaffReservationsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly activeUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly sidebarOpen = signal(false);
  protected readonly user = this.session.currentUser;
  protected readonly branch = this.reservations.branch;
  protected readonly sectionTitle = computed(() => {
    const url = this.activeUrl();
    if (url.startsWith('/staff/reservas/')) return 'Detalle de reserva';
    if (url.startsWith('/staff/reservas')) return 'Reservas';
    if (url.startsWith('/staff/disponibilidad')) return 'Disponibilidad';
    if (url.startsWith('/staff/perfil')) return 'Mi perfil';
    return 'Inicio';
  });
  protected readonly initials = computed(() => {
    const current = this.user();
    return current
      ? `${current.nombre.charAt(0)}${current.apellido.charAt(0)}`.toUpperCase()
      : 'FS';
  });

  ngOnInit(): void {
    this.reservations
      .loadBranchContext()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ error: () => undefined });
  }

  protected toggleSidebar(): void {
    this.sidebarOpen.update((open) => !open);
  }

  protected closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  protected logout(): void {
    this.reservations.clearContext();
    this.session.logout();
    this.closeSidebar();
    void this.router.navigateByUrl('/login');
  }

  @HostListener('document:keydown.escape')
  protected closeWithEscape(): void {
    this.closeSidebar();
  }
}
