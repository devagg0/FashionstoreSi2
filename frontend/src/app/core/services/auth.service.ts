import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface RegisterClientRequest {
  nombre: string;
  apellido: string;
  correo: string;
  telefono: string | null;
  password: string;
  confirm_password: string;
}

export interface RegisterClientResponse {
  success: true;
  message: string;
  data: {
    id_usuario: number;
    nombre: string;
    apellido: string;
    correo: string;
  };
}

export interface LoginRequest {
  correo: string;
  password: string;
}

export interface AuthenticatedUser {
  id_usuario: number;
  nombre: string;
  apellido: string;
  correo: string;
  rol: string;
  estado?: boolean;
}

export interface LoginResponse {
  success: true;
  message: string;
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  usuario: AuthenticatedUser;
}

export interface CurrentUserResponse {
  success: true;
  data: AuthenticatedUser;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export interface ChangePasswordResponse {
  success: true;
  message: string;
}

export interface PasswordRecoveryRequestResponse {
  success: true;
  message: string;
}

export interface PasswordRecoveryVerifyResponse {
  success: true;
  message: string;
  reset_token: string;
}

export interface PasswordRecoveryResetResponse {
  success: true;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly sessionService = inject(SessionService);
  private readonly authUrl = `${environment.apiUrl}/api/auth`;

  registerClient(payload: RegisterClientRequest): Observable<RegisterClientResponse> {
    return this.http.post<RegisterClientResponse>(`${this.authUrl}/register`, payload);
  }

  login(payload: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${this.authUrl}/login`, payload);
  }

  me(): Observable<CurrentUserResponse> {
    return this.http.get<CurrentUserResponse>(`${this.authUrl}/me`, {
      headers: this.authenticatedHeaders(),
    });
  }

  changePassword(payload: ChangePasswordRequest): Observable<ChangePasswordResponse> {
    return this.http.put<ChangePasswordResponse>(`${this.authUrl}/change-password`, payload, {
      headers: this.authenticatedHeaders(),
    });
  }

  requestPasswordRecovery(correo: string): Observable<PasswordRecoveryRequestResponse> {
    return this.http.post<PasswordRecoveryRequestResponse>(
      `${this.authUrl}/password-recovery/request`,
      { correo },
    );
  }

  verifyPasswordRecovery(
    correo: string,
    codigo: string,
  ): Observable<PasswordRecoveryVerifyResponse> {
    return this.http.post<PasswordRecoveryVerifyResponse>(
      `${this.authUrl}/password-recovery/verify`,
      { correo, codigo },
    );
  }

  resetPassword(
    resetToken: string,
    newPassword: string,
    confirmPassword: string,
  ): Observable<PasswordRecoveryResetResponse> {
    return this.http.post<PasswordRecoveryResetResponse>(
      `${this.authUrl}/password-recovery/reset`,
      {
        reset_token: resetToken,
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
    );
  }

  private authenticatedHeaders(): HttpHeaders {
    const accessToken = this.sessionService.getAccessToken();
    return accessToken
      ? new HttpHeaders({ Authorization: `Bearer ${accessToken}` })
      : new HttpHeaders();
  }
}
