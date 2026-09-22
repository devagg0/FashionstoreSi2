import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface ChatbotMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatbotProduct {
  id_producto: number;
  nombre: string;
  categoria: string;
  precio: string;
  colores: string[];
  tallas: string[];
  disponibilidad: 'DISPONIBLE' | 'AGOTADO' | null;
  cantidad_disponible: number | null;
}

export interface ChatbotRequest {
  message: string;
  history: ChatbotMessage[];
}

export interface ChatbotResponse {
  success: true;
  data: {
    reply: string;
    products: ChatbotProduct[];
  };
}

export function chatbotErrorMessage(error: HttpErrorResponse): string {
  if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
  if (error.status === 403) return 'El asistente está disponible para cuentas de cliente.';
  if (error.status === 0) return 'No pudimos conectar con FashionStore. Revisa tu conexión.';
  if (error.status === 503) return 'El asistente no está disponible en este momento.';
  if (error.status >= 500) return 'No fue posible procesar tu consulta. Inténtalo nuevamente.';
  if (typeof error.error?.message === 'string') return error.error.message;
  return 'No fue posible enviar tu mensaje. Inténtalo nuevamente.';
}

@Injectable({ providedIn: 'root' })
export class ClientChatbotService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/client/chatbot/message`;

  sendMessage(payload: ChatbotRequest): Observable<ChatbotResponse> {
    return this.http.post<ChatbotResponse>(this.url, payload, {
      headers: this.headers(),
    });
  }

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
}