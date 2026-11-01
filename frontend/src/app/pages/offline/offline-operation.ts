import { CommonModule, DatePipe } from '@angular/common';
import { Component, computed, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { OfflineService } from '../../core/services/offline.service';
import { SessionService } from '../../core/services/session.service';
import { Icon } from '../../shared/components/icon/icon';

@Component({
  selector: 'app-offline-operation',
  standalone: true,
  imports: [CommonModule, DatePipe, Icon, RouterLink],
  templateUrl: './offline-operation.html',
  styleUrl: './offline-operation.scss',
})
export class OfflineOperation implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly session = inject(SessionService);
  protected readonly offlineService = inject(OfflineService);

  protected readonly user = this.session.currentUser;
  protected readonly isOnline = this.offlineService.isOnline;
  protected readonly isLoading = this.offlineService.isLoading;
  protected readonly errorMessage = this.offlineService.error;
  protected readonly actionMessage = this.offlineService.lastActionMessage;
  protected readonly localSummary = this.offlineService.localSummary;
  protected readonly statusCheck = this.offlineService.statusCheck;

  protected readonly selectedBranchId = signal<number | null>(null);

  protected readonly isCashierOrStaff = computed(() => {
    const role = this.user()?.rol?.toUpperCase();
    return role === 'CAJERO' || role === 'ENCARGADO_SUCURSAL';
  });

  protected readonly isAdmin = computed(() => {
    return this.user()?.rol?.toUpperCase() === 'ADMINISTRADOR';
  });

  protected readonly isSaaSError = computed(() => {
    const err = this.errorMessage();
    if (!err) return false;
    return err.toLowerCase().includes('suscripción') || err.toLowerCase().includes('offline');
  });

  async ngOnInit(): Promise<void> {
    // Cargar resumen local desde IndexedDB al ingresar
    await this.offlineService.loadLocalSummary();

    // Si hay conexión y no hay datos locales, podemos verificar estado automáticamente
    if (this.isOnline() && !this.localSummary()) {
      this.verifyServerStatus();
    }
  }

  protected downloadPackage(): void {
    const branchId = this.selectedBranchId() ?? undefined;
    this.offlineService
      .downloadPackage(branchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // Tras completar la descarga y persistencia en IndexedDB, validar vigencia automáticamente
          this.verifyServerStatus();
        },
        error: () => {},
      });
  }

  protected verifyServerStatus(): void {
    const branchId = this.selectedBranchId() ?? undefined;
    const currentVersion = this.localSummary()?.metadata?.version;
    this.offlineService
      .checkStatus(branchId, currentVersion)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {},
        error: () => {},
      });
  }

  protected async clearLocalCache(): Promise<void> {
    const confirmClear = window.confirm(
      '¿Está seguro de limpiar el paquete offline almacenado en este navegador? Deberá descargarlo nuevamente cuando disponga de conexión.',
    );
    if (confirmClear) {
      await this.offlineService.clearLocalData();
    }
  }

  protected dismissError(): void {
    this.offlineService.error.set(null);
  }

  protected dismissMessage(): void {
    this.offlineService.lastActionMessage.set(null);
  }
}
