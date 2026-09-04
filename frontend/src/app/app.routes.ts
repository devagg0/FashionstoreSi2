import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { SessionService } from './core/services/session.service';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./pages/home/home').then(({ Home }) => Home),
    title: 'FashionStore | Moda para tu estilo',
  },
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login').then(({ Login }) => Login),
    title: 'Iniciar sesión | FashionStore',
  },
  {
    path: 'registro',
    loadComponent: () => import('./pages/register/register').then(({ Register }) => Register),
    title: 'Crear cuenta | FashionStore',
  },
  {
    path: 'perfil',
    loadComponent: () => import('./pages/profile/profile').then(({ Profile }) => Profile),
    canActivate: [
      () => (inject(SessionService).getUser() ? true : inject(Router).createUrlTree(['/login'])),
    ],
    title: 'Mi perfil | FashionStore',
  },
  { path: '**', redirectTo: '' },
];
