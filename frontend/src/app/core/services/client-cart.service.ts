import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { CatalogColor, CatalogPromotion, CatalogSize } from './catalog.service';
import { SessionService } from './session.service';

export interface CartItem {
  id_detalle_carrito: number;
  id_variante_producto: number;
  id_producto: number;
  nombre_producto: string;
  sku: string;
  talla: CatalogSize;
  color: CatalogColor;
  imagen_principal: string | null;
  cantidad: number;
  precio_base: string;
  precio_final: string;
  promocion: CatalogPromotion | null;
  subtotal_linea: string;
  disponibilidad_actual: number;
  estado_producto: boolean;
  estado_variante: boolean;
}

export interface CartData {
  id_carrito: number | null;
  estado: 'ACTIVO' | null;
  items: CartItem[];
  cantidad_items: number;
  cantidad_unidades: number;
  subtotal: string;
  descuento_total: string;
  total: string;
}

export interface CartResponse { success: true; data: CartData; message: string; }

export function cartErrorMessage(error: HttpErrorResponse): string {
  if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
  if (error.status >= 500) return 'No fue posible procesar el carrito. Inténtalo nuevamente.';
  if ([403, 404, 409, 422].includes(error.status) && typeof error.error?.message === 'string') {
    return error.error.message;
  }
  const messages: Record<number, string> = {
    403: 'El carrito está disponible para cuentas de cliente.',
    404: 'El artículo ya no está disponible. Actualiza el carrito.',
    409: 'No hay stock suficiente para esta cantidad.',
    422: 'Revisa la cantidad y la disponibilidad del artículo.',
  };
  return messages[error.status] ?? 'No pudimos conectar con el carrito. Inténtalo nuevamente.';
}

@Injectable({ providedIn: 'root' })
export class ClientCartService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly url = `${environment.apiUrl}/api/client/cart`;

  getCart() { return this.http.get<CartResponse>(this.url, { headers: this.headers() }); }
  addItem(idVarianteProducto: number, cantidad: number) {
    return this.http.post<CartResponse>(`${this.url}/items`, {
      id_variante_producto: idVarianteProducto, cantidad,
    }, { headers: this.headers() });
  }
  updateQuantity(idVarianteProducto: number, cantidad: number) {
    return this.http.patch<CartResponse>(`${this.url}/items/${idVarianteProducto}`, { cantidad }, { headers: this.headers() });
  }
  removeItem(idVarianteProducto: number) {
    return this.http.delete<CartResponse>(`${this.url}/items/${idVarianteProducto}`, { headers: this.headers() });
  }
  clearCart() { return this.http.delete<CartResponse>(`${this.url}/items`, { headers: this.headers() }); }
  private headers() {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
}
