import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { from, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

export interface DigitalSaleItem {
  id_variante_producto: number;
  id_promocion: number | null;
  cantidad: number;
  precio_unitario: string;
  descuento_unitario: string;
  subtotal_linea: string;
}

export interface DigitalSale {
  id_venta: number;
  numero_venta: string;
  id_cliente: number;
  id_carrito: number;
  id_sucursal: number;
  canal: 'DIGITAL';
  moneda: 'BOB';
  estado: 'PENDIENTE';
  stock_comprometido: boolean;
  fecha_expiracion_pago: string | null;
  subtotal: string;
  descuento_total: string;
  total: string;
  items: DigitalSaleItem[];
}

export interface DigitalSaleResponse {
  success: true;
  data: DigitalSale;
  message: string;
}

export interface SalePresentation {
  id_sucursal: number;
  sucursal: string;
  items: {
    id_variante_producto: number;
    nombre: string;
    talla: string;
    color: string;
    imagen?: string | null;
  }[];
}

export function checkoutErrorMessage(error: HttpErrorResponse): string {
  if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
  if (error.status === 0)
    return 'No pudimos conectar. Reintenta con la misma sucursal; si la compra ya fue preparada, recuperarás la misma venta.';
  if ([403, 404, 409, 422].includes(error.status) && typeof error.error?.message === 'string')
    return error.error.message;
  return (
    ({
      403: 'Esta compra está disponible para cuentas de cliente.',
      404: 'El carrito, la variante, la sucursal o la venta ya no están disponibles.',
      409: 'No hay stock suficiente o el carrito ya fue convertido. Revisa tu compra.',
      422: 'Revisa el carrito y selecciona una sucursal válida.',
    } as Record<number, string>)[error.status] ??
    'No fue posible procesar la compra. Inténtalo nuevamente.'
  );
}

@Injectable({ providedIn: 'root' })
export class ClientCheckoutService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly offlineService = inject(OfflineService);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly url = `${environment.apiUrl}/api/client`;

  private isOffline(): boolean {
    return (
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine)
    );
  }

  confirm(idCarrito: number, idSucursal: number): Observable<DigitalSaleResponse> {
    if (this.isOffline()) {
      return from(this.confirmOffline(idCarrito, idSucursal));
    }
    return this.http.post<DigitalSaleResponse>(
      `${this.url}/cart/checkout`,
      { id_carrito: idCarrito, id_sucursal: idSucursal },
      { headers: this.headers() },
    );
  }

  getPendingSale(idVenta: number): Observable<DigitalSaleResponse> {
    if (this.isOffline()) {
      return from(this.getPendingSaleOffline(idVenta));
    }
    return this.http.get<DigitalSaleResponse>(`${this.url}/sales/${idVenta}`, {
      headers: this.headers(),
    });
  }

  private async confirmOffline(
    idCarrito: number,
    idSucursal: number,
  ): Promise<DigitalSaleResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const items = await this.offlineStorage.getOfflineCartItems(empresaId, user.id_usuario);
    if (!items.length) {
      throw new HttpErrorResponse({
        status: 422,
        error: { message: 'El carrito no contiene prendas.' },
      });
    }

    const existing = this.offlineSaleByCart(idCarrito, idSucursal);
    if (existing) {
      return { success: true, data: existing, message: 'Venta recuperada en modo offline.' };
    }

    const localSaleId = 90000000 + Math.floor(Math.random() * 8999999);
    const saleNum = `DIG-LOC-${localSaleId.toString().slice(-4)}`;
    const subtotal = items.reduce((acc, i) => acc + i.subtotal, 0);

    let idCliente = user.id_usuario;
    if (typeof this.offlineStorage.getClients === 'function') {
      try {
        const clients = await this.offlineStorage.getClients(empresaId, user.id_usuario);
        const client = clients?.find((c) => c.id_usuario === user.id_usuario);
        if (client) idCliente = client.id_cliente;
      } catch {
        // Fallback al ID de usuario de la sesión
      }
    }

    const sale: DigitalSale = {
      id_venta: localSaleId,
      numero_venta: saleNum,
      id_cliente: idCliente,
      id_carrito: idCarrito,
      id_sucursal: idSucursal,
      canal: 'DIGITAL',
      moneda: 'BOB',
      estado: 'PENDIENTE',
      stock_comprometido: true,
      fecha_expiracion_pago: null,
      subtotal: subtotal.toFixed(2),
      descuento_total: '0.00',
      total: subtotal.toFixed(2),
      items: items.map((i) => ({
        id_variante_producto: i.id_variante_producto,
        id_promocion: null,
        cantidad: i.cantidad,
        precio_unitario: i.precio_unitario.toFixed(2),
        descuento_unitario: '0.00',
        subtotal_linea: i.subtotal.toFixed(2),
      })),
    };

    this.saveOfflinePreparedSale(sale);
    return {
      success: true,
      data: sale,
      message: 'Compra digital preparada localmente en modo offline.',
    };
  }

  private async getPendingSaleOffline(idVenta: number): Promise<DigitalSaleResponse> {
    const cached = this.offlineSale(idVenta);
    if (cached) {
      return {
        success: true,
        data: cached,
        message: 'Venta recuperada de almacenamiento local.',
      };
    }

    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (user && empresaId) {
      const stored = await this.offlineStorage.getOfflinePurchaseByLocalId(
        empresaId,
        user.id_usuario,
        idVenta,
      );
      if (stored) {
        const details = await this.offlineStorage.getOfflinePurchaseDetails(
          empresaId,
          user.id_usuario,
          stored.uuid_venta_offline,
        );
        const sale: DigitalSale = {
          id_venta: stored.id_venta_local,
          numero_venta: stored.numero_venta_local,
          id_cliente: stored.id_cliente ?? 0,
          id_carrito: 999999,
          id_sucursal: stored.id_sucursal,
          canal: 'DIGITAL',
          moneda: 'BOB',
          estado: 'PENDIENTE',
          stock_comprometido: true,
          fecha_expiracion_pago: null,
          subtotal: stored.subtotal.toFixed(2),
          descuento_total: stored.descuento_total.toFixed(2),
          total: stored.total.toFixed(2),
          items: details.map((d) => ({
            id_variante_producto: d.id_variante_producto,
            id_promocion: null,
            cantidad: d.cantidad,
            precio_unitario: d.precio_unitario.toFixed(2),
            descuento_unitario: d.descuento_unitario.toFixed(2),
            subtotal_linea: d.subtotal_linea.toFixed(2),
          })),
        };
        return {
          success: true,
          data: sale,
          message: 'Venta offline recuperada de IndexedDB.',
        };
      }
    }

    throw new HttpErrorResponse({
      status: 404,
      error: { message: 'No se encontró la venta solicitada en modo offline.' },
    });
  }

  saveOfflinePreparedSale(sale: DigitalSale): void {
    try {
      sessionStorage.setItem(`fashionstore_offline_sale_${sale.id_venta}`, JSON.stringify(sale));
      sessionStorage.setItem(
        `fashionstore_offline_cart_${sale.id_carrito}_${sale.id_sucursal}`,
        JSON.stringify(sale),
      );
    } catch {
      /* storage optional */
    }
  }

  offlineSale(idVenta: number): DigitalSale | null {
    try {
      const raw = sessionStorage.getItem(`fashionstore_offline_sale_${idVenta}`);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  private offlineSaleByCart(idCarrito: number, idSucursal: number): DigitalSale | null {
    try {
      const raw = sessionStorage.getItem(
        `fashionstore_offline_cart_${idCarrito}_${idSucursal}`,
      );
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  // Solo etiquetas para presentar IDs del backend; no guarda precios ni estados.
  savePresentation(idVenta: number, presentation: SalePresentation): void {
    try {
      sessionStorage.setItem(this.key(idVenta), JSON.stringify(presentation));
    } catch {
      /* storage optional */
    }
  }

  presentation(idVenta: number): SalePresentation | null {
    try {
      const value: unknown = JSON.parse(sessionStorage.getItem(this.key(idVenta)) ?? 'null');
      if (!value || typeof value !== 'object') return null;
      const data = value as SalePresentation;
      return typeof data.sucursal === 'string' &&
        Number.isInteger(data.id_sucursal) &&
        Array.isArray(data.items) &&
        data.items.every(
          (item) =>
            Number.isInteger(item.id_variante_producto) &&
            typeof item.nombre === 'string' &&
            typeof item.talla === 'string' &&
            typeof item.color === 'string',
        )
        ? data
        : null;
    } catch {
      return null;
    }
  }

  private key(id: number) {
    return `fashionstore_checkout_${this.session.getUser()?.id_usuario ?? 'guest'}_${id}`;
  }

  private headers() {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
}
