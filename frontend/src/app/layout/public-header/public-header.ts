import { Component, ElementRef, HostListener, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { ReservationSelectionService } from '../../core/services/reservation-selection.service';
import { Icon } from '../../shared/components/icon/icon';

interface NavigationGroup {
  label: string;
  section: 'HOMBRE' | 'MUJER' | 'UNISEX';
  items: readonly string[];
}

@Component({
  selector: 'app-public-header',
  imports: [Icon, RouterLink],
  templateUrl: './public-header.html',
  styleUrl: './public-header.scss',
})
export class PublicHeader implements OnInit {
  private readonly elementRef = inject(ElementRef<HTMLElement>);
  private readonly router = inject(Router);
  private readonly sessionService = inject(SessionService);
  private readonly offlineService = inject(OfflineService, { optional: true });
  private readonly reservationSelection = inject(ReservationSelectionService);

  protected readonly mobileOpen = signal(false);
  protected readonly openDropdown = signal<string | null>(null);
  protected readonly user = this.sessionService.currentUser;
  protected readonly reservationItemCount = this.reservationSelection.itemCount;
  protected readonly navigation: readonly NavigationGroup[] = [
    {
      label: 'Hombre',
      section: 'HOMBRE',
      items: ['Poleras', 'Camisas', 'Pantalones', 'Shorts', 'Chaquetas'],
    },
    {
      label: 'Mujer',
      section: 'MUJER',
      items: ['Poleras', 'Camisas', 'Pantalones', 'Shorts', 'Chaquetas', 'Vestidos'],
    },
    { label: 'Unisex', section: 'UNISEX', items: ['Poleras', 'Chaquetas', 'Shorts'] },
  ];

  ngOnInit(): void {
    if (this.user()?.rol.toUpperCase() === 'CLIENTE') {
      void this.offlineService?.ensurePreparedAutomatically();
    }
  }

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
