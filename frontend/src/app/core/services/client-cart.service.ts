import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { from, Observable, switchMap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OfflineCartItemLocal } from '../models/offline.model';
import { CatalogColor, CatalogPromotion, CatalogSize } from './catalog.service';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
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

export interface CartResponse {
  success: true;
  data: CartData;
  message: string;
}

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
  private readonly offlineService = inject(OfflineService);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly url = `${environment.apiUrl}/api/client/cart`;

  private isOffline(): boolean {
    return (
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine)
    );
  }

  getCart(): Observable<CartResponse> {
    if (this.isOffline()) {
      return from(this.buildOfflineCartData());
    }
    return this.http.get<CartResponse>(this.url, { headers: this.headers() });
  }

  addItem(idVarianteProducto: number, cantidad: number): Observable<CartResponse> {
    if (this.isOffline()) {
      return from(this.addOfflineItem(idVarianteProducto, cantidad));
    }
    return this.http.post<CartResponse>(
      `${this.url}/items`,
      { id_variante_producto: idVarianteProducto, cantidad },
      { headers: this.headers() },
    );
  }

  updateQuantity(idVarianteProducto: number, cantidad: number): Observable<CartResponse> {
    if (this.isOffline()) {
      return from(this.updateOfflineQuantity(idVarianteProducto, cantidad));
    }
    return this.http.patch<CartResponse>(
      `${this.url}/items/${idVarianteProducto}`,
      { cantidad },
      { headers: this.headers() },
    );
  }

  removeItem(idVarianteProducto: number): Observable<CartResponse> {
    if (this.isOffline()) {
      return from(this.removeOfflineItem(idVarianteProducto));
    }
    return this.http.delete<CartResponse>(`${this.url}/items/${idVarianteProducto}`, {
      headers: this.headers(),
    });
  }

  clearCart(): Observable<CartResponse> {
    if (this.isOffline()) {
      return from(this.clearOfflineCart());
    }
    return this.http.delete<CartResponse>(`${this.url}/items`, { headers: this.headers() });
  }

  private async buildOfflineCartData(): Promise<CartResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      return {
        success: true,
        data: {
          id_carrito: 999999,
          estado: 'ACTIVO',
          items: [],
          cantidad_items: 0,
          cantidad_unidades: 0,
          subtotal: '0.00',
          descuento_total: '0.00',
          total: '0.00',
        },
        message: 'Carrito offline local vacío.',
      };
    }

    const [offlineItems, variants, products, stock, pendingMap] = await Promise.all([
      this.offlineStorage.getOfflineCartItems(empresaId, user.id_usuario),
      this.offlineStorage.getVariants(empresaId, user.id_usuario),
      this.offlineStorage.getCatalogProducts(empresaId, user.id_usuario),
      this.offlineStorage.getInventory(empresaId, user.id_usuario),
      this.offlineStorage.getPendingReservedQuantities(empresaId, user.id_usuario),
    ]);

    const items: CartItem[] = [];
    let subtotalNum = 0;
    let totalUnits = 0;

    for (const item of offlineItems) {
      const v = variants.find(
        (variant) => variant.id_variante_producto === item.id_variante_producto,
      );
      const p = products.find(
        (prod) => prod.id_producto === (v?.id_producto ?? item.id_producto),
      );

      const vStock = stock.filter((s) => s.id_variante_producto === item.id_variante_producto);
      let totalAvailable = 0;
      for (const s of vStock) {
        const pending = pendingMap.get(`${s.id_sucursal}_${s.id_variante_producto}`) ?? 0;
        totalAvailable += Math.max(0, s.stock_disponible - pending);
      }

      const unitPrice = item.precio_unitario;
      const lineSubtotal = unitPrice * item.cantidad;
      subtotalNum += lineSubtotal;
      totalUnits += item.cantidad;

      items.push({
        id_detalle_carrito: item.id_variante_producto,
        id_variante_producto: item.id_variante_producto,
        id_producto: item.id_producto,
        nombre_producto: item.nombre_producto,
        sku: item.sku,
        talla: { id_talla: item.id_talla ?? 0, nombre: item.talla },
        color: {
          id_color: item.id_color ?? 0,
          nombre: item.color,
          codigo_hex: item.color_hex ?? null,
        },
        imagen_principal: item.imagen_principal ?? p?.imagen_principal ?? null,
        cantidad: item.cantidad,
        precio_base: unitPrice.toFixed(2),
        precio_final: unitPrice.toFixed(2),
        promocion: null,
        subtotal_linea: lineSubtotal.toFixed(2),
        disponibilidad_actual: totalAvailable,
        estado_producto: p ? p.estado : true,
        estado_variante: v ? v.estado : true,
      });
    }

    return {
      success: true,
      data: {
        id_carrito: 999999,
        estado: 'ACTIVO',
        items,
        cantidad_items: items.length,
        cantidad_unidades: totalUnits,
        subtotal: subtotalNum.toFixed(2),
        descuento_total: '0.00',
        total: subtotalNum.toFixed(2),
      },
      message: 'Carrito local offline recuperado.',
    };
  }

  private async addOfflineItem(
    idVarianteProducto: number,
    cantidad: number,
  ): Promise<CartResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const [variants, products, stock, pendingMap, currentItems] = await Promise.all([
      this.offlineStorage.getVariants(empresaId, user.id_usuario),
      this.offlineStorage.getCatalogProducts(empresaId, user.id_usuario),
      this.offlineStorage.getInventory(empresaId, user.id_usuario),
      this.offlineStorage.getPendingReservedQuantities(empresaId, user.id_usuario),
      this.offlineStorage.getOfflineCartItems(empresaId, user.id_usuario),
    ]);

    const variant = variants.find((v) => v.id_variante_producto === idVarianteProducto);
    if (!variant || !variant.estado) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: 'La prenda seleccionada ya no está disponible offline.' },
      });
    }
    const product = products.find((p) => p.id_producto === variant.id_producto);
    if (!product || !product.estado) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: 'El producto seleccionado no está disponible offline.' },
      });
    }

    const vStock = stock.filter((s) => s.id_variante_producto === idVarianteProducto);
    let totalAvailable = 0;
    for (const s of vStock) {
      const pending = pendingMap.get(`${s.id_sucursal}_${s.id_variante_producto}`) ?? 0;
      totalAvailable += Math.max(0, s.stock_disponible - pending);
    }

    const existing = currentItems.find((i) => i.id_variante_producto === idVarianteProducto);
    const newQty = (existing?.cantidad ?? 0) + cantidad;
    if (newQty > totalAvailable) {
      throw new HttpErrorResponse({
        status: 409,
        error: {
          message: `Stock offline insuficiente para esta variante. Disponible estimado: ${totalAvailable}.`,
        },
      });
    }

    const unitPrice = Number(
      variant.precio ?? product.precio_final ?? product.precio ?? 0,
    );
    const nowIso = new Date().toISOString();

    const cartItem: OfflineCartItemLocal = {
      id_variante_producto: variant.id_variante_producto,
      id_producto: product.id_producto,
      nombre_producto: product.nombre,
      sku: variant.sku,
      id_talla: variant.id_talla,
      talla: variant.talla || 'Única',
      id_color: variant.id_color,
      color: variant.color || 'Único',
      color_hex: variant.color_hex ?? null,
      precio_unitario: unitPrice,
      cantidad: newQty,
      subtotal: unitPrice * newQty,
      imagen_principal: product.imagen_principal ?? null,
      created_at: existing?.created_at ?? nowIso,
      updated_at: nowIso,
    };

    await this.offlineStorage.saveOfflineCartItem(empresaId, user.id_usuario, cartItem);
    return this.buildOfflineCartData();
  }

  private async updateOfflineQuantity(
    idVarianteProducto: number,
    cantidad: number,
  ): Promise<CartResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const currentItems = await this.offlineStorage.getOfflineCartItems(
      empresaId,
      user.id_usuario,
    );
    const existing = currentItems.find((i) => i.id_variante_producto === idVarianteProducto);
    if (!existing) {
      throw new HttpErrorResponse({
        status: 404,
        error: { message: 'El artículo no está en el carrito.' },
      });
    }

    const stock = await this.offlineStorage.getInventory(empresaId, user.id_usuario);
    const pendingMap = await this.offlineStorage.getPendingReservedQuantities(
      empresaId,
      user.id_usuario,
    );
    const vStock = stock.filter((s) => s.id_variante_producto === idVarianteProducto);
    let totalAvailable = 0;
    for (const s of vStock) {
      const pending = pendingMap.get(`${s.id_sucursal}_${s.id_variante_producto}`) ?? 0;
      totalAvailable += Math.max(0, s.stock_disponible - pending);
    }

    if (cantidad > totalAvailable) {
      throw new HttpErrorResponse({
        status: 409,
        error: {
          message: `Stock offline insuficiente para esta cantidad. Disponible estimado: ${totalAvailable}.`,
        },
      });
    }

    const updatedItem: OfflineCartItemLocal = {
      ...existing,
      cantidad,
      subtotal: existing.precio_unitario * cantidad,
      updated_at: new Date().toISOString(),
    };
    await this.offlineStorage.saveOfflineCartItem(empresaId, user.id_usuario, updatedItem);
    return this.buildOfflineCartData();
  }

  private async removeOfflineItem(idVarianteProducto: number): Promise<CartResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (user && empresaId) {
      await this.offlineStorage.removeOfflineCartItem(
        empresaId,
        user.id_usuario,
        idVarianteProducto,
      );
    }
    return this.buildOfflineCartData();
  }

  private async clearOfflineCart(): Promise<CartResponse> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (user && empresaId) {
      await this.offlineStorage.clearOfflineCart(empresaId, user.id_usuario);
    }
    return this.buildOfflineCartData();
  }

  private headers() {
    const token = this.session.getAccessToken();
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }
}
