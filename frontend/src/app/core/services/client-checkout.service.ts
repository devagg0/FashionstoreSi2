import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { SessionService } from './session.service';

export interface DigitalSaleItem {
  id_variante_producto: number; id_promocion: number | null; cantidad: number;
  precio_unitario: string; descuento_unitario: string; subtotal_linea: string;
}
export interface DigitalSale {
  id_venta: number; numero_venta: string; id_cliente: number; id_carrito: number;
  id_sucursal: number; canal: 'DIGITAL'; moneda: 'BOB'; estado: 'PENDIENTE';
  stock_comprometido: boolean; fecha_expiracion_pago: string | null;
  subtotal: string; descuento_total: string; total: string; items: DigitalSaleItem[];
}
export interface DigitalSaleResponse { success: true; data: DigitalSale; message: string; }
export interface SalePresentation {
  id_sucursal: number; sucursal: string;
  items: { id_variante_producto: number; nombre: string; talla: string; color: string; imagen?: string | null }[];
}

export function checkoutErrorMessage(error: HttpErrorResponse): string {
  if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
  if (error.status === 0) return 'No pudimos conectar. Reintenta con la misma sucursal; si la compra ya fue preparada, recuperarás la misma venta.';
  if ([403, 404, 409, 422].includes(error.status) && typeof error.error?.message === 'string') return error.error.message;
  return ({
    403: 'Esta compra está disponible para cuentas de cliente.',
    404: 'El carrito, la variante, la sucursal o la venta ya no están disponibles.',
    409: 'No hay stock suficiente o el carrito ya fue convertido. Revisa tu compra.',
    422: 'Revisa el carrito y selecciona una sucursal válida.',
  } as Record<number, string>)[error.status] ?? 'No fue posible procesar la compra. Inténtalo nuevamente.';
}

@Injectable({ providedIn: 'root' })
export class ClientCheckoutService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/client`;
  confirm(idCarrito: number, idSucursal: number) {
    return this.http.post<DigitalSaleResponse>(`${this.url}/cart/checkout`, {
      id_carrito: idCarrito, id_sucursal: idSucursal,
    }, { headers: this.headers() });
  }
  getPendingSale(idVenta: number) {
    return this.http.get<DigitalSaleResponse>(`${this.url}/sales/${idVenta}`, { headers: this.headers() });
  }
  // Solo etiquetas para presentar IDs del backend; no guarda precios ni estados.
  savePresentation(idVenta: number, presentation: SalePresentation): void {
    try { sessionStorage.setItem(this.key(idVenta), JSON.stringify(presentation)); } catch { /* storage optional */ }
  }
  presentation(idVenta: number): SalePresentation | null {
    try {
      const value: unknown = JSON.parse(sessionStorage.getItem(this.key(idVenta)) ?? 'null');
      if (!value || typeof value !== 'object') return null;
      const data = value as SalePresentation;
      return typeof data.sucursal === 'string' && Number.isInteger(data.id_sucursal) && Array.isArray(data.items)
        && data.items.every(item => Number.isInteger(item.id_variante_producto) && typeof item.nombre === 'string'
          && typeof item.talla === 'string' && typeof item.color === 'string') ? data : null;
    } catch { return null; }
  }
  private key(id: number) { return `fashionstore_checkout_${this.session.getUser()?.id_usuario ?? 'guest'}_${id}`; }
  private headers() {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
}
