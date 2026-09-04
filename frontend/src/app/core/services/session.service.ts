import { isPlatformBrowser } from '@angular/common';
import { inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import type { AuthenticatedUser } from './auth.service';

const ACCESS_TOKEN_KEY = 'fashionstore_access_token';
const USER_KEY = 'fashionstore_user';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly currentUserState = signal<AuthenticatedUser | null>(this.readStoredUser());

  readonly currentUser = this.currentUserState.asReadonly();

  saveAccessToken(accessToken: string): void {
    this.requireStorage().setItem(ACCESS_TOKEN_KEY, accessToken);
  }

  getAccessToken(): string | null {
    return this.storage?.getItem(ACCESS_TOKEN_KEY) ?? null;
  }

  saveUser(user: AuthenticatedUser): void {
    this.requireStorage().setItem(USER_KEY, JSON.stringify(user));
    this.currentUserState.set(user);
  }

  getUser(): AuthenticatedUser | null {
    return this.currentUserState();
  }

  logout(): void {
    this.storage?.removeItem(ACCESS_TOKEN_KEY);
    this.storage?.removeItem(USER_KEY);
    this.currentUserState.set(null);
  }

  private readStoredUser(): AuthenticatedUser | null {
    const serializedUser = this.storage?.getItem(USER_KEY);
    if (!serializedUser) {
      return null;
    }

    try {
      const user: unknown = JSON.parse(serializedUser);
      if (this.isAuthenticatedUser(user)) {
        return user;
      }
    } catch {
      // Un valor local corrupto no debe impedir que la aplicación continúe.
    }

    this.storage?.removeItem(USER_KEY);
    return null;
  }

  private get storage(): Storage | null {
    if (!isPlatformBrowser(this.platformId)) {
      return null;
    }

    try {
      return localStorage;
    } catch {
      return null;
    }
  }

  private requireStorage(): Storage {
    const storage = this.storage;
    if (!storage) {
      throw new Error('Local storage is not available');
    }

    return storage;
  }

  private isAuthenticatedUser(value: unknown): value is AuthenticatedUser {
    if (typeof value !== 'object' || value === null) {
      return false;
    }

    const user = value as Partial<AuthenticatedUser>;
    return (
      typeof user.id_usuario === 'number' &&
      typeof user.nombre === 'string' &&
      typeof user.apellido === 'string' &&
      typeof user.correo === 'string' &&
      typeof user.rol === 'string'
    );
  }
}
