import { Component, ElementRef, HostListener, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

interface NavigationGroup {
  label: string;
  items: readonly string[];
}

@Component({
  selector: 'app-public-header',
  imports: [Icon, RouterLink],
  templateUrl: './public-header.html',
  styleUrl: './public-header.scss',
})
export class PublicHeader {
  private readonly elementRef = inject(ElementRef<HTMLElement>);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);

  protected readonly mobileOpen = signal(false);
  protected readonly openDropdown = signal<string | null>(null);
  protected readonly user = this.sessionService.currentUser;
  protected readonly navigation: readonly NavigationGroup[] = [
    { label: 'Hombre', items: ['Poleras', 'Camisas', 'Pantalones', 'Shorts', 'Chaquetas'] },
    {
      label: 'Mujer',
      items: ['Poleras', 'Camisas', 'Pantalones', 'Shorts', 'Chaquetas', 'Vestidos'],
    },
    { label: 'Unisex', items: ['Poleras', 'Chaquetas', 'Shorts'] },
  ];

  protected toggleMobile(): void {
    this.mobileOpen.update((isOpen) => !isOpen);
  }

  protected closeMobile(): void {
    this.mobileOpen.set(false);
    this.openDropdown.set(null);
  }

  protected toggleDropdown(label: string): void {
    this.openDropdown.update((current) => (current === label ? null : label));
  }

  protected logout(): void {
    this.sessionService.logout();
    this.closeMenus();
    void this.router.navigateByUrl('/');
  }

  @HostListener('document:click', ['$event'])
  protected closeDropdownOnOutsideClick(event: Event): void {
    const target = event.target;
    if (target instanceof Node && !this.elementRef.nativeElement.contains(target)) {
      this.openDropdown.set(null);
    }
  }

  @HostListener('document:keydown.escape')
  protected closeMenus(): void {
    this.mobileOpen.set(false);
    this.openDropdown.set(null);
  }
}
