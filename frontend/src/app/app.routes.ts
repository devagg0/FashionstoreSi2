import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { adminChildGuard, adminGuard } from './core/guards/admin.guard';
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
  {
    path: 'admin',
    canActivate: [adminGuard],
    canActivateChild: [adminChildGuard],
    loadComponent: () =>
      import('./layout/admin-layout/admin-layout').then(({ AdminLayout }) => AdminLayout),
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./pages/admin/dashboard/admin-dashboard').then(
            ({ AdminDashboard }) => AdminDashboard,
          ),
        title: 'Resumen administrativo | FashionStore',
      },
      {
        path: 'usuarios',
        loadComponent: () =>
          import('./pages/admin/users/admin-users').then(({ AdminUsers }) => AdminUsers),
        title: 'Usuarios y roles | FashionStore',
      },
      {
        path: 'roles',
        loadComponent: () =>
          import('./pages/admin/roles/admin-roles').then(({ AdminRoles }) => AdminRoles),
        title: 'Roles | FashionStore',
      },
      {
        path: 'ciudades',
        loadComponent: () =>
          import('./pages/admin/cities/admin-cities').then(({ AdminCities }) => AdminCities),
        title: 'Gestión de ciudades | FashionStore',
      },
      {
        path: 'perfil',
        loadComponent: () =>
          import('./pages/admin/profile/admin-profile').then(({ AdminProfile }) => AdminProfile),
        title: 'Mi perfil administrativo | FashionStore',
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
