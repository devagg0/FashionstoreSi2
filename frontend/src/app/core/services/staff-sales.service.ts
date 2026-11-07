import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { from, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OfflineReservationDetailLocal, OfflineReservationLocal, hashReservationUuidToId } from '../models/offline.model';
import { OfflineStorageService } from './offline-storage.service';
import { OfflineService } from './offline.service';
import { SessionService } from './session.service';

export interface SaleRequest {
  id_sucursal: number;
  id_reserva?: number | null;
  items: { id_variante_producto: number; cantidad: number }[];
}
export interface SaleBranch {
  id_sucursal: number;
  nombre: string;
  ciudad: string;
  direccion: string;
  id_empleado_sucursal: number;
}
export interface SaleLine {
  id_variante_producto: number;
  sku: string;
  producto: string;
  talla: string;
  color: string;
  cantidad: number;
  precio_unitario: string;
  descuento_unitario: string;
  id_promocion: number | null;
  subtotal_linea: string;
}
export interface SaleQuote {
  sucursal: SaleBranch;
  id_empleado: number;
  id_cliente: number | null;
  id_reserva: number | null;
  detalles: (SaleLine & { cantidad_disponible: number })[];
  liberaciones: {
    id_variante_producto: number;
    cantidad_reservada: number;
    cantidad_compra: number;
    cantidad_liberar: number;
  }[];
  subtotal: string;
  descuento_total: string;
  total: string;
}
interface SalePerson {
  id_usuario: number;
  nombre: string;
  apellido: string;
}
export interface SaleData {
  id_venta: number;
  numero_venta: string;
  estado: 'PENDIENTE' | 'COMPLETADA' | 'ANULADA' | 'RECHAZADA';
  id_sucursal: number;
  id_empleado: number;
  id_cliente: number | null;
  id_reserva: number | null;
  sucursal: SaleBranch;
  cajero: SalePerson & { id_empleado: number };
  cliente: (SalePerson & { id_cliente: number }) | null;
  reserva: { id_reserva: number; codigo: string; estado: string } | null;
  fecha_venta: string;
  detalles: SaleLine[];
  subtotal: string;
  descuento_total: string;
  total: string;
  movimiento: {
    id_movimiento_inventario: number;
    id_empleado_sucursal: number;
    tipo_movimiento: 'VENTA';
    estado: 'PENDIENTE' | 'CONFIRMADO' | 'ANULADO';
  };
}
export interface SalesResponse<T> {
  success: true;
  data: T;
}

@Injectable({ providedIn: 'root' })
export class StaffSalesService {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  private readonly offlineService = inject(OfflineService);
  private readonly offlineStorage = inject(OfflineStorageService);
  private readonly url = `${environment.apiUrl}/api/staff/sales`;

  private headers(): HttpHeaders {
    const token = this.session.getAccessToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : new HttpHeaders();
  }

  private isOffline(): boolean {
    return (
      !this.offlineService.isOnline() || (typeof navigator !== 'undefined' && !navigator.onLine)
    );
  }

  getBranches(): Observable<SalesResponse<SaleBranch[]>> {
    if (this.isOffline()) {
      return from(this.getBranchesOffline());
    }
    return this.http.get<SalesResponse<SaleBranch[]>>(`${this.url}/branches`, {
      headers: this.headers(),
    });
  }

  quoteSale(payload: SaleRequest): Observable<SalesResponse<SaleQuote>> {
    if (this.isOffline()) {
      return from(this.quoteSaleOffline(payload));
    }
    return this.http.post<SalesResponse<SaleQuote>>(`${this.url}/quote`, payload, {
      headers: this.headers(),
    });
  }

  createSale(payload: SaleRequest, idempotencyKey: string): Observable<SalesResponse<SaleData>> {
    if (this.isOffline()) {
      return from(this.createSaleOffline(payload, idempotencyKey));
    }
    return this.http.post<SalesResponse<SaleData>>(this.url, payload, {
      headers: this.headers().set('Idempotency-Key', idempotencyKey),
    });
  }

  getSale(idVenta: number): Observable<SalesResponse<SaleData>> {
    if (this.isOffline()) {
      return from(this.getSaleOffline(idVenta));
    }
    return this.http.get<SalesResponse<SaleData>>(`${this.url}/${idVenta}`, {
      headers: this.headers(),
    });
  }

  private async getBranchesOffline(): Promise<SalesResponse<SaleBranch[]>> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    const branches = await this.offlineStorage.getBranches(empresaId, user.id_usuario);
    const active = branches.filter((b) => b.estado);
    const mapped: SaleBranch[] = active.map((b) => ({
      id_sucursal: b.id_sucursal,
      nombre: b.nombre,
      ciudad: b.ciudad ?? '',
      direccion: b.direccion,
      id_empleado_sucursal: 0,
    }));
    return { success: true, data: mapped };
  }

  private async quoteSaleOffline(payload: SaleRequest): Promise<SalesResponse<SaleQuote>> {
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId();
    if (!user || !empresaId) {
      throw new HttpErrorResponse({
        status: 401,
        error: { message: 'Tu sesión expiró. Inicia sesión nuevamente.' },
      });
    }

    if (!payload.items || !payload.items.length) {
      throw new HttpErrorResponse({
        status: 422,
        error: { message: 'Selecciona al menos una prenda para la venta.' },
      });
    }

    const [branches, products, variants, stock, pendingMap] = await Promise.all([
      this.offlineStorage.getBranches(empresaId, user.id_usuario),
      this.offlineStorage.getCatalogProducts(empresaId, user.id_usuario),
      this.offlineStorage.getVariants(empresaId, user.id_usuario),
      this.offlineStorage.getInventory(empresaId, user.id_usuario),
      this.offlineStorage.getPendingReservedQuantities(empresaId, user.id_usuario),
    ]);

    const branch = branches.find((b) => b.id_sucursal === payload.id_sucursal);
    if (!branch || !branch.estado) {
      throw new HttpErrorResponse({
        status: 422,
        error: { message: 'La sucursal seleccionada no está disponible offline.' },
      });
    }

    let reservation: OfflineReservationLocal | null = null;
    const reservedMap = new Map<number, OfflineReservationDetailLocal>();
    const releases: {
      id_variante_producto: number;
      cantidad_reservada: number;
      cantidad_compra: number;
      cantidad_liberar: number;
    }[] = [];

    if (payload.id_reserva) {
      const allReservations = await this.offlineStorage.getOfflineReservations(empresaId, user.id_usuario);
      reservation =
        allReservations.find(
          (r) =>
            r.id_reserva === payload.id_reserva ||
            hashReservationUuidToId(r.uuid_reserva_offline) === payload.id_reserva,
        ) ?? null;

      if (!reservation) {
        throw new HttpErrorResponse({
          status: 404,
          error: { message: 'Reserva no encontrada en almacenamiento offline.' },
        });
      }

      if (reservation.id_sucursal !== payload.id_sucursal) {
        throw new HttpErrorResponse({
          status: 403,
          error: { message: 'La reserva no pertenece a la sucursal de la venta.' },
        });
      }

      const resState = reservation.estado === 'REGISTRADA_LOCAL' ? 'PENDIENTE' : reservation.estado;
      if (resState !== 'ATENDIDA') {
        throw new HttpErrorResponse({
          status: 409,
          error: { message: `La reserva debe estar ATENDIDA. Estado actual: ${resState}.` },
        });
      }

      const purchases = await this.offlineStorage.getOfflinePurchases(empresaId, user.id_usuario);
      const alreadySold = purchases.some((p) => p.id_reserva === payload.id_reserva);
      if (alreadySold) {
        throw new HttpErrorResponse({
          status: 409,
          error: { message: 'La reserva ya tiene una venta asociada.' },
        });
      }

      const resDetails = await this.offlineStorage.getOfflineReservationDetails(
        empresaId,
        user.id_usuario,
        reservation.uuid_reserva_offline,
      );
      for (const rd of resDetails) {
        reservedMap.set(rd.id_variante_producto, rd);
      }

      for (const it of payload.items) {
        const resItem = reservedMap.get(it.id_variante_producto);
        if (!resItem) {
          throw new HttpErrorResponse({
            status: 422,
            error: { message: `La variante #${it.id_variante_producto} no pertenece a la reserva.` },
          });
        }
        if (it.cantidad > resItem.cantidad) {
          throw new HttpErrorResponse({
            status: 422,
            error: {
              message: `La cantidad de compra supera la reservada para ${resItem.sku || 'la variante'}.`,
            },
          });
        }
      }

      for (const rd of resDetails) {
        const itemBought = payload.items.find((it) => it.id_variante_producto === rd.id_variante_producto);
        const boughtQty = itemBought ? itemBought.cantidad : 0;
        releases.push({
          id_variante_producto: rd.id_variante_producto,
          cantidad_reservada: rd.cantidad,
          cantidad_compra: boughtQty,
          cantidad_liberar: rd.cantidad - boughtQty,
        });
      }
    }

    const lines: (SaleLine & { cantidad_disponible: number })[] = [];
    let subtotal = 0;
    let descuentoTotal = 0;

    for (const it of payload.items) {
      const variant = variants.find((v) => v.id_variante_producto === it.id_variante_producto);
      const product = products.find((p) => p.id_producto === variant?.id_producto);
      if (!variant || !product) {
        throw new HttpErrorResponse({
          status: 422,
          error: { message: `Variante #${it.id_variante_producto} no encontrada en el catálogo local.` },
        });
      }

      let unitPrice = 0;
      let available = 0;

      if (reservation) {
        const resItem = reservedMap.get(it.id_variante_producto)!;
        unitPrice = Number(resItem.precio_referencial ?? variant.precio ?? product.precio_final ?? product.precio ?? 0);
        available = resItem.cantidad;
      } else {
        const inv = stock.find(
          (s) => s.id_sucursal === payload.id_sucursal && s.id_variante_producto === it.id_variante_producto,
        );
        const pending = pendingMap.get(`${payload.id_sucursal}_${it.id_variante_producto}`) ?? 0;
        available = Math.max(0, (inv?.stock_disponible ?? 0) - pending);

        if (it.cantidad > available) {
          throw new HttpErrorResponse({
            status: 409,
            error: {
              message: `Stock insuficiente para ${variant.sku}. Disponible estimado: ${available}, solicitado: ${it.cantidad}.`,
            },
          });
        }

        unitPrice = Number(variant.precio ?? product.precio_final ?? product.precio ?? 0);
      }

      const discountUnit = 0;
      const lineSubtotal = (unitPrice - discountUnit) * it.cantidad;

      subtotal += unitPrice * it.cantidad;
      descuentoTotal += discountUnit * it.cantidad;

      lines.push({
        id_variante_producto: variant.id_variante_producto,
        sku: variant.sku,
        producto: product.nombre,
        talla: variant.talla || 'Única',
        color: variant.color || 'Único',
        cantidad: it.cantidad,
        precio_unitario: unitPrice.toFixed(2),
        descuento_unitario: discountUnit.toFixed(2),
        id_promocion: null,
        subtotal_linea: lineSubtotal.toFixed(2),
        cantidad_disponible: available,
      });
    }

    const total = subtotal - descuentoTotal;

    const quote: SaleQuote = {
      sucursal: {
        id_sucursal: branch.id_sucursal,
        nombre: branch.nombre,
        ciudad: branch.ciudad ?? '',
        direccion: branch.direccion,
        id_empleado_sucursal: 0,
      },
      id_empleado: user.id_usuario,
      id_cliente: reservation?.id_cliente ?? null,
      id_reserva: payload.id_reserva ?? null,
      detalles: lines,
      liberaciones: releases,
      subtotal: subtotal.toFixed(2),
      descuento_total: descuentoTotal.toFixed(2),
      total: total.toFixed(2),
    };

    return { success: true, data: quote };
  }

  private async createSaleOffline(
    payload: SaleRequest,
    idempotencyKey: string,
  ): Promise<SalesResponse<SaleData>> {
    const quoteResp = await this.quoteSaleOffline(payload);
    const quote = quoteResp.data;

    let hash = 0;
    for (let i = 0; i < idempotencyKey.length; i++) {
      hash = (Math.imul(31, hash) + idempotencyKey.charCodeAt(i)) | 0;
    }
    const localSaleId = 80000000 + (Math.abs(hash) % 9999999);
    const saleNumber = `VTA-LOC-${idempotencyKey.replace(/-/g, '').slice(0, 8).toUpperCase()}`;
    const user = this.session.getUser();
    const empresaId = this.offlineService.resolveEffectiveCompanyId() ?? 1;

    let clienteData = null;
    let reservaData = null;

    if (payload.id_reserva) {
      const allReservations = await this.offlineStorage.getOfflineReservations(empresaId, user?.id_usuario ?? 1);
      const res = allReservations.find(
        (r) =>
          r.id_reserva === payload.id_reserva ||
          hashReservationUuidToId(r.uuid_reserva_offline) === payload.id_reserva,
      );
      if (res) {
        reservaData = {
          id_reserva: payload.id_reserva,
          codigo: res.codigo_local,
          estado: 'ATENDIDA',
        };
        if (res.cliente_nombre) {
          clienteData = {
            id_usuario: res.id_cliente ?? 1,
            id_cliente: res.id_cliente ?? 1,
            nombre: res.cliente_nombre,
            apellido: res.cliente_apellido ?? '',
          };
        }
      }
    }

    const saleData: SaleData = {
      id_venta: localSaleId,
      numero_venta: saleNumber,
      estado: 'PENDIENTE',
      id_sucursal: quote.sucursal.id_sucursal,
      id_empleado: user?.id_usuario ?? 1,
      id_cliente: quote.id_cliente,
      id_reserva: payload.id_reserva ?? null,
      sucursal: quote.sucursal,
      cajero: {
        id_usuario: user?.id_usuario ?? 1,
        nombre: user?.nombre ?? 'Cajero',
        apellido: user?.apellido ?? '',
        id_empleado: user?.id_usuario ?? 1,
      },
      cliente: clienteData,
      reserva: reservaData,
      fecha_venta: new Date().toISOString(),
      detalles: quote.detalles.map((d) => ({
        id_variante_producto: d.id_variante_producto,
        sku: d.sku,
        producto: d.producto,
        talla: d.talla,
        color: d.color,
        cantidad: d.cantidad,
        precio_unitario: d.precio_unitario,
        descuento_unitario: d.descuento_unitario,
        id_promocion: d.id_promocion,
        subtotal_linea: d.subtotal_linea,
      })),
      subtotal: quote.subtotal,
      descuento_total: quote.descuento_total,
      total: quote.total,
      movimiento: {
        id_movimiento_inventario: localSaleId,
        id_empleado_sucursal: 0,
        tipo_movimiento: 'VENTA',
        estado: 'PENDIENTE',
      },
    };

    this.saveOfflineDraft(saleData);

    return { success: true, data: saleData };
  }

  private getSaleOffline(idVenta: number): Promise<SalesResponse<SaleData>> {
    const draft = this.getOfflineDraft(idVenta);
    if (draft) {
      return Promise.resolve({ success: true, data: draft });
    }
    return Promise.reject(
      new HttpErrorResponse({
        status: 404,
        error: { message: 'Venta no encontrada en almacenamiento offline.' },
      }),
    );
  }

  private saveOfflineDraft(sale: SaleData): void {
    try {
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem(`fashionstore_cu20_offline_draft_${sale.id_venta}`, JSON.stringify(sale));
      }
    } catch {
      // Ignorar si sessionStorage falla
    }
  }

  private getOfflineDraft(idVenta: number): SaleData | null {
    try {
      if (typeof sessionStorage === 'undefined') return null;
      const raw = sessionStorage.getItem(`fashionstore_cu20_offline_draft_${idVenta}`);
      return raw ? (JSON.parse(raw) as SaleData) : null;
    } catch {
      return null;
    }
  }
}
