import { Component, computed, HostListener, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-admin-layout',
  imports: [Icon, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './admin-layout.html',
  styleUrl: './admin-layout.scss',
})
export class AdminLayout {
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);
  private readonly activeUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly sidebarOpen = signal(false);
  protected readonly user = this.sessionService.currentUser;
  protected readonly sectionTitle = computed(() => {
    const url = this.activeUrl();
    if (url.startsWith('/admin/productos')) return 'Productos';
    if (url.startsWith('/admin/promociones')) return 'Promociones';
    if (url.startsWith('/admin/proveedores')) return 'Proveedores';
    if (url.startsWith('/admin/usuarios')) return 'Usuarios y roles';
    if (url.startsWith('/admin/roles')) return 'Roles';
    if (url.startsWith('/admin/ciudades')) return 'Ciudades';
    if (url.startsWith('/admin/configuracion-catalogo')) return 'Configuración de catálogo';
    if (url.startsWith('/admin/sucursales')) return 'Sucursales';
    if (url.startsWith('/admin/asignaciones-sucursal')) return 'Asignación de empleados';
    if (url.startsWith('/admin/temporadas-colecciones')) return 'Temporadas y colecciones';
    if (url.startsWith('/admin/perfil')) return 'Mi perfil';
    return 'Resumen';
  });
  protected readonly usersSectionActive = computed(() =>
    /^\/admin\/(usuarios|roles)(?:[/?#]|$)/.test(this.activeUrl()),
  );
  protected readonly initials = computed(() => {
    const currentUser = this.user();
    if (!currentUser) return 'AD';
    return `${currentUser.nombre.charAt(0)}${currentUser.apellido.charAt(0)}`.toUpperCase();
  });

  protected toggleSidebar(): void {
    this.sidebarOpen.update((isOpen) => !isOpen);
  }

  protected closeSidebar(): void {
    this.sidebarOpen.set(false);
  }

  protected logout(): void {
    this.sessionService.logout();
    this.closeSidebar();
    void this.router.navigateByUrl('/');
  }

  @HostListener('document:keydown.escape')
  protected closeSidebarWithEscape(): void {
    this.closeSidebar();
  }
}
