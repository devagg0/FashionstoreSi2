import { Component, computed, HostListener, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-superadmin-layout',
  imports: [Icon, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './superadmin-layout.html',
  styleUrl: '../admin-layout/admin-layout.scss',
})
export class SuperadminLayout {
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);

  protected readonly sidebarOpen = signal(false);
  protected readonly user = this.sessionService.currentUser;
  protected readonly initials = computed(() => {
    const currentUser = this.user();
    if (!currentUser) return 'SA';
    return `${currentUser.nombre.charAt(0)}${currentUser.apellido.charAt(0)}`.toUpperCase();
  });

  protected toggleSidebar(): void {
    this.sidebarOpen.update((open) => !open);
  }

  protected closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  protected logout(): void {
    this.sessionService.logout();
    this.closeSidebar();
    void this.router.navigateByUrl('/login');
  }

  @HostListener('document:keydown.escape')
  protected closeSidebarWithEscape(): void {
    this.closeSidebar();
  }
}
