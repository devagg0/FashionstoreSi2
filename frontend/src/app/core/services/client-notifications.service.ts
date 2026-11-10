import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface NotificationItem {
  id_notificacion: number;
  usuario_id: number;
  empresa_id: number;
  tipo: string;
  titulo: string;
  mensaje: string;
  referencia_origen?: string | null;
  referencia_id?: number | null;
  codigo_referencia?: string | null;
  leido: boolean;
  fecha_lectura?: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  no_leidas: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface UnreadCountResponse {
  no_leidas: number;
}

export interface MarkReadResponse {
  success: boolean;
  marcadas: number;
  mensaje: string;
}

@Injectable({ providedIn: 'root' })
export class ClientNotificationsService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);

  private getHeaders(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  getNotifications(
    page: number = 1,
    pageSize: number = 20,
    unreadOnly: boolean = false,
  ): Observable<NotificationListResponse> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('page_size', pageSize.toString());

    if (unreadOnly) {
      params = params.set('unread_only', 'true');
    }

    return this.http.get<NotificationListResponse>(
      `${environment.apiUrl}/api/client/notifications`,
      {
        headers: this.getHeaders(),
        params,
      },
    );
  }

  getUnreadCount(): Observable<UnreadCountResponse> {
    return this.http.get<UnreadCountResponse>(
      `${environment.apiUrl}/api/client/notifications/unread-count`,
      { headers: this.getHeaders() },
    );
  }

  markAsRead(idNotificacion: number): Observable<NotificationItem> {
    return this.http.patch<NotificationItem>(
      `${environment.apiUrl}/api/client/notifications/${idNotificacion}/read`,
      {},
      { headers: this.getHeaders() },
    );
  }

  markAllAsRead(): Observable<MarkReadResponse> {
    return this.http.post<MarkReadResponse>(
      `${environment.apiUrl}/api/client/notifications/mark-all-read`,
      {},
      { headers: this.getHeaders() },
    );
  }
}

