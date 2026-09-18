import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { adminChildGuard, adminGuard } from './core/guards/admin.guard';
import { clientGuard } from './core/guards/client.guard';
import { cashierGuard } from './core/guards/cashier.guard';
import { staffChildGuard, staffGuard } from './core/guards/staff.guard';
import { SessionService } from './core/services/session.service';

export const routes: Routes = [
  {
    path: 'mis-compras/:id/comprobante',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/receipt/receipt').then(m => m.ReceiptPage),
    title: 'Comprobante de venta | FashionStore',
  },
  {
    path: 'mis-compras',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/purchases/purchases').then((m) => m.PurchasesPage),
    title: 'Mis compras | FashionStore',
  },
  {
    path: 'mis-compras/:id',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/purchases/purchases').then((m) => m.PurchasesPage),
    title: 'Detalle de compra | FashionStore',
  },
  {
    path: 'compra/:id/pago',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/payment/payment').then((m) => m.PaymentPage),
    title: 'Finalizar pago | FashionStore',
  },
  {
    path: 'compra',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/checkout/checkout').then(({ Checkout }) => Checkout),
    title: 'Procesar compra | FashionStore',
  },
  {
    path: 'compra/:id',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/checkout/checkout').then(({ Checkout }) => Checkout),
    title: 'Compra pendiente | FashionStore',
  },
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
    path: 'catalogo',
    loadComponent: () => import('./pages/catalog/catalog').then(({ Catalog }) => Catalog),
    title: 'Catálogo | FashionStore',
  },
  {
    path: 'catalogo/producto/:id',
    loadComponent: () =>
      import('./pages/product-detail/product-detail').then(({ ProductDetail }) => ProductDetail),
    title: 'Detalle de producto | FashionStore',
  },
  {
    path: 'carrito',
    canActivate: [clientGuard],
    loadComponent: () => import('./pages/cart/cart').then(({ Cart }) => Cart),
    title: 'Mi carrito | FashionStore',
  },
  {
    path: 'reservar',
    canActivate: [clientGuard],
    loadComponent: () =>
      import('./pages/reservations/reservation-checkout').then(
        ({ ReservationCheckout }) => ReservationCheckout,
      ),
    title: 'Tu reserva | FashionStore',
  },
  {
    path: 'mis-reservas',
    canActivate: [clientGuard],
    loadComponent: () =>
      import('./pages/reservations/my-reservations').then(({ MyReservations }) => MyReservations),
    title: 'Reservas | FashionStore',
  },
  {
    path: 'mis-reservas/:id',
    canActivate: [clientGuard],
    loadComponent: () =>
      import('./pages/reservations/reservation-detail').then(
        ({ ReservationDetailPage }) => ReservationDetailPage,
      ),
    title: 'Detalle de reserva | FashionStore',
  },
  {
    path: 'staff',
    canActivate: [staffGuard],
    canActivateChild: [staffChildGuard],
    loadComponent: () =>
      import('./layout/staff-layout/staff-layout').then(({ StaffLayout }) => StaffLayout),
    children: [
      {
        path: 'ventas/:id/comprobante',
        data: { audience: 'staff' },
        loadComponent: () => import('./pages/receipt/receipt').then(m => m.ReceiptPage),
        title: 'Comprobante de venta | FashionStore',
      },
      { path: 'devoluciones', canActivate: [cashierGuard], loadComponent: () => import('./pages/staff/returns/staff-returns').then(m => m.StaffReturnsPage), title: 'Devoluciones | FashionStore' },
      { path: 'devoluciones/:id', canActivate: [cashierGuard], loadComponent: () => import('./pages/staff/returns/staff-returns').then(m => m.StaffReturnsPage), title: 'Detalle de devoluci?n | FashionStore' },
      { path: '', pathMatch: 'full', redirectTo: 'inicio' },
      {
        path: 'ventas/:id/pago',
        canActivate: [cashierGuard],
        loadComponent: () => import('./pages/payment/payment').then((m) => m.PaymentPage),
        title: 'Finalizar pago | FashionStore',
      },
      {
        path: 'ventas/nueva',
        canActivate: [cashierGuard],
        loadComponent: () =>
          import('./pages/staff/sales/new-sale/new-sale').then(({ NewSale }) => NewSale),
        title: 'Nueva venta | FashionStore',
      },
      {
        path: 'inicio',
        loadComponent: () =>
          import('./pages/staff/dashboard/staff-dashboard').then(
            ({ StaffDashboard }) => StaffDashboard,
          ),
        title: 'Inicio de sucursal | FashionStore',
      },
      {
        path: 'reservas',
        loadComponent: () =>
          import('./pages/staff/reservations/staff-reservations').then(
            ({ StaffReservations }) => StaffReservations,
          ),
        title: 'Reservas de sucursal | FashionStore',
      },
      {
        path: 'reservas/:id',
        loadComponent: () =>
          import('./pages/staff/reservation-detail/staff-reservation-detail').then(
            ({ StaffReservationDetailPage }) => StaffReservationDetailPage,
          ),
        title: 'Detalle de reserva | FashionStore',
      },
      {
        path: 'disponibilidad',
        loadComponent: () =>
          import('./pages/staff/availability/staff-availability').then(
            ({ StaffAvailability }) => StaffAvailability,
          ),
        title: 'Disponibilidad de sucursal | FashionStore',
      },
      {
        path: 'perfil',
        loadComponent: () =>
          import('./pages/staff/profile/staff-profile').then(({ StaffProfile }) => StaffProfile),
        title: 'Mi perfil | FashionStore',
      },
    ],
  },
  {
    path: 'admin',
    canActivate: [adminGuard],
    canActivateChild: [adminChildGuard],
    loadComponent: () =>
      import('./layout/admin-layout/admin-layout').then(({ AdminLayout }) => AdminLayout),
    children: [
      { path: 'devoluciones', loadComponent: () => import('./pages/staff/returns/staff-returns').then(m => m.StaffReturnsPage), title: 'Devoluciones | FashionStore' },
      { path: 'devoluciones/:id', loadComponent: () => import('./pages/staff/returns/staff-returns').then(m => m.StaffReturnsPage), title: 'Detalle de devoluci?n | FashionStore' },
      {
        path: 'inventario-global',
        loadComponent: () =>
          import('./pages/admin/global-inventory/admin-global-inventory').then(
            ({ AdminGlobalInventory }) => AdminGlobalInventory,
          ),
        title: 'Inventario global | FashionStore',
      },
      {
        path: 'inventario',
        loadComponent: () =>
          import('./pages/admin/inventory/admin-inventory').then(
            ({ AdminInventory }) => AdminInventory,
          ),
        title: 'Inventario por sucursal | FashionStore',
      },
      {
        path: 'movimientos-inventario',
        loadComponent: () =>
          import('./pages/admin/inventory-movements/admin-inventory-movements').then(
            ({ AdminInventoryMovements }) => AdminInventoryMovements,
          ),
        title: 'Movimientos de inventario | FashionStore',
      },
      {
        path: 'productos',
        loadComponent: () =>
          import('./pages/admin/products/admin-products').then(
            ({ AdminProducts }) => AdminProducts,
          ),
        title: 'Productos | FashionStore',
      },
      {
        path: 'promociones',
        loadComponent: () =>
          import('./pages/admin/promotions/admin-promotions').then(
            ({ AdminPromotions }) => AdminPromotions,
          ),
        title: 'Promociones | FashionStore',
      },
      {
        path: 'proveedores',
        loadComponent: () =>
          import('./pages/admin/suppliers/admin-suppliers').then(
            ({ AdminSuppliers }) => AdminSuppliers,
          ),
        title: 'Proveedores | FashionStore',
      },
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
        path: 'sucursales',
        loadComponent: () =>
          import('./pages/admin/branches/admin-branches').then(
            ({ AdminBranches }) => AdminBranches,
          ),
        title: 'Gestión de sucursales | FashionStore',
      },
      {
        path: 'temporadas-colecciones',
        loadComponent: () =>
          import('./pages/admin/season-collection-config/admin-season-collection-config').then(
            ({ AdminSeasonCollectionConfig }) => AdminSeasonCollectionConfig,
          ),
        title: 'Temporadas y colecciones | FashionStore',
      },
      {
        path: 'configuracion-catalogo',
        loadComponent: () =>
          import('./pages/admin/catalog-config/admin-catalog-config').then(
            ({ AdminCatalogConfig }) => AdminCatalogConfig,
          ),
        title: 'Configuración de catálogo | FashionStore',
      },
      {
        path: 'asignaciones-sucursal',
        loadComponent: () =>
          import('./pages/admin/employee-branches/admin-employee-branches').then(
            ({ AdminEmployeeBranches }) => AdminEmployeeBranches,
          ),
        title: 'Asignación de empleados | FashionStore',
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
