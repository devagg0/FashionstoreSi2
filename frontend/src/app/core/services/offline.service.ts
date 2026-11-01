import { HttpClient, HttpErrorResponse, HttpHeaders, HttpResponse } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { catchError, concatMap, map, Observable, of, tap, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  OfflinePackageResponse,
  OfflineStatusResponse,
  OfflineStoredSummary,
} from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { SessionService } from './session.service';

export interface DownloadResult {
  notModified: boolean;
  package?: OfflinePackageResponse;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class OfflineService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly storage = inject(OfflineStorageService);

  readonly isOnline = signal<boolean>(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  readonly isLoading = signal<boolean>(false);
  readonly error = signal<string | null>(null);
  readonly lastActionMessage = signal<string | null>(null);
  readonly localSummary = signal<OfflineStoredSummary | null>(null);
  readonly statusCheck = signal<OfflineStatusResponse | null>(null);

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.isOnline.set(true));
      window.addEventListener('offline', () => this.isOnline.set(false));
    }
  }

  /**
   * Carga el resumen local desde IndexedDB sin requerir conexión a internet.
   */
  async loadLocalSummary(): Promise<OfflineStoredSummary | null> {
    const user = this.session.getUser();
    if (!user || !user.id_empresa) {
      this.localSummary.set(null);
      return null;
    }

    try {
      const summary = await this.storage.getStoredPackageSummary(
        user.id_empresa,
        user.id_usuario,
      );
      this.localSummary.set(summary);
      return summary;
    } catch {
      this.localSummary.set(null);
      return null;
    }
  }

  /**
   * Consulta liviana al endpoint GET /api/offline/status para verificar
   * vigencia y si existen cambios en el servidor antes de descargar.
   */
  checkStatus(branchId?: number, version?: string): Observable<OfflineStatusResponse> {
    const token = this.session.getAccessToken();
    const user = this.session.getUser();

    if (!token || !user) {
      const msg = 'Sesión no válida o no autenticada.';
      this.error.set(msg);
      return throwError(() => new Error(msg));
    }

    this.isLoading.set(true);
    this.error.set(null);

    let headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    const params: Record<string, string | number> = {};
    if (branchId) params['id_sucursal'] = branchId;
    const targetVersion = version || this.localSummary()?.metadata.version;
    if (targetVersion) {
      params['version'] = targetVersion;
      params['since_version'] = targetVersion;
      headers = headers.set('If-None-Match', `"${targetVersion}"`);
    }

    return this.http
      .get<OfflineStatusResponse>(`${environment.apiUrl}/api/offline/status`, {
        headers,
        params,
      })
      .pipe(
        tap({
          next: (res) => {
            this.statusCheck.set(res);
            this.isLoading.set(false);
            this.lastActionMessage.set(res.message);
          },
          error: (err) => {
            this.isLoading.set(false);
            const msg =
              err.error?.message ||
              'No fue posible verificar el estado del paquete en el servidor.';
            this.error.set(msg);
          },
        }),
      );
  }

  /**
   * Descarga o actualiza el paquete de datos offline mediante GET /api/offline/package.
   * - Soporta HTTP 304 condicional (mediante If-None-Match y since_version).
   * - Guarda en IndexedDB de forma atómica y espera su finalización antes de emitir.
   * - Una descarga fallida conserva intactos los últimos datos válidos.
   */
  downloadPackage(branchId?: number): Observable<DownloadResult> {
    const token = this.session.getAccessToken();
    const user = this.session.getUser();

    if (!token || !user) {
      const msg = 'Sesión no válida o no autenticada.';
      this.error.set(msg);
      return throwError(() => new Error(msg));
    }

    if (!user.id_empresa) {
      const msg = 'El usuario no tiene una empresa asociada para sincronizar offline.';
      this.error.set(msg);
      return throwError(() => new Error(msg));
    }

    this.isLoading.set(true);
    this.error.set(null);

    const currentVersion = this.localSummary()?.metadata.version;
    let headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    const params: Record<string, string | number> = {};
    if (branchId) params['id_sucursal'] = branchId;
    if (currentVersion) {
      headers = headers.set('If-None-Match', `"${currentVersion}"`);
      params['since_version'] = currentVersion;
      params['version'] = currentVersion;
    }

    return this.http
      .get<OfflinePackageResponse>(`${environment.apiUrl}/api/offline/package`, {
        headers,
        params,
        observe: 'response',
      })
      .pipe(
        map((response: HttpResponse<OfflinePackageResponse>): DownloadResult => {
          if (response.status === 304) {
            const message =
              'El paquete offline local se encuentra actualizado (HTTP 304). No hubo cambios.';
            this.lastActionMessage.set(message);
            this.isLoading.set(false);
            return { notModified: true, message };
          }

          const pkg = response.body;
          if (!pkg || !pkg.metadata) {
            throw new Error('Respuesta inválida del servidor al descargar paquete offline.');
          }

          return {
            notModified: false,
            package: pkg,
            message: pkg.message || 'Paquete offline descargado exitosamente.',
          };
        }),
        catchError((err: unknown) => {
          if (err instanceof HttpErrorResponse && err.status === 304) {
            const message =
              'El paquete offline local se encuentra actualizado (HTTP 304). No hubo cambios.';
            this.lastActionMessage.set(message);
            this.isLoading.set(false);
            return of<DownloadResult>({ notModified: true, message });
          }
          this.isLoading.set(false);
          const msg =
            (err as any)?.error?.message ||
            'Error de conexión o permisos al descargar el paquete offline. Los datos previos se conservan intactos.';
          this.error.set(msg);
          return throwError(() => err);
        }),
        concatMap(async (result: DownloadResult) => {
          if (!result.notModified && result.package && user.id_empresa) {
            await this.storage.savePackageAtomic(
              user.id_empresa,
              user.id_usuario,
              result.package,
            );
            await this.loadLocalSummary();
            const countInfo = `${result.package.metadata.total_productos} productos, ${result.package.metadata.total_variantes} variantes y ${result.package.metadata.total_existencias} existencias guardadas en IndexedDB.`;
            this.lastActionMessage.set(`Paquete preparado: ${countInfo}`);
          }
          this.isLoading.set(false);
          return result;
        }),
      );
  }

  /**
   * Elimina los datos locales almacenados en IndexedDB.
   */
  async clearLocalData(): Promise<void> {
    const user = this.session.getUser();
    if (user && user.id_empresa) {
      await this.storage.clearDatabase(user.id_empresa, user.id_usuario);
      this.localSummary.set(null);
      this.statusCheck.set(null);
      this.lastActionMessage.set('Los datos locales offline han sido eliminados de IndexedDB.');
    }
  }
}
